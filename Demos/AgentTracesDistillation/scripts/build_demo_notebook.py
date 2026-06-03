"""Build a clean, explanatory demo notebook for FT distillation.

Outputs: demo_distillation.ipynb

The notebook walks through the distillation cycle end-to-end in a single linear
narrative, then closes with a live FT-agent showcase that loads pre-generated
conversations from results/eval_result/demo_transcripts.json.

This builder script is idempotent: re-running it overwrites the .ipynb.
"""
from __future__ import annotations

import json
from pathlib import Path

NB_DIR = Path(__file__).resolve().parents[1]
OUT = NB_DIR / "demo_distillation.ipynb"


def md(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": text.splitlines(keepends=True) or [""],
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True) or [""],
    }


CELLS: list[dict] = []

# =====================================================================
# 0. Title + overview
# =====================================================================
CELLS.append(md("""# Distilling a production retail agent into a small model

This notebook walks step-by-step through one full **distillation cycle**: taking a
small, cheap model that struggles on hard customer-support scenarios and lifting
its quality to near-teacher level by fine-tuning on traces from the production
agent.

**The cast**
| Role | Model | Why |
|---|---|---|
| **Student** | `gpt-4.1-nano` | Small, cheap, fast — what we want in production. Struggles on hard scenarios out of the box. |
| **Teacher** | `gpt-5.5` (running inside the production retail agent) | Strong reasoning. Produces high-quality traces we can learn from. |
| **Fine-tuned student** | `gpt-4.1-nano` fine-tuned on teacher traces | The hoped-for outcome — student-cost, teacher-quality. |

**The cycle**
1. **Score** — define a single number per scenario so we can compare runs.
2. **Baseline** — measure student and teacher on the same 100 hard scenarios.
3. **Harvest** — turn the teacher's recent production traffic into SFT examples.
4. **Fine-tune** — train the student on those examples.
5. **Re-measure** — re-run the fine-tuned student on the same scenarios and a hold-out set.
6. **Showcase** — drive the fine-tuned model through 4 representative scenarios end-to-end so you can see the post-training behavior.

All quality numbers are reported as **pass^k @ 0.70**: the fraction of scenarios
where the model meets the quality bar (combined score ≥ 0.70) on **all k of k**
independent attempts. We run 3 passes per role, so `pass^1 / pass^2 / pass^3` are
all reported. `pass^3` is the strictest — every attempt has to pass. We do **not**
report mean combined scores: averaging a 4-dimension score hides whether the
model is reliably crossing the bar or whether it's noisy.
"""))

# =====================================================================
# 1. Setup
# =====================================================================
CELLS.append(md("""## 1. Setup

Paths, env, projector-friendly styling, and a couple of print helpers reused
by every cell below. Nothing here calls a model.
"""))

CELLS.append(code("""# === Presentation styling: bump font sizes so this renders well on a projector. ===
from IPython.display import HTML, display

display(HTML('''
<style>
/* Rendered markdown */
.jp-RenderedHTMLCommon, .markdown-body, .text_cell_render {
    font-size: 19px !important;
    line-height: 1.6 !important;
}
.jp-RenderedHTMLCommon h1, .markdown-body h1 { font-size: 2.6em !important; }
.jp-RenderedHTMLCommon h2, .markdown-body h2 {
    font-size: 2.0em !important; margin-top: 1.3em !important;
    padding-top: .25em !important; border-top: 3px solid #d1d5da !important;
}
.jp-RenderedHTMLCommon h3, .markdown-body h3 {
    font-size: 1.55em !important; margin-top: 1.0em !important;
}
.jp-RenderedHTMLCommon h4, .markdown-body h4 { font-size: 1.25em !important; }
.jp-RenderedHTMLCommon table, .markdown-body table { font-size: 17px !important; }
.jp-RenderedHTMLCommon code, .markdown-body code { font-size: 16px !important; }
.jp-RenderedHTMLCommon blockquote, .markdown-body blockquote {
    font-size: 17px !important; line-height: 1.55 !important;
}
/* Cell output (print statements) */
.jp-RenderedText, .jp-OutputArea-output pre {
    font-size: 17px !important; line-height: 1.45 !important;
}
/* Code editor */
.cm-editor, .CodeMirror, .jp-CodeMirrorEditor { font-size: 16px !important; }
</style>
'''))

# === Imports + paths + env ===
import json
import os
import textwrap
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

NB_DIR = Path.cwd()
EVAL_DIR = NB_DIR / "eval"
RESULTS_DIR = NB_DIR / "results" / "eval_result"

load_dotenv(NB_DIR / ".env")

STUDENT_MODEL  = os.environ.get("STUDENT_MODEL", "gpt-4.1-nano")
TEACHER_MODEL  = os.environ.get("TEACHER_MODEL", "gpt-5.5")
FT_MODEL       = os.environ.get("FT_MODEL",      "gpt-4.1-nano-demo1")

# === Print helpers used by every cell below ===
BANNER_W = 72

def banner(title: str, sub: str = "") -> None:
    print("═" * BANNER_W)
    print(f"   {title}")
    if sub:
        print(f"   {sub}")
    print("═" * BANNER_W)

def section(title: str) -> None:
    print()
    print(f"   ── {title} ──")

def wrap_field(label: str, value: str, *, width: int = 56) -> None:
    prefix = f"   {label:<11}:  "
    pad = " " * len(prefix)
    lines = textwrap.wrap(value or "", width=width) or [""]
    print(prefix + lines[0])
    for line in lines[1:]:
        print(pad + line)

# === Show what we loaded ===
banner("MODELS  &  PATHS")
print(f"   Student     →  {STUDENT_MODEL}")
print(f"   Teacher     →  {TEACHER_MODEL}  (running inside hosted retail agent)")
print(f"   Fine-tuned  →  {FT_MODEL}")
print()
print(f"   Results dir :  {RESULTS_DIR.relative_to(NB_DIR)}")
print(f"   Eval tasks  :  {EVAL_DIR.relative_to(NB_DIR)}")
"""))

# =====================================================================
# 2. The scenarios
# =====================================================================
CELLS.append(md("""## 2. The evaluation scenarios

Each scenario is a multi-turn customer conversation with a ground-truth
expected resolution (refund, replace, deny, or clarify). The scenarios are
sorted into **categories** — `long_distracting_context`, `restocking_fee_math`,
`multi_item_mixed_outcomes`, `out_of_scope`, etc. — so we can see which
categories are causing the most pain.

- **Training tasks** (`eval/training_tasks.json`, 80 scenarios) — used to harvest fine-tuning examples.
- **Hold-out tasks** (`eval/eval_tasks.json`, 20 scenarios) — held out; the fine-tuned model never sees these during training.
"""))

CELLS.append(code("""train_scenarios = json.loads((EVAL_DIR / "training_tasks.json").read_text(encoding="utf-8"))
val_scenarios   = json.loads((EVAL_DIR / "eval_tasks.json").read_text(encoding="utf-8"))

banner("EVALUATION SCENARIOS")
print(f"   Training tasks    →  {len(train_scenarios)}")
print(f"   Hold-out tasks    →  {len(val_scenarios)}   (held out from training)")

section("Example training scenario (#1)")
ex = train_scenarios[0]
wrap_field("id",        str(ex['id']))
wrap_field("category",  ex['category'])
wrap_field("customer",  '"' + ex['user_message'] + '"')
wrap_field("expected",  ex['expected_resolution_summary'])
"""))

# =====================================================================
# 3. Scoring
# =====================================================================
CELLS.append(md("""## 3. A live customer ↔ teacher conversation

The cell below drives a fresh conversation against the **deployed Foundry teacher agent** (`retail-agent-langgraph` wrapping `gpt-5.5`) — every customer turn and every teacher reply prints as it arrives.

Scenario: `H059: counter_factual_claims` — the customer falsely claims gold tier and asks for a refund. The teacher must *not* trust that claim and must apply the standard-tier 15% restocking fee.

> Requires Azure auth (`azd auth login` or `az login`) and the `.env` values for `AZURE_OPENAI_API_KEY` / `OPENAI_BASE_URL`. Expect ~30–60 s for the conversation.
"""))

CELLS.append(code("""import importlib
import sys
import time

sys.path.insert(0, str(NB_DIR / "scripts"))

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

import run_baselines_hosted as _rbh
_rbh = importlib.reload(_rbh)

# ── Scenario (shared with the next cell's cached scoring) ──
SHOWCASE_NAME = "H059: counter_factual_claims"
scenario = next(s for s in train_scenarios if s["name"] == SHOWCASE_NAME)
HOSTED_AGENT_NAME = os.environ.get("HOSTED_AGENT_NAME", "demo1-retail-agent-langraph-responses")

banner(f"LIVE TEACHER RUN — {scenario['name']}",
       f"Teacher: {TEACHER_MODEL}   ·   hosted agent: {HOSTED_AGENT_NAME}")
wrap_field("scenario", '"' + scenario['user_message'] + '"')
wrap_field("note",     "⚠️  Customer falsely claims 'gold tier' — the teacher must NOT trust this.")
wrap_field("expected", scenario['expected_resolution_summary'])

section("Customer ↔ teacher conversation  (LIVE)")
pc = AIProjectClient(endpoint=_rbh.PROJECT_ENDPOINT,
                     credential=DefaultAzureCredential(),
                     allow_preview=True)
agent_client = pc.get_openai_client(agent_name=HOSTED_AGENT_NAME)

DEMO_MAX_ROUNDS = 5
transcript: list[dict] = []
previous_id = None

for r in range(1, DEMO_MAX_ROUNDS + 1):
    cust = _rbh._customer_reply(transcript, scenario["user_message"])
    ended = "[END]" in cust
    cust = cust.replace("[END]", "").strip()
    if not cust:
        break
    transcript.append({"role": "customer", "content": cust})
    print()
    print(f"   👤 customer  (round {r})")
    for line in textwrap.wrap(cust, width=88) or [""]:
        print(f"      {line}")

    kw = {"input": cust}
    if previous_id:
        kw["previous_response_id"] = previous_id
    t0 = time.perf_counter()
    print(f"   🤖 teacher   (round {r}, thinking…)", end="", flush=True)
    try:
        resp = agent_client.responses.create(**kw)
    except Exception as e:
        print(f"\\n   ❌ teacher call failed: {type(e).__name__}: {str(e)[:160]}")
        raise
    dt = time.perf_counter() - t0
    previous_id = resp.id
    agent_text = (resp.output_text or "").strip()
    transcript.append({"role": "agent", "content": agent_text})
    print(f"  ←  {dt:.1f}s")
    for raw in agent_text.splitlines():
        for line in textwrap.wrap(raw, width=88) or [""]:
            print(f"      {line}")
    if ended:
        break

print()
print(f"   ── conversation done: {len(transcript)//2} round(s) ──")
print(f"   ▶ next cell scores the same scenario from the cached teacher eval")
print(f"     (skips the ~30–90 s App Insights ingestion wait for tool traces)")
"""))

# =====================================================================
# 3b. Step-by-step scoring (cached, same scenario)
# =====================================================================
CELLS.append(md("""## 3b. How that conversation is scored

The previous cell ran a live conversation. Scoring requires the **tool traces**, which
arrive in App Insights after a 30–90 s ingestion delay. To keep the demo flowing, this
cell loads the **same scenario's** cached teacher run (`H059` from
`results/eval_result/train/...teacher...v2.pass1.json`) and walks through scoring
**dimension by dimension**, printing expected vs. actual tools so the grading is auditable.

Scoring dimensions (calibrated, same as the rest of the notebook):

| Dimension | Weight | What it checks |
|---|---:|---|
| **Decision correctness** | 35% | Right action and reason per line item, no over-resolution |
| **Tool trajectory**      | 25% | Right tools in the right order; no forbidden tools |
| **Financial accuracy**   | 20% | Refund / restocking amounts within tolerance |
| **Communication**        | 20% | Specific amounts, per-item summary, policy keywords |

Pass bar: combined ≥ **0.70**.
"""))

CELLS.append(code("""import sys
sys.path.insert(0, str(EVAL_DIR))
from evaluate_v2 import (  # noqa: E402
    score_decision_correctness, score_tool_usage,
    score_financial_accuracy, score_communication,
    _extract_actions_v2, _normalize_tool_calls,
    _has_shipping_credit_for,
)

# ── Load cached teacher run for the SAME scenario (H059) ──
TEACHER_CACHE = RESULTS_DIR / "train" / (
    "baseline__mt__teacher__demo1-retail-agent-langraph-responses.v2.pass1.json"
)
cache = json.loads(TEACHER_CACHE.read_text(encoding="utf-8"))
per_scenario = next(ps for ps in cache["per_scenario"]
                    if ps["scenario_name"] == SHOWCASE_NAME)
final_text = next(
    (t["content"] for t in reversed(per_scenario["transcript"]) if t["role"] == "agent"),
    "",
)
result = {
    "response":   final_text,
    "messages":   per_scenario["transcript"],
    "tool_calls": per_scenario["tool_calls"],
}
tool_calls = per_scenario["tool_calls"]

banner(f"CACHED SCORING — {SHOWCASE_NAME}",
       f"source: train / teacher / pass^1   ·   {len(tool_calls)} tool calls captured")

def _bar(score: float, n: int = 32) -> str:
    fill = int(round(score * n))
    return "█" * fill + "░" * (n - fill)

def _step_header(n: int, total: int, title: str, weight: float, checks: str) -> None:
    print()
    print("  " + "═" * 72)
    print(f"  STEP {n} of {total}  ·  {title:<40}weight = {int(weight*100)}%")
    print("  " + "═" * 72)
    print(f"  what it checks:  {checks}")

def _step_score(score: float, weight: float) -> None:
    print()
    print(f"  ▸ SCORE   {_bar(score)}   {score:>5.3f} / 1.000")
    print(f"            └─ contribution = {score:.3f} × {weight:.2f} = {score*weight:.3f}")

contributions: list[tuple[str, float, float]] = []

# ── Step 1: Decision correctness ──
_step_header(1, 4, "Decision correctness", 0.35,
             "right action + reason per line item, no over-resolution")
expected_actions = scenario.get("expected_actions", {})
actual_actions   = _extract_actions_v2(_normalize_tool_calls(tool_calls))
norm_tcs         = _normalize_tool_calls(tool_calls)
print()
print("  ▸ Expected per-item actions:")
for k, exp in expected_actions.items():
    print(f"      • {k:<22}  action={exp.get('action'):<18} reason={exp.get('reason')}")
print()
print("  ▸ Actual per-item actions (extracted from tool calls):")
for k, exp in expected_actions.items():
    exp_a = exp.get("action")
    exp_r = exp.get("reason")
    # Shipping-credit pseudo-keys are stored under a synthetic id but the
    # actual call carries item_id = real_iid; the scorer dereferences via
    # _has_shipping_credit_for, so mirror that here.
    if k.startswith("shipping_credit"):
        real_iid = exp.get("item_id")
        if real_iid and _has_shipping_credit_for(norm_tcs, real_iid):
            print(f"      • {k:<22}  ✅ shipping_credit found for item {real_iid}")
        else:
            print(f"      • {k:<22}  ❌ no shipping_credit call for item {real_iid}")
        continue
    act = actual_actions.get(k)
    if not act:
        print(f"      • {k:<22}  ❌ MISSING from tool calls")
        continue
    mark_a = "✅ match" if exp_a == act.get("action") else "⚠️  differs"
    mark_r = "✅ match" if (exp_r is None or exp_r == act.get("reason")) else "⚠️  differs"
    print(f"      • {k:<22}  action={act.get('action'):<18} reason={act.get('reason')}")
    print(f"        {' '*22}  {mark_a:<18}        {mark_r}")
# Surface anything the agent resolved that wasn't expected (over-resolution).
extra = [k for k in actual_actions if k not in expected_actions]
for k in extra:
    a = actual_actions[k]
    print(f"      • {k:<22}  ⚠️  unexpected: action={a.get('action')} reason={a.get('reason')}")
sc1 = score_decision_correctness(result, scenario)
_step_score(sc1, 0.35)
contributions.append(("decision", sc1, 0.35))

# ── Step 2: Tool trajectory ──
_step_header(2, 4, "Tool trajectory", 0.25,
             "right tools in right order, no forbidden tools")
expected_tools = scenario.get("expected_tools", [])
forbidden      = scenario.get("forbidden_tools", [])
actual_tools   = [tc["name"] for tc in tool_calls]
exp_set, act_set = set(expected_tools), set(actual_tools)
print()
print(f"  ▸ Expected tools  ({len(expected_tools)}):")
for t in expected_tools:
    mark = "✅ called" if t in act_set else "❌ MISSING"
    print(f"      • {t:<30}  {mark}")
print()
print(f"  ▸ Actual tools called  ({len(actual_tools)}, in order):")
for i, t in enumerate(actual_tools, 1):
    mark = "✅" if t in exp_set else "⚠️  unexpected"
    print(f"      {i:>2}. {t:<30}  {mark}")
if forbidden:
    print()
    print(f"  ▸ Forbidden tools  ({len(forbidden)}):")
    for t in forbidden:
        mark = "❌ CALLED!" if t in act_set else "✅ avoided"
        print(f"      • {t:<30}  {mark}")
sc2 = score_tool_usage(result, scenario)
_step_score(sc2, 0.25)
contributions.append(("tools", sc2, 0.25))

# ── Step 3: Financial accuracy ──
_step_header(3, 4, "Financial accuracy", 0.20,
             "refund / restocking amounts within tolerance")
expected_amounts = scenario.get("expected_amounts", {}) or {}
if expected_amounts:
    print()
    print("  ▸ Expected amounts:")
    for k, v in expected_amounts.items():
        print(f"      • {k:<24}  ${v:>9.2f}")
print()
print("  ▸ Checked against agent's final message and submit_resolution args")
sc3 = score_financial_accuracy(result, scenario)
_step_score(sc3, 0.20)
contributions.append(("financial", sc3, 0.20))

# ── Step 4: Communication ──
_step_header(4, 4, "Communication quality", 0.20,
             "specific amounts, per-item summary, policy keywords")
print()
print("  ▸ Checked against agent's final message to the customer")
sc4 = score_communication(result, scenario)
_step_score(sc4, 0.20)
contributions.append(("comm", sc4, 0.20))

# ── Final verdict ──
print()
print()
print("  " + "═" * 72)
print("  FINAL SCORE")
print("  " + "═" * 72)
print(f"      {'dimension':<14}{'score':>8}  {'×':^3}  {'weight':>6}  {'=':^3}  {'contribution':>12}")
print(f"      {'-'*14}{'-'*8}  {'-'*3}  {'-'*6}  {'-'*3}  {'-'*12}")
for name, s, w in contributions:
    print(f"      {name:<14}{s:>8.3f}  {'×':^3}  {w:>6.2f}  {'=':^3}  {s*w:>12.3f}")
combined = sum(s * w for _, s, w in contributions)
verdict  = "✅  PASS" if combined >= 0.70 else "❌  FAIL"
print(f"      {'-'*14}{'-'*8}  {'-'*3}  {'-'*6}  {'-'*3}  {'-'*12}")
print(f"      {'COMBINED':<14}{'':>8}  {' ':^3}  {'':>6}  {' ':^3}  {combined:>12.3f}")
print()
print(f"      pass bar  =  0.700")
print(f"      verdict   =  {verdict}    (combined {combined:.3f} {'≥' if combined>=0.70 else '<'} 0.700)")
"""))

# =====================================================================
# 4. Helper: load cached results
# =====================================================================
CELLS.append(md("""## 4. Loading the cached eval runs

Every cell in the 3×3×2 evaluation matrix (3 roles × 3 passes × 2 sets) is on
disk under `results/eval_result/{train,validation}/`. The notebook does not
re-run the eval — it loads the cached JSON.
"""))

CELLS.append(code("""def _file(role: str, k: int) -> str:
    if role == "student":
        return f"baseline__mt__student__{STUDENT_MODEL}.v2.pass{k}.json"
    if role == "ft":
        return f"baseline__mt__ft__{FT_MODEL}.v2.pass{k}.json"
    # teacher's deployment is reported under its hosted agent name
    return "baseline__mt__teacher__demo1-retail-agent-langraph-responses.v2.pass{k}.json".format(k=k)


def load_runs(set_name: str, role: str) -> list[dict]:
    runs = []
    for k in (1, 2, 3):
        path = RESULTS_DIR / set_name / _file(role, k)
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    return runs


banner("CACHED EVAL RUNS",
       "3 roles × 3 passes × 2 sets  =  18 cells on disk, all scored")
print(f"   {'set':<12} {'role':<10} {'pass^1':>10} {'pass^2':>10} {'pass^3':>10}")
print(f"   {'─' * 56}")
_SET_LABEL = {"train": "train", "validation": "hold-out"}
for set_name in ("train", "validation"):
    for role in ("student", "teacher", "ft"):
        ns = [len(r["per_scenario"]) for r in load_runs(set_name, role)]
        print(f"   {_SET_LABEL[set_name]:<12} {role:<10} {ns[0]:>10} {ns[1]:>10} {ns[2]:>10}")
"""))

# =====================================================================
# 5. Pass^k aggregator
# =====================================================================
CELLS.append(md("""## 5. The pass^k aggregator

`pass^k @ tau` for a scenario is 1 if every one of its k passes scored at or above `tau`,
else 0. We average across all scenarios to get the headline number.
"""))

CELLS.append(code("""TAU = 0.70

def pass_k_at(set_name: str, role: str, tau: float = TAU) -> dict:
    runs = load_runs(set_name, role)
    by_sid = defaultdict(list)
    for run in runs:
        for ps in run["per_scenario"]:
            by_sid[ps["scenario_id"]].append(ps.get("combined", 0.0))
    n = len(by_sid)
    p1 = sum(1 for scores in by_sid.values() if scores[0] >= tau) / n
    p2 = sum(1 for scores in by_sid.values() if all(s >= tau for s in scores[:2])) / n
    p3 = sum(1 for scores in by_sid.values() if all(s >= tau for s in scores[:3])) / n
    return {"n": n, "pass^1": p1, "pass^2": p2, "pass^3": p3}


_ROLE_LABEL = {
    "student": f"student   ({STUDENT_MODEL})",
    "teacher": f"teacher   ({TEACHER_MODEL})",
    "ft":      f"ft        ({FT_MODEL})",
}

banner(f"PASS^k  @  τ = {TAU}",
       "fraction of scenarios meeting the bar on all k of k tries")

for set_name, set_title in (
    ("train",      "TRAIN  (80 scenarios)"),
    ("validation", "HOLD-OUT  (20 scenarios — never seen during training)"),
):
    print()
    print(f"   {set_title}")
    print(f"   {'─' * 68}")
    print(f"   {'role':<38} {'pass^1':>9} {'pass^2':>9} {'pass^3':>9}")
    print(f"   {'─' * 68}")
    for role in ("student", "teacher", "ft"):
        s = pass_k_at(set_name, role)
        print(f"   {_ROLE_LABEL[role]:<38} "
              f"{s['pass^1']*100:>8.0f}% {s['pass^2']*100:>8.0f}% {s['pass^3']*100:>8.0f}%")
"""))

# =====================================================================
# 6. Headline lift
# =====================================================================
CELLS.append(md("""## 6. Headline: how much did fine-tuning lift the student?

The interesting comparison is **student vs fine-tuned student**: same base model,
same cost-per-token. The teacher is shown as a reference ceiling.

Two metrics per pass^k row:

- **ft lift** = `ft - student`, in percentage points. Absolute gain from fine-tuning.
- **headroom recovered** = `(ft - student) / (teacher - student)`. Fraction of the
  student → teacher gap that fine-tuning closed. 1.000 means FT matched the teacher;
  values >1.000 mean FT exceeded it. Undefined when the student already matches the
  teacher (`n/a`).
"""))

CELLS.append(code("""def lift_table(set_name: str, title: str) -> None:
    s = pass_k_at(set_name, "student")
    f = pass_k_at(set_name, "ft")
    t = pass_k_at(set_name, "teacher")
    banner(f"FT LIFT — {title}",
           f"{s['n']} scenarios   ·   student → FT (same base model, same cost)")
    print(f"   {'metric':<8} {'student':>8} {'→':>3} {'ft':>8} {'teacher':>9}"
          f"   {'lift':>8}   {'headroom recovered':>20}")
    print(f"   {'─' * 78}")
    for key in ("pass^1", "pass^2", "pass^3"):
        ds_pp = (f[key] - s[key]) * 100
        gap = t[key] - s[key]
        if gap > 0:
            head = f"{(f[key] - s[key]) / gap * 100:>+18.0f}%"
        else:
            head = f"{'n/a':>19}"
        print(f"   {key:<8} {s[key]*100:>7.0f}% "
              f"{'→':>3} {f[key]*100:>7.0f}% {t[key]*100:>8.0f}%"
              f"   {ds_pp:>+6.1f}pp   {head}")


lift_table("train",      "Train")
print()
lift_table("validation", "Hold-out")
"""))

# =====================================================================
# 6b. Visual: grouped bar chart of pass^k for student / FT / teacher
# =====================================================================
CELLS.append(md("""### Visualizing the lift

The same numbers as a grouped bar chart, so the **student &rarr; FT** uplift is
visually obvious against the teacher ceiling.
"""))

CELLS.append(code("""import matplotlib.pyplot as plt
import numpy as np

ROLES   = ("student", "ft", "teacher")
LABELS  = {"student": "Student (baseline)",
           "ft":      "FT student (after distillation)",
           "teacher": "Teacher (reference ceiling)"}
COLORS  = {"student": "#c0c4cc",  # neutral grey
           "ft":      "#1f77b4",  # blue, the hero
           "teacher": "#2ca02c"}  # green ceiling
METRICS = ("pass^1", "pass^2", "pass^3")
SETS    = (("train", "Train (80 scenarios)"),
           ("validation", "Hold-out (20 scenarios)"))

fig, axes = plt.subplots(1, 2, figsize=(15, 6.2), sharey=True)
x = np.arange(len(METRICS))
w = 0.26

for ax, (set_name, set_title) in zip(axes, SETS):
    scores = {role: pass_k_at(set_name, role) for role in ROLES}
    for i, role in enumerate(ROLES):
        vals = [scores[role][m] for m in METRICS]
        bars = ax.bar(x + (i - 1) * w, vals, w,
                      label=LABELS[role], color=COLORS[role],
                      edgecolor="white", linewidth=0.8,
                      zorder=3)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width()/2, v + 0.015,
                    f"{v:.2f}", ha="center", va="bottom",
                    fontsize=12, fontweight="bold", color="#222", zorder=4)

    # FT uplift annotation: arrow from student to ft at pass^3
    s3 = scores["student"]["pass^3"]
    f3 = scores["ft"]["pass^3"]
    t3 = scores["teacher"]["pass^3"]
    gap3 = t3 - s3
    if f3 > s3:
        x_anchor = x[-1] + w * 0.45
        ax.annotate("", xy=(x_anchor, f3), xytext=(x_anchor, s3),
                    arrowprops=dict(arrowstyle="->", color="#d62728", lw=2.2),
                    zorder=5)
        if gap3 > 0:
            headroom_pct = (f3 - s3) / gap3 * 100
            label = f"{headroom_pct:.0f}%\\nheadroom\\nrecovered"
        else:
            label = f"+{(f3-s3)*100:.0f}pp"
        ax.text(x_anchor + 0.05, (s3 + f3)/2,
                label, color="#d62728",
                fontsize=12, fontweight="bold", va="center", zorder=5)

    ax.set_xticks(x)
    ax.set_xticklabels(METRICS, fontsize=13)
    ax.set_title(set_title, fontsize=15, pad=12)
    ax.set_ylim(0, 1.1)
    ax.set_yticks(np.linspace(0, 1.0, 6))
    ax.set_yticklabels([f"{v:.0%}" for v in np.linspace(0, 1.0, 6)], fontsize=12)
    ax.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

axes[0].set_ylabel(f"pass^k @ τ = {TAU}", fontsize=14)
# Legend goes to the right of the figure so it doesn't overlap the bars
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="center left",
           bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=13)
fig.suptitle("Fine-tuning lifts the student toward the teacher ceiling",
             fontsize=18, fontweight="bold", y=1.03)
fig.tight_layout(rect=(0, 0, 0.84, 1))
plt.show()
"""))

# =====================================================================
# 7. The distillation pipeline — narrated with concrete artifacts
# =====================================================================
CELLS.append(md("""## 7. How the SFT training data was generated

> **TL;DR.** Teacher traces from the deployed agent → Foundry `DataGenerationJob`
> reshapes them into chat-completion JSONL → light dedup/cleanup → upload as a
> fine-tuning job against `gpt-4.1-nano` → new deployment (`gpt-4.1-nano-demo1`).
> No human labeling. No synthetic prompts. The cells below show the exact API
> calls (as reference — not re-executed here) and one real cached trace.

The fine-tuning data is just **the teacher's own conversation traces**, captured
from the deployed production agent and turned into chat-completion training
examples. No human labeling, no synthetic prompts. Four steps:

### 7a. Drive traffic against the deployed teacher
The teacher (`gpt-5.5`) is wrapped inside a deployed Foundry agent
(`retail-agent-langgraph`) — the same agent customers would hit in production.
We pointed `scripts/drive_teacher_traffic.py` at the hosted endpoint and replayed
the 80 training scenarios through it, several times with different random
seeds. Two design choices matter:

- **Literal-replay first turn.** The customer's opening message is the scenario's
  `user_message` verbatim — adversarial framing intact ("I shouldn't pay a
  restocking fee because the keys aren't what I expected"). The persona simulator
  only kicks in for follow-up turns. This preserves the hard adversarial context
  that a vague "Hi I need help with my keyboard" would strip.
- **No scoring.** The driver only needs traces flowing through App Insights;
  scoring happens later, in a separate eval pass.

### 7b. Harvest traces from telemetry & shape into SFT JSONL

The Foundry agent emits OpenTelemetry to App Insights — one span per tool call,
one span per assistant message. Rather than write our own KQL+join job, we use
the Foundry `DataGenerationJob` API which does exactly this server-side: it
pulls a time window of traces, joins spans by conversation ID, reshapes each
conversation into a chat-completion training example, and emits a train/valid
JSONL pair ready for fine-tuning. Each example is one line:

```
[
  {"role": "system",    "content": "<agent_policy.md, the full instructions>"},
  {"role": "user",      "content": "<customer's opening turn>"},
  {"role": "assistant", "content": null, "tool_calls": [...]},
  {"role": "tool",      "content": "<tool result JSON>",       "tool_call_id": "..."},
  {"role": "assistant", "content": "<reply or null + more tool_calls>"},
  ...
]
```

**The actual code we ran** (from `demo1_agent_distillation.ipynb` §10.1–§10.4 —
shown here as reference; not re-executed in this walkthrough because it requires
Azure login and overwrites the cached SFT data the FT model was trained on):

```python
# §7b.1 — connect to the Foundry project and pick the window
from datetime import datetime, timedelta, timezone
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

ENDPOINT     = "https://smamgain-tip-aifoundry.services.ai.azure.com/api/projects/smamgain-tip-aiproject"
HOSTED_AGENT = "retail-agent-langgraph"
SFT_DIR      = NB_DIR / "results" / "sft_demo1_last24h"
SFT_DIR.mkdir(parents=True, exist_ok=True)

end_dt   = datetime.now(timezone.utc)
start_dt = end_dt - timedelta(hours=24)             # last 24h of teacher traffic

project_client = AIProjectClient(endpoint=ENDPOINT,
                                 credential=DefaultAzureCredential(),
                                 allow_preview=True)
conn = project_client.telemetry.get_application_insights_connection_string()
assert conn, "Project has no App Insights resource attached."
```

```python
# §7b.2 — submit the supervised-finetuning datagen job
from azure.ai.projects.models import (
    DataGenerationJob, DataGenerationJobInputs, DataGenerationJobScenario,
    TracesDataGenerationJobOptions, TracesDataGenerationJobSource,
)

options = TracesDataGenerationJobOptions(max_samples=200, train_split=0.8)
source  = TracesDataGenerationJobSource(agent_name=HOSTED_AGENT,
                                        start_time=int(start_dt.timestamp()))

job = project_client.beta.datasets.create_generation_job(DataGenerationJob(
    inputs=DataGenerationJobInputs(
        name=f"demo1-sft-{int(time.time())}",
        scenario=DataGenerationJobScenario.SUPERVISED_FINETUNING,
        sources=[source], options=options,
    ),
))
print(f"Job created: {job.id} ({job.status})")
```

```python
# §7b.3 — poll until terminal (usually 1–3 minutes for a 24h window)
from azure.ai.projects.models import JobStatus
TERMINAL = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
while job.status not in TERMINAL:
    job = project_client.beta.datasets.get_generation_job(job.id)
    time.sleep(10)
assert job.status == JobStatus.SUCCEEDED, f"datagen failed: {job!r}"
```

```python
# §7b.4 — download outputs (training + validation JSONL + tool_definitions.json)
from azure.ai.projects.models import DataGenerationJobOutputType
aoai = project_client.get_openai_client()
for output in job.result.outputs:
    if output.type != DataGenerationJobOutputType.FILE:
        continue
    dest = SFT_DIR / (output.filename or f"{output.id}.jsonl")
    dest.write_bytes(aoai.files.content(output.id).content)
    print(f"  {output.id} -> {dest.name}  ({dest.stat().st_size:,} bytes)")
```

The worker then runs a small `dedup_and_clean()` pass on the downloaded JSONL
(trace-level dedup by canonical key-map, within-example message dedup, truncate
unanswered tool calls, keep refusal-style examples, inject system prompt + tool
schema) — full implementation in `demo1_agent_distillation.ipynb` §10.5. Output
is `train_sft.jsonl` + `valid_sft.jsonl`, ready for `fine_tuning.jobs.create`.

### 7c. Submit the fine-tuning job
The cleaned `train_sft.jsonl` + `valid_sft.jsonl` were uploaded as a
supervised-finetuning job against `gpt-4.1-nano` on the Sweden Azure OpenAI
resource. The job took roughly 30 minutes and produced a new deployment
(`gpt-4.1-nano-demo1`).

### 7d. Re-evaluate
The full 3×3×2 matrix was re-run against the new deployment with identical
seeds, producing the cached files §4 loaded.

Below: a peek at one actual teacher trace from the cached eval, to make the
"a conversation = a training example" pattern concrete.
"""))

CELLS.append(code("""# Peek at a single teacher conversation from the cached eval data.
# (The eval runner stores the same shape we'd harvest from telemetry.)
teacher_pass1 = load_runs("train", "teacher")[0]
sample = next(ps for ps in teacher_pass1["per_scenario"] if ps.get("transcript"))

banner("ONE TEACHER TRACE  =  ONE SFT TRAINING EXAMPLE")
wrap_field("scenario_id",   str(sample['scenario_id']))
wrap_field("category",      sample['category'])
wrap_field("combined",      f"{sample['combined']:.3f}")
wrap_field("rounds",        str(sample['rounds']))
wrap_field("tool calls",    str(len(sample.get('tool_calls') or [])))

section("Conversation turns (first 6)")
for turn in sample["transcript"][:6]:
    speaker = "👤 customer" if turn['role'] == 'customer' else "🤖 agent   "
    content = (turn.get("content") or "").strip().replace("\\n", " ")
    if len(content) > 120:
        content = content[:120] + "…"
    print(f"     {speaker}  │  {content}")

section("Tool calls in order (first 6)")
for i, tc in enumerate((sample.get('tool_calls') or [])[:6], 1):
    args = tc.get('arguments', {})
    result = (tc.get('result') or '')[:90].replace('\\n', ' ')
    print(f"     {i}. {tc['name']}({json.dumps(args)})")
    print(f"        ↳ {result}…")
"""))

# =====================================================================
# 8. Live showcase — student vs fine-tuned, side by side
# =====================================================================
CELLS.append(md("""## 8. Side-by-side showcase — student vs fine-tuned model

To build intuition for **what changed** behaviorally, we picked four scenarios
where the FT model substantially outperformed the student in the eval, then
re-ran each scenario twice live — once against the **deployed student endpoint**
(`gpt-4.1-nano`) and once against the **deployed fine-tuned endpoint**
(`gpt-4.1-nano-demo1`). Both runs used the same customer simulator and the same
opening user message; only the agent model differs.

The transcripts in this section were generated by
`scripts/generate_demo_conversations.py` and cached in
`results/eval_result/demo_transcripts.json` — the notebook never hits either
endpoint at render time.
"""))

CELLS.append(code("""DEMOS_PATH = RESULTS_DIR / "demo_transcripts.json"
demos = json.loads(DEMOS_PATH.read_text(encoding="utf-8"))

banner("LIVE SHOWCASE — student vs FT, side by side")
print(f"   Demo conversations  :  {len(demos['demos'])}")
print(f"   Student model       :  {demos['student_model']}")
print(f"   FT model            :  {demos['ft_model']}")
print(f"   Generated           :  {demos['generated_at']}")
"""))

# =====================================================================
# 8b. Renderer
# =====================================================================
CELLS.append(md("""### Rendering helper

Each demo has a `student` and an `ft` block, each with its own transcript and
tool calls. The helper renders the scenario context once, then the two
conversations stacked (student first, then FT) for easy visual comparison.
"""))

CELLS.append(code("""from IPython.display import Markdown, display


def _fmt_args(args) -> str:
    if isinstance(args, dict):
        return ", ".join(f"{k}={json.dumps(v, default=str)}" for k, v in args.items())
    return str(args)


def _render_one_side(label: str, model_name: str, side: dict) -> list[str]:
    lines: list[str] = []
    n_tools = len(side.get("tool_calls") or [])
    tool_names = [tc.get("name") for tc in (side.get("tool_calls") or [])]
    lines.append(f"#### {label} — `{model_name}`")
    lines.append(f"_Rounds: {side.get('rounds')}  •  Tool calls: {n_tools}  "
                 f"•  Stop: `{side.get('stop_reason')}`_")
    lines.append("")
    if tool_names:
        lines.append(f"**Tool sequence:** {' → '.join(f'`{t}`' for t in tool_names)}")
        lines.append("")
    lines.append("<details><summary><b>Full transcript</b></summary>")
    lines.append("")
    for turn in side.get("transcript", []):
        speaker = "👤 **Customer**" if turn["role"] == "customer" else "🤖 **Agent**"
        content = (turn.get("content") or "").strip()
        lines.append(f"{speaker}:")
        lines.append("")
        for line in (content.splitlines() or [""]):
            lines.append(f"> {line}")
        lines.append("")
    lines.append("</details>")
    lines.append("")
    return lines


def render_demo(demo: dict, diagnosis_md: str = "") -> None:
    md_lines: list[str] = []
    md_lines.append(f"### {demo['set']}/{demo['scenario_id']} — {demo['headline']}")
    md_lines.append(f"**Category:** `{demo['category']}`")
    md_lines.append("")
    md_lines.append(f"**Customer opens with:**")
    md_lines.append(f"> {demo['scenario']['user_message']}")
    md_lines.append("")
    md_lines.append(f"**Expected resolution:** {demo['scenario']['expected_resolution_summary']}")
    if demo['scenario'].get('expected_amounts'):
        ea = demo['scenario']['expected_amounts']
        if 'total_refund' in ea:
            md_lines.append(f"**Expected refund:** ${ea['total_refund']:.2f}")
    md_lines.append(f"**Expected tools:** `{demo['scenario'].get('expected_tools')}`")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.extend(_render_one_side("Before fine-tuning (student)", demos['student_model'], demo['student']))
    md_lines.extend(_render_one_side("After fine-tuning (FT)",       demos['ft_model'],      demo['ft']))
    if diagnosis_md:
        md_lines.append("---")
        md_lines.append("")
        md_lines.append("#### Why the student failed and the FT model succeeded")
        md_lines.append("")
        md_lines.append(diagnosis_md)
    display(Markdown("\\n".join(md_lines)))
"""))

# =====================================================================
# 8c. Render each demo with hand-written diagnosis
# =====================================================================
CELLS.append(md("""### Demo 1 — Restocking-fee math: customer tries to dodge the fee

Diego argues that not liking the keys is "basically a defect" and shouldn't owe a
15% fee. Standard-tier non-defective electronics owe 15% — the correct refund is
$110.49 on a $129.99 keyboard.
"""))
CELLS.append(code("""diagnosis = '''
Both runs landed on the same $110.49 net refund, but **the reason classification is completely different — and the student's submission validates the customer's false premise**.

- **Student** classified the return reason as `doesnt_fit` in `check_resolution_policy` / `calculate_resolution` (already a stretch — the customer's complaint is preference, not fit), and then in `submit_resolution` the customer-facing summary literally reads: *"Refund of $110.49 for the Mechanical Keyboard **due to defect**. Restocking fee of $19.50 applied."* — agreeing on the record that the keyboard was defective even though it isn't, and even though its own tool call didn't say so. It also opened with a tool error: `get_order_details({"order_id": "diego.rivera@example.com"})` — passing the **email as the order id** instead of `ORD-H11`. Its final customer message reports only the net `$110.49` with no breakdown and never mentions the restocking fee.
- **FT** classified the reason as `buyers_remorse` — the correct policy bucket for *"the keys aren't what I expected"*. Its `submit_resolution` summary is the right one: *"Refund for Mechanical Keyboard (LI-H11) due to **buyer's remorse**. Refund amount $129.99 minus $19.50 restocking fee, net $110.49."* No bogus tool calls. Its final message to the customer itemizes the gross, the fee, and the net.

The financial outcomes happen to match here because `doesnt_fit` and `buyers_remorse` both carry the same 15% restocking fee for standard electronics — but the **paper trail is wrong** for the student. On other passes the student frequently goes further and classifies as `defective`, which yields a full $129.99 refund and the wrong financial outcome too — which is why student `pass^3` on `restocking_fee_math` is **0.00** while FT's is high.

What fine-tuning taught is the reason-classification heuristic that the teacher uses consistently: *customer dissatisfaction with how a working product performs is not a defect, no matter how the customer phrases it.*
'''
render_demo(demos['demos'][0], diagnosis)
"""))

CELLS.append(md("""### Demo 2 — Multi-item cart: cancel both items before shipment

Liam wants to cancel an unshipped order with two items. Both are still
processing, so the correct outcome is a full $164.98 refund (no fees) and a
confirmation ID.
"""))
CELLS.append(code("""diagnosis = '''
This is a clear student failure: it claimed the cancellation was complete without ever computing or quoting the refund amount.

- **Student** called only **3 tools** — it **skipped `check_resolution_policy` and `calculate_resolution` entirely** and jumped straight to `submit_resolution`. Its confirmation message says *"Your order has been successfully canceled, and a full refund has been issued for all items"* — but with **no dollar amount, no confirmation ID, and no per-item breakdown**. The customer is told it's done, but with nothing they can verify or quote back.
- **FT** called all 5 expected tools (plus one extra `check_resolution_policy` to verify both items) and produced a fully-specified confirmation: $129.99 + $34.99 = **$164.98 total refund**, confirmation ID `RES-80B1A814`, and an email confirmation note.

The student's failure mode is **dropping the policy/calc steps that produce the dollar amounts**, then writing a confirmation that sounds right but is content-free. The FT model learned from teacher traces that a resolution conversation isn't finished until the customer hears the exact dollar amount and a reference number.
'''
render_demo(demos['demos'][1], diagnosis)
"""))

CELLS.append(md("""### Demo 3 — Sale-priced item with a non-defective complaint: correct denial

Aisha's water bottle is a sale item and her complaint is *"doesn't keep drinks
cold as long as advertised"* — performance dissatisfaction, not a manufacturing
defect. Sale-final items are non-returnable except for defects, so the correct
answer is **deny**.
"""))
CELLS.append(code("""diagnosis = '''
This is a clear student failure: it issued a refund on a non-returnable item.

- **Student** made **8 tool calls** including duplicate `get_order_details`, duplicate `check_resolution_policy`, **`calculate_resolution`, and `submit_resolution`** — meaning it actually *submitted a refund* on a sale-final, non-defective item. The final message is a content-free pleasantry that hides what just happened. This is the worst class of failure: a wrong action wrapped in a friendly tone.
- **FT** made 4 tool calls and **stopped after `calculate_resolution` returned ineligible**. It did **not** call `submit_resolution`. The final message politely accepts the denial and offers further help.

The student's failure mode here is **not honoring the eligibility result** — once `check_resolution_policy` and `calculate_resolution` say "ineligible / sale-final / no refund", the next correct action is to **stop and explain**, not to call `submit_resolution` anyway. The FT model learned the deny-path from the teacher.
'''
render_demo(demos['demos'][2], diagnosis)
"""))

CELLS.append(md("""### Demo 4 — Out-of-scope request: refuse without invoking any tools

Yusuf asks to **place a new order** for a Bluetooth Speaker. The agent's scope
is post-purchase support (returns, exchanges, replacements) — placing new orders
is out of scope, and the correct behavior is to refuse and redirect **without
calling any tool**.
"""))
CELLS.append(code("""diagnosis = '''
This is the cleanest behavioral contrast in the demo set.

- **Student** called `check_inventory` — a **tool that is forbidden** for out-of-scope queries. The student treated "place a new order" as a legitimate task and reached for the inventory tool to start fulfilling it. It took 5 rounds of back-and-forth before stopping.
- **FT** made **zero tool calls** and answered in 3 rounds. It recognized the request as out of scope, politely declined to place an order, and redirected the customer to use the website while keeping the door open for any *existing*-order issues.

This is the hardest behavior to teach without examples: "do not act, do not look anything up, just refuse politely". It only comes from training data that includes refusal traces — which is why the cleaner in §7b **explicitly preserves** substantive-text/no-tool-call examples instead of filtering them out as "empty".
'''
render_demo(demos['demos'][3], diagnosis)
"""))

# =====================================================================
# 9. Wrap-up
# =====================================================================
CELLS.append(md("""## 9. Takeaways

- Fine-tuning a small model on traces from a strong production agent produced a
  large, consistent lift: roughly **+19 pp** on `pass^3 ≥ 0.7` on the training
  scenarios and **+40 pp** on the hold-out scenarios. No mean was
  needed to tell the story — the pass-bar table speaks for itself.
- The lift was largest on the categories where the student was weakest:
  multi-item mixed outcomes, restocking-fee math, sale + defective edge cases,
  and out-of-scope refusals. The four side-by-side demos in §8 show the typical
  failure modes the student now avoids: skipping the resolution flow and giving
  content-free pleasantries (§8 demo 2), submitting refunds on ineligible items
  (§8 demo 3), and calling tools on out-of-scope requests (§8 demo 4).
- The post-FT model still costs the same per call as the base student.
- Reproducing this cycle on a new agent is mostly mechanical:
  1. Define a scorer + a hard scenario set.
  2. Capture teacher traces from production telemetry (see §7 for the harvest
     and cleaning steps that matter).
  3. Convert + clean → SFT JSONL.
  4. Submit a fine-tuning job.
  5. Re-evaluate with the same harness.

The complete eval results (3 roles × 3 passes × 2 sets = 18 cells, 900 scored
scenarios) are in `results/eval_result/`. The live conversation transcripts
rendered above are in `results/eval_result/demo_transcripts.json` and were
generated by `scripts/generate_demo_conversations.py`.
"""))


# =====================================================================
# Assemble
# =====================================================================
nb = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3 (.venv-hosted)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT.relative_to(NB_DIR)} with {len(CELLS)} cells")
