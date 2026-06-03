"""Build a single-page HTML showcase of the four side-by-side demos.

Reads the same demo_transcripts.json the notebook reads, plus the per-demo
written diagnoses from build_demo_notebook.py, and produces a self-contained,
light-theme HTML page tuned for presentation reading (medium-to-large fonts,
clear scenario / before / after layout).

Usage:
    python scripts/build_showcase_html.py
    # writes results/eval_result/demo_showcase.html
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS_PATH = REPO_ROOT / "results" / "eval_result" / "demo_transcripts.json"
OUT_PATH = REPO_ROOT / "results" / "eval_result" / "demo_showcase.html"


# Hand-written per-demo diagnoses, kept in lockstep with build_demo_notebook.py.
DIAGNOSES: list[tuple[str, str]] = [
    (
        "Restocking-fee math: customer tries to dodge the fee",
        """Both runs landed on the same $110.49 net refund, but **the reason classification is completely different — and the student's submission validates the customer's false premise**.

- **Student** classified the return reason as `doesnt_fit` in `check_resolution_policy` / `calculate_resolution` (already a stretch — the customer's complaint is preference, not fit), and then in `submit_resolution` the customer-facing summary literally reads: *"Refund of $110.49 for the Mechanical Keyboard **due to defect**. Restocking fee of $19.50 applied."* — agreeing on the record that the keyboard was defective even though it isn't, and even though its own tool call didn't say so. It also opened with a tool error: `get_order_details({"order_id": "diego.rivera@example.com"})` — passing the **email as the order id** instead of `ORD-H11`. Its final customer message reports only the net `$110.49` with no breakdown and never mentions the restocking fee.
- **FT** classified the reason as `buyers_remorse` — the correct policy bucket for *"the keys aren't what I expected"*. Its `submit_resolution` summary is the right one: *"Refund for Mechanical Keyboard (LI-H11) due to **buyer's remorse**. Refund amount $129.99 minus $19.50 restocking fee, net $110.49."* No bogus tool calls. Its final message to the customer itemizes the gross, the fee, and the net.

The financial outcomes happen to match here because `doesnt_fit` and `buyers_remorse` both carry the same 15% restocking fee for standard electronics — but the **paper trail is wrong** for the student. On other passes the student frequently goes further and classifies as `defective`, which yields a full $129.99 refund and the wrong financial outcome too — which is why student `pass^3` on `restocking_fee_math` is **0.00** while FT's is high.

What fine-tuning taught is the reason-classification heuristic that the teacher uses consistently: *customer dissatisfaction with how a working product performs is not a defect, no matter how the customer phrases it.*""",
    ),
    (
        "Multi-item cart: cancel both items before shipment",
        """This is a clear student failure: it claimed the cancellation was complete without ever computing or quoting the refund amount.

- **Student** called only **3 tools** — it **skipped `check_resolution_policy` and `calculate_resolution` entirely** and jumped straight to `submit_resolution`. Its confirmation message says *"Your order has been successfully canceled, and a full refund has been issued for all items"* — but with **no dollar amount, no confirmation ID, and no per-item breakdown**. The customer is told it's done, but with nothing they can verify or quote back.
- **FT** called all 5 expected tools (plus one extra `check_resolution_policy` to verify both items) and produced a fully-specified confirmation: $129.99 + $34.99 = **$164.98 total refund**, confirmation ID `RES-80B1A814`, and an email confirmation note.

The student's failure mode is **dropping the policy/calc steps that produce the dollar amounts**, then writing a confirmation that sounds right but is content-free. The FT model learned from teacher traces that a resolution conversation isn't finished until the customer hears the exact dollar amount and a reference number.""",
    ),
    (
        "Sale-priced item with a non-defective complaint: correct denial",
        """This is a clear student failure: it issued a refund on a non-returnable item.

- **Student** made **8 tool calls** including duplicate `get_order_details`, duplicate `check_resolution_policy`, **`calculate_resolution`, and `submit_resolution`** — meaning it actually *submitted a refund* on a sale-final, non-defective item. The final message is a content-free pleasantry that hides what just happened. This is the worst class of failure: a wrong action wrapped in a friendly tone.
- **FT** made 4 tool calls and **stopped after `calculate_resolution` returned ineligible**. It did **not** call `submit_resolution`. The final message politely accepts the denial and offers further help.

The student's failure mode here is **not honoring the eligibility result** — once `check_resolution_policy` and `calculate_resolution` say "ineligible / sale-final / no refund", the next correct action is to **stop and explain**, not to call `submit_resolution` anyway. The FT model learned the deny-path from the teacher.""",
    ),
    (
        "Out-of-scope request: refuse without invoking any tools",
        """This is the cleanest behavioral contrast in the demo set.

- **Student** called `check_inventory` — a **tool that is forbidden** for out-of-scope queries. The student treated "place a new order" as a legitimate task and reached for the inventory tool to start fulfilling it. It took 5 rounds of back-and-forth before stopping.
- **FT** made **zero tool calls** and answered in 3 rounds. It recognized the request as out of scope, politely declined to place an order, and redirected the customer to use the website while keeping the door open for any *existing*-order issues.

This is the hardest behavior to teach without examples: "do not act, do not look anything up, just refuse politely". It only comes from training data that includes refusal traces — which is why the cleaner in §7b **explicitly preserves** substantive-text/no-tool-call examples instead of filtering them out as "empty".""",
    ),
]


CSS = """
:root {
  --bg: #f7f9fc;
  --card: #ffffff;
  --border: #d9dde3;
  --text: #1f2937;
  --muted: #6b7280;
  --accent: #1f6feb;
  --good: #1f8b4c;
  --bad: #c0392b;
  --warn: #b45309;
  --code-bg: #f1f4f9;
  --student: #f5e6e0;
  --student-strong: #c0392b;
  --ft: #e0ecfa;
  --ft-strong: #1f6feb;
  --customer: #f3f4f6;
  --agent: #e8f2ec;
}
* { box-sizing: border-box; }
html { font-size: 18px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.55;
  margin: 0;
  padding: 0 0 80px 0;
}
.page-header {
  background: linear-gradient(180deg, #ffffff 0%, #eef2f7 100%);
  border-bottom: 1px solid var(--border);
  padding: 36px 48px 28px;
}
.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 2.2rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.page-header .subtitle {
  font-size: 1.15rem;
  color: var(--muted);
  max-width: 1100px;
}
.page-header .meta {
  margin-top: 18px;
  display: flex; flex-wrap: wrap; gap: 18px 36px;
  font-size: 0.95rem; color: var(--muted);
}
.page-header .meta strong { color: var(--text); }

main { max-width: 1280px; margin: 0 auto; padding: 32px 48px 0; }

.toc {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 24px;
  margin-bottom: 36px;
  font-size: 1.05rem;
}
.toc strong { display: block; margin-bottom: 8px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.85rem; }
.toc ol { margin: 0; padding-left: 22px; }
.toc li { margin: 4px 0; }
.toc a { color: var(--accent); text-decoration: none; }
.toc a:hover { text-decoration: underline; }

.demo {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 32px 36px;
  margin-bottom: 40px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.demo h2 {
  margin: 0 0 4px 0;
  font-size: 1.65rem;
  font-weight: 700;
  letter-spacing: -0.005em;
}
.demo .demo-sub {
  color: var(--muted);
  font-size: 1.0rem;
  margin-bottom: 22px;
}
.demo .demo-sub code { font-size: 0.95rem; }

.context {
  background: #fafbfd;
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  padding: 18px 22px;
  margin-bottom: 28px;
}
.context dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 18px; margin: 0; }
.context dt { font-weight: 600; color: var(--muted); font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.04em; padding-top: 3px; }
.context dd { margin: 0; font-size: 1.05rem; }
.context dd code { font-size: 0.95rem; }
.context .quote {
  font-style: italic;
  background: #fff;
  padding: 10px 14px;
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  color: #111827;
}

.comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 8px;
}
@media (max-width: 1100px) { .comparison { grid-template-columns: 1fr; } }
.side {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  background: #fcfdff;
}
.side.student { border-top: 5px solid var(--student-strong); background: linear-gradient(180deg, var(--student) 0%, #fff 16%); }
.side.ft      { border-top: 5px solid var(--ft-strong);      background: linear-gradient(180deg, var(--ft)      0%, #fff 16%); }
.side h3 {
  margin: 0 0 4px 0;
  font-size: 1.25rem;
  font-weight: 700;
}
.side .model { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.95rem; color: var(--muted); }
.side .stats { margin: 12px 0 16px 0; font-size: 0.98rem; color: var(--text); }
.side .stats span { display: inline-block; margin-right: 18px; }
.side .stats .kpi-bad  { color: var(--bad); font-weight: 600; }
.side .stats .kpi-good { color: var(--good); font-weight: 600; }

.tool-section { margin-bottom: 18px; }
.tool-section h4 {
  margin: 0 0 8px 0;
  font-size: 1.0rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}
.tool-list { list-style: none; padding: 0; margin: 0; counter-reset: tool; }
.tool-list li {
  counter-increment: tool;
  padding: 6px 8px 6px 38px;
  position: relative;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.95rem;
  background: var(--code-bg);
  border-radius: 4px;
  margin-bottom: 4px;
  word-break: break-word;
}
.tool-list li::before {
  content: counter(tool);
  position: absolute;
  left: 8px; top: 6px;
  display: inline-block;
  min-width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  background: var(--accent);
  color: #fff;
  border-radius: 50%;
  font-size: 0.8rem;
  font-family: -apple-system, sans-serif;
  font-weight: 600;
}
.tool-list .tool-name { font-weight: 600; color: var(--text); }
.tool-list .tool-args { color: var(--muted); }
.tool-empty { font-style: italic; color: var(--muted); padding: 8px 12px; background: var(--code-bg); border-radius: 4px; }

.transcript { margin-top: 14px; }
.transcript h4 {
  margin: 0 0 10px 0;
  font-size: 1.0rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}
.turn { margin-bottom: 12px; padding: 12px 14px; border-radius: 8px; font-size: 1.0rem; }
.turn.customer { background: var(--customer); border-left: 4px solid #9ca3af; }
.turn.agent    { background: var(--agent);    border-left: 4px solid var(--good); }
.turn .who { font-weight: 700; font-size: 0.95rem; margin-bottom: 4px; }
.turn .who.customer { color: #374151; }
.turn .who.agent    { color: var(--good); }
.turn .body { white-space: pre-wrap; word-wrap: break-word; }

.diagnosis {
  margin-top: 28px;
  padding: 22px 24px;
  background: #fffaf0;
  border: 1px solid #f3d8a6;
  border-left: 5px solid var(--warn);
  border-radius: 8px;
}
.diagnosis h3 {
  margin: 0 0 12px 0;
  font-size: 1.2rem;
  color: var(--warn);
}
.diagnosis p { margin: 0 0 12px 0; font-size: 1.05rem; }
.diagnosis ul { margin: 8px 0; padding-left: 24px; }
.diagnosis li { margin-bottom: 8px; font-size: 1.05rem; }
.diagnosis code { background: #fdecc8; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; }
.diagnosis em { color: #4b5563; }
.diagnosis strong { color: #1f2937; }

footer {
  text-align: center;
  margin-top: 60px;
  color: var(--muted);
  font-size: 0.9rem;
}
"""


def _esc(s) -> str:
    return html.escape("" if s is None else str(s))


def _md_inline(text: str) -> str:
    """Minimal markdown: **bold**, *italic*, `code`."""
    out = _esc(text)
    # code first so we don't bold inside it
    import re

    out = re.sub(r"`([^`]+?)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", out)
    return out


def _md_block(text: str) -> str:
    """Render hand-written diagnosis: paragraphs + '-' bullet lists."""
    lines = text.strip().splitlines()
    out: list[str] = []
    buf: list[str] = []
    in_list = False

    def flush_para():
        nonlocal buf
        if buf:
            out.append("<p>" + _md_inline(" ".join(buf).strip()) + "</p>")
            buf = []

    def flush_list_open():
        nonlocal in_list
        if not in_list:
            out.append("<ul>")
            in_list = True

    def flush_list_close():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        stripped = line.rstrip()
        if not stripped.strip():
            flush_para()
            flush_list_close()
            continue
        if stripped.lstrip().startswith("- "):
            flush_para()
            flush_list_open()
            item = stripped.lstrip()[2:]
            out.append("<li>" + _md_inline(item) + "</li>")
            continue
        # paragraph line
        flush_list_close()
        buf.append(stripped.strip())
    flush_para()
    flush_list_close()
    return "\n".join(out)


def _fmt_args(args) -> str:
    if isinstance(args, dict):
        if not args:
            return "{}"
        parts = []
        for k, v in args.items():
            if isinstance(v, (dict, list)):
                sv = json.dumps(v, default=str, ensure_ascii=False)
            else:
                sv = str(v)
            if len(sv) > 140:
                sv = sv[:140] + "…"
            parts.append(f"{k}={sv}")
        return ", ".join(parts)
    return str(args)


def _render_side(label: str, kind: str, model_name: str, side: dict) -> str:
    tool_calls = side.get("tool_calls") or []
    transcript = side.get("transcript") or []
    n_tools = len(tool_calls)
    rounds = side.get("rounds", 0)
    stop = side.get("stop_reason") or "—"

    # Tool list HTML.
    if tool_calls:
        tool_items = []
        for tc in tool_calls:
            name = _esc(tc.get("name"))
            args = _esc(_fmt_args(tc.get("arguments")))
            tool_items.append(
                f'<li><span class="tool-name">{name}</span>'
                f'<span class="tool-args">({args})</span></li>'
            )
        tools_html = '<ul class="tool-list">' + "".join(tool_items) + "</ul>"
    else:
        tools_html = '<div class="tool-empty">No tools called.</div>'

    # Transcript HTML.
    turn_html: list[str] = []
    for t in transcript:
        role = t.get("role", "")
        body = _esc(t.get("content") or "")
        is_cust = role == "customer"
        cls = "customer" if is_cust else "agent"
        who = "👤 Customer" if is_cust else "🤖 Agent"
        turn_html.append(
            f'<div class="turn {cls}">'
            f'<div class="who {cls}">{who}</div>'
            f'<div class="body">{body}</div>'
            f'</div>'
        )
    transcript_html = "".join(turn_html)

    return f"""
<div class="side {kind}">
  <h3>{_esc(label)}</h3>
  <div class="model">{_esc(model_name)}</div>
  <div class="stats">
    <span>Rounds: <strong>{rounds}</strong></span>
    <span>Tool calls: <strong>{n_tools}</strong></span>
    <span>Stop: <code>{_esc(stop)}</code></span>
  </div>
  <div class="tool-section">
    <h4>Tools called</h4>
    {tools_html}
  </div>
  <div class="transcript">
    <h4>Transcript</h4>
    {transcript_html}
  </div>
</div>
"""


def _render_context(demo: dict) -> str:
    sc = demo.get("scenario", {})
    exp_amt = sc.get("expected_amounts") or {}
    refund = exp_amt.get("total_refund")
    expected_tools = sc.get("expected_tools") or []
    tools_html = " → ".join(f"<code>{_esc(t)}</code>" for t in expected_tools) if expected_tools else "<em>(none)</em>"

    rows = [
        ("Customer opens with",
         f'<div class="quote">{_esc(sc.get("user_message", ""))}</div>'),
        ("Order", f"<code>{_esc(sc.get('order_id', '—'))}</code>"),
        ("Expected resolution", _esc(sc.get("expected_resolution_summary", "—"))),
    ]
    if refund is not None:
        rows.append(("Expected refund", f"<strong>${refund:.2f}</strong>"))
    rows.append(("Expected tools", tools_html))

    items = "\n".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in rows)
    return f'<div class="context"><dl>{items}</dl></div>'


def _render_demo(demo: dict, idx: int, models: dict, diagnosis_md: str) -> str:
    headline = _esc(demo.get("headline", ""))
    cat = _esc(demo.get("category", ""))
    student_html = _render_side(
        "Before fine-tuning (Student)", "student", models["student_model"], demo.get("student", {})
    )
    ft_html = _render_side(
        "After fine-tuning (FT)", "ft", models["ft_model"], demo.get("ft", {})
    )
    diag = _md_block(diagnosis_md) if diagnosis_md else ""
    return f"""
<section class="demo" id="demo-{idx}">
  <h2>Demo {idx}. {headline}</h2>
  <div class="demo-sub">Category: <code>{cat}</code> · Set: <code>{_esc(demo.get('set'))}</code> · Scenario: <code>{_esc(demo.get('scenario_id'))}</code></div>
  {_render_context(demo)}
  <div class="comparison">
    {student_html}
    {ft_html}
  </div>
  {f'<div class="diagnosis"><h3>Why the student failed and the FT model succeeded</h3>{diag}</div>' if diag else ''}
</section>
"""


def main() -> None:
    data = json.loads(DEMOS_PATH.read_text(encoding="utf-8"))
    models = {
        "student_model": data.get("student_model", "?"),
        "ft_model": data.get("ft_model", "?"),
    }
    demos = data.get("demos", [])

    toc_items = "\n".join(
        f'<li><a href="#demo-{i+1}">Demo {i+1}. {_esc(d.get("headline", ""))}</a></li>'
        for i, d in enumerate(demos)
    )

    demo_html = "\n".join(
        _render_demo(d, i + 1, models, DIAGNOSES[i][1] if i < len(DIAGNOSES) else "")
        for i, d in enumerate(demos)
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Agent Traces Distillation — Side-by-side Showcase</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
</head>
<body>
<header class="page-header">
  <h1>Side-by-side showcase: Student vs. Fine-tuned</h1>
  <div class="subtitle">
    Four representative scenarios where the FT model substantially outperformed
    the baseline student. Each scenario was run twice live — once against the
    deployed student endpoint and once against the deployed fine-tuned endpoint
    — using the same customer simulator and the same opening user message.
    Only the agent model differs.
  </div>
  <div class="meta">
    <div><strong>Student:</strong> <code>{_esc(models['student_model'])}</code></div>
    <div><strong>FT:</strong> <code>{_esc(models['ft_model'])}</code></div>
    <div><strong>Generated:</strong> {_esc(data.get('generated_at', '?'))}</div>
    <div><strong>Demos:</strong> {len(demos)}</div>
  </div>
</header>

<main>
  <nav class="toc">
    <strong>Contents</strong>
    <ol>
      {toc_items}
    </ol>
  </nav>
  {demo_html}
  <footer>
    Generated by <code>scripts/build_showcase_html.py</code> from
    <code>results/eval_result/demo_transcripts.json</code>.
  </footer>
</main>
</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}  ({os.path.getsize(OUT_PATH):,} bytes, {len(demos)} demos)")


if __name__ == "__main__":
    main()
