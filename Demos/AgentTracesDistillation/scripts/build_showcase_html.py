"""Full-page, minimalistic, elegant demo replay.

One demo per viewport. Editorial typography, lots of whitespace.
Each demo shows the expected resolution at the top, then Before / After
panels with their own circular play button and inline tool blocks that
surface argument values (the key signal when an arg was wrong).
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
    "Out-of-scope request",
]


CSS = r"""
:root {
  --bg: #fafaf7;
  --ink: #1a1a1a;
  --ink-soft: #555;
  --ink-mute: #9a9a93;
  --rule: #e6e3da;
  --customer: #f1efe9;
  --before: #b14a3c;
  --before-soft: #f7eae6;
  --after: #2c5ea8;
  --after-soft: #e8eff8;
  --good: #4e7a4d;
  --good-soft: #ecf2eb;
  --warn: #a16207;
  --warn-soft: #f8efdc;
  --bad: #a83b2c;
  --bad-soft: #f5e3df;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--ink);
  font-weight: 400;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  overflow: hidden;
}

/* ── top bar ───────────────────────────────────────────── */
.topbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 56px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 32px;
  z-index: 50;
  background: rgba(250, 250, 247, 0.85);
  backdrop-filter: saturate(150%) blur(8px);
  -webkit-backdrop-filter: saturate(150%) blur(8px);
  border-bottom: 1px solid var(--rule);
}
.brand {
  font-size: 0.75rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-mute);
  font-weight: 500;
}
.dots { display: flex; gap: 14px; }
.dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: transparent;
  border: 1.5px solid var(--ink-mute);
  cursor: pointer;
  transition: all 200ms ease;
}
.dot:hover { border-color: var(--ink); }
.dot.active { background: var(--ink); border-color: var(--ink); transform: scale(1.15); }
.counter {
  font-variant-numeric: tabular-nums;
  font-size: 0.85rem;
  color: var(--ink-mute);
  letter-spacing: 0.04em;
  min-width: 48px;
  text-align: right;
}

/* ── deck ──────────────────────────────────────────────── */
.deck {
  height: 100vh;
  overflow-y: scroll;
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
}
.deck::-webkit-scrollbar { display: none; }

.slide {
  height: 100vh;
  min-height: 740px;
  scroll-snap-align: start;
  padding: 76px 56px 28px;
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 22px;
}

.intro { text-align: center; max-width: 980px; margin: 0 auto; }
.intro .eyebrow {
  font-size: 0.7rem;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 10px;
}
.intro h1 {
  font-family: "Cormorant Garamond", "EB Garamond", Georgia, "Times New Roman", serif;
  font-weight: 500;
  font-size: 2.4rem;
  line-height: 1.15;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.expected {
  max-width: 860px;
  margin: 0 auto;
  padding: 14px 20px;
  background: #fff;
  border: 1px solid var(--rule);
  border-radius: 6px;
  text-align: left;
  display: grid;
  grid-template-columns: max-content 1fr;
  column-gap: 18px;
  align-items: baseline;
}
.expected .label {
  font-size: 0.66rem;
  letter-spacing: 0.26em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-mute);
}
.expected .text {
  font-size: 1rem;
  line-height: 1.55;
  color: var(--ink);
}

/* ── compare grid ──────────────────────────────────────── */
.compare {
  display: grid;
  grid-template-columns: 1fr 1px 1fr;
  gap: 0;
  max-width: 1520px;
  width: 100%;
  margin: 0 auto;
  min-height: 0;
}
.divider { background: var(--rule); }

.side {
  display: grid;
  grid-template-rows: auto 1fr;
  min-height: 0;
  padding: 0 36px;
}

.side-head {
  display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 14px;
}
.side-label { display: flex; align-items: baseline; gap: 12px; }
.side-label .kicker {
  font-size: 0.7rem;
  letter-spacing: 0.26em;
  text-transform: uppercase;
  font-weight: 600;
}
.side.before .kicker { color: var(--before); }
.side.after  .kicker { color: var(--after); }
.side-label .model {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.78rem;
  color: var(--ink-mute);
}
.actions { display: flex; align-items: center; gap: 8px; }
.iconbtn {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: 1px solid var(--rule);
  background: #fff;
  color: var(--ink);
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 180ms ease;
}
.iconbtn:hover { background: var(--ink); color: #fff; border-color: var(--ink); }
.iconbtn.play { width: 42px; height: 42px; font-size: 0.95rem; }
.side.before .iconbtn.play { background: var(--before); border-color: var(--before); color: #fff; }
.side.before .iconbtn.play:hover { background: #8a3a2f; border-color: #8a3a2f; }
.side.after  .iconbtn.play { background: var(--after);  border-color: var(--after);  color: #fff; }
.side.after  .iconbtn.play:hover { background: #21498a; border-color: #21498a; }

/* ── transcript flow ───────────────────────────────────── */
.script {
  overflow-y: auto;
  padding-right: 6px;
  min-height: 0;
}
.script::-webkit-scrollbar { width: 6px; }
.script::-webkit-scrollbar-thumb { background: var(--rule); border-radius: 3px; }

.turn {
  margin-bottom: 12px;
  font-size: 0.94rem;
  line-height: 1.55;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 260ms ease, transform 260ms ease;
}
.turn.show { opacity: 1; transform: translateY(0); }
.turn .who {
  font-size: 0.66rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-mute);
  margin-bottom: 4px;
}
.turn .body {
  white-space: pre-wrap;
  word-wrap: break-word;
  color: var(--ink);
  padding: 10px 14px;
  border-radius: 6px;
  background: var(--customer);
  border-left: 2px solid var(--ink-mute);
  max-width: 95%;
}
.side.before .turn.agent .body { background: var(--before-soft); border-left-color: var(--before); }
.side.after  .turn.agent .body { background: var(--after-soft);  border-left-color: var(--after); }

/* inline tool call block (the key visual: name + arg values) */
.toolcall {
  margin: 4px 0 12px 0;
  padding: 9px 14px 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--good-soft);
  border: 1px solid var(--rule);
  border-left: 3px solid var(--good);
  border-radius: 5px;
  font-size: 0.82rem;
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 240ms ease, transform 240ms ease;
}
.toolcall.show { opacity: 1; transform: translateX(0); }
.toolcall .head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 5px;
}
.toolcall .glyph {
  font-family: inherit;
  font-size: 0.62rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 1px 7px;
  border-radius: 3px;
  color: var(--good);
  background: rgba(78,122,77,0.14);
  font-weight: 600;
}
.toolcall .name {
  color: var(--ink);
  font-weight: 600;
  font-size: 0.86rem;
}
.toolcall .args {
  display: grid;
  grid-template-columns: max-content 1fr;
  column-gap: 14px;
  row-gap: 3px;
  padding-left: 2px;
  font-size: 0.78rem;
  line-height: 1.45;
}
.toolcall .args .k { color: var(--ink-mute); }
.toolcall .args .v { color: var(--ink); word-break: break-word; white-space: pre-wrap; }
.toolcall.no-args .args { display: none; }
.toolcall .empty {
  font-style: italic;
  color: var(--ink-mute);
  font-size: 0.76rem;
  font-family: "Inter", sans-serif;
}

/* typing indicator */
.typing {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 12px;
  background: #fff;
  border: 1px solid var(--rule);
  border-radius: 14px;
  margin-bottom: 12px;
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-mute);
}
.typing .dot {
  width: 5px; height: 5px;
  background: var(--ink-mute);
  border-radius: 50%;
  animation: blink 1.2s infinite ease-in-out;
}
.typing .dot:nth-child(3) { animation-delay: 0.18s; }
.typing .dot:nth-child(4) { animation-delay: 0.36s; }
@keyframes blink { 0%, 60%, 100% { opacity: 0.25; } 30% { opacity: 1; } }

/* arrow nav */
.arrows {
  position: fixed;
  bottom: 24px; right: 32px;
  display: flex; gap: 8px;
  z-index: 50;
}
.arrows .iconbtn { background: #fff; }

@media (max-width: 980px) {
  .compare { grid-template-columns: 1fr; }
  .divider { display: none; }
  .side { padding: 0 8px; margin-bottom: 24px; }
  .slide { padding: 76px 20px 24px; height: auto; }
  .intro h1 { font-size: 1.9rem; }
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

    def _tool_event(tc):
        name = tc.get("name", "")
        kind = "expected" if name in expected else ("forbidden" if name in forbidden else "extra")
        return {"type": "tool", "name": name, "kind": kind, "args": tc.get("arguments") or {}}

    for t in transcript:
        role = t.get("role", "")
        if role == "customer":
            events.append({"type": "turn", "role": "customer", "body": t.get("content") or ""})
        else:
            take = per_agent[agent_seen] if agent_seen < len(per_agent) else 0
            for tc in tool_calls[cursor:cursor + take]:
                events.append(_tool_event(tc))
            cursor += take
            agent_seen += 1
            events.append({"type": "turn", "role": "agent", "body": t.get("content") or ""})
    for tc in tool_calls[cursor:]:
        events.append(_tool_event(tc))
    return events


def _render_side(label: str, model: str, kind: str, events: list) -> str:
    blob = json.dumps({"events": events}, ensure_ascii=False).replace("</", "<\\/")
    return f"""
    <div class="side {kind}" data-side="{kind}">
      <div class="side-head">
        <div class="side-label">
          <span class="kicker">{_esc(label)}</span>
          <span class="model">{_esc(model)}</span>
        </div>
        <div class="actions">
          <button class="iconbtn" data-action="reset" title="Reset">↻</button>
          <button class="iconbtn play" data-action="play" title="Play">▶</button>
        </div>
      </div>
      <div class="script" data-script></div>
      <script type="application/json" class="events-data">{blob}</script>
    </div>
"""


def _render_slide(demo: dict, idx: int, total: int, models: dict) -> str:
    sc = demo.get("scenario", {})
    expected = set(sc.get("expected_tools") or [])
    forbidden = set(sc.get("forbidden_tools") or [])
    s_events = _build_timeline(demo.get("student", {}), expected, forbidden)
    f_events = _build_timeline(demo.get("ft", {}), expected, forbidden)
    headline = HEADLINES[idx - 1] if idx - 1 < len(HEADLINES) else demo.get("headline", "")
    expected_text = sc.get("expected_resolution_summary", "") or ""
    return f"""
<section class="slide" id="slide-{idx}" data-slide="{idx}">
  <div class="intro">
    <div class="eyebrow">Demo {idx} of {total}</div>
    <h1>{_esc(headline)}</h1>
  </div>
  <div class="expected">
    <span class="label">Expected</span>
    <span class="text">{_esc(expected_text)}</span>
  </div>
  <div class="compare">
    {_render_side("Before", models['student_model'], "before", s_events)}
    <div class="divider"></div>
    {_render_side("After", models['ft_model'], "after", f_events)}
  </div>
</section>
"""


JS = r"""
(function () {
  const CUSTOMER_THINK_MS = 800;
  const AGENT_THINK_MS    = 1400;
  const TOOL_GAP_MS       = 450;

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fmtVal(v) {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    try { return JSON.stringify(v); } catch (e) { return String(v); }
  }

  function setupSide(sideEl) {
    const dataNode = sideEl.querySelector('.events-data');
    let events;
    try { events = JSON.parse(dataNode.textContent).events; }
    catch (e) { console.error('events parse failed', e); return; }

    const scriptEl = sideEl.querySelector('[data-script]');
    const playBtn  = sideEl.querySelector('[data-action="play"]');
    const resetBtn = sideEl.querySelector('[data-action="reset"]');

    let timers = [];
    let typingEl = null;
    let playing = false;

    function clearAll() { timers.forEach(t => clearTimeout(t)); timers = []; }

    function reset() {
      clearAll();
      scriptEl.innerHTML = '';
      typingEl = null;
      playing = false;
      playBtn.innerHTML = '▶';
    }

    function showTyping(who) {
      removeTyping();
      const el = document.createElement('div');
      el.className = 'typing';
      el.innerHTML = '<span>' + escapeHtml(who) + '</span><span class="dot"></span><span class="dot"></span><span class="dot"></span>';
      scriptEl.appendChild(el);
      scriptEl.scrollTop = scriptEl.scrollHeight;
      typingEl = el;
    }
    function removeTyping() { if (typingEl) { typingEl.remove(); typingEl = null; } }

    function addTurn(role, body) {
      removeTyping();
      const t = document.createElement('div');
      t.className = 'turn ' + role;
      const who = role === 'customer' ? 'Customer' : 'Agent';
      t.innerHTML = '<div class="who">' + who + '</div><div class="body">' + escapeHtml(body) + '</div>';
      scriptEl.appendChild(t);
      requestAnimationFrame(() => t.classList.add('show'));
      scriptEl.scrollTop = scriptEl.scrollHeight;
    }

    function addToolCall(name, args) {
      removeTyping();
      const tc = document.createElement('div');
      tc.className = 'toolcall';
      const keys = Object.keys(args || {});
      let argsHtml;
      if (keys.length === 0) {
        argsHtml = '<div class="args"><span class="empty">(no arguments)</span></div>';
        tc.classList.add('no-args');
      } else {
        argsHtml = '<div class="args">' + keys.map(k =>
          '<span class="k">' + escapeHtml(k) + '</span><span class="v">' + escapeHtml(fmtVal(args[k])) + '</span>'
        ).join('') + '</div>';
      }
      tc.innerHTML =
        '<div class="head">' +
          '<span class="glyph">Tool</span>' +
          '<span class="name">' + escapeHtml(name) + '</span>' +
        '</div>' +
        argsHtml;
      scriptEl.appendChild(tc);
      requestAnimationFrame(() => tc.classList.add('show'));
      scriptEl.scrollTop = scriptEl.scrollHeight;
    }

    function play() {
      if (playing) return;
      reset();
      playing = true;
      playBtn.innerHTML = '<span style="font-size:0.7rem;letter-spacing:0;">●</span>';

      let t = 200;
      events.forEach(ev => {
        if (ev.type === 'turn') {
          const thinkMs = ev.role === 'customer' ? CUSTOMER_THINK_MS : AGENT_THINK_MS;
          const who = ev.role === 'customer' ? 'Customer' : 'Agent';
          timers.push(setTimeout(() => showTyping(who), t));
          t += thinkMs;
          timers.push(setTimeout(() => addTurn(ev.role, ev.body), t));
          t += 220;
        } else if (ev.type === 'tool') {
          t += TOOL_GAP_MS;
          timers.push(setTimeout(() => addToolCall(ev.name, ev.args), t));
        }
      });
      timers.push(setTimeout(() => {
        playing = false;
        playBtn.innerHTML = '↻';
        setTimeout(() => { if (!playing) playBtn.innerHTML = '▶'; }, 1600);
      }, t + 300));
    }

    playBtn.addEventListener('click', play);
    resetBtn.addEventListener('click', reset);
  }

  function setupNav() {
    const deck = document.querySelector('.deck');
    const slides = Array.from(document.querySelectorAll('.slide'));
    const dots = Array.from(document.querySelectorAll('.dot'));
    const counter = document.querySelector('.counter');
    const total = slides.length;

    function go(i) {
      i = Math.max(0, Math.min(total - 1, i));
      slides[i].scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    dots.forEach((d, i) => d.addEventListener('click', () => go(i)));

    const io = new IntersectionObserver(entries => {
      entries.forEach(en => {
        if (en.isIntersecting && en.intersectionRatio > 0.55) {
          const idx = parseInt(en.target.dataset.slide, 10) - 1;
          dots.forEach((d, i) => d.classList.toggle('active', i === idx));
          if (counter) counter.textContent = String(idx + 1).padStart(2, '0') + ' / ' + String(total).padStart(2, '0');
        }
      });
    }, { root: deck, threshold: [0.55] });
    slides.forEach(s => io.observe(s));

    document.addEventListener('keydown', e => {
      const cur = dots.findIndex(d => d.classList.contains('active'));
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
        e.preventDefault(); go(cur + 1);
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault(); go(cur - 1);
      } else if (e.key === 'Home') { e.preventDefault(); go(0); }
      else if (e.key === 'End') { e.preventDefault(); go(total - 1); }
    });

    const prev = document.querySelector('[data-nav="prev"]');
    const next = document.querySelector('[data-nav="next"]');
    if (prev) prev.addEventListener('click', () => {
      const cur = dots.findIndex(d => d.classList.contains('active'));
      go(cur - 1);
    });
    if (next) next.addEventListener('click', () => {
      const cur = dots.findIndex(d => d.classList.contains('active'));
      go(cur + 1);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.side').forEach(setupSide);
    setupNav();
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
    total = len(demos)
    slides_html = "\n".join(_render_slide(d, i + 1, total, models) for i, d in enumerate(demos))
    dots_html = "\n".join(
        f'<button class="dot{" active" if i == 0 else ""}" data-i="{i}" aria-label="Demo {i+1}"></button>'
        for i in range(total)
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Distillation · before & after</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=Inter:wght@400;500;600&display=swap">
<style>{CSS}</style>
</head>
<body>
<div class="topbar">
  <div class="brand">Distillation · Before / After</div>
  <div class="dots">{dots_html}</div>
  <div class="counter">01 / {total:02d}</div>
</div>
<div class="deck">
  {slides_html}
</div>
<div class="arrows">
  <button class="iconbtn" data-nav="prev" title="Previous (↑)">↑</button>
  <button class="iconbtn" data-nav="next" title="Next (↓)">↓</button>
</div>
<script>{JS}</script>
</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}  ({os.path.getsize(OUT_PATH):,} bytes, {total} demos)")


if __name__ == "__main__":
    main()
