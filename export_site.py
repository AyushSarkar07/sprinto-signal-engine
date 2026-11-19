"""Build a static, read-only results dashboard (sprinto-dashboard/index.html) from the latest pipeline outputs.

    python export_site.py            # then: cd sprinto-dashboard && vercel deploy --prod

It contains only what the reports already contain: decisions, cited evidence, contacts' public job titles,
review-gate drafts and revenue metrics. No credentials, no email addresses, nothing is sent from it.

Visual direction: warm paper canvas and deep-brown ink (calm, archival), an editorial serif for statements
paired with a tight grotesk for data, bracketed section labels, an inset hero panel with a faint crosshair
grid, black pill controls, and a single electric-lime accent reserved for what matters most.
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from config import ROOT, load_settings
from src import review_gate, site_chrome
from src.evidence_map import map_table
from src.pipeline import Pipeline
from src.qualification_engine import FALLBACK_CONFIDENCE_CAP, ICP_WEIGHTS, THRESHOLDS, TIMING_WEIGHTS

def E(s) -> str:
    """Escape for HTML, and drop em dashes from pipeline-generated text (they read as machine-written)."""
    s = str(s).replace(" — ", ", ").replace("—", "").replace(" ,", ",").replace("–", " to ")
    return html.escape(s.strip())
TOUR = """
<style>
.tour-dim{position:fixed;inset:0;background:rgba(20,14,10,.28);z-index:40;pointer-events:none;opacity:0;transition:opacity .2s}
.tour-on .tour-dim{opacity:1}
.tour-spot{position:relative;z-index:41;outline:3px solid var(--lime);outline-offset:6px;border-radius:14px;
box-shadow:0 0 0 9999px rgba(20,14,10,.0);scroll-margin:120px 0 260px}
.tour-card{position:fixed;z-index:50;left:50%;bottom:22px;transform:translateX(-50%);width:min(520px,calc(100vw - 32px));
background:var(--ink);color:var(--paper);border-radius:20px;padding:20px 22px 16px;box-shadow:0 18px 50px rgba(0,0,0,.28);display:none}
.tour-on .tour-card{display:block}
.tour-card .tstep{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;opacity:.65}
.tour-card .ttitle{font-family:var(--serif);font-weight:400;font-size:28px;line-height:1.05;margin:6px 0 8px}
.tour-card .tbody{margin:0;font-size:15px;line-height:1.5;opacity:.9}
.tour-card .tnav{display:flex;align-items:center;gap:8px;margin-top:16px}
.tour-card button{font:600 14px var(--sans);border-radius:999px;padding:9px 16px;cursor:pointer;border:1px solid currentColor;background:transparent;color:inherit}
.tour-card button.tnext{background:var(--lime);color:var(--limeink);border-color:var(--lime)}
.tour-card .tdots{margin-left:auto;display:flex;gap:5px}.tour-card .tdots i{width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.3}
.tour-card .tdots i.on{opacity:1;background:var(--lime)}
.tour-close{position:absolute;top:12px;right:14px;border:0!important;padding:4px 8px!important;font-size:20px!important;opacity:.7}
.tour-fab{position:fixed;right:18px;bottom:18px;z-index:30;display:inline-flex;align-items:center;gap:8px;background:var(--lime);color:var(--limeink);
border:0;border-radius:999px;padding:12px 18px;font:700 14px var(--sans);cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.18)}
.tour-on .tour-fab{display:none}
@media (max-width:640px){.tour-card .ttitle{font-size:23px}.tour-card .tbody{font-size:14px}.tour-fab{right:12px;bottom:12px}}
</style>
<button class="tour-fab" type="button" data-tour-start>Take a tutorial ✦</button>
<div class="tour-dim"></div>
<div class="tour-card" role="dialog" aria-live="polite" aria-label="Tutorial">
  <button class="tour-close" type="button" aria-label="Close tutorial">×</button>
  <div class="tstep"></div><p class="ttitle"></p><p class="tbody"></p>
  <div class="tnav"><button class="tback" type="button">Back</button><button class="tnext" type="button">Next</button><div class="tdots"></div></div>
</div>
<script>
(function(){
  var steps = [
    {sel:".hero", t:"What this is", p:"A research tool for Sprinto, a company that helps businesses pass security audits like SOC 2. It finds companies likely to need Sprinto right now, and explains why using real evidence."},
    {sel:".flow", t:"The process", p:"Companies go from a shortlist, through deep research, a Go or No-Go check, finding the right person, drafting an email, and a human review. Only then could anything be sent, and only to a test inbox."},
    {sel:"#pipeline", t:"The results", p:"Each company gets a decision. Green means qualify, blue means nurture (right company, wrong time), red means drop. Click any row to jump to its details."},
    {sel:"#revenue", t:"Revenue and conversion", p:"The lime card is real, logged revenue. The other numbers are estimates based on assumptions, and are always labelled that way. The queue shows who to contact first."},
    {sel:".co", t:"One company, in full", p:"Each card shows the decision, three scores, the person to contact, and every piece of evidence behind it."},
    {sel:".co .map", t:"The Evidence Map answers", p:"Three core questions decide the outcome: is it SaaS, is it the right size, is it preparing for an audit? A filled dot means yes. Each answer quotes the page it came from."},
    {sel:".co .bd", open:true, t:"How the scores add up", p:"Open the breakdown to see every point. For example, SaaS can earn up to 25 points for ICP fit. Nothing scores without a quote behind it."},
    {sel:".co .letter", open:true, t:"The email draft", p:"A short email that opens with the real evidence. It waits here until a person approves it. It is never sent to the prospect, only to the operator's own test inbox."},
    {sel:"#scoring", t:"The scoring rules", p:"These are the weights behind every score, plus the rules that keep them honest: no double counting, weak or old evidence counts less, and missing evidence is never a minus."},
    {sel:"#map", t:"The Go or No-Go gate", p:"The final decision comes from these rules, written down before any scoring. Two yes answers and one unknown means qualify, but flag it for a human to check."},
    {sel:".bar-top", t:"Safety first", p:"This is a controlled demo. Nothing is invented, prospects are never contacted, and every send needs human approval. That is the end of the tour."}
  ];
  var i = 0, cur = null, root = document.documentElement;
  var card = document.querySelector(".tour-card"), dots = card.querySelector(".tdots");
  steps.forEach(function(){ dots.appendChild(document.createElement("i")); });
  function clear(){ if (cur) cur.classList.remove("tour-spot"); cur = null; }
  function show(n){
    i = Math.max(0, Math.min(steps.length - 1, n));
    var s = steps[i], el = document.querySelector(s.sel);
    clear();
    if (el){ if (s.open && el.tagName === "DETAILS") el.open = true; el.classList.add("tour-spot"); cur = el;
      el.scrollIntoView({behavior:"smooth", block: el.offsetHeight > window.innerHeight * .6 ? "start" : "center"}); }
    card.querySelector(".tstep").textContent = "Step " + (i + 1) + " of " + steps.length;
    card.querySelector(".ttitle").textContent = s.t;
    card.querySelector(".tbody").textContent = s.p;
    card.querySelector(".tback").style.visibility = i ? "visible" : "hidden";
    card.querySelector(".tnext").textContent = i === steps.length - 1 ? "Finish" : "Next";
    Array.prototype.forEach.call(dots.children, function(d, k){ d.className = k === i ? "on" : ""; });
  }
  function start(){ root.classList.add("tour-on"); show(0); }
  function stop(){ root.classList.remove("tour-on"); clear(); }
  document.querySelectorAll("[data-tour-start]").forEach(function(b){ b.addEventListener("click", start); });
  card.querySelector(".tnext").addEventListener("click", function(){ i === steps.length - 1 ? stop() : show(i + 1); });
  card.querySelector(".tback").addEventListener("click", function(){ show(i - 1); });
  card.querySelector(".tour-close").addEventListener("click", stop);
  document.addEventListener("keydown", function(e){
    if (!root.classList.contains("tour-on")) return;
    if (e.key === "Escape") stop();
    if (e.key === "ArrowRight") card.querySelector(".tnext").click();
    if (e.key === "ArrowLeft" && i) show(i - 1);
  });
  try { if (new URLSearchParams(location.search).get("tour") === "1") start(); } catch (e) {}
})();
</script>
"""
GATE_TONE = {"QUALIFY": "go", "QUALIFY_AND_FLAG": "flag", "NURTURE": "hold", "DROP": "stop", "HAND_TO_HUMAN": "flag"}
GATE_LABEL = {"QUALIFY": "Qualify", "QUALIFY_AND_FLAG": "Qualify + flag", "NURTURE": "Nurture", "DROP": "Drop",
              "HAND_TO_HUMAN": "Hand to human"}
ANS_GLYPH = {"yes": ("●", "yes", "Yes"), "no": ("○", "no", "No"), "unknown": ("◌", "unk", "Unknown")}


def pill(text: str, tone: str) -> str:
    return f'<span class="pill {tone}">{E(text)}</span>'


def link(url: str) -> str:
    if url.startswith("http"):
        return f'<a href="{E(url)}" target="_blank" rel="noopener">{E(url.split("//", 1)[-1].rstrip("/")[:56])} ↗</a>'
    return f"<code>{E(url)}</code>"


def evidence_line(s: str) -> str:
    quote, _, url = s.rpartition(" — ")
    if not url:
        return f"<li>{E(s)}</li>"
    return f"<li><q>{E(quote.strip(chr(34)))}</q><span class='src'>{link(url)}</span></li>"


def breakdown(q) -> str:
    """Per-criterion points for both scores, so every number on the card can be traced."""
    def col(title: str, total: int, items) -> str:
        rows = "".join(
            f"<div class='crit'><div class='ct'><span>{E(c.criterion)}</span><b>{c.points:g}<i>/{c.max_points}</i></b></div>"
            f"<div class='cb'><i style='width:{100 * c.points / c.max_points:.0f}%'></i></div><p>{E(c.rationale)}</p></div>"
            for c in items)
        return f"<div class='bcol'><h4>{title} <b>{total}/100</b></h4>{rows}</div>"
    pens = "".join(f"<li>{E(p_)}</li>" for p_ in q.penalties)
    return (f"<details class='bd'><summary><span>(Score breakdown)</span> <b>ICP {q.icp_fit_score} · Timing {q.buying_timing_score}"
            f" · Confidence {q.evidence_confidence:.2f}</b></summary><div class='bgrid'>{col('ICP fit', q.icp_fit_score, q.icp_breakdown)}"
            f"{col('Buying timing', q.buying_timing_score, q.timing_breakdown)}</div>"
            + (f"<div class='pens'><b>Penalties applied to timing</b><ul>{pens}</ul></div>" if pens else "")
            + "</details>")


def scoring_section() -> str:
    def weights(title: str, w: dict) -> str:
        rows = "".join(f"<div class='wrow'><span>{E(k)}</span><div class='cb'><i style='width:{v * 100 / max(w.values()):.0f}%'></i></div>"
                       f"<b>{v}</b></div>" for k, v in w.items())
        return f"<div class='panel'><h3>{title}</h3>{rows}<p class='note'>Total {sum(w.values())} points.</p></div>"
    conf = [("Average confidence of the evidence items", 35), ("Key questions answered (of 6)", 35),
            ("Share stated directly, not inferred", 15), ("Pages read (4 or more = full)", 15)]
    crows = "".join(f"<div class='wrow'><span>{E(k)}</span><div class='cb'><i style='width:{v * 100 / 35:.0f}%'></i></div><b>{v}%</b></div>"
                    for k, v in conf)
    return f"""
<section id="scoring" class="sec">
  <div class="sec-head"><h2><span class="tag">(How scoring works)</span> Three scores, kept apart. <em>Every point</em> traces to a quote.</h2></div>
  <div class="three">{weights('ICP fit: is this Sprinto\'s kind of company?', ICP_WEIGHTS)}
  {weights('Buying timing: does compliance matter now?', TIMING_WEIGHTS)}
  <div class="panel"><h3>Evidence confidence: how much to trust them?</h3>{crows}
  <p class="note">Minus 0.05 per contradiction. Capped at {FALLBACK_CONFIDENCE_CAP} when the rule-based fallback reads the pages instead of Claude.</p></div></div>
  <div class="rules">
    <div><b>No double counting</b>One piece of evidence earns points for one criterion per score.</div>
    <div><b>Weak evidence earns less</b>Points scale with confidence; inferred evidence counts 70%.</div>
    <div><b>Old evidence counts half</b>Anything 3 or more years old is halved.</div>
    <div><b>Missing is not negative</b>No evidence means zero points, never a minus.</div>
    <div><b>Penalties</b>Minus 10 timing if Vanta, Drata or similar is already visible; minus 3 per contradiction.</div>
    <div><b>Scores rank, the gate decides</b>Audit intent counts as yes at timing {THRESHOLDS['timing_qualify']} or more, or with direct proof such as a security job post.</div>
  </div>
</section>"""


def company_card(i: int, run, review: dict | None) -> str:
    q = run.qualification
    if not q:
        return ""
    gate = q.gate_decision or "HAND_TO_HUMAN"
    cs = run.contact_selection
    rows = []
    for a in q.evidence_map:
        glyph, cls, word = ANS_GLYPH[a["answer"]]
        ev = "".join(evidence_line(x) for x in a["evidence"])
        rows.append(f"""<div class="q {'core' if a['core'] else ''}">
  <div class="qa"><span class="dot {cls}" title="{word}">{glyph}</span><span class="qt">{E(a['question'])}</span>
  <span class="ans {cls}">{word}</span></div>
  <p class="basis">{E(a['basis'])}</p>{f'<ul class="ev">{ev}</ul>' if ev else ''}</div>""")
    flags = "".join(f"<li>{E(f)}</li>" for f in q.review_flags)
    if cs and cs.contact:
        src = link(cs.contact.source_url) if cs.contact.source_url else E(cs.contact.source)
        contact = f"<b>{E(cs.contact.full_name)}</b><span>{E(cs.contact.job_title)}</span><span class='src'>{src}</span>"
    else:
        contact = "<span class='muted'>No decision-maker identified</span>"
    draft = ""
    if run.email:
        status = review["status"] if review else (run.dispatch.status if run.dispatch else "not sent")
        approved = review and review["status"] == "approved"
        body = review.get("approved_body") if approved else run.email.email_body
        subject = review.get("approved_subject") if approved else run.email.subject
        draft = f"""<details class="letter"><summary><span>(Draft email)</span> <b>{E(subject)}</b>
  {pill(status.replace('_', ' '), 'hold')}<i>{run.email.word_count} words</i></summary>
  <div class="paper"><div class="subj">Subject: {E(subject)}</div><pre>{E(body)}</pre>
  <p class="hook">Hook source {link(run.email.hook_source_url)}</p></div></details>"""
    first = q.qualification_reasoning[0].split(": ", 1)[-1] if q.qualification_reasoning else ""
    return f"""
<article class="co" id="{E(run.slug)}">
  <div class="co-head">
    <span class="idx">({i:02d})</span>
    <h3>{E(run.company)}</h3><span class="dom">{E(run.domain)}</span>
    {pill(GATE_LABEL.get(gate, gate), GATE_TONE.get(gate, 'hold'))}
  </div>
  <p class="verdict">{E(first)}</p>
  <div class="co-grid">
    <div class="scores">
      <div><span>ICP fit</span><b>{q.icp_fit_score}</b><i style="--v:{q.icp_fit_score}"></i></div>
      <div><span>Buying timing</span><b>{q.buying_timing_score}</b><i style="--v:{q.buying_timing_score}"></i></div>
      <div><span>Evidence confidence</span><b>{q.evidence_confidence:.2f}</b><i style="--v:{q.evidence_confidence * 100:.0f}"></i></div>
      <div class="who"><span>Decision-maker</span>{contact}</div>
    </div>
    <div class="map">{''.join(rows)}</div>
  </div>
  {f'<div class="flags"><b>(Review gate must check)</b><ul>{flags}</ul></div>' if flags else ''}
  {breakdown(q)}
  {draft}
</article>"""


def main() -> Path:
    s = load_settings()
    runs = Pipeline(s, None).load_all()
    order = {"QUALIFY": 0, "QUALIFY_AND_FLAG": 1, "NURTURE": 2, "HAND_TO_HUMAN": 3, "DROP": 4}
    runs = [r for r in runs if r.qualification]
    runs.sort(key=lambda r: (order.get(r.qualification.gate_decision, 5), -r.qualification.icp_fit_score))
    metrics_path = s.output_dir / "revenue" / "revenue_metrics.json"
    rev = json.loads(metrics_path.read_text()) if metrics_path.exists() else None
    reviews = {r["slug"]: r for r in review_gate.all_records(s.output_dir) if r["status"] != "withdrawn"}
    qualified = sum(1 for r in runs if r.qualification.qualified)
    drafts = sum(1 for r in runs if r.email)

    summary = "".join(
        f"<a class='row' href='#{E(r.slug)}'><span class='c'>{E(r.company)}</span>"
        f"{pill(GATE_LABEL.get(r.qualification.gate_decision, 'Pending'), GATE_TONE.get(r.qualification.gate_decision, 'hold'))}"
        f"<span class='n'>{r.qualification.icp_fit_score}</span><span class='n'>{r.qualification.buying_timing_score}</span>"
        f"<span class='n cf'>{r.qualification.evidence_confidence:.2f}</span>"
        f"<span class='p'>{E(r.contact_selection.contact.full_name) if r.contact_selection and r.contact_selection.contact else 'Not found'}</span>"
        f"<span class='arrow'>→</span></a>" for r in runs)

    map_rows = "".join("<tr>" + "".join(f"<td>{E(c)}</td>" for c in row) + "</tr>" for row in map_table())
    map_rows += ("<tr class='worst'><td>Worst case</td><td>Site unreachable or nearly empty</td><td></td><td></td><td></td>"
                 "<td>Hand to a human. Never an automatic rejection.</td><td></td><td></td></tr>")

    rev_html, won, expected, cur = "", 0, 0, "USD"
    if rev:
        cur, r_ = rev["currency"], rev["revenue"]
        won, expected = r_["won_revenue"], r_["expected_revenue"]
        base = rev["funnel"][0][1] or 1
        bars = "".join(f"<div class='fun'><span>{E(n)}</span><div class='bar'><i style='width:{max(1.5, 100 * v / base):.1f}%'></i></div>"
                       f"<b>{v}</b></div>" for n, v in rev["funnel"])
        queue = "".join(f"<div class='qrow'><span class='c'>{E(x['company'])}</span><span>{E(x['stage'])}</span>"
                        f"<span class='n'>{x['p_win']:.1%}</span><span class='n strong'>{cur} {x['expected_revenue']:,.0f}</span>"
                        f"<span class='act'>{E(x['next_action'])}</span></div>" for x in rev["priority_queue"])
        rev_html = f"""
<section id="revenue" class="sec">
  <div class="sec-head"><h2><span class="tag">(Revenue &amp; conversion)</span> What the pipeline is worth, with <em>measured</em> kept apart from <em>estimated</em>.</h2></div>
  <div class="stats">
    <div class="stat hi"><span>Won revenue · measured</span><b>{cur} {won:,.0f}</b><i>{r_['deals_won']} deal(s) logged</i></div>
    <div class="stat"><span>Open pipeline · measured</span><b>{cur} {r_['open_pipeline_value']:,.0f}</b><i>logged opportunities</i></div>
    <div class="stat"><span>Expected · estimated</span><b>{cur} {expected:,.0f}</b><i>P(win) × assumed ACV</i></div>
    <div class="stat"><span>Blocked by missing contact</span><b>{cur} {r_['blocked_no_contact']:,.0f}</b><i>estimated</i></div>
  </div>
  <div class="two">
    <div class="panel"><h3>Funnel</h3>{bars}
      <p class="note">Open rate {E(rev['conversion'].get('open_rate', 'no data'))} · reply {E(rev['conversion']['contacted_to_reply'])} ·
      won {E(rev['conversion']['contacted_to_won_observed'])}. One logged deal swings every estimate, so treat it as directional.</p></div>
    <div class="panel"><h3>Priority queue</h3><div class="queue">
      <div class="qrow hdr"><span>Company</span><span>Stage</span><span class="n">P(win)</span><span class="n">Expected</span><span>Next</span></div>
      {queue or "<p class='muted'>Nothing open.</p>"}</div></div>
  </div>
</section>"""

    page = f"""<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Results · Signal Engine</title>
<meta name="description" content="Evidence-driven outbound research for Sprinto: every decision cites its source.">
{site_chrome.FONTS}{site_chrome.FAVICON}
<style>
:root{{--paper:#f3eee6;--card:#fbf8f3;--ink:#2a1f1a;--soft:#6f625a;--line:#e2d9cc;--lime:#e4ff5c;--limeink:#1d2400;
--go:#1f6b4a;--gobg:#e3efe5;--flag:#8a5a00;--flagbg:#f8ecd2;--hold:#3e4f7a;--holdbg:#e6e9f3;--stop:#9b2c1f;--stopbg:#f6e2dd;
--serif:"Instrument Serif",Georgia,"Times New Roman",serif;--sans:{site_chrome.SANS}}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--paper:#16110e;--card:#1f1915;--ink:#f1e9df;--soft:#a8998c;--line:#342b25;
--gobg:#16301f;--go:#8fd8ad;--flagbg:#33270d;--flag:#f0c46a;--holdbg:#1d2438;--hold:#a9b8e8;--stopbg:#3a1913;--stop:#f29a8a}}}}
:root[data-theme="dark"]{{--paper:#16110e;--card:#1f1915;--ink:#f1e9df;--soft:#a8998c;--line:#342b25;--gobg:#16301f;--go:#8fd8ad;
--flagbg:#33270d;--flag:#f0c46a;--holdbg:#1d2438;--hold:#a9b8e8;--stopbg:#3a1913;--stop:#f29a8a}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--paper);color:var(--ink);font:15.5px/1.55 var(--sans);-webkit-font-smoothing:antialiased}}
a{{color:inherit}}em{{font-family:var(--serif);font-style:italic;font-weight:400}}.tag{{font-family:var(--sans);font-size:13px;font-weight:600;letter-spacing:.04em;color:var(--soft);vertical-align:middle;margin-right:.3em}}::selection{{background:var(--lime);color:var(--limeink)}}:focus-visible{{outline:2px solid var(--ink);outline-offset:2px;border-radius:6px}}
.bar-top{{background:var(--ink);color:var(--paper);font-size:13px;text-align:center;padding:9px 16px}}
.bar-top b{{background:var(--lime);color:var(--limeink);padding:1px 7px;border-radius:4px;margin-right:6px;font-weight:600}}
{site_chrome.CSS}
nav.pnav{{position:sticky;top:60px;z-index:5;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 24px;
background:color-mix(in srgb,var(--paper) 86%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}}
.brand{{font-weight:700;letter-spacing:-.02em;font-size:17px;text-decoration:none}}.brand span{{font-family:var(--serif);font-weight:400;font-style:italic;font-size:19px}}
.links{{display:flex;gap:6px;flex-wrap:wrap}}.links a{{text-decoration:none;font-size:13px;padding:6px 12px;border-radius:999px;border:1px solid var(--line)}}
.links a:hover{{background:var(--ink);color:var(--paper);border-color:var(--ink)}}
main{{max-width:1180px;margin:0 auto;padding:0 24px 80px}}
.hero{{position:relative;margin:22px 0 0;border-radius:22px;background:var(--card);border:1px solid var(--line);padding:56px 48px 40px;overflow:hidden}}
.hero:before{{content:"";position:absolute;inset:0;pointer-events:none;opacity:.55;
background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);
background-size:88px 88px;background-position:-1px -1px;mask-image:radial-gradient(circle at 70% 40%,#000 0,transparent 75%)}}
.hero>*{{position:relative}}.label{{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}}
.hero h1{{font-family:var(--serif);font-weight:400;font-size:clamp(42px,6.4vw,86px);line-height:.98;letter-spacing:-.02em;margin:14px 0 18px;max-width:15ch}}
.hero h1 b{{font-family:var(--sans);font-weight:700;letter-spacing:-.045em;font-size:.86em}}
.hero h1 mark{{-webkit-box-decoration-break:clone;box-decoration-break:clone;background:var(--lime);color:var(--limeink);padding:0 .12em;border-radius:.12em}}
.hero p.lede{{max-width:62ch;color:var(--soft);font-size:17px;margin:0 0 28px}}
.ctas{{display:flex;gap:10px;flex-wrap:wrap}}.btn{{display:inline-flex;align-items:center;gap:10px;text-decoration:none;padding:12px 20px;
border-radius:999px;font-weight:600;font-size:14px;background:var(--ink);color:var(--paper)}}button.btn{{border:0;cursor:pointer;font-family:var(--sans)}}.btn.tour{{background:var(--lime);color:var(--limeink)}}.btn.ghost{{background:transparent;color:var(--ink);border:1px solid var(--ink)}}
.snap{{font-size:13px;color:var(--soft);margin:16px 0 0;max-width:70ch}}
.hero-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin-top:44px;border-top:1px solid var(--line)}}
.hero-stats div{{padding:18px 18px 0 0}}.hero-stats div+div{{padding-left:18px;border-left:1px solid var(--line)}}
.hero-stats b{{display:block;font-family:var(--serif);font-weight:400;font-size:46px;line-height:1}}.hero-stats span{{font-size:13px;color:var(--soft)}}
.flow{{display:flex;flex-wrap:wrap;gap:8px;margin:26px 0 0;font-size:13px}}
.flow span{{padding:6px 12px;border-radius:999px;border:1px dashed var(--line);color:var(--soft)}}
.flow span.key{{border:1px solid var(--ink);color:var(--ink);font-weight:600}}
.sec{{margin-top:84px}}.sec-head{{display:grid;gap:10px;margin-bottom:26px;max-width:820px}}
.sec-head h2{{font-family:var(--serif);font-weight:400;font-size:clamp(30px,4vw,48px);line-height:1.04;letter-spacing:-.01em;margin:0}}
.pill{{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}}
.pill:before{{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}}
.go{{color:var(--go);background:var(--gobg)}}.flag{{color:var(--flag);background:var(--flagbg)}}.hold{{color:var(--hold);background:var(--holdbg)}}.stop{{color:var(--stop);background:var(--stopbg)}}
.table{{border-top:1px solid var(--ink)}}.row,.thead{{display:grid;grid-template-columns:1.4fr 1.1fr .5fr .5fr .7fr 1.4fr 24px;gap:12px;align-items:center;padding:16px 4px;border-bottom:1px solid var(--line);text-decoration:none}}
.thead{{font-size:12px;color:var(--soft);font-weight:600;text-transform:uppercase;letter-spacing:.06em;padding:10px 4px}}
.row .c{{font-family:var(--serif);font-size:26px;line-height:1}}.row .n{{font-variant-numeric:tabular-nums;font-weight:600}}.row .p{{color:var(--soft)}}
.row .arrow{{opacity:.35;transition:.2s}}.row:hover{{background:var(--card)}}.row:hover .arrow{{opacity:1;transform:translateX(3px)}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.stat{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px}}
.stat span{{font-size:12.5px;color:var(--soft)}}.stat b{{display:block;font-family:var(--serif);font-weight:400;font-size:38px;line-height:1.1;margin:6px 0 2px}}
.stat i{{font-style:normal;font-size:12px;color:var(--soft)}}.stat.hi{{background:var(--lime);color:var(--limeink);border-color:transparent}}.stat.hi span,.stat.hi i{{color:var(--limeink);opacity:.75}}
.two{{display:grid;grid-template-columns:1fr 1.15fr;gap:12px;margin-top:12px}}.panel{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}}
.panel h3{{margin:0 0 12px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--soft)}}
.fun{{display:grid;grid-template-columns:150px 1fr 30px;gap:12px;align-items:center;margin:7px 0;font-size:14px}}
.fun .bar{{height:10px;border-radius:99px;background:var(--line);overflow:hidden}}.fun .bar i{{display:block;height:100%;border-radius:99px;background:var(--ink)}}
.fun b{{text-align:right;font-variant-numeric:tabular-nums}}.note{{font-size:12.5px;color:var(--soft);margin:14px 0 0}}
.queue .qrow{{display:grid;grid-template-columns:1fr .9fr .6fr .8fr 1.5fr;gap:10px;padding:11px 0;border-bottom:1px solid var(--line);font-size:14px;align-items:baseline}}
.qrow.hdr{{font-size:11.5px;color:var(--soft);text-transform:uppercase;letter-spacing:.06em;padding-top:0}}.qrow .c{{font-weight:600}}.qrow .n{{text-align:right;font-variant-numeric:tabular-nums}}
.qrow .strong{{font-weight:700}}.qrow .act{{color:var(--soft)}}
.co{{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:28px;margin:14px 0}}
.co-head{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}}.idx{{font-size:12px;color:var(--soft);font-weight:600}}
.co-head h3{{font-family:var(--serif);font-weight:400;font-size:44px;line-height:1;margin:0;letter-spacing:-.01em}}.dom{{color:var(--soft);font-size:14px;margin-right:auto}}
.verdict{{font-size:16px;margin:12px 0 22px;max-width:75ch}}
.co-grid{{display:grid;grid-template-columns:280px 1fr;gap:28px}}
.scores{{display:grid;gap:14px;align-content:start}}.scores div{{border-top:1px solid var(--line);padding-top:10px;display:grid;gap:2px}}
.scores span{{font-size:12px;color:var(--soft)}}.scores b{{font-family:var(--serif);font-weight:400;font-size:34px;line-height:1}}
.scores i{{height:4px;border-radius:9px;background:var(--line);position:relative;overflow:hidden;margin-top:6px}}
.scores i:after{{content:"";position:absolute;inset:0;width:calc(var(--v)*1%);background:var(--ink);border-radius:9px}}
.who b{{font-size:16px}}.who span{{font-size:13.5px}}.src{{display:block;font-size:12px;color:var(--soft);word-break:break-word}}.src a{{color:var(--soft)}}
.map{{display:grid;gap:0;border-top:1px solid var(--ink)}}.q{{padding:12px 0;border-bottom:1px solid var(--line)}}
.qa{{display:grid;grid-template-columns:20px 1fr auto;gap:10px;align-items:baseline}}.q.core .qt{{font-weight:700}}.qt{{font-size:15px}}
.dot{{font-size:14px}}.dot.yes{{color:var(--go)}}.dot.no{{color:var(--stop)}}.dot.unk{{color:var(--soft)}}
.ans{{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em}}.ans.yes{{color:var(--go)}}.ans.no{{color:var(--stop)}}.ans.unk{{color:var(--soft)}}
.basis{{margin:3px 0 0 30px;color:var(--soft);font-size:13.5px}}.ev{{margin:6px 0 0 30px;padding:0;list-style:none;display:grid;gap:6px}}
.ev li{{font-size:13.5px;position:relative;padding-left:16px}}.ev li:before{{content:'';position:absolute;left:0;top:.6em;width:7px;height:7px;border-radius:2px;background:var(--lime);box-shadow:0 0 0 1px var(--ink)}}.ev q{{font-family:var(--serif);font-size:16px;font-style:italic}}
.flags{{margin:18px 0 0;background:var(--flagbg);color:var(--ink);border-radius:14px;padding:14px 18px;font-size:14px}}.flags ul{{margin:6px 0 0;padding-left:18px}}
.letter{{margin-top:20px;border-top:1px dashed var(--line);padding-top:14px}}.letter summary{{cursor:pointer;display:flex;gap:10px;align-items:center;flex-wrap:wrap;list-style:none}}
.letter summary::-webkit-details-marker{{display:none}}.letter summary span{{font-size:12px;color:var(--soft);font-weight:600;text-transform:uppercase;letter-spacing:.08em}}
.letter summary b{{font-family:var(--serif);font-weight:400;font-size:22px}}.letter summary i{{font-style:normal;color:var(--soft);font-size:13px}}
.letter summary:after{{content:"+";margin-left:auto;font-size:22px;line-height:1}}.letter[open] summary:after{{content:"×"}}
.paper{{margin-top:14px;background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px 24px;max-width:660px}}
.paper .subj{{font-weight:600;margin-bottom:12px}}.paper pre{{white-space:pre-wrap;font:15px/1.65 var(--sans);margin:0}}.hook{{font-size:12.5px;color:var(--soft);margin:14px 0 0}}
.tbl{{overflow-x:auto;border-top:1px solid var(--ink);padding-top:6px}}table{{width:100%;border-collapse:collapse;font-size:13.5px;min-width:900px}}
th,td{{text-align:left;padding:12px 10px 12px 0;border-bottom:1px solid var(--line);vertical-align:top}}th{{font-size:11.5px;color:var(--soft);text-transform:uppercase;letter-spacing:.06em}}
td:first-child{{font-weight:600;min-width:180px}}tr.worst td{{background:var(--flagbg)}}
.rule{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:0 0 22px}}.rule div{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;font-size:13.5px}}
.rule b{{display:block;margin:8px 0 2px}}
.bd{{margin-top:18px;border-top:1px dashed var(--line);padding-top:14px}}.bd summary{{cursor:pointer;display:flex;gap:10px;align-items:center;flex-wrap:wrap;list-style:none}}
.bd summary::-webkit-details-marker{{display:none}}.bd summary span{{font-size:12px;color:var(--soft);font-weight:600;text-transform:uppercase;letter-spacing:.08em}}
.bd summary b{{font-family:var(--serif);font-weight:400;font-size:22px}}.bd summary:after{{content:"+";margin-left:auto;font-size:22px;line-height:1}}.bd[open] summary:after{{content:"×"}}
.bgrid{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:16px}}.bcol h4{{margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--soft);display:flex;justify-content:space-between;border-bottom:1px solid var(--ink);padding-bottom:8px}}
.bcol h4 b{{color:var(--ink)}}.crit{{padding:10px 0;border-bottom:1px solid var(--line)}}.ct{{display:flex;justify-content:space-between;gap:12px;font-size:14.5px;font-weight:600}}
.ct b{{font-variant-numeric:tabular-nums}}.ct i{{font-style:normal;color:var(--soft);font-weight:400}}
.cb{{height:4px;border-radius:9px;background:var(--line);overflow:hidden;margin:7px 0 6px}}.cb i{{display:block;height:100%;background:var(--ink);border-radius:9px}}
.crit p{{margin:0;font-size:13px;color:var(--soft)}}.pens{{margin-top:14px;font-size:13.5px}}.pens ul{{margin:4px 0 0;padding-left:18px}}
.three{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.wrow{{display:grid;grid-template-columns:1fr 70px 34px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line);font-size:13.5px}}
.wrow .cb{{margin:0}}.wrow b{{text-align:right;font-variant-numeric:tabular-nums}}
.rules{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}}.rules div{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;font-size:13.5px;color:var(--soft)}}
.rules b{{display:block;color:var(--ink);margin-bottom:4px;font-size:14px}}
@media (max-width:900px){{.bgrid,.three,.rules{{grid-template-columns:1fr}}}}
footer{{margin-top:80px;padding-top:22px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;color:var(--soft);font-size:13px}}
.muted{{color:var(--soft)}}code{{font-size:12px}}
@media (max-width:900px){{.co-grid,.two{{grid-template-columns:1fr}}.stats,.hero-stats{{grid-template-columns:repeat(2,1fr)}}.rule{{grid-template-columns:1fr 1fr}}
.hero-stats div:nth-child(3){{padding-left:0;border-left:0}}.hero{{padding:40px 22px 28px}}}}
@media (max-width:640px){{main{{padding:0 16px 60px}}nav.pnav{{padding:10px 16px;top:0;position:static}}.links{{display:none}}.co{{padding:20px}}.co-head h3{{font-size:34px}}
.row,.thead{{grid-template-columns:1fr auto 44px 52px}}.row .p,.row .arrow,.row .cf,.thead .p,.thead .x,.thead .cf{{display:none}}.row .c{{font-size:22px}}
.fun{{grid-template-columns:110px 1fr 26px}}.queue .qrow{{grid-template-columns:1fr .7fr .8fr}}.queue .qrow>:nth-child(2),.queue .qrow>:nth-child(5){{display:none}}
.rule{{grid-template-columns:1fr}}.stat b{{font-size:30px}}.hero-stats b{{font-size:36px}}}}
</style></head><body>
<div class="bar-top"><b>Controlled demo</b>Prospects are never contacted. Drafts can only reach the operator's own test inbox, after human approval.</div>
{site_chrome.sitebar("results")}
<nav class="pnav" aria-label="On this page"><a class="brand" href="#top">Results <span>of the latest run</span></a>
<div class="links"><a href="#pipeline">Pipeline</a><a href="#revenue">Revenue</a><a href="#companies">Companies</a><a href="#scoring">Scoring</a><a href="#map">Evidence Map</a></div></nav>
<main id="top">
<header class="hero">
  <h1>Find the <mark>buying moment</mark>, <b>not just the inbox.</b></h1>
  <p class="lede">Every company is researched, scored and gated against an Evidence Map before anyone is contacted.
  Each decision cites the page it came from; anything the evidence can't support is flagged, not invented.</p>
  <div class="ctas"><button class="btn tour" type="button" data-tour-start>Take a tutorial ✦</button><a class="btn ghost" href="#companies">See the companies →</a><a class="btn ghost" href="#map">How the gate decides</a></div>
  <p class="snap">Snapshot of the latest run, published {dt.datetime.now().strftime('%d %b %Y')}. Want to try it on another company?
  <a href="/run"><b>Research a company live</b></a> (public sandbox: nothing is saved or sent).</p>
  <div class="hero-stats">
    <div><b>{len(runs)}</b><span>companies researched</span></div>
    <div><b>{qualified}</b><span>qualified at the gate</span></div>
    <div><b>{drafts}</b><span>drafts awaiting review</span></div>
    <div><b>{cur} {won / 1000:,.0f}k</b><span>won revenue, measured</span></div>
  </div>
  <div class="flow"><span>Define ICP</span><span>Shortlist</span><span>Deep research</span><span class="key">Evidence Map · Go / No-Go</span>
  <span>Find POC</span><span>Draft email</span><span class="key">Human review gate</span><span>Send (test inbox)</span><span>Track revenue</span></div>
</header>

<section id="pipeline" class="sec">
  <div class="sec-head"><h2><span class="tag">(Pipeline results)</span> {len(runs)} companies in, {qualified} worth a conversation <em>today</em>.</h2></div>
  <div class="table"><div class="thead"><span>Company</span><span>Gate</span><span>ICP</span><span>Timing</span><span class="cf">Confidence</span><span class="p">Decision-maker</span><span class="x"></span></div>
  {summary}</div>
</section>
{rev_html}
<section id="companies" class="sec">
  <div class="sec-head"><h2><span class="tag">(Companies)</span> Each answer, <em>with its receipt.</em></h2></div>
  {''.join(company_card(i, r, reviews.get(r.slug)) for i, r in enumerate(runs, 1))}
</section>

{scoring_section()}
<section id="map" class="sec">
  <div class="sec-head"><h2><span class="tag">(The Evidence Map)</span> Written down <em>before</em> any scoring.</h2></div>
  <div class="rule">
    <div>{pill('Drop', 'stop')}<b>Any short-circuit</b>Not SaaS, or already a Sprinto customer.</div>
    <div>{pill('Drop / nurture', 'stop')}<b>A core answer is no</b>Nurture if only audit intent is missing.</div>
    <div>{pill('Qualify', 'go')}<b>Three yes</b>SaaS, growth band, preparing for an audit.</div>
    <div>{pill('Qualify + flag', 'flag')}<b>Two yes, one unknown</b>The unknown becomes a review-gate check.</div>
    <div>{pill('Hand to human', 'flag')}<b>Anything else</b>Never an automatic rejection.</div>
  </div>
  <div class="tbl"><table><thead><tr><th>Question</th><th>Data that answers it</th><th>Where it lives</th><th>Sufficient when</th><th>Limit</th>
  <th>If unanswered</th><th>Short-circuit</th><th>Role</th></tr></thead><tbody>{map_rows}</tbody></table></div>
</section>
<footer><span>Sprinto Signal Engine · academic demonstration · generated {dt.datetime.now().strftime('%d %b %Y, %H:%M')}</span>
<span>Contacts are public job titles verified on each company's own site. No email addresses are shown or used.</span></footer>
</main>{TOUR}</body></html>"""
    out = ROOT / "sprinto-dashboard"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    return out / "index.html"


if __name__ == "__main__":
    print(main())
