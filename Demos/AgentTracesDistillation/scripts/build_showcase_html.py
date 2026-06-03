"""Minimal animated side-by-side demo showcase.

Reads results/eval_result/demo_transcripts.json and writes a clean
demo_showcase.html where:
- Left card  = BEFORE (student).
- Right card = AFTER  (fine-tuned).
- Each card has its OWN play / reset button so they animate independently.
- Each message arrives with a small "think" delay so the conversation feels
  natural to watch.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS_PATH = REPO_ROOT / "results" / "eval_result" / "demo_transcripts.json"
OUT_PATH = REPO_ROOT / "results" / "eval_result" / "demo_showcase.html"


HEADLINES = [
    "Restocking-fee math",
    "Multi-item cart cancel",
    "Sale item, no defect — should deny",
    "Out-of-scope: place a new order",
]


CSS = """
:root {
  --bg: #f6f8fb;
  --card: #ffffff;
  --border: #e1e5ec;
  --text: #111827;
  --muted: #6b7280;
  --student: #c0392b;
  --student-soft: #fdecea;
  --ft: #1f6feb;
  --ft-soft: #e7f0fd;
  --customer: #eef1f5;
  --good: #1f8b4c;
  --good-soft: #e7f5ec;
  --warn: #b45309;
  --warn-soft: #fdf2dc;
  --bad: #c0392b;
  --bad-soft: #fbe9e7;
}
* { box-sizing: border-box; }
html { font-size: 17px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  margin: 0;
  padding: 0 0 60px 0;
}

header.page {
  padding: 28px 40px 18px;
  background: #fff;
  border-bottom: 1px solid var(--border);
}
header.page h1 {
  margin: 0;
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}
header.page .sub {
  margin-top: 4px;
  color: var(--muted);
  font-size: 0.95rem;
}

main { max-width: 1340px; margin: 0 auto; padding: 28px 32px 0; }

.demo {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 22px 26px 24px;
  margin-bottom: 28px;
}
.demo h2 {
  margin: 0 0 6px 0;
  font-size: 1.3rem;
  font-weight: 700;
}
.demo .opener {
  color: var(--muted);
  font-size: 0.98rem;
  margin-bottom: 18px;
  font-style: italic;
}
.demo .opener::before { content: '👤  '; font-style: normal; }

.compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 1000px) { .compare { grid-template-columns: 1fr; } }

.side {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.side-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}
.side.student .side-head { background: var(--student-soft); }
.side.ft      .side-head { background: var(--ft-soft); }

.side-title { font-weight: 700; font-size: 0.95rem; letter-spacing: 0.01em; }
.side.student .side-title { color: var(--student); }
.side.ft      .side-title { color: var(--ft); }
.side-title .tag {
  display: inline-block;
  margin-left: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}

.side-actions { display: flex; gap: 6px; }
.btn {
  border: 1px solid var(--border);
  background: #fff;
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
}
.btn:hover { background: #f3f5f8; }
.btn.play { color: #fff; }
.side.student .btn.play { background: var(--student); border-color: var(--student); }
.side.student .btn.play:hover { background: #a33122; }
.side.ft      .btn.play { background: var(--ft); border-color: var(--ft); }
.side.ft      .btn.play:hover { background: #155bc4; }

.chips {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  min-height: 38px;
  display: flex; flex-wrap: wrap; gap: 5px;
  background: #fcfdff;
}
.chip {
  display: inline-flex; align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.78rem;
  background: #fff;
  border: 1px solid var(--border);
  color: var(--text);
  opacity: 0;
  transform: translateY(-3px);
  transition: opacity 220ms ease, transform 220ms ease;
}
.chip.show { opacity: 1; transform: translateY(0); }
.chip.expected { border-color: var(--good); color: var(--good); background: var(--good-soft); }
.chip.forbidden { border-color: var(--bad);  color: var(--bad);  background: var(--bad-soft); font-weight: 700; }
.chip.extra    { border-color: var(--warn); color: var(--warn); background: var(--warn-soft); }
.chips .placeholder { color: #b1b6bf; font-style: italic; font-size: 0.85rem; }

.script {
  padding: 12px 14px;
  flex: 1;
  min-height: 240px;
  max-height: 520px;
  overflow-y: auto;
}

.turn {
  margin-bottom: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.95rem;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 220ms ease, transform 220ms ease;
}
.turn.show { opacity: 1; transform: translateY(0); }
.turn.customer { background: var(--customer); border-left: 3px solid #9ca3af; }
.side.student .turn.agent { background: var(--student-soft); border-left: 3px solid var(--student); }
.side.ft      .turn.agent { background: var(--ft-soft);      border-left: 3px solid var(--ft); }
.turn .who { font-weight: 700; font-size: 0.78rem; margin-bottom: 2px; color: var(--muted); }
.turn .body { white-space: pre-wrap; word-wrap: break-word; }

.typing {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 6px 12px;
  background: #f3f5f8;
  border-radius: 14px;
  font-size: 0.78rem;
  color: var(--muted);
  margin-bottom: 8px;
}
.typing .dot {
  width: 6px; height: 6px; background: #9ca3af; border-radius: 50%;
  animation: blink 1.1s infinite ease-in-out;
}
.typing .dot:nth-child(2) { animation-delay: 0.18s; }
.typing .dot:nth-child(3) { animation-delay: 0.36s; }
@keyframes blink {
  0%, 60%, 100% { opacity: 0.3; }
  30% { opacity: 1; }
}

footer {
  text-align: center;
  margin-top: 50px;
  color: var(--muted);
  font-size: 0.82rem;
}
"""


def _esc(s) -> str:
    return html.escape("" if s is None else str(s))


def _build_timeline(side: dict, expected: set, forbidden: set) -> list:
    transcript = side.get("transcript") or []
    tool_calls = side.get("tool_calls") or []
    agent_turn_count = sum(1 for t in transcript if t.get("role") != "customer") or 1
    per_agent = [0] * agent_turn_count
    n = len(tool_calls)
    base = n // agent_turn_count
    extra = n % agent_turn_count
    for i in range(agent_turn_count):
        per_agent[i] = base + (1 if i < extra else 0)
    events = []
    cursor = 0
    agent_seen = 0
    for t in transcript:
        role = t.get("role", "")
        if role == "customer":
            events.append({"type": "turn", "role": "customer", "body": t.get("content") or ""})
        else:
            take = per_agent[agent_seen] if agent_seen < len(per_agent) else 0
            for tc in tool_calls[cursor:cursor + take]:
                name = tc.get("name", "")
                kind = "expected" if name in expected else ("forbidden" if name in forbidden else "extra")
                events.append({"type": "tool", "name": name, "kind": kind})
            cursor += take
            agent_seen += 1
            events.append({"type": "turn", "role": "agent", "body": t.get("content") or ""})
    for tc in tool_calls[cursor:]:
        name = tc.get("name", "")
        kind = "expected" if name in expected else ("forbidden" if name in forbidden else "extra")
        events.append({"type": "tool", "name": name, "kind": kind})
    return events


def _render_side(label: str, model: str, kind: str, events: list) -> str:
    blob = json.dumps({"events": events}).replace("</", "<\\/")
    return f"""
<div class="side {kind}" data-side="{kind}">
  <div class="side-head">
    <div class="side-title">{_esc(label)}<span class="tag">{_esc(model)}</span></div>
    <div class="side-actions">
      <button class="btn play" data-action="play">▶ Play</button>
      <button class="btn" data-action="reset">↻</button>
    </div>
  </div>
  <div class="chips" data-chips><span class="placeholder">tools will appear here</span></div>
  <div class="script" data-script></div>
  <script type="application/json" class="events-data">{blob}</script>
</div>
"""


def _render_demo(demo: dict, idx: int, models: dict) -> str:
    sc = demo.get("scenario", {})
    expected = set(sc.get("expected_tools") or [])
    forbidden = set(sc.get("forbidden_tools") or [])
    s_events = _build_timeline(demo.get("student", {}), expected, forbidden)
    f_events = _build_timeline(demo.get("ft", {}), expected, forbidden)
    headline = HEADLINES[idx - 1] if idx - 1 < len(HEADLINES) else demo.get("headline", "")
    return f"""
<section class="demo" id="demo-{idx}">
  <h2>Demo {idx}. {_esc(headline)}</h2>
  <div class="opener">"{_esc(sc.get('user_message', ''))}"</div>
  <div class="compare">
    {_render_side("Before · Student", models['student_model'], "student", s_events)}
    {_render_side("After · Fine-tuned", models['ft_model'], "ft", f_events)}
  </div>
</section>
"""


JS = r"""
(function () {
  const CUSTOMER_THINK_MS = 800;
  const AGENT_THINK_MS    = 1400;
  const TOOL_GAP_MS       = 350;

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function setupSide(sideEl) {
    const dataNode = sideEl.querySelector('.events-data');
    let events;
    try {
      events = JSON.parse(dataNode.textContent).events;
    } catch (e) {
      console.error('events parse failed', e);
      return;
    }
    const chipsEl  = sideEl.querySelector('[data-chips]');
    const scriptEl = sideEl.querySelector('[data-script]');
    const playBtn  = sideEl.querySelector('[data-action="play"]');
    const resetBtn = sideEl.querySelector('[data-action="reset"]');

    let timers = [];
    let typingEl = null;
    let placeholderRemoved = false;
    let playing = false;

    function clearAll() {
      timers.forEach(t => clearTimeout(t));
      timers = [];
    }

    function reset() {
      clearAll();
      scriptEl.innerHTML = '';
      chipsEl.innerHTML = '<span class="placeholder">tools will appear here</span>';
      placeholderRemoved = false;
      typingEl = null;
      playing = false;
      playBtn.textContent = '▶ Play';
    }

    function showTyping(who) {
      removeTyping();
      const el = document.createElement('div');
      el.className = 'typing';
      el.innerHTML = '<span>' + who + ' typing</span><span class="dot"></span><span class="dot"></span><span class="dot"></span>';
      scriptEl.appendChild(el);
      scriptEl.scrollTop = scriptEl.scrollHeight;
      typingEl = el;
    }

    function removeTyping() {
      if (typingEl) { typingEl.remove(); typingEl = null; }
    }

    function addTurn(role, body) {
      removeTyping();
      const t = document.createElement('div');
      t.className = 'turn ' + role;
      const who = role === 'customer' ? '👤 Customer' : '🤖 Agent';
      t.innerHTML = '<div class="who">' + who + '</div><div class="body">' + escapeHtml(body) + '</div>';
      scriptEl.appendChild(t);
      requestAnimationFrame(() => t.classList.add('show'));
      scriptEl.scrollTop = scriptEl.scrollHeight;
    }

    function addChip(name, kind) {
      if (!placeholderRemoved) {
        const ph = chipsEl.querySelector('.placeholder');
        if (ph) ph.remove();
        placeholderRemoved = true;
      }
      const c = document.createElement('span');
      c.className = 'chip ' + kind;
      c.textContent = name;
      chipsEl.appendChild(c);
      requestAnimationFrame(() => c.classList.add('show'));
    }

    function play() {
      if (playing) return;
      reset();
      playing = true;
      playBtn.textContent = '⏵ Playing…';

      let t = 200;
      events.forEach(ev => {
        if (ev.type === 'turn') {
          const thinkMs = ev.role === 'customer' ? CUSTOMER_THINK_MS : AGENT_THINK_MS;
          const who = ev.role === 'customer' ? '👤 Customer' : '🤖 Agent';
          timers.push(setTimeout(() => showTyping(who), t));
          t += thinkMs;
          timers.push(setTimeout(() => addTurn(ev.role, ev.body), t));
          t += 200;
        } else if (ev.type === 'tool') {
          t += TOOL_GAP_MS;
          timers.push(setTimeout(() => addChip(ev.name, ev.kind), t));
        }
      });
      timers.push(setTimeout(() => {
        playing = false;
        playBtn.textContent = '▶ Play again';
      }, t + 300));
    }

    playBtn.addEventListener('click', play);
    resetBtn.addEventListener('click', reset);
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.side').forEach(setupSide);
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
    demo_html = "\n".join(_render_demo(d, i + 1, models) for i, d in enumerate(demos))

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Distillation showcase</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
</head>
<body>
<header class="page">
  <h1>Student → Fine-tuned · side-by-side</h1>
  <div class="sub">Left = before. Right = after. Same opener, same customer simulator. Press <strong>▶ Play</strong> on either card.</div>
</header>
<main>
  {demo_html}
  <footer>Generated from <code>results/eval_result/demo_transcripts.json</code> · <code>scripts/build_showcase_html.py</code></footer>
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
