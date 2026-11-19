"""The home page at /, drawn from the real research results (never hand-written numbers).

Sections: a live scope with the latest run's readings, how it decides (eight steps), the Evidence Map as a
grid of readings you can inspect, the accounts in big type, the guardrails, and a form to point it at a company.
"""

from __future__ import annotations

import json
import math

from export_site import E, GATE_LABEL, GATE_TONE
from src import site_chrome

SHORT = {"certifications": "Left to certify", "competitor_vendor": "No rival platform", "saas": "SaaS",
         "growth_stage": "Series A to C", "audit_intent": "Audit intent", "clients": "50+ clients",
         "industry": "Regulated", "cloud": "Cloud stack", "cloud_stack": "Cloud stack"}

STEPS = [
    ("Read", "It reads the company's own pages (home, pricing, security, trust, careers, customers) within a fixed page budget, plus recent news through a search API."),
    ("Gate", "The Evidence Map runs first: two rule out checks (already certified, or a rival compliance platform behind the trust centre), then three core questions."),
    ("Score", "Fit and timing are scored separately, and every point carries the line it came from."),
    ("Find the person", "A decision maker is chosen only when the title is confirmed on the company's own site."),
    ("Match the pain", "The evidence is matched to one problem Sprinto solves, never a generic one."),
    ("Draft", "A short email that opens with a real, cited fact about the company."),
    ("Review", "A person signs off, edits or declines. Repeated edits become lessons for later drafts."),
    ("Send", "Only ever to the operator's own test inbox. Prospects are never contacted."),
]

GUARDRAILS = [
    ("Prospects are never contacted", "Every send is forced to the operator's own test inbox, and sending is off by default."),
    ("Unknown stays unknown", "If a page does not say it, the answer is unknown and a person decides. Nothing is guessed."),
    ("Rival platforms rule out", "A trust centre run on Vanta, Drata or Secureframe is read from the page source and ends the account."),
    ("Only forward looking intent counts", "A certificate already held or a DPA on offer is not a buying signal. An audit in progress or a fresh security hire is."),
    ("A person signs off every email", "Drafts wait on the draft desk until someone approves them."),
    ("No secrets in logs or code", "Keys live in the environment, never in the source or the output files."),
]


def _quote(ev: str) -> tuple[str, str]:
    """Evidence is stored as '"quote" — url'. Split it for display."""
    ev = str(ev)
    if " — " in ev:
        q, url = ev.rsplit(" — ", 1)
    else:
        q, url = ev, ""
    return q.strip().strip('"').strip("“”"), url.strip()


def _deciding(q) -> dict | None:
    m = q.evidence_map
    for test in (lambda a: a.get("short_circuit_hit"), lambda a: a.get("core") and a["answer"] == "no",
                 lambda a: a.get("core") and a["answer"] == "unknown", lambda a: a.get("evidence")):
        hit = next((a for a in m if test(a)), None)
        if hit:
            return hit
    return m[0] if m else None


def _wave(n: int = 2) -> str:
    """A pulse train for the scope: calm baseline with sharp readings, repeated so it can scroll forever."""
    pts, x = [], 0.0
    for _ in range(n):
        for i in range(24):
            y = 60 + 6 * math.sin(i * 0.9)
            pts.append((x, y)); x += 10
            if i in (5, 13, 19):
                for dy in (-38, 30, -14):
                    pts.append((x, 60 + dy)); x += 6
    return " ".join(f"{px:.0f},{py:.0f}" for px, py in pts), x


def render(runs: list, history: list) -> str:
    scored = [r for r in runs if r.qualification]
    gate = [r.qualification.gate_decision for r in scored]
    n_q = sum(g in ("QUALIFY", "QUALIFY_AND_FLAG") for g in gate)
    n_n = gate.count("NURTURE")
    n_d = gate.count("DROP")
    last = history[-1] if history else None
    stamp = f"Run {last['run']}, {last['at'][:10]}" if last else "No runs yet"
    pts, width = _wave()

    # ---- the Evidence Map grid
    keys = []
    for r in scored:
        for a in r.qualification.evidence_map:
            if a["key"] not in keys:
                keys.append(a["key"])
    head = "".join(f'<th scope="col"><span>{E(SHORT.get(k, k))}</span></th>' for k in keys)
    rows, first = [], None
    for r in scored:
        q = r.qualification
        by = {a["key"]: a for a in q.evidence_map}
        cells = []
        for k in keys:
            a = by.get(k)
            if not a:
                cells.append("<td></td>"); continue
            quote, src = _quote(a["evidence"][0]) if a.get("evidence") else ("", "")
            data = {"company": r.company, "q": a["question"], "ans": a["answer"], "basis": a.get("basis") or "", "quote": quote, "src": src}
            if first is None and a.get("short_circuit_hit"):
                first = data
            label = f'{r.company}, {a["question"]}: {a["answer"]}'
            cells.append(f'<td><button type="button" class="cell a-{E(a["answer"])}" aria-label="{E(label)}" '
                         f'data-read="{E(json.dumps(data))}"><i></i></button></td>')
        tone = GATE_TONE.get(q.gate_decision, "flag")
        rows.append(f'<tr><th scope="row">{E(r.company)}</th>{"".join(cells)}'
                    f'<td class="dec"><span class="tag t-{tone}">{E(GATE_LABEL.get(q.gate_decision, q.gate_decision))}</span></td></tr>')

    # ---- the accounts, in big type
    acc = []
    for i, r in enumerate(scored, 1):
        q = r.qualification
        d = _deciding(q)
        line = d.get("basis") if d else ""
        tone = GATE_TONE.get(q.gate_decision, "flag")
        acc.append(f'<li><a href="/companies/{E(r.slug)}"><span class="idx">{i:02d}</span><span class="nm">{E(r.company)}</span>'
                   f'<span class="tag t-{tone}">{E(GATE_LABEL.get(q.gate_decision, q.gate_decision))}</span>'
                   f'<span class="why">{E(line)}</span></a></li>')

    steps = "".join(f'<li><span class="idx">{i:02d}</span><div><h3>{E(t)}</h3><p>{E(d)}</p></div></li>' for i, (t, d) in enumerate(STEPS, 1))
    rails = "".join(f'<li><span class="idx">{i:02d}</span><h3>{E(t)}</h3><p>{E(d)}</p></li>' for i, (t, d) in enumerate(GUARDRAILS, 1))

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signal Engine: evidence, not guesses</title>
<meta name="description" content="Prospect research for Sprinto. It reads a SaaS company's own pages, answers a written Evidence Map and drafts an email only when quotes back the decision.">
<meta name="theme-color" content="#0c0d0c">
{site_chrome.HEAD}
<style>{CSS}</style></head><body>
<a class="skip" href="#main">Skip to content</a>
{site_chrome.sitebar("home")}
<main id="main">

<section class="hero">
  <div class="wrap">
    <h1>Evidence,<br>not guesses<span class="cursor" aria-hidden="true"></span></h1>
    <p class="lede">Signal Engine reads a SaaS company's own pages, answers a written Evidence Map, and drafts an email only when quotes back the decision. Everything else goes to a person.</p>
    <div class="ctas"><a class="btn solid" href="/dashboard">See the results</a><a class="btn line" href="#map">Inspect the readings</a></div>
    <p class="note"><span class="dot"></span>Prospect research for Sprinto · case study build</p>
  </div>
  <div class="wrap">
    <div class="scope" role="img" aria-label="Latest run: {len(runs)} accounts read, {n_q} qualified, {n_n} to nurture, {n_d} dropped">
      <div class="scope-top"><span>CH1 · Evidence signal</span><span>{E(stamp)}</span></div>
      <div class="trace"><svg viewBox="0 0 {width:.0f} 120" preserveAspectRatio="none" aria-hidden="true">
        <polyline points="{pts}"/></svg><svg viewBox="0 0 {width:.0f} 120" preserveAspectRatio="none" aria-hidden="true"><polyline points="{pts}"/></svg></div>
      <div class="readouts">
        <div><span>Accounts read</span><b>{len(runs):02d}</b></div>
        <div class="hot"><span>Qualified</span><b>{n_q:02d}</b></div>
        <div><span>Nurture</span><b>{n_n:02d}</b></div>
        <div><span>Ruled out</span><b>{n_d:02d}</b></div>
      </div>
    </div>
  </div>
</section>

<section class="sec" id="how"><span class="ch" aria-hidden="true">CH 01 · How it decides</span>
  <div class="wrap split">
    <div class="sticky">
      <h2>Eight steps.<br><em>One gate.</em></h2>
      <p class="muted">The gate runs before any scoring, so a company that already holds every certificate never reaches a draft.</p></div>
    <ol class="steps">{steps}</ol>
  </div>
</section>

<section class="sec alt" id="map"><span class="ch" aria-hidden="true">CH 02 · The Evidence Map</span>
  <div class="wrap">
    <div class="sec-head">
      <h2>Every answer is a <em>reading.</em></h2>
      <p class="muted">Pick any square to see the line on the company's own site it rests on. Filled is yes, hollow is no, dotted is unknown.</p></div>
    <div class="board">
      <div class="grid-wrap"><table class="grid"><thead><tr><th scope="col"><span>Account</span></th>{head}<th scope="col"><span>Decision</span></th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table></div>
      <aside class="readout" aria-live="polite" data-first="{E(json.dumps(first)) if first else ''}">
        <p class="r-label">Reading</p><p class="r-co">Pick a square</p><p class="r-q"></p>
        <blockquote class="r-quote"></blockquote><p class="r-basis"></p><p class="r-src"></p>
      </aside>
    </div>
  </div>
</section>

<section class="sec" id="accounts"><span class="ch" aria-hidden="true">CH 03 · The accounts</span>
  <div class="wrap">
    <div class="sec-head row"><div>
      <h2>{len(runs)} read. <em>{n_q} worth a conversation now.</em></h2></div>
      <a class="btn line" href="/companies">Open every account</a></div>
    <ol class="accounts">{"".join(acc)}</ol>
  </div>
</section>

<section class="sec alt" id="guardrails"><span class="ch" aria-hidden="true">CH 04 · Guardrails</span>
  <div class="wrap">
    <div class="sec-head"><h2>Built to say <em>no.</em></h2></div>
    <ol class="rails">{rails}</ol>
  </div>
</section>

<section class="close">
  <div class="wrap">
    <h2>Point it at a company.</h2>
    <form class="probe" action="/run" method="get" role="search">
      <label for="probe-d">Company website</label>
      <div><input id="probe-d" name="domain" placeholder="acme.com" autocomplete="off" inputmode="url" required>
      <button class="btn dark" type="submit">Research it</button></div>
      <p>Opens the research form with the site filled in. The public sandbox saves nothing and sends nothing.</p>
    </form>
  </div>
</section>
</main>
<footer class="foot"><div class="wrap"><span>Signal Engine · Case study build, not affiliated with Sprinto.</span>
<span><a href="/dashboard">Results</a><a href="/app">Control panel</a><a href="{site_chrome.REPO}">Source code</a></span></div></footer>
<script>{JS}</script>
</body></html>"""


CSS = r"""
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit}img,svg{display:block}
.skip{position:absolute;left:-999px;top:8px;z-index:99;background:var(--accent);color:var(--accent-ink);padding:8px 12px;border-radius:8px}.skip:focus{left:16px}
.wrap{max-width:1328px;margin:0 auto;padding:0 24px}
.eyebrow{font:500 12.5px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 18px;display:flex;align-items:center;gap:10px}
.dot{width:8px;height:8px;border-radius:2px;background:var(--accent);flex:none}
.muted{color:var(--muted)}
h2{font-size:clamp(36px,5.4vw,76px);line-height:.98;margin:0 0 18px}
h3{font-size:18px;margin:0 0 6px;font-weight:650;font-stretch:110%}
.btn{display:inline-flex;align-items:center;gap:8px;height:48px;padding:0 22px;border-radius:12px;font-weight:700;font-size:15px;text-decoration:none;
  border:1px solid transparent;cursor:pointer;transition:transform .15s,background .15s,border-color .15s}
.btn:hover{transform:translateY(-2px)}.btn:active{transform:translateY(0) scale(.98)}
.btn.solid{background:var(--accent);color:var(--accent-ink)}.btn.line{border-color:var(--line);color:var(--ink)}.btn.line:hover{border-color:var(--ink)}
.btn.dark{background:var(--accent-ink);color:var(--accent);font:700 15px var(--sans)}
.tag{display:inline-flex;align-items:center;gap:6px;font:600 11.5px var(--mono);text-transform:uppercase;letter-spacing:.06em;padding:5px 9px;border-radius:6px;white-space:nowrap}
.tag::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.t-go{background:var(--go-bg);color:var(--go)}.t-flag{background:var(--flag-bg);color:var(--flag)}.t-hold{background:var(--hold-bg);color:var(--hold)}.t-stop{background:var(--stop-bg);color:var(--stop)}

/* hero */
.hero{padding:clamp(48px,9vh,110px) 0 56px;min-height:calc(100svh - 60px);display:flex;flex-direction:column;justify-content:center;gap:48px}
.hero h1{font-size:clamp(52px,9vw,140px);margin:0 0 24px}
.cursor{display:inline-block;width:.42em;height:.78em;background:var(--accent);margin-left:.08em;vertical-align:-.04em;animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.lede{font-size:clamp(17px,1.5vw,20px);max-width:56ch;color:var(--muted);margin:0 0 30px}
.hero>.wrap{width:100%}
.ctas{display:flex;gap:12px;flex-wrap:wrap}
.scope{border:1px solid var(--line);border-radius:18px;background:var(--surface);overflow:hidden}
.scope-top{display:flex;justify-content:space-between;gap:12px;padding:12px 18px;border-bottom:1px solid var(--line);font:500 12px var(--mono);
  text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.trace{position:relative;height:120px;display:flex;overflow:hidden;
  background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:40px 30px;background-position:-1px -1px}
.trace svg{flex:none;width:100%;height:100%;animation:scan 9s linear infinite}
.trace polyline{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke;stroke-linejoin:round;filter:drop-shadow(0 0 6px var(--accent))}
@keyframes scan{to{transform:translateX(-100%)}}
.readouts{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--line)}
.readouts div{padding:16px 18px;border-left:1px solid var(--line)}.readouts div:first-child{border-left:0}
.readouts span{display:block;font:500 11.5px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.readouts b{display:block;font:500 clamp(30px,4vw,48px)/1.1 var(--mono);margin-top:6px}
.readouts .hot b{color:var(--accent-text)}

/* sections */
.sec{position:relative;padding:clamp(72px,12vh,140px) 0;border-top:1px solid var(--line)}
.ch{position:absolute;top:-10px;right:max(24px,calc((100vw - 1328px)/2 + 24px));background:var(--bg);padding:0 10px;
  font:500 11.5px/20px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.sec.alt .ch{background:var(--bg)}
.ch::before{content:"";display:inline-block;width:7px;height:7px;border-radius:2px;background:var(--accent);margin-right:8px;vertical-align:0}
.note{display:flex;align-items:center;gap:10px;margin:22px 0 0;font:500 12.5px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.sec.alt{background:var(--surface)}
.sec-head{margin-bottom:44px;max-width:860px}.sec-head.row{max-width:none;display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap}
.split{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:clamp(32px,6vw,96px)}
.sticky{position:sticky;top:100px;align-self:start}.sticky p.muted{max-width:40ch}
.steps{list-style:none;margin:0;padding:0}
.steps li{display:grid;grid-template-columns:56px 1fr;gap:16px;padding:26px 0;border-top:1px solid var(--line)}.steps li:last-child{border-bottom:1px solid var(--line)}
.steps p{margin:0;color:var(--muted);max-width:60ch}
.idx{font:500 13px var(--mono);color:var(--accent-text);padding-top:3px}

/* evidence map board */
.board{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px;align-items:start}
.grid-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:16px;background:var(--bg)}
.grid{border-collapse:collapse;width:100%;min-width:760px}
.grid th,.grid td{padding:0;border-bottom:1px solid var(--line);text-align:center}
.grid tbody tr:last-child>*{border-bottom:0}
.grid thead th{font:500 11px var(--mono);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding:14px 6px;vertical-align:bottom;line-height:1.3}
.grid thead th:first-child,.grid tbody th{text-align:left;padding-left:18px}
.grid tbody th{font-weight:650;font-stretch:112%;font-size:15px;padding-right:12px;white-space:nowrap}
.grid td.dec{padding:0 14px;text-align:right}
.cell{width:100%;height:54px;display:grid;place-items:center;background:none;border:0;cursor:pointer;color:var(--ink)}
.cell i{width:18px;height:18px;border-radius:5px;display:block;transition:transform .15s}
.cell:hover i,.cell[aria-pressed="true"] i{transform:scale(1.25)}
.cell[aria-pressed="true"]{background:var(--surface-2)}
.a-yes i{background:var(--go)}.a-no i{border:2px solid var(--stop)}.a-unknown i{border:2px dotted var(--muted)}
.readout{position:sticky;top:84px;border:1px solid var(--line);border-radius:16px;background:var(--bg);padding:20px;min-height:280px}
.r-label{font:500 11.5px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 12px}
.r-co{font-size:22px;font-weight:700;font-stretch:118%;margin:0}.r-q{color:var(--muted);margin:4px 0 14px;font-size:14.5px}
.r-quote{margin:0 0 14px;padding:12px 14px;border-left:3px solid var(--accent);background:var(--surface);font:15px/1.55 var(--mono);border-radius:0 8px 8px 0}
.r-quote:empty{display:none}.r-basis{margin:0 0 10px;font-size:14.5px}.r-src{margin:0;font:12px var(--mono);color:var(--muted);word-break:break-all}
.r-src a{color:var(--accent-text)}

/* accounts */
.accounts{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.accounts a{display:grid;grid-template-columns:56px minmax(0,auto) auto 1fr;align-items:center;gap:8px 22px;padding:24px 0;border-bottom:1px solid var(--line);text-decoration:none}
.accounts .nm{font-family:var(--display);font-weight:var(--dw);font-stretch:var(--ds);letter-spacing:var(--dt);text-transform:var(--dc);
  font-size:clamp(34px,5.6vw,80px);line-height:1;transition:color .2s}
.accounts .why{color:var(--muted);font-size:14.5px;max-width:52ch;justify-self:end;text-align:right}
.accounts a:hover .nm{color:var(--accent-text)}

/* guardrails */
.rails{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.rails li{background:var(--surface);padding:28px 24px 30px}.rails .idx{display:block;margin-bottom:22px}.rails p{margin:0;color:var(--muted);font-size:15px}

/* close */
.close{background:var(--accent);color:var(--accent-ink);padding:clamp(72px,12vh,140px) 0}
.close .wrap{display:grid;grid-template-columns:1.2fr 1fr;gap:40px;align-items:end}
.close h2{font-size:clamp(44px,5.6vw,88px);margin:0;max-width:11ch}
.probe label{display:block;font:600 12px var(--mono);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px}
.probe div{display:flex;gap:8px;background:var(--accent-ink);padding:6px;border-radius:14px}
.probe input{flex:1;min-width:0;border:0;background:transparent;color:#fff;font:500 17px var(--mono);padding:0 12px;outline:none}
.probe input::placeholder{color:rgba(255,255,255,.5)}
.probe .btn.dark{background:var(--accent);color:var(--accent-ink)}
.probe:focus-within div{box-shadow:0 0 0 3px var(--accent-ink)}
.probe p{margin:12px 0 0;font-size:14px;opacity:.8}
.foot{padding:28px 0;border-top:1px solid var(--line)}
.foot .wrap{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;font:13px var(--mono);color:var(--muted)}
.foot a{margin-left:18px;text-decoration:none}.foot a:hover{color:var(--ink)}

@media (max-width:1100px){.board{grid-template-columns:1fr}.readout{position:static;min-height:0}}
@media (max-width:900px){.split{grid-template-columns:1fr}.sticky{position:static}.rails{grid-template-columns:1fr 1fr}
  .accounts a{grid-template-columns:44px 1fr auto}.accounts .why{grid-column:2/-1;justify-self:start;text-align:left}
  .close .wrap{grid-template-columns:1fr}}
@media (max-width:640px){.wrap{padding:0 16px}.readouts{grid-template-columns:1fr 1fr}.readouts div:nth-child(3){border-left:0}
  .readouts div:nth-child(n+3){border-top:1px solid var(--line)}.rails{grid-template-columns:1fr}.foot a{margin:0 14px 0 0}
  .probe div{flex-direction:column}.probe input{height:48px}.hero{min-height:0}
  .accounts a{grid-template-columns:32px minmax(0,1fr) auto;gap:6px 12px}.accounts .nm{font-size:clamp(26px,8.5vw,40px);overflow-wrap:anywhere;min-width:0}}
"""

JS = r"""
(function(){
  var cells=[].slice.call(document.querySelectorAll('.cell')), box=document.querySelector('.readout');
  if(!box)return;
  function show(d,btn){
    cells.forEach(function(c){c.setAttribute('aria-pressed','false')}); if(btn)btn.setAttribute('aria-pressed','true');
    box.querySelector('.r-label').textContent='Reading · '+(d.ans==='yes'?'Yes':d.ans==='no'?'No':'Unknown');
    box.querySelector('.r-co').textContent=d.company; box.querySelector('.r-q').textContent=d.q;
    box.querySelector('.r-quote').textContent=d.quote||''; box.querySelector('.r-basis').textContent=d.basis||'';
    var s=box.querySelector('.r-src'); s.textContent='';
    if(d.src&&/^https?:\/\//.test(d.src)){var a=document.createElement('a');a.href=d.src;a.target='_blank';a.rel='noopener';a.textContent=d.src.replace(/^https?:\/\//,'');s.append('Source: ',a)}
    else if(!d.quote){s.textContent='No quote on the pages read, so this stays as stated.'}
  }
  cells.forEach(function(c){var d=JSON.parse(c.dataset.read);
    c.addEventListener('click',function(){show(d,c)}); c.addEventListener('mouseenter',function(){show(d,c)}); c.addEventListener('focus',function(){show(d,c)})});
  var first=box.dataset.first; if(first){var d=JSON.parse(first);var b=cells.find(function(c){var x=JSON.parse(c.dataset.read);return x.company===d.company&&x.q===d.q});show(d,b)}
})();
"""
