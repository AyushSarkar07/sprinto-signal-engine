"""Sprinto Signal Engine control panel: a multi-page web app to run, review and improve the pipeline.

    .venv/bin/python app.py        # then open http://127.0.0.1:5050

Pages
  Overview        status, the route from website to signed-off email, both desks, a per-run scorecard,
                  why accounts were ruled out, which gaps reached a person, latest reactions
  Run research    up to 3 websites, a funding-news scan that keeps going until N accounts qualify, a list of sites
                  showing audit signals, live log, past runs
  Accounts        every account researched, searchable and filterable; each shows how it was decided
  Decision desk   accounts with a gap in the Evidence Map: qualify or rule out (with a reason), or research again
  Draft desk      tweak, sign off or decline drafts, give a quick verdict, log real replies
  Learning log    write, react, log, distil, recall, use: lessons kept from your reactions and whether they help

Locally it listens on 127.0.0.1 only and every form carries a per-session token. Sending obeys every safety rule:
test inbox only, DRY_RUN respected, recipient guard enforced.

PUBLIC_MODE=1 (automatic on Vercel) makes it safe to open without a password:
  * research works, rate-limited, writing only to a temporary sandbox seeded from a read-only snapshot;
  * nothing can be sent: DRY_RUN is forced on and TEST_TO_EMAIL is blanked, so the guard blocks every send;
  * actions that change real data or spend credits (decisions, approvals, ratings, outcomes, lead search,
    publish) are disabled and point to the local panel.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import re
import secrets
import shutil
import subprocess
import threading
import traceback
from collections import Counter
from pathlib import Path

from flask import Flask, abort, redirect, request, send_from_directory, url_for

from config import ROOT, load_settings, setup_logging
from export_site import E, GATE_LABEL, GATE_TONE
from src import feedback_loop, review_gate, run_history, site_chrome
from src.decision_ledger import write_outputs
from src.lead_finder import find_leads, funding_leads
from src.llm import make_llm
from src.pipeline import Pipeline, read_prospects, slugify
from src.revenue_tracker import ALL_OUTCOMES, record_outcome
from src.scraper import normalise_domain

app = Flask(__name__)
PUBLIC = os.getenv("PUBLIC_MODE") == "1" or os.getenv("VERCEL") == "1"   # any Vercel deploy is public mode
# Online, several server instances must agree on the form token, so it is tied to the deployment.
TOKEN = os.getenv("PANEL_TOKEN") or (os.getenv("VERCEL_DEPLOYMENT_ID") if PUBLIC else None) or secrets.token_urlsafe(24)
SNAPSHOT = ROOT / "snapshot"
RATE: dict[str, list[float]] = {}
PUBLIC_RUNS_PER_HOUR = 4
MAX_DOMAINS = 3
LOCAL_ONLY = "This action changes real data or spends credits, so it is only available in the local control panel."
DOMAIN_RX = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
JOB = {"running": False, "title": "", "lines": [], "started": None, "finished": None, "error": None}
LEADS: dict = {"items": [], "notes": [], "searched": None}
FLASH: list[str] = []
LOCK = threading.Lock()


# ================================================================ plumbing

def settings():
    s = load_settings()
    if PUBLIC:
        s.output_dir = Path(os.getenv("OUTPUT_DIR") or "/tmp/sse-output")
        s.dry_run, s.test_to_email, s.review_gate = True, "", True   # guard blocks every send
        s.hunter_api_key, s.serper_api_key, s.search_provider = "", "", ""  # no paid lookups for anonymous visitors
        s.max_research_rounds, s.request_delay = 1, 0.5             # fit one run inside a serverless request
        s.enrichment_csv, s.contacts_csv = ROOT / "data" / "company_enrichment.csv", ROOT / "data" / "contacts_override.csv"
        seed_sandbox(s.output_dir)
    setup_logging(s)
    return s


def seed_sandbox(out: Path) -> None:
    """First request on a fresh instance: copy the bundled snapshot of real results into the sandbox."""
    if (out / "state").exists() or not SNAPSHOT.exists():
        return
    shutil.copytree(SNAPSHOT, out, dirs_exist_ok=True)


def rate_limited(ip: str) -> bool:
    now = dt.datetime.now().timestamp()
    hits = [h for h in RATE.get(ip, []) if now - h < 3600]
    RATE[ip] = hits
    if len(hits) >= PUBLIC_RUNS_PER_HOUR:
        return True
    hits.append(now)
    return False


def local_only(back: str = "home"):
    if PUBLIC:
        FLASH.append(LOCAL_ONLY)
        return redirect(url_for(back))
    return None


def check_token():
    if request.form.get("token") != TOKEN:
        abort(403)


def add_to_prospects(company: str, domain: str) -> bool:
    path = ROOT / "data" / "prospects.csv"
    if domain in {d for _, d in read_prospects(path)}:
        return False
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([company, domain])
    return True


def _refresh(s, pipe) -> None:
    from main import run_revenue  # refresh revenue outputs for every saved company
    run_revenue(s, pipe.load_all(), header=False)


def start_job(title: str, prospects: list[tuple[str, str]], resume: bool = False, work=None) -> bool:
    with LOCK:
        if JOB["running"]:
            FLASH.append("A run is already in progress. Wait for it to finish.")
            return False
        JOB.update(running=True, title=title, lines=[], started=dt.datetime.now(), finished=None, error=None)

    def default_work(s, pipe):
        pipe.run(prospects, resume=resume, mode="domains")

    def runner():
        try:
            s = settings()
            llm = make_llm(s)
            JOB["lines"].append("Claude: on" if llm else "Claude not configured: labelled rule-based fallback")
            pipe = Pipeline(s, llm, send_test=False, on_event=JOB["lines"].append)
            (work or default_work)(s, pipe)
            _refresh(s, pipe)
            JOB["lines"].append("Done. Reports, ledger, revenue and run history updated.")
        except Exception as exc:
            JOB["error"] = f"{exc.__class__.__name__}: {exc}"
            JOB["lines"].append(traceback.format_exc(limit=2))
        finally:
            JOB.update(running=False, finished=dt.datetime.now())

    threading.Thread(target=runner, daemon=True).start()
    return True


# ================================================================ derived views

STATUS_TONE = {"Qualified": "go", "Drafted": "hold", "Approved": "go", "Sent": "go", "Flagged": "flag",
               "Nurture": "hold", "Dropped": "stop", "Rejected": "stop", "Not scored": "hold"}


def status_of(run, review: dict | None) -> str:
    q = run.qualification
    if not q:
        return "Not scored"
    if run.dispatch and run.dispatch.status == "sent":
        return "Sent"
    if review:
        return {"approved": "Approved", "rejected": "Rejected"}.get(review["status"], "Drafted")
    if q.gate_decision in ("QUALIFY_AND_FLAG", "HAND_TO_HUMAN") or (q.qualified and run.contact_selection
                                                                     and run.contact_selection.status != "selected"):
        return "Flagged"
    return {"QUALIFY": "Qualified", "NURTURE": "Nurture", "DROP": "Dropped"}.get(q.gate_decision, "Not scored")


def load(s):
    pipe = Pipeline(s, None)
    runs = sorted(pipe.load_all(), key=lambda r: r.company.lower())
    reviews = {r["slug"]: r for r in review_gate.all_records(s.output_dir) if r["status"] != "withdrawn"}
    return pipe, runs, reviews


def pill(text: str, tone: str) -> str:
    return f'<span class="pill {tone}">{E(text)}</span>'


def ans_pill(answer: str, role: str) -> str:
    word = {"yes": "Pass", "no": "Fail", "unknown": "Unknown"}[answer] if role == "gate" else answer.capitalize()
    return pill(word, {"yes": "go", "no": "stop", "unknown": "hold"}[answer])


def src_link(url: str) -> str:
    if url.startswith("http"):
        return f"<a class='src' href='{E(url)}' target='_blank' rel='noopener'>{E(url.split('//', 1)[-1].rstrip('/')[:52])} ↗</a>"
    return f"<span class='src'>{E(url)}</span>"


def quote(ev: str) -> str:
    text, _, url = ev.rpartition(" — ")
    return f"<div class='quote'><q>{E(text.strip(chr(34)))}</q>{src_link(url) if url else ''}</div>" if url else f"<div class='quote'>{E(ev)}</div>"


def tok() -> str:
    return f"<input type='hidden' name='token' value='{TOKEN}'>"


# ================================================================ layout

CSS = """
:root{--paper:#f3eee6;--card:#fbf8f3;--ink:#2a1f1a;--soft:#6f625a;--line:#e2d9cc;--lime:#e4ff5c;--limeink:#1d2400;--side:#2a1f1a;--sideink:#f3eee6;
--go:#1f6b4a;--gobg:#e3efe5;--flag:#8a5a00;--flagbg:#f8ecd2;--hold:#3e4f7a;--holdbg:#e6e9f3;--stop:#9b2c1f;--stopbg:#f6e2dd;
--serif:"Instrument Serif",Georgia,serif;--sans:"Instrument Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root.dark-ok{--paper:#16110e;--card:#1f1915;--ink:#f1e9df;--soft:#a8998c;--line:#342b25;--side:#0f0b09;--sideink:#f1e9df;
--gobg:#16301f;--go:#8fd8ad;--flagbg:#33270d;--flag:#f0c46a;--holdbg:#1d2438;--hold:#a9b8e8;--stopbg:#3a1913;--stop:#f29a8a}}
*{box-sizing:border-box}::selection{background:var(--lime);color:var(--limeink)}
::placeholder{color:var(--soft);opacity:1}input[type=checkbox]{width:20px;height:20px;accent-color:var(--ink);vertical-align:-5px}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}:focus-visible{outline:2px solid var(--ink);outline-offset:2px;border-radius:6px}
aside :focus-visible{outline-color:var(--lime)}.icon{width:16px;height:16px;flex:none;vertical-align:-3px}
.stat b{display:block;font-family:var(--serif);font-weight:400;font-size:30px;line-height:1.05}.stat span{display:block;font-size:12.5px;color:var(--soft)}
.dark{background:var(--side);color:var(--sideink);border-color:transparent}.dark .tagline{color:var(--lime);font-weight:600;font-size:13px}
.section{border-top:1px solid var(--line);margin-top:18px;padding-top:16px}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans)}a{color:inherit}
.shell{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:calc(100vh - 60px)}.shell>*{min-width:0}main{min-width:0}
aside{background:var(--side);color:var(--sideink);padding:18px 14px;position:sticky;top:60px;height:calc(100vh - 60px);display:flex;flex-direction:column;gap:4px}
.logo{font-weight:700;font-size:16px;padding:4px 10px 16px;text-decoration:none}.logo em{font-family:var(--serif);font-weight:400;font-size:19px}
.navh{font-size:11px;letter-spacing:.1em;text-transform:uppercase;opacity:.55;padding:14px 10px 6px}
.nav{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border-radius:10px;text-decoration:none;font-size:14.5px;opacity:.85}
.nav:hover{background:rgba(255,255,255,.07);opacity:1}.nav.on{background:var(--lime);color:var(--limeink);opacity:1;font-weight:600}
.nav b{font-size:12px;background:rgba(255,255,255,.14);border-radius:999px;padding:1px 8px}.nav.on b{background:rgba(0,0,0,.12)}
.side-note{margin-top:auto;font-size:12px;opacity:.6;padding:10px;line-height:1.45}
.top{display:flex;align-items:center;gap:12px;padding:14px 28px;border-bottom:1px solid var(--line);position:sticky;top:60px;background:var(--paper);z-index:3}
.search{flex:1;max-width:420px;display:flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--card);border-radius:999px;padding:8px 14px}
.search input{border:0;background:transparent;font:inherit;color:inherit;outline:none;flex:1}.kbd{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:1px 6px;color:var(--soft)}
.chip{font-size:13px;border:1px solid var(--line);border-radius:999px;padding:7px 12px;background:var(--card);white-space:nowrap}.chip i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--go);margin-right:6px}
.chip.run i{background:var(--flag);animation:pulse 1s infinite}@keyframes pulse{50%{opacity:.3}}
main{padding:26px 28px 80px;max-width:1180px}.lbl{display:block;font-size:13px;font-weight:600;margin:14px 0 6px}.stat .meter{margin-top:8px}.stat strong{color:var(--ink);font-weight:600}
h1{font-family:var(--serif);font-weight:400;font-size:clamp(34px,4.6vw,52px);line-height:1.02;margin:8px 0 8px;letter-spacing:-.01em}
h2{font-family:var(--serif);font-weight:400;font-size:28px;margin:0 0 4px;line-height:1.1}h3{margin:0;font-size:16px}
.lede{color:var(--soft);max-width:62ch;margin:0 0 18px}.sub{color:var(--soft);font-size:15px;margin:-2px 0 6px}.hint{color:var(--soft);font-size:13.5px;margin:4px 0 12px;max-width:75ch}.sub{max-width:75ch}
.stage-t{font:600 16px/1.3 var(--sans);margin:4px 0}
.card.dark{background:var(--side);color:var(--sideink)}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px;margin:14px 0}
.grid{display:grid;gap:12px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}.g6{grid-template-columns:repeat(6,1fr)}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px}.kpi span{font-size:11.5px;color:var(--soft);text-transform:uppercase;letter-spacing:.06em}
.kpi b{display:block;font-family:var(--serif);font-weight:400;font-size:38px;line-height:1.05;margin-top:4px}.kpi i{font-style:normal;font-size:12.5px;color:var(--soft)}
.kpi.hi{background:var(--lime);border-color:transparent;color:var(--limeink)}.kpi.hi span,.kpi.hi i{color:var(--limeink);opacity:.75}
.steps{display:grid;grid-template-columns:repeat(8,1fr);gap:0;margin:14px 0 4px;position:relative}
.step{text-align:center;text-decoration:none;padding:6px 2px;position:relative}.step:before{content:"";position:absolute;top:22px;left:-50%;width:100%;height:2px;background:var(--line);z-index:0}
.step:first-child:before{display:none}.step .dot{width:34px;height:34px;border-radius:50%;margin:0 auto 6px;display:grid;place-items:center;background:var(--ink);color:var(--paper);font-size:13px;font-weight:700;position:relative;z-index:1}
.step.human .dot{background:var(--lime);color:var(--limeink)}.step b{display:block;font-size:13px}.step span{display:block;font-size:11.5px;color:var(--soft)}
.step strong{display:block;font-family:var(--serif);font-weight:400;font-size:26px}
.gatecard{border:1px dashed var(--flag);background:var(--flagbg);border-radius:14px;padding:14px 16px;text-decoration:none;display:block}
.gatecard b{font-size:15px}.gatecard p{margin:4px 0 0;font-size:13.5px;color:var(--soft)}
.meter{height:5px;border-radius:9px;background:var(--line);overflow:hidden;margin:6px 0}.meter i{display:block;height:100%;background:var(--ink)}
.bars .row{display:grid;grid-template-columns:1fr 34px;gap:8px;font-size:13.5px;margin:7px 0}.bars .row div{grid-column:1/-1}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.pill:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.go{color:var(--go);background:var(--gobg)}.flag{color:var(--flag);background:var(--flagbg)}.hold{color:var(--hold);background:var(--holdbg)}.stop{color:var(--stop);background:var(--stopbg)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:11px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11.5px;color:var(--soft);text-transform:uppercase;letter-spacing:.06em;font-weight:600}td.n{font-variant-numeric:tabular-nums;font-weight:600}
tr.click{cursor:pointer}tr.click:hover td{background:var(--card)}.tw{overflow-x:auto}.muted{color:var(--soft)}.small{font-size:13px}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 12px}.filters a{font-size:13px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);text-decoration:none}
.filters a.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
input[type=text],input[type=number],select,textarea{font:inherit;color:var(--ink);background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:10px 13px}
textarea{width:100%;min-height:200px;resize:vertical;line-height:1.55}.full{width:100%}
.btn{font:600 14px var(--sans);border-radius:999px;padding:10px 17px;cursor:pointer;border:1px solid var(--ink);background:var(--ink);color:var(--paper);text-decoration:none;display:inline-flex;gap:8px;align-items:center}
.btn.lime{background:var(--lime);color:var(--limeink);border-color:var(--lime)}.btn.ghost{background:transparent;color:var(--ink)}.btn.sm{padding:6px 12px;font-size:13px}
.btn:disabled{opacity:.4;cursor:not-allowed}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.flash{background:var(--lime);color:var(--limeink);border-radius:14px;padding:11px 16px;margin:12px 0;font-weight:500}
.log{background:var(--ink);color:var(--paper);border-radius:14px;padding:14px 16px;font:12.5px/1.5 ui-monospace,Menlo,monospace;max-height:340px;overflow:auto;white-space:pre-wrap}
.trail h3{margin:18px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--soft)}
.check{display:grid;grid-template-columns:96px 1fr;gap:12px;padding:12px 0;border-top:1px solid var(--line)}.check:first-of-type{border-top:0}
.check .what{font-weight:600}.check .rule{font-size:12.5px;color:var(--soft)}.quote{position:relative;padding-left:16px;margin:6px 0;font-size:13.5px}.quote:before{content:"";position:absolute;left:0;top:.55em;width:7px;height:7px;border-radius:2px;background:var(--lime);box-shadow:0 0 0 1px var(--ink)}
.quote q{font-family:var(--serif);font-size:16px;font-style:italic}.src{display:block;font-size:12px;color:var(--soft);word-break:break-word}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0 0;position:sticky;top:61px;background:var(--paper);padding:8px 0;z-index:2}
.tabs a{font-size:13.5px;padding:7px 13px;border-radius:999px;border:1px solid var(--line);text-decoration:none}
.split{display:grid;grid-template-columns:240px 1fr;gap:16px}.list a{display:block;padding:11px 12px;border-radius:12px;text-decoration:none;border:1px solid transparent}
.list a.on{background:var(--card);border-color:var(--line)}.list a span{display:block;font-size:12.5px;color:var(--soft)}
.tags{display:flex;gap:6px;flex-wrap:wrap}.tags label{font-size:12.5px;border:1px solid var(--line);border-radius:999px;padding:5px 10px;cursor:pointer}
.tags input{margin-right:4px}.loop{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.stage{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}.stage small{color:var(--soft);font-weight:600}
.stage b{display:block;font-family:var(--serif);font-weight:400;font-size:40px;line-height:1}.stage p{margin:4px 0 0;font-size:13px;color:var(--soft)}
.feed div{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:13.5px}
pre.md{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;font:13px/1.55 ui-monospace,Menlo,monospace}
@media (max-width:960px){.shell{grid-template-columns:minmax(0,1fr)}aside{position:static;height:auto;flex-direction:row;flex-wrap:nowrap;overflow-x:auto;gap:2px}
.nav{white-space:nowrap;flex:none}.logo{flex:none;padding:8px 10px}.navh,.side-note{display:none}.kbd{display:none}.top{padding:12px 16px;position:static}.search{max-width:none;flex:1 1 100%}
main{padding:18px 16px 60px}.chip{white-space:normal}
.g2,.g3,.loop,.split{grid-template-columns:1fr}.g6{grid-template-columns:repeat(2,1fr)}.steps{grid-template-columns:repeat(4,1fr);row-gap:14px}.top{flex-wrap:wrap}}
"""

JS = """
<script>
document.addEventListener('keydown',function(e){if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();var i=document.getElementById('q');if(i)i.focus();}});
document.querySelectorAll('tr[data-href]').forEach(function(r){r.addEventListener('click',function(){location=r.dataset.href;});});
(function(){var log=document.getElementById('jlog');if(!log)return;var was=log.dataset.running==='1';
function poll(){fetch('/status').then(function(r){return r.json()}).then(function(j){log.textContent=j.lines.join('\\n')||'No run yet.';
log.scrollTop=log.scrollHeight;if(was&&!j.running){location.reload();return;}was=j.running;setTimeout(poll,j.running?1500:6000);}).catch(function(){setTimeout(poll,6000)});}
poll();})();
</script>"""


def layout(title: str, active: str, body: str, s, runs, reviews) -> str:
    flashes = "".join(f"<div class='flash'>{E(m)}</div>" for m in FLASH)
    FLASH.clear()
    flagged = sum(1 for r in runs if status_of(r, reviews.get(r.slug)) == "Flagged")
    drafts = sum(1 for r in reviews.values() if r["status"] == "pending")
    hist = run_history.history(s.output_dir)
    last = hist[-1] if hist else None
    chip = (f"<span class='chip run'><i></i>Running: {E(JOB['title'])}</span>" if JOB["running"] else
            f"<span class='chip'><i></i>Run {last['run']} · {last['qualified']}/{last['researched']} qualified · {E(last['at'][5:16].replace('T', ' '))}</span>"
            if last else "<span class='chip'><i></i>No runs yet</span>")

    def nav(key, label, href, count=None):
        badge = f"<b>{count}</b>" if count else ""
        return f"<a class='nav {'on' if active == key else ''}' href='{href}'><span>{label}</span>{badge}</a>"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} · Signal Engine</title>
{site_chrome.FAVICON}{site_chrome.FONTS}
<style>{site_chrome.CSS}{CSS}</style></head><body>{site_chrome.sitebar("panel")}<div class="shell">
<aside><a class="logo" href="/app">Control <em>panel</em></a>
<div class="navh">Pipeline</div>{nav('home', 'Overview', '/app')}{nav('run', 'Run research', '/run')}{nav('companies', 'Accounts', '/companies', len(runs))}
<div class="navh">People decide</div>{nav('review', 'Decision desk', '/review', flagged)}{nav('drafts', 'Draft desk', '/drafts', drafts)}
<div class="navh">Improve</div>{nav('loop', 'Learning log', '/loop')}
<div class="side-note">The Evidence Map decides, quotes back every claim, and you sign off every email. Test inbox only.
{'<br><br><b>Public demo:</b> a sandbox; nothing is saved or sent.' if PUBLIC else ''}<br><br>Case-study build, not affiliated with Sprinto.</div></aside>
<div><div class="top"><form class="search" action="/companies" role="search"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><label for="q" class="sr">Find an account</label><input id="q" name="q" placeholder="Find an account…" value="{E(request.args.get('q', ''))}"><span class="kbd">⌘K</span></form>
{chip}<a class="btn lime sm" href="/run">New research</a></div>
<main>{flashes}{body}</main></div></div>{JS}</body></html>"""


# ================================================================ pages

def _site_dir() -> Path:
    built = ROOT / "site"            # the Vercel bundle (build_panel_deploy.sh)
    return built if built.exists() else ROOT / "signal-engine-landing"


@app.get("/")
def landing():
    return send_from_directory(_site_dir(), "index.html")


@app.get("/dashboard")
def dashboard():
    built = ROOT / "site" / "dashboard.html"
    if built.exists():
        return send_from_directory(ROOT / "site", "dashboard.html")
    return send_from_directory(ROOT / "sprinto-dashboard", "index.html")


@app.get("/<any('favicon.svg', 'share.jpg'):name>")
def site_file(name: str):
    return send_from_directory(_site_dir(), name)


@app.get("/assets/<path:path>")
def site_assets(path: str):
    return send_from_directory(_site_dir() / "assets", path)


@app.get("/app")
def home():
    s = settings()
    _, runs, reviews = load(s)
    statuses = Counter(status_of(r, reviews.get(r.slug)) for r in runs)
    hist = run_history.history(s.output_dir)
    pick = request.args.get("run", type=int)
    cur = next((h for h in hist if h["run"] == pick), hist[-1] if hist else None)
    overall = run_history.summarise(runs, s.initial_page_budget + s.research_page_budget)
    stats = review_gate.stats(s.output_dir)
    loop = feedback_loop.loop_stats(s.output_dir, list(reviews.values()))
    scraped = sum(1 for r in runs if r.scrape and r.scrape.scraping_status != "failed")
    gated = sum(1 for r in runs if r.qualification)
    qualified = sum(1 for r in runs if r.qualification and r.qualification.qualified)
    with_contact = sum(1 for r in runs if r.contact_selection and r.contact_selection.status == "selected")
    with_pain = sum(1 for r in runs if r.pain_points and r.pain_points.pain_points)
    drafted = sum(1 for r in runs if r.email)
    reviewed = stats["approved"]
    sent = sum(1 for r in runs if r.dispatch and r.dispatch.status in ("sent", "dry_run_preview"))
    steps = [("Scrape", "website + news", scraped, "/companies", False), ("Gate", "Evidence Map", gated, "/companies", False),
             ("Qualify", "rules + research", qualified, "/companies?status=Qualified", False),
             ("Contact", "verified role", with_contact, "/companies", False), ("Pain", "evidence-linked", with_pain, "/drafts", False),
             ("Draft", "checked email", drafted, "/drafts", False), ("Review", "a person approves", reviewed, "/drafts", True),
             ("Send", "test inbox only", sent, "/drafts", False)]
    step_html = "".join(f"<a class='step {'human' if h else ''}' href='{href}'><div class='dot'>{i}</div><b>{n}</b><span>{d}</span>"
                        f"<strong>{c}</strong></a>" for i, (n, d, c, href, h) in enumerate(steps, 1))
    src = cur or overall
    runsel = "".join(f"<option value='{h['run']}' {'selected' if cur and h['run'] == cur['run'] else ''}>Run {h['run']} · "
                     f"{h['at'][5:10]} · {h['researched']} companies</option>" for h in reversed(hist))

    def bars(d: dict, tone_bg: str) -> str:
        if not d:
            return "<p class='muted small'>Nothing yet.</p>"
        top = max(d.values())
        return "<div class='bars'>" + "".join(f"<div class='row'><span>{E(k)}</span><b>{v}</b><div class='meter'><i style='width:{100 * v / top:.0f}%;background:{tone_bg}'></i></div></div>"
                                              for k, v in sorted(d.items(), key=lambda kv: -kv[1])) + "</div>"

    sigs = feedback_loop.signals(s.output_dir)[-8:][::-1]
    feed = "".join(f"<div><span><b>{E(x['kind'].replace('_', ' ').capitalize())}</b> · {E(x['company'])}</span><span class='muted'>{E(x['actor'])} · {E(x['ts'][5:16].replace('T', ' '))}</span></div>" for x in sigs)
    avg_edit = stats["avg_change"]
    body = f"""<div class="row" style="justify-content:space-between;align-items:flex-end"><div><h1>Signal Engine overview</h1><p class="sub">{('Showing run ' + str(cur['run']) + ', ' + cur['at'][:16].replace('T', ' ')) if cur else 'No runs recorded yet'}</p>
<p class="lede">Each account is read from its own pages, put through the Evidence Map, and only drafted when the quotes back it up.
Where the map has a gap, you make the call.</p></div>
{f"<form><select name='run' onchange='this.form.submit()'>{runsel}</select></form>" if hist else ''}</div>
<div class="grid g6">
<div class="kpi"><span>Accounts read</span><b>{len(runs)}</b><i>{scraped} read OK</i></div>
<div class="kpi hi"><span>Qualified</span><b>{qualified}</b><i>three core yeses</i></div>
<div class="kpi"><span>On your desk</span><b>{statuses['Flagged']}</b><i>a gap to settle</i></div>
<div class="kpi"><span>Nurture</span><b>{statuses['Nurture']}</b><i>check back later</i></div>
<div class="kpi"><span>Dropped</span><b>{statuses['Dropped']}</b><i>out of scope</i></div>
<div class="kpi"><span>Drafts</span><b>{stats['pending']}</b><i>to sign off</i></div></div>
<section class="card"><h2>From a website to a signed-off email</h2>
<div class="steps">{step_html}</div>
<div class="grid g2" style="margin-top:14px"><a class="gatecard" href="/review"><b>Decision desk</b> {pill(str(statuses['Flagged']) + ' to settle', 'flag')}
<p>Accounts with a gap in the map: a core question left unknown, a site that would not load, or nobody verified to write to. You fill the gap; the engine never guesses it.</p></a>
<a class="gatecard" href="/drafts"><b>Draft desk</b> {pill(str(stats['pending']) + ' to sign off', 'flag')}
<p>No draft leaves without your sign-off, and a signed-off draft can only reach your own test inbox.</p></a></div></section>
<div class="grid g3">
<section class="card" style="grid-column:span 2;margin:0"><h3>Scorecard for {'run ' + str(cur['run']) if cur else 'all accounts'}</h3><p class="hint">Pick another run at the top to compare</p>
<div class="grid g3" style="grid-template-columns:repeat(4,1fr)">
<div class="stat"><b>{src['qualified']}/{src['researched']}</b><span><strong>Qualified</strong> of accounts read</span><div class="meter"><i style="width:{100 * src['hit_rate']:.0f}%"></i></div></div>
<div class="stat"><b>{100 * src['flag_rate']:.0f}%</b><span><strong>Sent to your desk</strong> share with a gap</span><div class="meter"><i style="width:{100 * src['flag_rate']:.0f}%"></i></div></div>
<div class="stat"><b>{src['pages_per_company']}</b><span><strong>Pages read</strong> per account, of {src['page_budget']} allowed</span><div class="meter"><i style="width:{min(100, 100 * src['pages_per_company'] / max(1, src['page_budget'])):.0f}%"></i></div></div>
<div class="stat"><b>{'None yet' if avg_edit is None else f'{100 * avg_edit:.0f}%'}</b><span><strong>Rewritten by you</strong> average across {stats['approved']} sign-offs</span><div class="meter"><i style="width:{0 if avg_edit is None else 100 * avg_edit:.0f}%"></i></div></div>
</div></section>
<a class="card dark" href="/loop" style="margin:0;text-decoration:none"><span class="tagline">Learning log</span>
<b style="display:block;font-family:var(--serif);font-weight:400;font-size:46px;line-height:1">{loop['stages_with_data']} of 6</b><p class="small" style="opacity:.8">parts of the loop have data · {loop['store']} lessons kept · {loop['apply']} drafts changed by them</p>
<span class="small" style="color:var(--lime)">See what it learned →</span></a></div>
<div class="grid g3" style="margin-top:14px">
<section class="card" style="margin:0"><h3>Out of scope, and why</h3><p class="hint">The question that ruled each one out</p>{bars(src['drop_reasons'], 'var(--stop)')}</section>
<section class="card" style="margin:0"><h3>Gaps sent to your desk</h3><p class="hint">What the map could not answer</p>{bars(src['human_reasons'], 'var(--flag)')}</section>
<section class="card" style="margin:0"><h3>Latest reactions</h3><p class="hint">Your edits, ratings and decisions</p><div class="feed">{feed or "<p class='muted small'>Nothing yet. Sign off, rate or settle an account.</p>"}</div></section></div>"""
    return layout("Overview", "home", body, s, runs, reviews)


@app.get("/run")
def run_page():
    s = settings()
    _, runs, reviews = load(s)
    hist = run_history.history(s.output_dir)
    busy = "disabled" if JOB["running"] else ""
    lockd = "disabled title='Local control panel only'" if PUBLIC else busy
    keyless = not s.serper_api_key
    hrows = "".join(f"<tr><td>Run {h['run']}</td><td>{E(h['at'][:16].replace('T', ' '))}</td><td>{E(h.get('mode', 'batch'))}</td>"
                    f"<td class='n'>{h['researched']}</td><td class='n'>{h['qualified']}</td><td class='n'>{h['needs_human']}</td>"
                    f"<td class='n'>{h['dropped']}</td><td class='small muted'>{E(', '.join(h['companies'][:4]))}{'…' if len(h['companies']) > 4 else ''}</td></tr>"
                    for h in reversed(hist[-12:]))
    leads = ""
    for c in LEADS["items"]:
        dom = getattr(c, "domain", "")
        label = getattr(c, "name", dom)
        extra = (f"{E(getattr(c, 'stage', ''))} · rank {getattr(c, 'rank', '')} · {E(getattr(c, 'domain_note', ''))}"
                 if hasattr(c, "rank") else E(getattr(c, "snippet", "")))
        btn = (f"<form method='post' action='/research'>{tok()}<input type='hidden' name='company' value='{E(label)}'>"
               f"<input type='hidden' name='domains' value='{E(dom)}'><input type='hidden' name='keep' value='1'>"
               f"<button class='btn lime sm' {busy}>Research</button></form>") if dom else "<span class='muted small'>needs a domain</span>"
        leads += f"<tr><td><b>{E(label)}</b><br><span class='muted small'>{E(dom or 'no domain')}</span></td><td class='small'>{extra}</td><td>{btn}</td></tr>"
    lead_notes = "".join(f"<p class='hint'>{E(n)}</p>" for n in LEADS["notes"])
    body = f"""<h1>Start new research</h1>
<p class="lede">Point it at websites you already have in mind, or let it scan funding news for SaaS accounts and keep researching until the target is met.</p>
<div class="grid g2">
<section class="card" style="margin:0"><h2>Research these websites</h2><p class="hint">Up to {MAX_DOMAINS}, separated by commas or new lines.</p>
<form method="post" action="/research">{tok()}<textarea name="domains" style="min-height:96px" placeholder="acme.com&#10;example.io" required></textarea>
<div class="row" style="margin-top:10px">{'' if PUBLIC else "<label class='muted small'><input type='checkbox' name='keep' value='1' checked> add to my prospect list</label>"}
<button class="btn lime" {busy} onclick="this.textContent='Researching…'">Start research →</button></div></form>
{"<p class='hint'>Public demo: one domain per run, up to 4 runs an hour, results in a temporary sandbox. Nothing is ever emailed.</p>" if PUBLIC else ''}</section>
<section class="card" style="margin:0"><h2>Scan funding news</h2><p class="hint">Pulls this year's Series A to C headlines, scores them on stage, software wording and how recent they are,
works out each website, then researches the best first.</p>
<form method="post" action="/find" class="row">{tok()}<span class="small muted">Keep going until</span>
<select name="target"><option>1</option><option>2</option><option selected>3</option></select><span class="small muted">accounts qualify</span>
<button class="btn" {'disabled' if (PUBLIC or keyless) else busy}>Scan and research →</button></form>
<form method="post" action="/leads" class="row" style="margin-top:8px">{tok()}<button class="btn ghost sm" {'disabled' if (PUBLIC or keyless) else ''}>Or list sites showing audit signals</button></form>
<p class="hint">{"Uses the operator's search key, so it runs in the local panel only." if PUBLIC else ("Needs SERPER_API_KEY in .env (free tier at serper.dev)." if keyless else "Uses your Serper key; about 6 searches per run.")}</p></section></div>
<section class="card"><div class="row" style="justify-content:space-between"><h2>Live log</h2>{pill('Running', 'flag') if JOB['running'] else pill('Idle', 'go')}</div>
<p class="hint">{E(JOB['title'] or 'Nothing running.')}</p><div class="log" id="jlog" data-running="{1 if JOB['running'] else 0}">{E(chr(10).join(JOB['lines'][-40:])) or 'No run yet.'}</div>
<div class="row" style="margin-top:10px"><form method="post" action="/rerun">{tok()}<input type="hidden" name="slug" value="__all__"><button class="btn ghost sm" {lockd}>Research every account again</button></form>
<form method="post" action="/publish">{tok()}<button class="btn ghost sm" {lockd}>Publish dashboard to Vercel</button></form></div></section>
{f"<section class='card'><h2>Candidates</h2>{lead_notes}<div class='tw'><table><tbody>{leads}</tbody></table></div></section>" if (leads or lead_notes) else ''}
<section class="card"><h2>Past runs</h2><div class="tw"><table><thead><tr><th>Run</th><th>When</th><th>Mode</th><th>Read</th><th>Qualified</th><th>To your desk</th><th>Out of scope</th><th>Accounts</th></tr></thead>
<tbody>{hrows or "<tr><td colspan=8 class='muted'>No runs recorded yet.</td></tr>"}</tbody></table></div></section>"""
    return layout("Run", "run", body, s, runs, reviews)


@app.get("/companies")
def companies():
    s = settings()
    _, runs, reviews = load(s)
    q = (request.args.get("q") or "").lower().strip()
    want = request.args.get("status", "All")
    rows, counts = "", Counter()
    for r in runs:
        st = status_of(r, reviews.get(r.slug))
        counts[st] += 1
        if (want != "All" and st != want) or (q and q not in (r.company + r.domain).lower()):
            continue
        qq = r.qualification
        stage = r.extraction.company_profile.funding_stage.value if r.extraction and r.extraction.company_profile.funding_stage.value else "Unknown"
        reason = (qq.qualification_reasoning[0].split(": ", 1)[-1] if qq and qq.qualification_reasoning else "")[:110]
        rows += (f"<tr class='click' data-href='/companies/{E(r.slug)}'><td><b>{E(r.company)}</b><br><span class='muted small'>{E(r.domain)}</span></td>"
                 f"<td>{E(stage)}</td><td>{pill(st, STATUS_TONE.get(st, 'hold'))}</td><td class='n'>{qq.icp_fit_score if qq else ''}</td>"
                 f"<td class='n'>{qq.buying_timing_score if qq else ''}</td><td class='n'>{f'{qq.evidence_confidence:.2f}' if qq else ''}</td>"
                 f"<td class='small muted'>{E(reason)}</td></tr>")
    chips = "".join(f"<a class='{'on' if want == k else ''}' href='/companies?status={k}{'&q=' + E(q) if q else ''}'>{k}{f' {counts[k]}' if k != 'All' and counts[k] else ''}</a>"
                    for k in ["All", "Qualified", "Flagged", "Drafted", "Approved", "Sent", "Nurture", "Dropped"])
    body = f"""<h1>Every account so far</h1><p class="lede">Click a row to see each question, the answer and the quote it rests on.</p>
<form class="row" action="/companies"><input type="text" name="q" value="{E(q)}" placeholder="Name or website" style="min-width:260px"><input type="hidden" name="status" value="{E(want)}"><button class="btn ghost sm">Search</button></form>
<div class="filters">{chips}</div><section class="card" style="padding:6px 14px"><div class="tw"><table><thead><tr><th>Company</th><th>Stage</th><th>Status</th><th>ICP</th><th>Timing</th><th>Conf.</th><th>Reason</th></tr></thead>
<tbody>{rows or "<tr><td colspan=7 class='muted'>No accounts match.</td></tr>"}</tbody></table></div></section>"""
    return layout("Companies", "companies", body, s, runs, reviews)


def company_body(s, run, reviews) -> str:
    q = run.qualification
    rev = reviews.get(run.slug)
    st = status_of(run, rev)
    prof = run.extraction.company_profile if run.extraction else None
    pages = len(run.scrape.ok_pages()) if run.scrape else 0
    budget = s.initial_page_budget + s.research_page_budget
    groups = {"gate": [], "core": [], "supporting": []}
    for a in (q.evidence_map if q else []):
        role = a.get("role") or ("core" if a.get("core") else "supporting")
        ev = "".join(quote(x) for x in a["evidence"])
        groups[role].append(f"<div class='check'><div>{ans_pill(a['answer'], role)}</div><div><div class='what'>{E(a['question'])}</div>"
                            f"<div class='rule'>{E(a['basis'])}</div>{ev}</div></div>")
    trail = "".join(f"<h3>{t}</h3>{''.join(groups[k])}" for k, t in (("gate", "Rule-outs (can only remove)"),
                                                                     ("core", "The three questions that decide"),
                                                                     ("supporting", "Extra colour (does not decide)")) if groups[k])
    crit = "".join(f"<tr><td>{E(c.criterion)}</td><td class='n'>{c.points:g}/{c.max_points}</td><td class='small muted'>{E(c.rationale)}</td></tr>"
                   for c in ((q.icp_breakdown + q.timing_breakdown) if q else []))
    cs = run.contact_selection
    contact = "<p class='muted'>Not reached: the company did not qualify.</p>"
    if cs:
        c = cs.contact
        alts = "".join(f"<li>{E(a.contact.full_name)}, {E(a.contact.job_title)} · relevance {a.relevance_score:g}</li>" for a in cs.alternative_contacts[:3])
        contact = (f"<p><b>{E(c.full_name)}</b>, {E(c.job_title)} {src_link(c.source_url) if c and c.source_url else ''}</p>" if c else "<p class='muted'>No verified decision-maker found.</p>") + \
                  f"<p class='small'>{E(cs.selection_reasoning)}</p>" + (f"<h3 style='margin-top:12px'>Other people considered</h3><ul class='small'>{alts}</ul>" if alts else "")
    email = "<p class='muted'>No draft: not qualified, no contact, or no grounded hook.</p>"
    if run.email:
        e = run.email
        trace = "".join(f"<tr><td class='small'>{E(t.sentence)}</td><td class='small muted'>{E(t.purpose)}</td><td>{src_link(t.source_url) if t.source_url else ''}</td></tr>"
                        for t in e.evidence_to_email_trace)
        email = (f"<p><b>Subject:</b> {E(e.subject)} · {pill(rev['status'] if rev else 'draft', 'hold')} "
                 f"{'· ' + str(len(e.learnings_applied)) + ' learning(s) applied' if e.learnings_applied else ''}</p>"
                 f"<pre class='md' style='font-family:var(--sans);font-size:14.5px'>{E(rev.get('approved_body') if rev and rev.get('approved_body') else e.email_body)}</pre>"
                 f"<h3 style='margin-top:12px'>Where each line comes from</h3><div class='tw'><table>{trace}</table></div>"
                 f"<p class='small'><a href='/drafts?slug={E(run.slug)}'>Open on the draft desk →</a></p>")
    pains = "".join(f"<li><b>{E(p.pain_point)}</b> {pill(p.basis, 'hold')}<br><span class='small muted'>{E(p.reasoning)}</span></li>"
                    for p in (run.pain_points.pain_points if run.pain_points else []))
    sig = [x for x in feedback_loop.signals(s.output_dir) if x["slug"] == run.slug][::-1]
    fb = "".join(f"<div><span>{E(x['kind'].replace('_', ' '))} {E(str(x['data'].get('reason') or x['data'].get('tags') or ''))}</span><span class='muted'>{E(x['ts'][:16].replace('T', ' '))}</span></div>" for x in sig)
    ov = feedback_loop.overrides(s.output_dir).get(run.slug)
    lockd = "disabled title='Local control panel only'" if PUBLIC else ""
    reasons = "<br>".join(E(r) for r in (q.qualification_reasoning[:3] if q else []))
    return f"""<p><a class="btn ghost sm" href="/companies">← Accounts</a></p>
<div class="row" style="justify-content:space-between;align-items:flex-end"><div><h1>{E(run.company)}</h1><p class="sub">{E(run.domain)}</p></div>{pill(st, STATUS_TONE.get(st, 'hold'))}</div>
<p class="lede">{reasons}</p>
<div class="grid g6">
<div class="kpi"><span>Funding stage</span><b style="font-size:26px">{E(prof.funding_stage.value if prof and prof.funding_stage.value else 'unknown')}</b><i>{E(prof.employee_range.value or '') if prof else ''}</i></div>
<div class="kpi"><span>Gate</span><b style="font-size:26px">{E(GATE_LABEL.get(q.gate_decision, 'n/a') if q else 'n/a')}</b><i>{'human override' if ov else 'rules'}</i></div>
<div class="kpi"><span>ICP fit</span><b>{q.icp_fit_score if q else 'n/a'}</b><i>/100</i></div>
<div class="kpi"><span>Timing</span><b>{q.buying_timing_score if q else 'n/a'}</b><i>/100</i></div>
<div class="kpi"><span>Confidence</span><b>{f'{q.evidence_confidence:.2f}' if q else 'n/a'}</b><i>0 to 1</i></div>
<div class="kpi"><span>Pages read</span><b>{pages}</b><i>budget {budget}</i></div></div>
<div class="tabs"><a href="#trail">How it decided</a><a href="#scores">Scores</a><a href="#contact">Who to write to</a><a href="#email">Email</a><a href="#feedback">Your input ({len(sig)})</a></div>
<section class="card trail" id="trail"><h2>How it decided</h2><p class="hint">Question by question: the answer, why, and the line on their site that backs it.</p>{trail or "<p class='muted'>Not evaluated.</p>"}</section>
<section class="card" id="scores"><h2>Score breakdown</h2><div class="tw"><table>{crit}</table></div></section>
<section class="card" id="contact"><h2>Who to write to</h2>{contact}{f"<h3 style='margin-top:12px'>Likely problems</h3><ul>{pains}</ul>" if pains else ''}</section>
<section class="card" id="email"><h2>Email</h2>{email}</section>
<section class="card" id="feedback"><h2>Your input</h2>
<form method="post" action="/override" class="row">{tok()}<input type="hidden" name="slug" value="{E(run.slug)}">
<input type="text" name="reason" placeholder="Reason (required)" style="min-width:260px">
<button class="btn sm" name="decision" value="QUALIFY" {lockd}>Mark as qualified</button><button class="btn ghost sm" name="decision" value="DROP" {lockd}>Mark out of scope</button></form>
{f"<p class='hint'>Current override: <b>{E(ov['decision'])}</b> · {E(ov['reason'])}. Re-run to apply it to drafting.</p>" if ov else ''}
<form method="post" action="/rerun" style="margin-top:8px">{tok()}<input type="hidden" name="slug" value="{E(run.slug)}"><button class="btn ghost sm" {lockd}>Research again</button>
<a class="btn ghost sm" href="/report/{E(run.slug)}">Full markdown report</a></form>
<div class="feed" style="margin-top:12px">{fb or "<p class='muted small'>No input on this account yet.</p>"}</div></section>"""


@app.get("/companies/<slug>")
def company(slug: str):
    s = settings()
    _, runs, reviews = load(s)
    run = next((r for r in runs if r.slug == slugify(slug)), None)
    if not run:
        abort(404)
    return layout(run.company, "companies", company_body(s, run, reviews), s, runs, reviews)


@app.get("/review")
def review_page():
    s = settings()
    _, runs, reviews = load(s)
    lockd = "disabled title='Local control panel only'" if PUBLIC else ""
    cards = ""
    for r in runs:
        if status_of(r, reviews.get(r.slug)) != "Flagged":
            continue
        q = r.qualification
        why = run_history.human_reasons(r)
        unknown = "".join(f"<div class='check'><div>{ans_pill(a['answer'], a.get('role', 'core'))}</div><div><div class='what'>{E(a['question'])}</div>"
                          f"<div class='rule'>{E(a['basis'])}</div>{''.join(quote(x) for x in a['evidence'][:1])}</div></div>"
                          for a in q.evidence_map if a.get("role") in ("gate", "core") or a.get("core"))
        cards += f"""<section class="card"><div class="row" style="justify-content:space-between"><div><h2>{E(r.company)}</h2>
<span class="muted small">{E(r.domain)} · {E(', '.join(why))}</span></div>{pill('Flagged', 'flag')}</div><div class="trail">{unknown}</div>
<form method="post" action="/override" class="row" style="margin-top:10px">{tok()}<input type="hidden" name="slug" value="{E(r.slug)}">
<input type="hidden" name="flagged_for" value="{E(why[0] if why else '')}"><input type="text" name="reason" placeholder="Your reason (needed)" style="min-width:300px;flex:1">
<button class="btn lime sm" name="decision" value="QUALIFY" {lockd}>It qualifies</button><button class="btn ghost sm" name="decision" value="DROP" {lockd}>Out of scope</button></form>
<form method="post" action="/rerun" style="margin-top:6px">{tok()}<input type="hidden" name="slug" value="{E(r.slug)}"><button class="btn ghost sm" {lockd}>Research again</button>
<a class="btn ghost sm" href="/companies/{E(r.slug)}">See how it decided</a></form></section>"""
    body = f"""<h1>Decision desk</h1>
<p class="lede">These accounts have a gap the Evidence Map could not close. Settle each one and say why. When you settle the same kind of gap the same way twice, the learning log suggests a rule.</p>
{cards or "<section class='card'><p class='muted'>Your desk is clear. The map settled every account on its own.</p></section>"}"""
    return layout("Review queue", "review", body, s, runs, reviews)


@app.get("/drafts")
def drafts_page():
    s = settings()
    _, runs, reviews = load(s)
    by_slug = {r.slug: r for r in runs}
    pend = [rv for rv in reviews.values() if rv["status"] == "pending" and rv["slug"] in by_slug]
    done = [rv for rv in reviews.values() if rv["status"] != "pending" and rv["slug"] in by_slug]
    sel = request.args.get("slug") or (pend[0]["slug"] if pend else (done[0]["slug"] if done else ""))
    lst = "".join(f"<a class='{'on' if rv['slug'] == sel else ''}' href='/drafts?slug={E(rv['slug'])}'><b>{E(rv['company'])}</b>"
                  f"<span>{E(by_slug[rv['slug']].contact_selection.contact.full_name)} · {E(rv['status'])}</span></a>" for rv in pend + done)
    pane = "<p class='muted'>No drafts yet.</p>"
    lockd = "disabled title='Local control panel only'" if PUBLIC else ""
    if sel and sel in reviews and sel in by_slug:
        rv, run = reviews[sel], by_slug[sel]
        e, c = run.email, run.contact_selection.contact
        try:
            subject, body = review_gate.read_edited(sel, s.output_dir)
        except Exception:
            subject, body = rv.get("approved_subject") or e.subject, rv.get("approved_body") or e.email_body
        decided = rv["status"] != "pending" or PUBLIC
        flags = "".join(f"<li>{E(f)}</li>" for f in rv.get("flags", []))
        claims = "".join(f"<li><span class='small'>{E(t.sentence)}</span> <span class='muted small'>· {E(t.purpose)}</span> "
                         f"{src_link(t.source_url) if t.source_url else ''}</li>" for t in e.evidence_to_email_trace)
        pains = "".join(f"<li class='small'>{E(p.pain_point)} {pill(p.basis, 'hold')}</li>" for p in run.pain_points.pain_points)
        tags = "".join(f"<label><input type='checkbox' name='tags' value='{t}'>{t}</label>" for t in feedback_loop.RATING_TAGS)
        ratings = [x for x in feedback_loop.signals(s.output_dir) if x["slug"] == sel and x["kind"] == "draft_rating"]
        last_rating = (f"<p class='hint'>Last verdict: {'works' if ratings[-1]['data']['thumbs'] == 'up' else 'does not work'} {E(', '.join(ratings[-1]['data']['tags']))}</p>"
                       if ratings else "")
        applied = rv.get("learnings_applied") or e.learnings_applied
        pane = f"""<div class="row" style="justify-content:space-between"><div><h2>{E(rv['company'])}</h2>
<span class="muted small">Goes to your test inbox · written for {E(c.full_name)}, {E(c.job_title)}</span></div>{pill(rv['status'], 'go' if rv['status'] == 'approved' else 'stop' if rv['status'] == 'rejected' else 'hold')}</div>
{f"<div class='gatecard' style='margin:12px 0'><b>Settle these first</b><ul class='small'>{flags}</ul></div>" if flags else ''}
{f"<p class='hint'>{len(applied)} lesson(s) from earlier sign-offs already shaped this draft.</p>" if applied else ''}
<form method="post" action="/review">{tok()}<input type="hidden" name="slug" value="{E(sel)}">
<label class="lbl" for="subj">Subject</label><input id="subj" type="text" name="subject" class="full" value="{E(subject)}" {'readonly' if decided else ''}>
<label class="lbl" for="bodytxt">Body · {e.word_count} words{f" · {100 * rv['change_ratio']:.0f}% edited" if rv.get('change_ratio') is not None else ''}</label>
<textarea id="bodytxt" name="body" {'readonly' if decided else ''}>{E(body)}</textarea>
{'' if decided else f'''<div class="row" style="margin-top:10px"><button class="btn lime" name="action" value="approve">Sign off</button>
<button class="btn ghost" name="action" value="save">Save edits</button><input type="text" name="reason" placeholder="Why not, if declining">
<button class="btn ghost" name="action" value="reject">Decline</button>
<label class="muted small"><input type="checkbox" name="send" value="1" {"disabled" if s.dry_run else ""}> also send a test to my inbox{" (turn off DRY_RUN to enable)" if s.dry_run else ""}</label></div>'''}</form>
<section class="section"><h3>Quick verdict</h3><p class="hint">Tick what applies. The same tick on two drafts becomes a lesson for the writer.</p>
<form method="post" action="/rate">{tok()}<input type="hidden" name="slug" value="{E(sel)}"><div class="tags">{tags}</div>
<div class="row" style="margin-top:10px"><button class="btn sm" name="thumbs" value="up" {lockd}>Works</button><button class="btn ghost sm" name="thumbs" value="down" {lockd}>Doesn't work</button></div></form>{last_rating}</section>
<div class="grid g2 section"><section><h3>Why them</h3><p class="small">{E(run.contact_selection.selection_reasoning)}</p>
<h3 style="margin-top:12px">The opening fact</h3><p class="small">{E(e.personalisation_hook)} {src_link(e.hook_source_url)}</p><h3 style="margin-top:12px">Likely problems</h3><ul>{pains}</ul></section>
<section><h3>Line by line</h3><p class="hint">What each sentence is doing, and its source.</p><ul>{claims}</ul></section></div>"""
    stages = "".join(f"<option>{x}</option>" for x in ALL_OUTCOMES)
    sent_rows = "".join(f"<tr><td><b>{E(rv['company'])}</b></td><td class='small'>{E(rv.get('approved_subject') or '')}</td><td class='small muted'>{E(rv.get('decided', '')[:16].replace('T', ' '))}</td>"
                        f"<td class='n'>{100 * rv.get('change_ratio', 0):.0f}%</td><td><form method='post' action='/outcome' class='row'>{tok()}<input type='hidden' name='slug' value='{E(rv['slug'])}'>"
                        f"<select name='stage'>{stages}</select><button class='btn ghost sm' {lockd}>Log</button></form></td></tr>"
                        for rv in done if rv["status"] == "approved")
    body = f"""<h1>Draft desk</h1>
<p class="lede">Read, tweak and sign off. Your changes are recorded so the next drafts need fewer of them. A signed-off email can only go to your own test inbox.</p>
<div class="split"><nav class="list">{lst or "<p class='muted'>No drafts.</p>"}</nav><section class="card" style="margin:0">{pane}</section></div>
<section class="card"><h2>Signed off</h2><p class="hint">When real outreach happens, log the reply here. Real replies count for more than any edit.</p>
<div class="tw"><table><thead><tr><th>Company</th><th>Subject</th><th>Signed off</th><th>Rewritten</th><th>What happened</th></tr></thead>
<tbody>{sent_rows or "<tr><td colspan=5 class='muted'>Nothing signed off yet.</td></tr>"}</tbody></table></div></section>"""
    return layout("Drafts", "drafts", body, s, runs, reviews)


@app.get("/loop")
def loop_page():
    s = settings()
    _, runs, reviews = load(s)
    feedback_loop.learn(s.output_dir, list(reviews.values()))
    L = feedback_loop.loop_stats(s.output_dir, list(reviews.values()))
    learns = feedback_loop.load_learnings(s.output_dir)
    sig = feedback_loop.signals(s.output_dir)
    lockd = "disabled title='Local control panel only'" if PUBLIC else ""
    stages = [("1", "Write", L["act"], "drafts produced"), ("2", "React", L["signal"], "changes, ticks, decisions, replies"),
              ("3", "Log", sum(L["capture"].values()), "reactions on file"), ("4", "Distil", L["store"], "lessons switched on"),
              ("5", "Recall", L["retrieve"], "times a lesson was loaded"), ("6", "Use", L["apply"], "drafts changed by a lesson")]
    st = "".join(f"<div class='stage'><small>{n}</small><h2 class='stage-t'>{t}</h2><b>{v}</b><p>{d}</p></div>" for n, t, v, d in stages)
    kinds = "".join(f"<div class='row' style='justify-content:space-between'><span>{E(k.replace('_', ' '))}</span><b>{v}</b></div>" for k, v in Counter(x["kind"] for x in sig).most_common())
    lrows = "".join(f"<tr><td>{pill(l['scope'], 'hold')}<br><span class='small muted'>{E(l['kind'].replace('_', ' '))}</span></td><td class='small'>{E(l['lesson'])}</td>"
                    f"<td class='small muted'>{E(l.get('applies_to', ''))}</td><td class='n'>{l['support']}</td><td class='n'>{l.get('used', 0)}</td>"
                    f"<td>{pill(l['status'], 'go' if l['status'] == 'active' else 'stop')}</td><td>"
                    + (f"<form method='post' action='/retire'>{tok()}<input type='hidden' name='id' value='{E(l['id'])}'><button class='btn ghost sm' {lockd}>Switch off</button></form>" if l['status'] == 'active' else '')
                    + "</td></tr>" for l in learns)
    feed = "".join(f"<div><span><b>{E(x['kind'].replace('_', ' '))}</b> · {E(x['company'])} {E(str(x['data'].get('tags') or x['data'].get('reason') or ''))}</span>"
                   f"<span class='muted'>{E(x['actor'])} · {E(x['ts'][5:16].replace('T', ' '))}</span></div>" for x in sig[::-1][:40])
    fmt = lambda v: "None yet" if v is None else f"{100 * v:.0f}%"  # noqa: E731
    body = f"""<h1>Learning log</h1>
<p class="lede">Write, react, log, distil, recall, use. A lesson needs the same reaction on at least {feedback_loop.MIN_SUPPORT} different accounts; a single edit never changes how drafts are written.</p>
<p>{pill(f"{L['stages_with_data']} of 6 parts have data", 'go' if L['stages_with_data'] == 6 else 'hold')}</p>
<div class="loop">{st}</div>
<div class="grid g2" style="margin-top:14px"><section class="card" style="margin:0"><h2>Are the lessons paying off?</h2><p class="hint">How much of each signed-off draft you rewrote</p>
<div class="grid g2"><div class="stat"><b style="font-size:40px">{fmt(L['edit_without'])}</b><span><strong>No lesson used</strong> {L['n_without']} signed off</span></div>
<div class="stat"><b style="font-size:40px">{fmt(L['edit_with'])}</b><span><strong>Lesson used</strong> {L['n_with']} signed off</span></div></div>
<p class="hint">If the right-hand number is lower, the lessons are saving you edits. With few sign-offs this moves a lot.</p></section>
<section class="card" style="margin:0"><h2>Reactions logged</h2><p class="hint">{len(sig)} so far</p>{kinds or "<p class='muted small'>Nothing logged yet.</p>"}</section></div>
<section class="card"><h2>Lessons kept</h2><p class="hint">Switch a lesson off at any time; switched-off lessons stay listed so you can see what changed.</p>
<div class="tw"><table><thead><tr><th>Area</th><th>Lesson</th><th>Where</th><th>Backed by</th><th>Times used</th><th>State</th><th></th></tr></thead>
<tbody>{lrows or "<tr><td colspan=7 class='muted'>No lessons yet. They appear once you make the same change or tick on two accounts.</td></tr>"}</tbody></table></div></section>
<section class="card"><h2>The six parts</h2><ol class="small">
<li><b>Write:</b> the engine drafts emails and answers the Evidence Map.</li>
<li><b>React:</b> you change a draft, tick a verdict, decline it, settle a gap on the decision desk, or log a reply.</li>
<li><b>Log:</b> every reaction is written to <code>output/feedback/signals.jsonl</code>.</li>
<li><b>Distil:</b> before each run, sentences you swapped or cut on two or more accounts, repeated ticks and repeated desk decisions become lessons.</li>
<li><b>Recall:</b> lessons that are switched on are loaded before each draft.</li>
<li><b>Use:</b> sentence swaps and cuts are made for you (never to the opening fact), the rest is passed to Claude as guidance, and each use is counted.</li></ol></section>
<section class="card"><h2>Everything you have done</h2><div class="feed">{feed or "<p class='muted small'>Nothing logged yet.</p>"}</div></section>"""
    return layout("Feedback loop", "loop", body, s, runs, reviews)


@app.get("/report/<slug>")
def report(slug: str):
    s = settings()
    path = s.output_dir / "company_reports" / f"{slugify(slug)}.md"
    if not path.exists():
        abort(404)
    _, runs, reviews = load(s)
    return layout("Report", "companies", f"<p><a class='btn ghost sm' href='/companies/{E(slugify(slug))}'>← Back</a></p><pre class='md'>{E(path.read_text())}</pre>", s, runs, reviews)


@app.get("/result/<slug>")
def result(slug: str):
    return company(slug)


@app.get("/status")
def status():
    return {"running": JOB["running"], "title": JOB["title"], "lines": JOB["lines"][-40:], "error": JOB["error"]}


# ================================================================ actions

def _parse_domains(raw: str) -> tuple[list[str], list[str]]:
    good, bad = [], []
    for part in re.split(r"[\s,]+", raw or ""):
        if not part:
            continue
        d = normalise_domain(part)
        (good if DOMAIN_RX.match(d) else bad).append(d if DOMAIN_RX.match(d) else part)
    return list(dict.fromkeys(good)), bad


@app.post("/research")
def research():
    check_token()
    raw = request.form.get("domains") or request.form.get("domain") or ""
    domains, bad = _parse_domains(raw)
    if bad or not domains:
        FLASH.append(f"'{raw.strip()[:80]}' is not a valid website address. Use a domain such as acme.com.")
        return redirect(url_for("run_page"))
    domains = domains[: (1 if PUBLIC else MAX_DOMAINS)]
    name = (request.form.get("company") or "").strip()[:80]
    targets = [((name if (name and len(domains) == 1) else d.split(".")[0].replace("-", " ").title()), d) for d in domains]
    if PUBLIC:
        return research_now(*targets[0])
    added = [add_to_prospects(c, d) for c, d in targets] if request.form.get("keep") else []
    if start_job("Researching " + ", ".join(c for c, _ in targets), targets):
        FLASH.append(f"Research started for {', '.join(f'{c} ({d})' for c, d in targets)}."
                     + (" Added to the prospect list." if any(added) else ""))
    return redirect(url_for("run_page"))


def research_now(company_name: str, domain: str):
    """Public mode: run inside this request (serverless has no background workers) and show the result."""
    ip = (request.headers.get("x-forwarded-for") or request.remote_addr or "?").split(",")[0].strip()
    if rate_limited(ip):
        FLASH.append(f"Limit reached: {PUBLIC_RUNS_PER_HOUR} research runs per hour per visitor. Try again later.")
        return redirect(url_for("run_page"))
    if not LOCK.acquire(blocking=False):
        FLASH.append("Another visitor's research is running right now. Try again in a minute.")
        return redirect(url_for("run_page"))
    try:
        s = settings()
        lines: list[str] = []
        Pipeline(s, make_llm(s), send_test=False, on_event=lines.append).run([(company_name, domain)], mode="public")
        JOB.update(title=f"Researched {company_name}", lines=lines, finished=dt.datetime.now())
    except Exception as exc:
        FLASH.append(f"Research failed ({exc.__class__.__name__}). The site may be blocking automated readers.")
        return redirect(url_for("run_page"))
    finally:
        LOCK.release()
    # Render in the same response: on serverless the next request may reach an instance without this sandbox.
    return company(slugify(domain))


@app.post("/find")
def find():
    check_token()
    if (r := local_only("run_page")):
        return r
    s = settings()
    target = max(1, min(3, request.form.get("target", type=int) or 3))
    known = {r.company for r in Pipeline(s, None).load_all()}

    def work(s, pipe):
        from src.scraper import clean_html
        def fetch(url):
            res = pipe.scraper.fetch(url)
            return res["status"] == "ok", clean_html(res.get("body", ""))[0] if res["status"] == "ok" else ""
        leads, notes = funding_leads(s.serper_api_key, known, fetch=fetch)
        for n in notes:
            JOB["lines"].append(n)
        LEADS.update(items=leads, notes=notes, searched=dt.datetime.now())
        qualified = 0
        for lead in [l for l in leads if l.domain][:10]:
            JOB["lines"].append(f"→ {lead.name} ({lead.domain}) · {lead.stage} · rank {lead.rank}")
            out, _ = pipe.run([(lead.name, lead.domain)], mode="find")
            if out and out[0].qualification and out[0].qualification.qualified:
                qualified += 1
                if qualified >= target:
                    JOB["lines"].append(f"Target reached: {qualified} qualified.")
                    break

    start_job(f"Scanning funding news until {target} qualify", [], work=work)
    return redirect(url_for("run_page"))


@app.post("/leads")
def leads():
    check_token()
    if (r := local_only("run_page")):
        return r
    s = settings()
    known = {r.domain for r in Pipeline(s, None).load_all()} | {d for _, d in read_prospects(ROOT / "data" / "prospects.csv")}
    items, notes = find_leads(s.serper_api_key, known)
    LEADS.update(items=items, notes=notes, searched=dt.datetime.now())
    return redirect(url_for("run_page"))


@app.post("/rerun")
def rerun():
    check_token()
    if (r := local_only("run_page")):
        return r
    s = settings()
    slug = request.form.get("slug", "")
    targets = [(r.company, r.domain) for r in Pipeline(s, None).load_all() if slug in ("__all__", r.slug)]
    if not targets:
        FLASH.append("Nothing to re-run.")
    elif start_job("Re-running research for " + ("every company" if slug == "__all__" else targets[0][0]), targets):
        FLASH.append("Re-run started.")
    return redirect(url_for("run_page"))


@app.post("/override")
def override():
    check_token()
    if (r := local_only("review_page")):
        return r
    s = settings()
    slug = request.form.get("slug", "")
    run = next((r for r in Pipeline(s, None).load_all() if r.slug == slug), None)
    if not run:
        abort(404)
    try:
        ov = feedback_loop.set_override(s.output_dir, slug, run.company, request.form.get("decision", ""),
                                        request.form.get("reason", ""), request.form.get("flagged_for", ""))
    except ValueError as exc:
        FLASH.append(f"Not saved: {exc}")
        return redirect(request.referrer or url_for("review_page"))
    if ov["decision"] == "QUALIFY":
        start_job(f"Re-running {run.company} with your QUALIFY override", [(run.company, run.domain)])
        FLASH.append(f"{run.company}: marked as qualified by you. Researching again so it gets a contact and a draft.")
    else:
        pipe = Pipeline(s, None)
        run.qualification = feedback_loop.apply_override(run.qualification, ov)
        pipe._save(run)
        write_outputs(pipe.load_all(), s.output_dir)
        FLASH.append(f"{run.company}: marked out of scope by you. Logged in the learning log.")
    return redirect(url_for("review_page"))


@app.post("/review")
def review():
    check_token()
    if (r := local_only("drafts_page")):
        return r
    s = settings()
    slug, action = request.form.get("slug", ""), request.form.get("action")
    pipe = Pipeline(s, None, send_test=bool(request.form.get("send")) and not s.dry_run)
    run = next((r for r in pipe.load_all() if r.slug == slug), None)
    if not run or not run.email:
        abort(404)
    try:
        if action == "reject":
            rec = review_gate.reject(slug, s.output_dir, (request.form.get("reason") or "").strip()[:300])
            from src.models import DispatchResult
            run.dispatch = DispatchResult(status="rejected_at_review", detail=f"Rejected at review: {rec['reason']}")
            pipe._save(run)
            FLASH.append(f"Rejected the {run.company} draft.")
        else:
            review_gate.write_edited(slug, s.output_dir, request.form.get("subject", ""), request.form.get("body", ""))
            if action == "approve":
                rec = review_gate.approve(slug, s.output_dir)
                res = pipe.send_reviewed(run)
                pipe._save(run)
                FLASH.append(f"Approved {run.company}: {rec['change_ratio']:.0%} of the draft changed"
                             + (" (heavy edit)." if rec["heavy_edit"] else ".") + f" Dispatch: {res.status.replace('_', ' ')}.")
            else:
                FLASH.append(f"Saved your edits to the {run.company} draft.")
    except ValueError as exc:
        FLASH.append(f"Not done: {exc}")
    write_outputs(pipe.load_all(), s.output_dir)
    return redirect(url_for("drafts_page", slug=slug))


@app.post("/rate")
def rate():
    check_token()
    if (r := local_only("drafts_page")):
        return r
    s = settings()
    slug = request.form.get("slug", "")
    run = next((r for r in Pipeline(s, None).load_all() if r.slug == slug), None)
    if not run:
        abort(404)
    try:
        feedback_loop.rate(s.output_dir, slug, run.company, request.form.get("thumbs", ""), request.form.getlist("tags"))
        FLASH.append(f"Verdict saved for {run.company}.")
    except ValueError as exc:
        FLASH.append(f"Not saved: {exc}")
    return redirect(url_for("drafts_page", slug=slug))


@app.post("/retire")
def retire():
    check_token()
    if (r := local_only("loop_page")):
        return r
    feedback_loop.retire(settings().output_dir, request.form.get("id", ""))
    FLASH.append("Lesson switched off. It stays listed but will not be used.")
    return redirect(url_for("loop_page"))


@app.post("/outcome")
def outcome():
    check_token()
    if (r := local_only("drafts_page")):
        return r
    s = settings()
    runs = {r.slug: r for r in Pipeline(s, None).load_all()}
    run = runs.get(request.form.get("slug", ""))
    if not run:
        abort(404)
    value = request.form.get("deal_value") or None
    try:
        row = record_outcome(s.outcomes_csv, run.company, request.form.get("stage", ""), float(value) if value else None,
                             domain=run.domain, notes=(request.form.get("notes") or "")[:200])
        feedback_loop.log_signal(s.output_dir, "outcome", run.slug, run.company, {"stage": row["stage"], "deal_value": row["deal_value"]})
        from main import run_revenue
        run_revenue(s, list(runs.values()), header=False)
        FLASH.append(f"Logged: {row['company']} → {row['stage']}" + (f" ({row['deal_value']})" if row["deal_value"] else ""))
    except ValueError as exc:
        FLASH.append(f"Not logged: {exc}")
    return redirect(url_for("drafts_page"))


@app.post("/publish")
def publish():
    check_token()
    if (r := local_only("run_page")):
        return r
    import export_site
    export_site.main()
    if not shutil.which("vercel"):
        FLASH.append("Dashboard rebuilt locally, but the Vercel CLI isn't installed, so nothing was deployed.")
        return redirect(url_for("run_page"))
    try:
        out = subprocess.run(["vercel", "deploy", "--prod", "--yes"], cwd=ROOT / "sprinto-dashboard",
                             capture_output=True, text=True, timeout=300)
        alias = re.search(r"Aliased\s+(https://\S+)", out.stdout + out.stderr)
        FLASH.append(f"Published: {alias.group(1)}" if alias else "Deploy finished; check the Vercel dashboard for the link.")
    except Exception as exc:
        FLASH.append(f"Deploy failed ({exc.__class__.__name__}).")
    return redirect(url_for("run_page"))


if __name__ == "__main__":
    import logging
    # The page polls /status every few seconds for the live log; keep those lines out of the terminal.
    logging.getLogger("werkzeug").addFilter(lambda rec: "GET /status" not in rec.getMessage())
    print("Control panel: http://127.0.0.1:5050  (local only, Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=5050, debug=False)
