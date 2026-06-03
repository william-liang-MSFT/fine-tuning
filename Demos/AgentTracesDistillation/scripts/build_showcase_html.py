"""Build a single-page HTML showcase with side-by-side animated playback.

Reads results/eval_result/demo_transcripts.json and emits a self-contained
light-theme demo_showcase.html optimized for live storytelling: minimal prose,
big visual contrast between Student (before) and FT (after), and synchronized
animated playback of each conversation with tool-call chips popping in as they
happen.

Usage:
    python scripts/build_showcase_html.py
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS_PATH = REPO_ROOT / "results" / "eval_result" / "demo_transcripts.json"
OUT_PATH = REPO_ROOT / "results" / "eval_result" / "demo_showcase.html"


# Per-demo compact pills (verdict + 2-3 short visual tags) used instead of a
# long diagnosis paragraph. Format: list of (tone, label) where tone ∈
# {"good", "bad", "warn", "info"}.
DEMO_TAGS: list[dict] = [
    {
        "headline": "Restocking-fee math",
        "subheadline": "Customer tries to dodge the 15% fee",
        "student_verdict": ("bad", "Submits wrong reason on the record"),
        "student_tags": [
            ("bad", "Reason = 'doesnt_fit' → submits as 'defect'"),
            ("warn", "Used customer email as order_id"),
            ("warn", "No fee in customer summary"),
        ],
        "ft_verdict": ("good", "Correct reason, itemised refund"),
        "ft_tags": [
            ("good", "Reason = 'buyers_remorse'"),
            ("good", "Gross / fee / net all quoted"),
            ("good", "No bogus tool calls"),
        ],
        "takeaway": "Net $ matched here, but the student records the wrong reason — on other passes that becomes a wrong $ too.",
    },
    {
        "headline": "Multi-item cart cancel",
        "subheadline": "Both items unshipped → full $164.98 refund",
        "student_verdict": ("bad", "Confirms cancel with no $ or ID"),
        "student_tags": [
            ("bad", "Skipped check_policy + calculate"),
            ("bad", "No amount, no confirmation ID"),
            ("warn", "Content-free pleasantry"),
        ],
        "ft_verdict": ("good", "$164.98 refund + confirmation ID"),
        "ft_tags": [
            ("good", "All 5 expected tools called"),
            ("good", "Per-item breakdown"),
            ("good", "Confirmation ID quoted"),
        ],
        "takeaway": "A resolution isn't finished until the customer hears the exact dollars and a reference number.",
    },
    {
        "headline": "Sale item, no defect → deny",
        "subheadline": "Performance complaint on a final-sale water bottle",
        "student_verdict": ("bad", "Submits refund on ineligible item"),
        "student_tags": [
            ("bad", "Called submit_resolution anyway"),
            ("warn", "Duplicate lookups (8 tools)"),
            ("warn", "Hides outcome in pleasantry"),
        ],
        "ft_verdict": ("good", "Stops, explains, no submission"),
        "ft_tags": [
            ("good", "Stopped after calculate said no"),
            ("good", "No submit_resolution"),
            ("good", "Clear polite denial"),
        ],
        "takeaway": "Once eligibility says 'no', the next correct action is to stop and explain.",
    },
    {
        "headline": "Out-of-scope: place a new order",
        "subheadline": "New orders are out of scope → refuse without tools",
        "student_verdict": ("bad", "Called a forbidden tool"),
        "student_tags": [
            ("bad", "Called check_inventory (forbidden)"),
            ("warn", "Treated request as a real task"),
            ("warn", "5 rounds to give up"),
        ],
        "ft_verdict": ("good", "Polite refusal, zero tools"),
        "ft_tags": [
            ("good", "Zero tool calls"),
            ("good", "Redirected to website"),
            ("good", "3 rounds total"),
        ],
        "takeaway": "Refusal-only traces in the SFT data teach the model to not act when it shouldn't act.",
    },
]


CSS = """
:root {
  --bg: #f5f7fb;
  --card: #ffffff;
  --border: #dde2ea;
  --text: #111827;
  --muted: #6b7280;
  --accent: #1f6feb;
  --good: #1f8b4c;
  --good-soft: #e7f5ec;
  --bad: #c0392b;
  --bad-soft: #fbe9e7;
  --warn: #b45309;
  --warn-soft: #fdf2dc;
  --info: #0c5aa6;
  --info-soft: #e2eefa;
  --student: #c0392b;
  --student-soft: #fff1ee;
  --student-bar: linear-gradient(135deg, #e57063 0%, #c0392b 100%);
  --ft: #1f6feb;
  --ft-soft: #eef4ff;
  --ft-bar: linear-gradient(135deg, #4c8ff0 0%, #1f6feb 100%);
  --customer: #eef0f4;
  --agent-student: #fbe9e7;
  --agent-ft: #eaf3fb;
}
* { box-sizing: border-box; }
html { font-size: 18px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  margin: 0;
  padding: 0 0 80px 0;
}
.page-header {
  background: #fff;
  border-bottom: 1px solid var(--border);
  padding: 28px 48px 22px;
}
.page-header h1 {
  margin: 0 0 6px 0;
  font-size: 2.0rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.page-header .subtitle {
  font-size: 1.05rem;
  color: var(--muted);
  max-width: 1100px;
}
.page-header .meta {
  margin-top: 16px;
  display: flex; flex-wrap: wrap; gap: 12px 28px;
  font-size: 0.95rem; color: var(--muted);
}
.page-header .meta strong { color: var(--text); }
.page-header .meta code { background: var(--info-soft); padding: 2px 8px; border-radius: 6px; color: var(--info); font-size: 0.92rem; }

main { max-width: 1400px; margin: 0 auto; padding: 28px 32px 0; }

.toc {
  display: flex; flex-wrap: wrap; gap: 10px;
  margin-bottom: 28px;
}
.toc a {
  background: #fff;
  border: 1px solid var(--border);
  padding: 8px 14px;
  border-radius: 999px;
  color: var(--text);
  text-decoration: none;
  font-size: 0.95rem;
}
.toc a:hover { background: var(--info-soft); border-color: var(--info); }

.demo {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 26px 30px 30px;
  margin-bottom: 36px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.demo-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 24px; flex-wrap: wrap;
  margin-bottom: 18px;
}
.demo-header h2 {
  margin: 0 0 2px 0;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.005em;
}
.demo-header .sub { color: var(--muted); font-size: 1.0rem; }

.controls { display: flex; gap: 8px; align-items: center; }
.controls button {
  cursor: pointer;
  border: 1px solid var(--border);
  background: #fff;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text);
  transition: background 80ms;
}
.controls button:hover { background: var(--info-soft); }
.controls button.play  { background: var(--accent); color: #fff; border-color: var(--accent); }
.controls button.play:hover { background: #155bc4; }
.controls .speed-label { font-size: 0.85rem; color: var(--muted); margin-right: 4px; }

.context {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
  background: #fafbfd;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 22px;
  font-size: 0.95rem;
}
.context .ctx-row { display: flex; flex-direction: column; gap: 2px; }
.context .ctx-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 600; }
.context .ctx-value { color: var(--text); }
.context .ctx-value code { background: var(--info-soft); padding: 1px 6px; border-radius: 4px; font-size: 0.9rem; color: var(--info); }
.context .opener {
  grid-column: 1 / -1;
  padding-top: 4px;
  border-top: 1px dashed var(--border);
  margin-top: 4px;
}
.context .opener .ctx-value {
  font-style: italic;
  color: #1f2937;
  font-size: 1.0rem;
}
@media (max-width: 900px) { .context { grid-template-columns: 1fr; } }

.comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
@media (max-width: 1100px) { .comparison { grid-template-columns: 1fr; } }

.side {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  display: flex; flex-direction: column;
}
.side .side-header {
  padding: 10px 16px;
  color: #fff;
  display: flex; align-items: center; justify-content: space-between;
}
.side.student .side-header { background: var(--student-bar); }
.side.ft      .side-header { background: var(--ft-bar); }
.side .side-header .label { font-weight: 700; font-size: 1.05rem; letter-spacing: 0.01em; }
.side .side-header .model { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; opacity: 0.92; }

.kpis {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border-bottom: 1px solid var(--border);
}
.kpi {
  text-align: center;
  padding: 10px 6px;
  border-right: 1px solid var(--border);
  background: #fcfdff;
}
.kpi:last-child { border-right: none; }
.kpi .num { font-size: 1.6rem; font-weight: 700; line-height: 1.0; }
.kpi .lbl { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-top: 2px; }
.kpi.tools .num { transition: color 200ms; }

.tool-chips {
  padding: 10px 14px;
  background: #fafbfd;
  border-bottom: 1px solid var(--border);
  min-height: 50px;
  display: flex; flex-wrap: wrap; gap: 6px;
  align-content: flex-start;
}
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.82rem;
  background: #fff;
  border: 1px solid var(--border);
  color: var(--text);
  opacity: 0;
  transform: translateY(-4px);
  transition: opacity 220ms ease, transform 220ms ease;
}
.chip.show { opacity: 1; transform: translateY(0); }
.chip.expected { border-color: var(--good); color: var(--good); background: var(--good-soft); }
.chip.forbidden { border-color: var(--bad);  color: var(--bad);  background: var(--bad-soft); font-weight: 700; }
.chip.extra    { border-color: var(--warn); color: var(--warn); background: var(--warn-soft); }
.chip .n { background: rgba(0,0,0,0.06); padding: 0 5px; border-radius: 999px; font-size: 0.72rem; }
.tool-chips .placeholder { color: var(--muted); font-style: italic; font-size: 0.9rem; }

.transcript {
  padding: 12px 14px;
  flex: 1;
  min-height: 260px;
  max-height: 520px;
  overflow-y: auto;
}
.turn {
  margin-bottom: 8px;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 0.97rem;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 260ms ease, transform 260ms ease;
}
.turn.show { opacity: 1; transform: translateY(0); }
.turn.customer { background: var(--customer); border-left: 3px solid #9ca3af; }
.side.student .turn.agent { background: var(--agent-student); border-left: 3px solid var(--student); }
.side.ft      .turn.agent { background: var(--agent-ft);      border-left: 3px solid var(--ft); }
.turn .who { font-weight: 700; font-size: 0.82rem; margin-bottom: 2px; }
.turn.customer .who { color: #4b5563; }
.side.student .turn.agent .who { color: var(--student); }
.side.ft      .turn.agent .who { color: var(--ft); }
.turn .body { white-space: pre-wrap; word-wrap: break-word; }

.verdict-row {
  margin-top: 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
@media (max-width: 1100px) { .verdict-row { grid-template-columns: 1fr; } }
.verdict {
  border-radius: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  background: #fff;
}
.verdict.student { background: var(--student-soft); border-color: #f1c8c1; }
.verdict.ft      { background: var(--ft-soft);      border-color: #c9d9f4; }
.verdict .vhead {
  display: flex; align-items: center; gap: 10px;
  font-size: 1.0rem; font-weight: 700;
  margin-bottom: 8px;
}
.verdict.student .vhead { color: var(--student); }
.verdict.ft      .vhead { color: var(--ft); }
.verdict .vhead .icon { font-size: 1.25rem; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 0.86rem;
  font-weight: 600;
  border: 1px solid transparent;
}
.tag.good { background: var(--good-soft); color: var(--good); border-color: #bfe5cc; }
.tag.bad  { background: var(--bad-soft);  color: var(--bad);  border-color: #f1c8c1; }
.tag.warn { background: var(--warn-soft); color: var(--warn); border-color: #f3d8a6; }
.tag.info { background: var(--info-soft); color: var(--info); border-color: #c9d9f4; }

.takeaway {
  margin-top: 14px;
  padding: 10px 14px;
  background: #fff8e8;
  border-left: 4px solid var(--warn);
  border-radius: 6px;
  font-size: 1.0rem;
  color: #4b3a05;
}

footer {
  text-align: center;
  margin-top: 60px;
  color: var(--muted);
  font-size: 0.85rem;
}
"""


def _esc(s) -> str:
    return html.escape("" if s is None else str(s))


def _fmt_args(args) -> str:
    if isinstance(args, dict):
        if not args:
            return ""
        parts = []
        for k, v in args.items():
            if isinstance(v, (dict, list)):
                sv = json.dumps(v, default=str, ensure_ascii=False)
            else:
                sv = str(v)
            if len(sv) > 60:
                sv = sv[:60] + "…"
            parts.append(f"{k}={sv}")
        s = ", ".join(parts)
        return f"({s})" if s else ""
    return str(args)


def _build_timeline(side: dict, expected_tools: set[str], forbidden_tools: set[str]):
    """Interleave transcript turns and the tool calls that happened between
    each pair of agent->customer messages. The exact correspondence isn't
    recorded, so attach all tool calls to the last preceding agent turn."""
    transcript = side.get("transcript") or []
    tool_calls = side.get("tool_calls") or []

    # Distribute tool calls evenly across agent turns (most common: bunched on
    # agent turn before each customer reply). Without per-turn metadata, we
    # release one batch per agent turn proportionally.
    agent_indices = [i for i, t in enumerate(transcript) if t.get("role") != "customer"]
    n_agents = max(1, len(agent_indices))
    n_tools = len(tool_calls)
    # Allocate tools to agent turns: front-load to earlier turns.
    per_turn: list[int] = [0] * n_agents
    if n_tools and n_agents:
        base = n_tools // n_agents
        extra = n_tools % n_agents
        for i in range(n_agents):
            per_turn[i] = base + (1 if i < extra else 0)
    # If there is only one agent turn but many tools, all attach to it.
    events: list[dict] = []
    cursor = 0
    agent_seen = 0
    for i, t in enumerate(transcript):
        role = t.get("role", "")
        events.append({
            "type": "turn",
            "role": "customer" if role == "customer" else "agent",
            "body": t.get("content") or "",
        })
        if role != "customer":
            take = per_turn[agent_seen] if agent_seen < len(per_turn) else 0
            for tc in tool_calls[cursor:cursor + take]:
                name = tc.get("name", "")
                kind = "expected" if name in expected_tools else (
                    "forbidden" if name in forbidden_tools else "extra"
                )
                events.append({
                    "type": "tool",
                    "name": name,
                    "args": _fmt_args(tc.get("arguments")),
                    "kind": kind,
                })
            cursor += take
            agent_seen += 1
    # Any leftover tools attach at the end.
    for tc in tool_calls[cursor:]:
        name = tc.get("name", "")
        kind = "expected" if name in expected_tools else (
            "forbidden" if name in forbidden_tools else "extra"
        )
        events.append({
            "type": "tool",
            "name": name,
            "args": _fmt_args(tc.get("arguments")),
            "kind": kind,
        })
    return events


def _render_side(label: str, kind: str, model_name: str, events: list[dict], n_rounds: int, n_tools: int, stop: str) -> str:
    return f"""
<div class="side {kind}" data-side="{kind}">
  <div class="side-header">
    <span class="label">{_esc(label)}</span>
    <span class="model">{_esc(model_name)}</span>
  </div>
  <div class="kpis">
    <div class="kpi rounds"><div class="num" data-num="rounds">0</div><div class="lbl">Rounds</div></div>
    <div class="kpi tools"><div class="num" data-num="tools">0</div><div class="lbl">Tool calls</div></div>
    <div class="kpi stop"><div class="num" data-num="stop">…</div><div class="lbl">Stop</div></div>
  </div>
  <div class="tool-chips" data-tool-chips><span class="placeholder">(tools appear as the agent calls them)</span></div>
  <div class="transcript" data-transcript></div>
  <script type="application/json" class="events-data">{_esc(json.dumps({"events": events, "rounds": n_rounds, "tools": n_tools, "stop": stop}))}</script>
</div>
"""


def _tag_html(tags: list[tuple[str, str]]) -> str:
    return "".join(f'<span class="tag {tone}">{_esc(label)}</span>' for tone, label in tags)


def _render_demo(demo: dict, idx: int, models: dict, meta: dict) -> str:
    sc = demo.get("scenario", {})
    expected_tools = sc.get("expected_tools") or []
    forbidden = sc.get("forbidden_tools") or []
    exp_amt = sc.get("expected_amounts") or {}
    refund = exp_amt.get("total_refund")

    expected_set = set(expected_tools)
    forbidden_set = set(forbidden)

    student_events = _build_timeline(demo.get("student", {}), expected_set, forbidden_set)
    ft_events = _build_timeline(demo.get("ft", {}), expected_set, forbidden_set)

    s = demo.get("student", {})
    f = demo.get("ft", {})

    expected_tool_chips = "".join(
        f'<span class="tag good">{_esc(t)}</span>' for t in expected_tools
    ) if expected_tools else '<span class="tag info">none expected (out-of-scope)</span>'
    forbidden_chips = "".join(
        f'<span class="tag bad">{_esc(t)}</span>' for t in forbidden
    )

    refund_html = f'<span class="ctx-value"><strong>${refund:.2f}</strong></span>' if refund is not None else '<span class="ctx-value">—</span>'

    student_verdict = meta["student_verdict"]
    ft_verdict = meta["ft_verdict"]

    return f"""
<section class="demo" id="demo-{idx}">
  <div class="demo-header">
    <div>
      <h2>Demo {idx}. {_esc(meta["headline"])}</h2>
      <div class="sub">{_esc(meta["subheadline"])}</div>
    </div>
    <div class="controls">
      <span class="speed-label">Speed</span>
      <button data-speed="1">1×</button>
      <button data-speed="2">2×</button>
      <button data-speed="4">4×</button>
      <button class="play" data-action="play">▶ Play</button>
      <button data-action="reset">↻ Reset</button>
    </div>
  </div>

  <div class="context">
    <div class="ctx-row"><div class="ctx-label">Order</div><div class="ctx-value"><code>{_esc(sc.get('order_id', '—'))}</code></div></div>
    <div class="ctx-row"><div class="ctx-label">Expected refund</div>{refund_html}</div>
    <div class="ctx-row"><div class="ctx-label">Expected tools</div><div class="ctx-value tag-row">{expected_tool_chips}{forbidden_chips and f'<span style="margin:0 4px;color:var(--muted);align-self:center;">·</span>'}{forbidden_chips}</div></div>
    <div class="ctx-row opener"><div class="ctx-label">Customer opens with</div><div class="ctx-value">"{_esc(sc.get('user_message', ''))}"</div></div>
  </div>

  <div class="comparison">
    {_render_side("Before fine-tuning · Student", "student", models["student_model"], student_events, s.get("rounds", 0), len(s.get("tool_calls") or []), s.get("stop_reason") or "—")}
    {_render_side("After fine-tuning · FT",       "ft",      models["ft_model"],      ft_events,      f.get("rounds", 0), len(f.get("tool_calls") or []), f.get("stop_reason") or "—")}
  </div>

  <div class="verdict-row">
    <div class="verdict student">
      <div class="vhead"><span class="icon">❌</span><span>{_esc(student_verdict[1])}</span></div>
      <div class="tag-row">{_tag_html(meta["student_tags"])}</div>
    </div>
    <div class="verdict ft">
      <div class="vhead"><span class="icon">✅</span><span>{_esc(ft_verdict[1])}</span></div>
      <div class="tag-row">{_tag_html(meta["ft_tags"])}</div>
    </div>
  </div>

  <div class="takeaway">💡 {_esc(meta["takeaway"])}</div>
</section>
"""


JS = r"""
(function () {
  const BASE_TURN_MS = 1500;   // base ms per customer/agent message
  const BASE_TOOL_MS = 250;    // base ms per tool chip

  function setupDemo(demoEl) {
    const sides = demoEl.querySelectorAll('.side');
    const sideStates = [];
    sides.forEach(side => {
      const dataNode = side.querySelector('.events-data');
      const data = JSON.parse(dataNode.textContent);
      sideStates.push({
        side: side,
        events: data.events,
        rounds: data.rounds,
        tools: data.tools,
        stop: data.stop,
        chipsEl: side.querySelector('[data-tool-chips]'),
        scriptEl: side.querySelector('[data-transcript]'),
        roundsNumEl: side.querySelector('[data-num="rounds"]'),
        toolsNumEl: side.querySelector('[data-num="tools"]'),
        stopNumEl: side.querySelector('[data-num="stop"]'),
        timers: [],
        roundsShown: 0,
        toolsShown: 0,
        running: false,
        done: false,
      });
    });

    let speed = 1;
    let playing = false;

    function clearTimers() {
      sideStates.forEach(st => {
        st.timers.forEach(t => clearTimeout(t));
        st.timers = [];
        st.running = false;
        st.done = false;
      });
    }

    function reset() {
      clearTimers();
      sideStates.forEach(st => {
        st.scriptEl.innerHTML = '';
        st.chipsEl.innerHTML = '<span class="placeholder">(tools appear as the agent calls them)</span>';
        st.roundsShown = 0;
        st.toolsShown = 0;
        st.roundsNumEl.textContent = '0';
        st.toolsNumEl.textContent = '0';
        st.stopNumEl.textContent = '…';
        st.stopNumEl.style.fontSize = '';
      });
      playing = false;
      playBtn.textContent = '▶ Play';
      playBtn.classList.add('play');
    }

    function scheduleSide(st) {
      st.running = true;
      let t = 0;
      // Strip placeholder once anything starts arriving.
      const turnMs = BASE_TURN_MS / speed;
      const toolMs = BASE_TOOL_MS / speed;
      let placeholderRemoved = false;
      st.events.forEach((ev, idx) => {
        if (ev.type === 'tool') {
          t += toolMs;
          st.timers.push(setTimeout(() => {
            if (!placeholderRemoved) {
              const ph = st.chipsEl.querySelector('.placeholder');
              if (ph) ph.remove();
              placeholderRemoved = true;
            }
            const chip = document.createElement('span');
            chip.className = 'chip ' + ev.kind;
            chip.innerHTML = '<span class="n">' + (st.toolsShown + 1) + '</span>' + escapeHtml(ev.name);
            st.chipsEl.appendChild(chip);
            // trigger transition
            requestAnimationFrame(() => chip.classList.add('show'));
            st.toolsShown += 1;
            st.toolsNumEl.textContent = String(st.toolsShown);
            // flash bad on forbidden
            if (ev.kind === 'forbidden') {
              st.toolsNumEl.style.color = 'var(--bad)';
            } else if (ev.kind === 'extra' && st.toolsNumEl.style.color !== 'var(--bad)') {
              st.toolsNumEl.style.color = 'var(--warn)';
            }
          }, t));
        } else {
          t += turnMs;
          st.timers.push(setTimeout(() => {
            const turn = document.createElement('div');
            turn.className = 'turn ' + ev.role;
            const who = ev.role === 'customer' ? '👤 Customer' : '🤖 Agent';
            turn.innerHTML = '<div class="who">' + who + '</div><div class="body">' + escapeHtml(ev.body) + '</div>';
            st.scriptEl.appendChild(turn);
            requestAnimationFrame(() => turn.classList.add('show'));
            st.scriptEl.scrollTop = st.scriptEl.scrollHeight;
            if (ev.role === 'customer') {
              st.roundsShown += 1;
              st.roundsNumEl.textContent = String(st.roundsShown);
            }
          }, t));
        }
      });
      // Final - set stop reason
      t += turnMs * 0.5;
      st.timers.push(setTimeout(() => {
        st.stopNumEl.textContent = st.stop;
        st.stopNumEl.style.fontSize = '0.95rem';
        st.done = true;
        if (sideStates.every(s => s.done)) {
          playing = false;
          playBtn.textContent = '▶ Play again';
        }
      }, t));
    }

    function play() {
      if (playing) return;
      reset();
      playing = true;
      playBtn.textContent = '⏸ Playing…';
      sideStates.forEach(scheduleSide);
    }

    function escapeHtml(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    const controls = demoEl.querySelector('.controls');
    const playBtn = controls.querySelector('[data-action="play"]');
    const resetBtn = controls.querySelector('[data-action="reset"]');
    const speedBtns = controls.querySelectorAll('[data-speed]');

    playBtn.addEventListener('click', play);
    resetBtn.addEventListener('click', reset);
    speedBtns.forEach(b => {
      b.addEventListener('click', () => {
        speed = parseFloat(b.getAttribute('data-speed'));
        speedBtns.forEach(x => x.classList.remove('play'));
        b.classList.add('play');
      });
    });

    // Default speed = 2x
    speed = 2;
    const def = controls.querySelector('[data-speed="2"]');
    if (def) def.classList.add('play');

    // Autoplay first demo when scrolled into view.
    if ('IntersectionObserver' in window) {
      let triggered = false;
      const io = new IntersectionObserver((entries) => {
        entries.forEach(e => {
          if (e.isIntersecting && !triggered && !playing) {
            triggered = true;
            play();
            io.disconnect();
          }
        });
      }, { threshold: 0.35 });
      io.observe(demoEl);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.demo').forEach(setupDemo);
  });
})();
"""


def main() -> None:
    data = json.loads(DEMOS_PATH.read_text(encoding="utf-8"))
    models = {
        "student_model": data.get("student_model", "?"),
        "ft_model": data.get("ft_model", "?"),
    }
    demos = data.get("demos", [])

    toc_items = "\n".join(
        f'<a href="#demo-{i+1}">{i+1}. {_esc(DEMO_TAGS[i]["headline"])}</a>'
        for i in range(len(demos))
    )

    demo_html = "\n".join(
        _render_demo(d, i + 1, models, DEMO_TAGS[i])
        for i, d in enumerate(demos)
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Distillation showcase — animated side-by-side</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
</head>
<body>
<header class="page-header">
  <h1>Student → Fine-tuned: animated side-by-side</h1>
  <div class="subtitle">
    Same opener, same customer simulator, different agent. Press <strong>▶ Play</strong>
    on any demo to watch both conversations unfold simultaneously, with tool calls
    popping in as the agent makes them.
  </div>
  <div class="meta">
    <div><strong>Student:</strong> <code>{_esc(models['student_model'])}</code></div>
    <div><strong>FT:</strong> <code>{_esc(models['ft_model'])}</code></div>
    <div><strong>Demos:</strong> {len(demos)}</div>
    <div><strong>Tool legend:</strong> <span class="tag good">expected</span> <span class="tag warn">extra / duplicate</span> <span class="tag bad">forbidden</span></div>
  </div>
</header>

<main>
  <nav class="toc">
    {toc_items}
  </nav>
  {demo_html}
  <footer>Generated by <code>scripts/build_showcase_html.py</code> from <code>results/eval_result/demo_transcripts.json</code>.</footer>
</main>

<script>{JS}</script>
</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}  ({os.path.getsize(OUT_PATH):,} bytes, {len(demos)} demos)")


if __name__ == "__main__":
    main()
