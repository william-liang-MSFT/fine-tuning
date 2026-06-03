"""Full-page, minimalistic, elegant demo replay.

One demo per viewport. Soft palette, generous whitespace, refined typography.
Each demo has Before (left) and After (right) panels with their own circular
play button. Navigate demos via top dots, arrow keys, or scroll.
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
  font-feature-settings: "ss01", "cv11";
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
.dots {
  display: flex; gap: 14px;
}
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

/* ── deck (snap container) ─────────────────────────────── */
.deck {
  height: 100vh;
  overflow-y: scroll;
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
}
.deck::-webkit-scrollbar { display: none; }

/* ── slide ─────────────────────────────────────────────── */
.slide {
  height: 100vh;
  min-height: 720px;
  scroll-snap-align: start;
  padding: 80px 56px 32px;
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 26px;
}

.intro { text-align: center; max-width: 980px; margin: 0 auto; }
.intro .eyebrow {
  font-size: 0.72rem;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 14px;
}
.intro h1 {
  font-family: "Cormorant Garamond", "EB Garamond", Georgia, "Times New Roman", serif;
  font-weight: 500;
  font-size: 2.6rem;
  line-height: 1.15;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.opener {
  text-align: center;
  max-width: 760px;
  margin: 0 auto;
  font-size: 1.05rem;
  line-height: 1.55;
  color: var(--ink-soft);
  font-style: italic;
  padding: 0 24px;
  position: relative;
}
.opener::before, .opener::after {
  font-family: Georgia, serif;
  color: var(--ink-mute);
  font-size: 1.6rem;
  line-height: 0;
  vertical-align: -0.3em;
}
.opener::before { content: '“ '; }
.opener::after  { content: ' ”'; }

/* ── compare grid ──────────────────────────────────────── */
.compare {
  display: grid;
  grid-template-columns: 1fr 1px 1fr;
  gap: 0;
  max-width: 1480px;
  width: 100%;
  margin: 0 auto;
  min-height: 0;
}
.divider { background: var(--rule); }

.side {
  display: grid;
  grid-template-rows: auto auto 1fr;
  min-height: 0;
  padding: 0 36px;
}

.side-head {
  display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 14px;
}
.side-label {
  display: flex; align-items: baseline; gap: 12px;
}
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
.iconbtn.play {
  width: 42px; height: 42px;
  font-size: 0.95rem;
}
.side.before .iconbtn.play { background: var(--before); border-color: var(--before); color: #fff; }
.side.before .iconbtn.play:hover { background: #8a3a2f; border-color: #8a3a2f; }
.side.after  .iconbtn.play { background: var(--after);  border-color: var(--after);  color: #fff; }
.side.after  .iconbtn.play:hover { background: #21498a; border-color: #21498a; }

.chips {
  min-height: 30px;
  display: flex; flex-wrap: wrap; gap: 6px;
  margin-bottom: 14px;
}
.chip {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.74rem;
  padding: 3px 10px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--rule);
  color: var(--ink-soft);
  opacity: 0;
  transform: translateY(-2px);
  transition: opacity 240ms ease, transform 240ms ease;
}
.chip.show { opacity: 1; transform: translateY(0); }
.chip.expected  { color: var(--good); border-color: var(--good); background: var(--good-soft); }
.chip.forbidden { color: var(--bad);  border-color: var(--bad);  background: var(--bad-soft); font-weight: 600; }
.chip.extra     { color: var(--warn); border-color: var(--warn); background: var(--warn-soft); }
.chips .ghost {
  font-style: italic;
  font-size: 0.78rem;
  color: var(--ink-mute);
  font-family: inherit;
  border: none;
  background: transparent;
  padding: 3px 0;
  opacity: 1;
  transform: none;
}

.script {
  overflow-y: auto;
  padding-right: 6px;
  min-height: 0;
}
.script::-webkit-scrollbar { width: 6px; }
.script::-webkit-scrollbar-thumb { background: var(--rule); border-radius: 3px; }

.turn {
  margin-bottom: 12px;
  font-size: 0.95rem;
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
.turn.customer .body { background: var(--customer); border-left-color: var(--ink-mute); }
.side.before .turn.agent .body { background: var(--before-soft); border-left-color: var(--before); }
.side.after  .turn.agent .body { background: var(--after-soft);  border-left-color: var(--after); }

.typing {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 12px;
  background: #fff;
  border: 1px solid var(--rule);
  border-radius: 14px;
  margin-bottom: 12px;
  font-size: 0.7rem;
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
.typing .dot:nth-child(2) { animation-delay: 0.18s; }
.typing .dot:nth-child(3) { animation-delay: 0.36s; }
@keyframes blink { 0%, 60%, 100% { opacity: 0.25; } 30% { opacity: 1; } }

/* ── arrow nav ─────────────────────────────────────────── */
.arrows {
  position: fixed;
  bottom: 24px; right: 32px;
  display: flex; gap: 8px;
  z-index: 50;
}
.arrows .iconbtn { background: #fff; }

/* hint */
.hint {
  position: fixed;
  bottom: 30px; left: 50%; transform: translateX(-50%);
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  z-index: 40;
  pointer-events: none;
}

@media (max-width: 980px) {
  .compare { grid-template-columns: 1fr; }
  .divider { display: none; }
  .side { padding: 0 8px; margin-bottom: 24px; }
  .slide { padding: 76px 20px 24px; }
  .intro h1 { font-size: 2rem; }
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
        <div class="side-label">
          <span class="kicker">{_esc(label)}</span>
          <span class="model">{_esc(model)}</span>
        </div>
        <div class="actions">
          <button class="iconbtn" data-action="reset" title="Reset">↻</button>
          <button class="iconbtn play" data-action="play" title="Play">▶</button>
        </div>
      </div>
      <div class="chips" data-chips><span class="chip ghost">tools appear as the agent calls them</span></div>
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
    return f"""
<section class="slide" id="slide-{idx}" data-slide="{idx}">
  <div class="intro">
    <div class="eyebrow">Demo {idx} of {total}</div>
    <h1>{_esc(headline)}</h1>
  </div>
  <div class="opener">{_esc(sc.get('user_message', ''))}</div>
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
  const TOOL_GAP_MS       = 350;

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function setupSide(sideEl) {
    const dataNode = sideEl.querySelector('.events-data');
    let events;
    try { events = JSON.parse(dataNode.textContent).events; }
    catch (e) { console.error('events parse failed', e); return; }

    const chipsEl  = sideEl.querySelector('[data-chips]');
    const scriptEl = sideEl.querySelector('[data-script]');
    const playBtn  = sideEl.querySelector('[data-action="play"]');
    const resetBtn = sideEl.querySelector('[data-action="reset"]');

    let timers = [];
    let typingEl = null;
    let placeholderRemoved = false;
    let playing = false;

    function clearAll() { timers.forEach(t => clearTimeout(t)); timers = []; }

    function reset() {
      clearAll();
      scriptEl.innerHTML = '';
      chipsEl.innerHTML = '<span class="chip ghost">tools appear as the agent calls them</span>';
      placeholderRemoved = false;
      typingEl = null;
      playing = false;
      playBtn.innerHTML = '▶';
    }

    function showTyping(who) {
      removeTyping();
      const el = document.createElement('div');
      el.className = 'typing';
      el.innerHTML = '<span>' + who + '</span><span class="dot"></span><span class="dot"></span><span class="dot"></span>';
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

    function addChip(name, kind) {
      if (!placeholderRemoved) {
        const ph = chipsEl.querySelector('.ghost');
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
      playBtn.innerHTML = '<span style="font-size:0.7rem;letter-spacing:0;">●</span>';

      let t = 200;
      events.forEach(ev => {
        if (ev.type === 'turn') {
          const thinkMs = ev.role === 'customer' ? CUSTOMER_THINK_MS : AGENT_THINK_MS;
          const who = ev.role === 'customer' ? 'Customer' : 'Agent';
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
          if (counter) {
            counter.textContent = String(idx + 1).padStart(2, '0') + ' / ' + String(total).padStart(2, '0');
          }
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
