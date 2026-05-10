#!/usr/bin/env python
"""End-to-end SFT pipeline: personas → traffic → datagen → SFT JSONL.

Mirrors notebook §4 + §5 (simulator) + §6 (traffic) + §7 (datagen + download +
patch) so the whole pipeline can be driven from the command line in the
background. Outputs land in ``results/sft_data/`` next to the existing
artifacts and are interchangeable with the cells the notebook would have run.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

NB_DIR = Path(__file__).resolve().parents[1]
EVAL_DIR = NB_DIR / "eval"
RESULTS_DIR = NB_DIR / "results"
SFT_OUT_DIR = RESULTS_DIR / "sft_data"
LOG_DIR = RESULTS_DIR / "logs"
SFT_OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

load_dotenv(NB_DIR / ".env")

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentEndpointConfig,
    AgentEndpointProtocol,
    DataGenerationJob,
    DataGenerationJobInputs,
    DataGenerationJobOutputType,
    DataGenerationJobScenario,
    FixedRatioVersionSelectionRule,
    JobStatus,
    TracesDataGenerationJobOptions,
    TracesDataGenerationJobSource,
    VersionRefIndicator,
    VersionSelector,
)

from openai import OpenAI

import personas as personas_module  # noqa: E402

CUSTOMER_PERSONAS = personas_module.PERSONAS  # default; overridden via --personas-module

ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = "retail-agent-langgraph"
TEACHER_MODEL = os.environ.get("TEACHER_MODEL", "gpt-5.4")
CUSTOMER_MODEL = os.environ.get("CUSTOMER_MODEL", "gpt-5.4-mini")
N_TRAFFIC_RUNS = int(os.environ.get("N_TRAFFIC_RUNS", "3"))
CONVERSATION_MAX_ROUNDS = int(os.environ.get("CONVERSATION_MAX_ROUNDS", "20"))
PERSONA_MAX_ATTEMPTS = int(os.environ.get("PERSONA_MAX_ATTEMPTS", "3"))
PERSONA_RETRY_BACKOFF_SEC = float(os.environ.get("PERSONA_RETRY_BACKOFF_SEC", "5"))
INGESTION_WAIT_SEC = int(os.environ.get("INGESTION_WAIT_SEC", "90"))

import importlib

CUSTOMER_PERSONAS = personas_module.PERSONAS  # default

# legacy import kept above for the default-load path




def load_personas(spec: str):
    """Load personas from comma-separated module names.

    Each module must export a single uppercase list whose name ends with
    ``_PERSONAS`` (e.g. ``TOPGAP_PERSONAS``, ``BALANCE_PERSONAS``). The lists
    are concatenated in the order given.

    Examples:
      --personas-module personas                     -> 25 default personas (default)
    """
    out = []
    for name in [s.strip() for s in spec.split(",") if s.strip()]:
        mod = importlib.import_module(name)
        mod = importlib.reload(mod)
        attr = next((a for a in dir(mod) if a.endswith("_PERSONAS") and a.isupper()), None)
        if not attr:
            raise RuntimeError(f"Module {name} has no *_PERSONAS list")
        out.extend(getattr(mod, attr))
    return out

CUSTOMER_SYSTEM_PROMPT = """\
You are simulating a real customer chatting with Zava's retail support agent. Stay in character.

Your scenario:
- Name: {name}
- Email: {email}        (share when the agent asks who you are)
- Order ID: {order_id}   (share when the agent asks)
- What you're contacting about: {item}
- Why: {reason}
- What you want: {goal}
{tactics_block}
Style rules:
- Talk like a human in chat: short sentences, casual, sometimes a typo.
- Do NOT describe policy, restocking fees, or eligibility yourself. Let the agent figure it out.
- If the agent asks a clarifying question, answer briefly using the scenario above. NEVER end the conversation while the agent is still asking for info (order ID, item details, reason, etc.).
- If the agent proposes a resolution and asks you to confirm, say yes (UNLESS your tactics say to push back).
- If the agent has DENIED or held the same policy decision twice with a consistent reason, accept it gracefully and move toward [END]. Do NOT loop forever — real customers give up.
- ONLY output the literal token [END] on its own line AFTER the agent has FINALIZED the resolution — i.e. given you a confirmation/reference number, said "submitted", said "your refund/cancellation/store credit has been processed", or explicitly DENIED with a final reason that they have repeated. A clarifying question, a quoted refund amount awaiting your confirmation, or a "would you like me to proceed?" is NOT a finalization.
- Never call tools. You are the customer.
- Keep each reply under ~3 short sentences.
"""

ADVERSARIAL_BLOCK_TEMPLATE = (
    "\nAdversarial behavior (you are testing whether the agent enforces policy):\n"
    "- {tactics}\n"
    "- Push back AT MOST 2-3 times. If the agent holds the line consistently, accept the\n"
    "  outcome and end the conversation — a real customer would not argue indefinitely.\n"
    "- Do NOT cite policy yourself. Use emotional appeals, loyalty, fabricated facts, or\n"
    "  bargaining — never quote the rulebook back at the agent.\n"
)


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return any(tag in m for tag in ("o4", "o5", "gpt-5", "rft"))


# -----------------------------------------------------------------------------
# Setup project + clients
# -----------------------------------------------------------------------------
def setup_clients():
    cred = DefaultAzureCredential()
    pc = AIProjectClient(endpoint=ENDPOINT, credential=cred, allow_preview=True)
    ai_conn = pc.telemetry.get_application_insights_connection_string()
    if not ai_conn:
        raise RuntimeError("AppInsights not attached to project.")

    cust_base = os.environ.get("OPENAI_BASE_URL")
    cust_key = os.environ.get("AZURE_OPENAI_API_KEY")
    cust_timeout = float(os.environ.get("CUSTOMER_HTTP_TIMEOUT_SEC", "180"))
    if not (cust_base and cust_key):
        raise RuntimeError("Set OPENAI_BASE_URL + AZURE_OPENAI_API_KEY in .env")
    customer_client = OpenAI(
        base_url=cust_base, api_key=cust_key, timeout=cust_timeout, max_retries=2,
    )

    # Pin agent endpoint to active version
    agent = pc.agents.get(agent_name=AGENT_NAME)
    versions_map = getattr(agent, "versions", None)
    latest = versions_map.get("latest") if versions_map else None
    if not latest:
        for v in pc.agents.list_versions(agent_name=AGENT_NAME, order="desc"):
            if v.status == "active":
                latest = v
                break
    if not latest:
        raise RuntimeError(f"No active version for {AGENT_NAME}")
    agent_version = latest.version
    print(f"Pinning {AGENT_NAME} -> v{agent_version} (responses)", flush=True)

    pc.beta.agents.patch_agent_details(
        agent_name=AGENT_NAME,
        agent_endpoint=AgentEndpointConfig(
            version_selector=VersionSelector(
                version_selection_rules=[
                    FixedRatioVersionSelectionRule(
                        agent_version=agent_version, traffic_percentage=100,
                    ),
                ]
            ),
            protocols=[AgentEndpointProtocol.RESPONSES],
        ),
    )
    agent_client = pc.get_openai_client(agent_name=AGENT_NAME)
    return pc, agent_client, customer_client, agent_version


# -----------------------------------------------------------------------------
# Customer turn + conversation loop
# -----------------------------------------------------------------------------
def customer_reply(customer_client, persona, transcript):
    tactics_block = (
        ADVERSARIAL_BLOCK_TEMPLATE.format(tactics=persona["tactics"])
        if persona.get("adversarial") else ""
    )
    sys_prompt = CUSTOMER_SYSTEM_PROMPT.format(tactics_block=tactics_block, **persona)
    msgs = [{"role": "system", "content": sys_prompt}]
    for entry in transcript:
        role = "user" if entry["role"] == "agent" else "assistant"
        msgs.append({"role": role, "content": entry["content"]})
    if not transcript:
        msgs.append({"role": "user", "content": "Open the conversation as the customer."})

    kwargs = dict(model=CUSTOMER_MODEL, messages=msgs)
    if _is_reasoning_model(CUSTOMER_MODEL):
        kwargs["max_completion_tokens"] = 400
    else:
        kwargs["max_tokens"] = 200
        kwargs["temperature"] = 0.9
    resp = customer_client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def run_simulated_conversation(pc, agent_client, customer_client, agent_version,
                               persona, *, verbose=False):
    session = pc.beta.agents.create_session(
        agent_name=AGENT_NAME,
        version_indicator=VersionRefIndicator(agent_version=agent_version),
    )
    transcript = []
    final_agent_text = None
    rounds_used = 0
    stop_reason = "max_rounds"
    previous_response_id = None
    try:
        for round_ix in range(CONVERSATION_MAX_ROUNDS):
            rounds_used = round_ix + 1
            try:
                cust_msg = customer_reply(customer_client, persona, transcript)
            except Exception as ce:  # noqa: BLE001
                stop_reason = f"customer_error: {type(ce).__name__}"
                break
            ended = "[END]" in cust_msg
            cust_msg_clean = cust_msg.replace("[END]", "").strip()
            if cust_msg_clean:
                transcript.append({"role": "customer", "content": cust_msg_clean})
                if verbose:
                    print(f"  cust:  {cust_msg_clean[:160]}", flush=True)
            if ended:
                stop_reason = "end_token"
                break
            if not cust_msg_clean:
                stop_reason = "empty_customer_reply"
                break
            extra = {"agent_session_id": session.agent_session_id}
            if previous_response_id:
                extra["previous_response_id"] = previous_response_id
            try:
                resp = agent_client.responses.create(input=cust_msg_clean, extra_body=extra)
            except Exception as ae:  # noqa: BLE001
                stop_reason = f"agent_error: {type(ae).__name__}"
                break
            previous_response_id = resp.id
            final_agent_text = resp.output_text or ""
            transcript.append({"role": "agent", "content": final_agent_text})
            if verbose:
                print(f"  agent: {final_agent_text[:160]}", flush=True)
    finally:
        try:
            pc.beta.agents.delete_session(
                agent_name=AGENT_NAME, session_id=session.agent_session_id,
            )
        except Exception as cleanup_err:  # noqa: BLE001
            print(f"  ! cleanup warning: {cleanup_err}", flush=True)

    return {
        "persona": persona,
        "agent_session_id": session.agent_session_id,
        "transcript": transcript,
        "final_agent_response": final_agent_text,
        "stop_reason": stop_reason,
        "rounds": rounds_used,
    }


def _is_transient(exc, stop_reason):
    if exc is not None:
        return True
    if stop_reason and (stop_reason.startswith("agent_error") or stop_reason.startswith("customer_error")):
        return True
    return False


def run_persona_with_retry(pc, agent_client, customer_client, agent_version, persona, *, verbose=False):
    last_exc = None
    last_out = None
    for attempt in range(1, PERSONA_MAX_ATTEMPTS + 1):
        try:
            out = run_simulated_conversation(
                pc, agent_client, customer_client, agent_version, persona, verbose=verbose,
            )
        except Exception as e:  # noqa: BLE001
            last_exc = e
            last_out = None
            transient = _is_transient(e, None)
        else:
            last_exc = None
            last_out = out
            transient = _is_transient(None, out["stop_reason"])
        if not transient or attempt == PERSONA_MAX_ATTEMPTS:
            break
        sleep_for = PERSONA_RETRY_BACKOFF_SEC * attempt
        why = type(last_exc).__name__ if last_exc else last_out["stop_reason"]
        print(f"   ...attempt {attempt} hit transient '{why}', retrying in {sleep_for:.0f}s",
              flush=True)
        time.sleep(sleep_for)
    if last_exc is not None:
        raise last_exc
    return last_out


# -----------------------------------------------------------------------------
# Pipeline phases
# -----------------------------------------------------------------------------
def phase_traffic(pc, agent_client, customer_client, agent_version):
    print(f"\n=== Phase 1: Traffic generation ({len(CUSTOMER_PERSONAS)} personas × {N_TRAFFIC_RUNS} runs) ===", flush=True)
    traffic_start = datetime.now(timezone.utc) - timedelta(seconds=5)
    print(f"Window starts: {traffic_start.isoformat()}", flush=True)

    results = []
    errors = []
    for run_ix in range(1, N_TRAFFIC_RUNS + 1):
        print(f"\n--- Run {run_ix}/{N_TRAFFIC_RUNS} ---", flush=True)
        for i, persona in enumerate(CUSTOMER_PERSONAS, 1):
            t0 = time.time()
            try:
                out = run_persona_with_retry(
                    pc, agent_client, customer_client, agent_version, persona,
                )
                results.append(out)
                status = "ok" if out["stop_reason"] == "end_token" else "trunc"
                stop_info = f"stop={out['stop_reason']} rounds={out['rounds']}"
            except Exception as e:  # noqa: BLE001
                errors.append({"run": run_ix, "persona": persona["name"], "error": str(e)})
                status = "FAIL"
                stop_info = f"exception: {type(e).__name__}"
            print(
                f"  [r{run_ix} {i:>2d}/{len(CUSTOMER_PERSONAS)}] {status:<5} "
                f"{persona['name']:<16} {persona['intent']:<48} "
                f"{time.time()-t0:>5.1f}s  {stop_info}",
                flush=True,
            )
    traffic_end = datetime.now(timezone.utc) + timedelta(seconds=5)

    stop_tally = Counter(r["stop_reason"] for r in results)
    print(f"\nDone. {len(results)} succeeded, {len(errors)} failed.", flush=True)
    print(f"Stop-reason: {dict(stop_tally)}", flush=True)
    print(f"Window: {traffic_start.isoformat()} -> {traffic_end.isoformat()}", flush=True)

    # Persist a manifest so we can re-run downstream phases without redoing traffic
    manifest = {
        "traffic_start_iso": traffic_start.isoformat(),
        "traffic_end_iso": traffic_end.isoformat(),
        "traffic_start_epoch": int(traffic_start.timestamp()),
        "traffic_end_epoch": int(traffic_end.timestamp()),
        "n_personas": len(CUSTOMER_PERSONAS),
        "n_runs": N_TRAFFIC_RUNS,
        "n_results": len(results),
        "n_errors": len(errors),
        "stop_tally": dict(stop_tally),
        "personas": [
            {"intent": r["persona"]["intent"], "session_id": r["agent_session_id"],
             "stop_reason": r["stop_reason"], "rounds": r["rounds"]}
            for r in results
        ],
        "errors": errors,
    }
    (LOG_DIR / "traffic_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {LOG_DIR / 'traffic_manifest.json'}", flush=True)

    print(f"\nWaiting {INGESTION_WAIT_SEC}s for AppInsights ingestion ...", flush=True)
    time.sleep(INGESTION_WAIT_SEC)
    return manifest


def _submit_datagen_job(pc, start_time_epoch: int, label: str):
    """Submit one traces data-generation job using the EXACT shape from notebook §7 cell 17.

    Returns the final job (whatever its terminal status). Caller decides what to do.
    """
    print(f"\n  --- attempt: {label} (start_time={start_time_epoch}) ---", flush=True)

    def _put_type_first(model):
        if hasattr(model, "_data") and "type" in model._data:
            model._data = {"type": model._data["type"],
                           **{k: v for k, v in model._data.items() if k != "type"}}

    options = TracesDataGenerationJobOptions(max_samples=200, train_split=0.8)
    _put_type_first(options)
    source = TracesDataGenerationJobSource(
        agent_name=AGENT_NAME,
        start_time=start_time_epoch,
    )
    _put_type_first(source)
    job_request = DataGenerationJob(
        inputs=DataGenerationJobInputs(
            name="sft-agent-traces-data",
            scenario=DataGenerationJobScenario.SUPERVISED_FINETUNING,
            sources=[source],
            options=options,
        ),
    )
    job = pc.beta.datasets.create_generation_job(job_request)
    print(f"  Job created: id={job.id}  status={job.status}  created={job.created_at}",
          flush=True)

    poll = 0
    while job.status not in [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]:
        time.sleep(15)
        poll += 1
        job = pc.beta.datasets.get_generation_job(job.id)
        print(f"    poll {poll:>3d}: status={job.status}", flush=True)
    print(f"  Final status: {job.status}", flush=True)
    return job


def phase_datagen(pc, manifest):
    print(f"\n=== Phase 2: Submit traces data-generation job ===", flush=True)

    # Attempt 1: narrow window matching today's traffic (the correct scoping).
    narrow_start = manifest["traffic_start_epoch"]
    job = _submit_datagen_job(pc, narrow_start, label=f"narrow window ({narrow_start})")

    # Attempt 2 (fallback): wider window matching the notebook's hardcoded value.
    # Triggers if the narrow window FAILS or SUCCEEDS but produces zero outputs.
    if job.status != JobStatus.SUCCEEDED or not getattr(job.result, "outputs", None):
        wide_start = int(os.environ.get("WIDE_DATAGEN_START_TIME", "1778070134"))
        if wide_start != narrow_start:
            print(f"\n  Narrow window did not yield usable outputs ({job.status}); "
                  f"retrying with wide window {wide_start} (May 6 12:22 UTC).", flush=True)
            job = _submit_datagen_job(pc, wide_start,
                                       label=f"wide fallback ({wide_start})")

    if job.status != JobStatus.SUCCEEDED:
        raise RuntimeError(f"Both datagen attempts failed; last status={job.status}")
    if not getattr(job.result, "outputs", None):
        raise RuntimeError("Datagen succeeded but produced no outputs")

    print("\n  Outputs:", flush=True)
    for o in job.result.outputs:
        print(f"    {o.type}  id={o.id}  filename={o.filename}", flush=True)
    return job


def phase_download(pc, job):
    print(f"\n=== Phase 3: Download SFT JSONL files ===", flush=True)
    aoai = pc.get_openai_client()
    downloaded = []
    for o in job.result.outputs:
        if o.type != DataGenerationJobOutputType.FILE:
            continue
        filename = o.filename
        if not filename:
            try:
                filename = aoai.files.retrieve(o.id).filename
            except Exception:
                filename = None
        if not filename:
            filename = f"{o.id}.jsonl"
        dest = SFT_OUT_DIR / filename
        dest.write_bytes(aoai.files.content(o.id).content)
        size = dest.stat().st_size
        n_lines = sum(1 for _ in dest.open())
        print(f"  Downloaded {o.id} -> {dest.name}  ({size:,} bytes, {n_lines} lines)", flush=True)
        downloaded.append(dest)
    return downloaded


def phase_patch(downloaded):
    print(f"\n=== Phase 4: Patch JSONL into OpenAI FT shape ===", flush=True)
    TOOL_DEFS_PATH = SFT_OUT_DIR / "tool_definitions.json"
    POLICY_PATH = NB_DIR / "src" / "retail-agent-langgraph" / "agent_policy.md"
    if not TOOL_DEFS_PATH.exists():
        # fall back to local tool defs
        alt = NB_DIR / "results" / "sft_data" / "tool_definitions.json"
        if alt.exists():
            TOOL_DEFS_PATH = alt
        else:
            raise RuntimeError(f"tool_definitions.json missing: {TOOL_DEFS_PATH}")
    if not POLICY_PATH.exists():
        raise RuntimeError(f"agent_policy.md missing at {POLICY_PATH}")

    tool_definitions = json.loads(TOOL_DEFS_PATH.read_text())
    agent_policy = POLICY_PATH.read_text(encoding="utf-8")
    SYSTEM_PROMPT = (
        "You are Zava's Post-Purchase Resolution Desk agent. "
        "Help customers with returns, exchanges, replacements, cancellations, and shipping disputes. "
        "Use the available tools to verify eligibility and compute resolutions.\n\n"
        + agent_policy
    )
    print(f"Loaded {len(tool_definitions)} tool definitions; system prompt {len(SYSTEM_PROMPT):,} chars",
          flush=True)

    def _key(m):
        tcs = m.get("tool_calls") or []
        tc_key = tuple(
            (tc.get("id"),
             (tc.get("function") or {}).get("name"),
             (tc.get("function") or {}).get("arguments"))
            for tc in tcs
        )
        return (m.get("role"), m.get("content") or "", m.get("tool_call_id"), tc_key)

    patched = []
    for src in downloaded:
        if src.stem.endswith("_sft"):
            continue
        dst = src.with_name(src.stem + "_sft.jsonl")
        n_in = n_out = n_skipped = n_dedup = n_fragment = 0
        with src.open() as fin, dst.open("w") as fout:
            for raw in fin:
                raw = raw.strip()
                if not raw:
                    continue
                n_in += 1
                ex = json.loads(raw)
                msgs = ex.get("messages", [])
                if not msgs:
                    n_skipped += 1
                    continue
                seen = set()
                deduped = []
                for m in msgs:
                    k = _key(m)
                    if k in seen:
                        n_dedup += 1
                        continue
                    seen.add(k)
                    deduped.append(m)
                msgs = deduped
                has_tool_calls = any(
                    m.get("role") == "assistant" and m.get("tool_calls") for m in msgs
                )
                if not has_tool_calls:
                    n_fragment += 1
                    continue
                if msgs and msgs[0].get("role") == "system":
                    msgs[0] = {"role": "system", "content": SYSTEM_PROMPT}
                else:
                    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + msgs
                patched_ex = {"messages": msgs, "tools": tool_definitions, "parallel_tool_calls": True}
                fout.write(json.dumps(patched_ex) + "\n")
                n_out += 1
        print(f"  {src.name} -> {dst.name}  ({n_in} in / {n_out} out / "
              f"{n_skipped} empty / {n_fragment} fragments / {n_dedup} dup msgs)", flush=True)
        patched.append(dst)
    return patched


# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["traffic", "datagen", "download", "patch", "all"],
                    default="all")
    ap.add_argument("--personas-module", default="personas",
                    help="Comma-separated personas modules to use (default: personas)")
    args = ap.parse_args()

    global CUSTOMER_PERSONAS
    CUSTOMER_PERSONAS = load_personas(args.personas_module)
    print(f"Loaded {len(CUSTOMER_PERSONAS)} personas from: {args.personas_module}", flush=True)

    pc, agent_client, customer_client, agent_version = setup_clients()

    manifest = None
    if args.phase in ("traffic", "all"):
        manifest = phase_traffic(pc, agent_client, customer_client, agent_version)
    else:
        manifest = json.loads((LOG_DIR / "traffic_manifest.json").read_text())

    job = None
    if args.phase in ("datagen", "all"):
        job = phase_datagen(pc, manifest)

    downloaded = []
    if args.phase in ("download", "all"):
        if job is None:
            raise SystemExit("--phase download needs a job; rerun with --phase all")
        downloaded = phase_download(pc, job)

    if args.phase in ("patch", "all"):
        if not downloaded:
            downloaded = sorted(p for p in SFT_OUT_DIR.glob("*.jsonl")
                                if not p.stem.endswith("_sft"))
        phase_patch(downloaded)

    print("\nPipeline complete.", flush=True)


if __name__ == "__main__":
    main()
