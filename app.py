"""Sprinto Signal Engine control panel: a local web app for running research without the command line.

    .venv/bin/python app.py        # then open http://127.0.0.1:5050

What you can do from it:
  * Research a company: type a name and website, the full pipeline runs on it.
  * Find more leads: search for SaaS companies showing audit signals (needs SERPER_API_KEY), then research any of them.
  * Re-run research for one company or all of them.
  * Review drafts: edit, approve or reject (the human review gate).
  * Log an outcome (contacted, opened, replied, meeting, opportunity, won, lost).
  * Publish: rebuild the public dashboard and deploy it to Vercel.

It only listens on 127.0.0.1 (your own machine) and every form carries a per-session token, so other websites
cannot trigger runs. Sending still obeys every safety rule: test inbox only, DRY_RUN respected, guard enforced.

PUBLIC_MODE=1 (the online deployment) makes it safe to open to anyone without a password:
  * "Research a company" works, rate-limited, writing only to a temporary sandbox (OUTPUT_DIR, default /tmp);
    it starts from a bundled read-only snapshot of the real results and never touches the operator's data;
  * nothing can be sent: DRY_RUN is forced on and TEST_TO_EMAIL is blanked, so the recipient guard blocks every send;
  * actions that change real data or spend credits (approve/reject, outcomes, re-run all, lead search, publish)
    are disabled and point to the local panel.
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

from pathlib import Path

from flask import Flask, abort, redirect, request, url_for

from config import ROOT, load_settings, setup_logging
from export_site import E, GATE_LABEL, GATE_TONE, pill
from src import review_gate
from src.decision_ledger import write_outputs
from src.lead_finder import find_leads
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
LOCAL_ONLY = "This action changes real data or spends credits, so it is only available in the local control panel."
DOMAIN_RX = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
JOB = {"running": False, "title": "", "lines": [], "started": None, "finished": None, "error": None}
LEADS: dict = {"items": [], "notes": [], "searched": None}
FLASH: list[str] = []
LOCK = threading.Lock()


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


def local_only():
    if PUBLIC:
        FLASH.append(LOCAL_ONLY)
        return redirect(url_for("home"))
    return None


def check_token():
    if request.form.get("token") != TOKEN:
        abort(403)


def add_to_prospects(company: str, domain: str) -> bool:
    s = settings()
    path = ROOT / "data" / "prospects.csv"
    if domain in {d for _, d in read_prospects(path)}:
        return False
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([company, domain])
    return True


def start_job(title: str, prospects: list[tuple[str, str]], resume: bool = False) -> bool:
    with LOCK:
        if JOB["running"]:
            FLASH.append("A run is already in progress. Wait for it to finish.")
            return False
        JOB.update(running=True, title=title, lines=[], started=dt.datetime.now(), finished=None, error=None)

    def work():
        try:
            s = settings()
            llm = make_llm(s)
            JOB["lines"].append("Claude: on" if llm else "Claude not configured: labelled rule-based fallback")
            pipe = Pipeline(s, llm, send_test=False, on_event=JOB["lines"].append)
            pipe.run(prospects, resume=resume)
            from main import run_revenue  # refresh revenue outputs for every saved company
            run_revenue(s, pipe.load_all(), header=False)
            JOB["lines"].append("Done. Reports, ledger and revenue updated.")
        except Exception as exc:
            JOB["error"] = f"{exc.__class__.__name__}: {exc}"
            JOB["lines"].append(traceback.format_exc(limit=2))
        finally:
            JOB.update(running=False, finished=dt.datetime.now())

    threading.Thread(target=work, daemon=True).start()
    return True


# ---------------------------------------------------------------- actions

@app.post("/research")
def research():
    check_token()
    company = (request.form.get("company") or "").strip()[:80]
    domain = normalise_domain(request.form.get("domain") or "")
    if not DOMAIN_RX.match(domain):
        FLASH.append(f"'{E(request.form.get('domain', ''))}' is not a valid website domain (example: acme.com).")
        return redirect(url_for("home"))
    company = company or domain.split(".")[0].replace("-", " ").title()
    if PUBLIC:
        return research_now(company, domain)
    added = add_to_prospects(company, domain) if request.form.get("keep") else False
    if start_job(f"Researching {company}", [(company, domain)]):
        FLASH.append(f"Research started for {company} ({domain})." + (" Added to the prospect list." if added else ""))
    return redirect(url_for("home") + "#job")


def research_now(company: str, domain: str):
    """Public mode: run inside this request (serverless has no background workers) and show the result."""
    ip = (request.headers.get("x-forwarded-for") or request.remote_addr or "?").split(",")[0].strip()
    if rate_limited(ip):
        FLASH.append(f"Limit reached: {PUBLIC_RUNS_PER_HOUR} research runs per hour per visitor. Try again later.")
        return redirect(url_for("home"))
    if not LOCK.acquire(blocking=False):
        FLASH.append("Another visitor's research is running right now. Try again in a minute.")
        return redirect(url_for("home"))
    try:
        s = settings()
        lines: list[str] = []
        Pipeline(s, make_llm(s), send_test=False, on_event=lines.append).run([(company, domain)])
        JOB.update(title=f"Researched {company}", lines=lines, finished=dt.datetime.now())
    except Exception as exc:
        FLASH.append(f"Research failed ({exc.__class__.__name__}). The site may be blocking automated readers.")
        return redirect(url_for("home"))
    finally:
        LOCK.release()
    # Render in the same response: on serverless the next request may reach an instance without this sandbox.
    return result(slugify(domain))


@app.get("/result/<slug>")
def result(slug: str):
    s = settings()
    run = next((r for r in Pipeline(s, None).load_all() if r.slug == slugify(slug)), None)
    if not run or not run.qualification:
        abort(404)
    q = run.qualification
    glyph = {"yes": "●", "no": "○", "unknown": "◌"}
    answers = "".join(
        f"<div class='lead' style='grid-template-columns:1fr'><div><b>{glyph[a['answer']]} {E(a['question'])}</b> "
        f"<span class='muted'>{a['answer'].upper()}</span><p>{E(a['basis'])}</p>"
        + "".join(f"<p>“{E(x.rpartition(' — ')[0].strip(chr(34)))}” <span class='muted'>{E(x.rpartition(' — ')[2])}</span></p>" for x in a["evidence"])
        + "</div></div>" for a in q.evidence_map)
    cs = run.contact_selection
    who = f"{E(cs.contact.full_name)}, {E(cs.contact.job_title)}" if cs and cs.contact else "No decision-maker found on the public pages read."
    email = (f"<h2 style='margin-top:18px'>Draft email</h2><p class='hint'>Waiting at the review gate. It cannot be sent from here.</p>"
             f"<div class='log' style='background:var(--paper);color:var(--ink);border:1px solid var(--line)'>Subject: {E(run.email.subject)}\n\n{E(run.email.email_body)}</div>"
             if run.email else "<p class='hint'>No email drafted: no grounded hook or no decision-maker.</p>")
    log = E("\n".join(JOB["lines"][-30:])) if JOB.get("title", "").endswith(run.company) else ""
    return f"""{HEAD}<header class='top'><a class='brand' href='/' style='text-decoration:none'>Sprinto <em>Signal Engine</em></a>
<a class='btn ghost small' href='/'>← Research another company</a></header><main class='wrap'>
<span class='label'>(Result) {E(run.domain)}</span><h1>{E(run.company)} {pill(GATE_LABEL.get(q.gate_decision, q.gate_decision), GATE_TONE.get(q.gate_decision, 'hold'))}</h1>
<p class='hint' style='font-size:15px'>{E(q.qualification_reasoning[0].split(': ', 1)[-1] if q.qualification_reasoning else '')}</p>
<section class='card'><div class='grid2'><div><span class='label'>ICP fit</span><h2>{q.icp_fit_score}/100</h2></div>
<div><span class='label'>Buying timing</span><h2>{q.buying_timing_score}/100</h2></div>
<div><span class='label'>Evidence confidence</span><h2>{q.evidence_confidence:.2f}</h2></div>
<div><span class='label'>Decision-maker</span><p>{who}</p></div></div></section>
<section class='card'><h2>Evidence Map</h2>{answers}{email}
<p class='row'><a class='btn ghost small' href='/report/{E(run.slug)}'>Full research report</a></p></section>
{f"<section class='card'><h2>Run log</h2><div class='log'>{log}</div></section>" if log else ''}
<p class='hint'>Rule-based reading (Claude not configured on this demo); results are labelled and cite their sources.</p></main></body></html>"""


@app.post("/rerun")
def rerun():
    check_token()
    if (r := local_only()):
        return r
    s = settings()
    slug = request.form.get("slug", "")
    runs = Pipeline(s, None).load_all()
    targets = [(r.company, r.domain) for r in runs if slug in ("__all__", r.slug)]
    if not targets:
        FLASH.append("Nothing to re-run.")
    elif start_job("Re-running research for " + ("all companies" if slug == "__all__" else targets[0][0]), targets):
        FLASH.append("Re-run started.")
    return redirect(url_for("home") + "#job")


@app.post("/leads")
def leads():
    check_token()
    if (r := local_only()):
        return r
    s = settings()
    known = {r.domain for r in Pipeline(s, None).load_all()} | {d for _, d in read_prospects(ROOT / "data" / "prospects.csv")}
    items, notes = find_leads(s.serper_api_key, known)
    LEADS.update(items=items, notes=notes, searched=dt.datetime.now())
    return redirect(url_for("home") + "#leads")


@app.post("/review")
def review():
    check_token()
    if (r := local_only()):
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
    return redirect(url_for("home") + "#review")


@app.post("/outcome")
def outcome():
    check_token()
    if (r := local_only()):
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
        from main import run_revenue
        run_revenue(s, list(runs.values()), header=False)
        FLASH.append(f"Logged: {row['company']} → {row['stage']}" + (f" ({row['deal_value']})" if row["deal_value"] else ""))
    except ValueError as exc:
        FLASH.append(f"Not logged: {exc}")
    return redirect(url_for("home") + "#outcomes")


@app.post("/publish")
def publish():
    check_token()
    if (r := local_only()):
        return r
    import export_site
    export_site.main()
    if not shutil.which("vercel"):
        FLASH.append("Dashboard rebuilt locally, but the Vercel CLI isn't installed, so nothing was deployed.")
        return redirect(url_for("home"))
    try:
        out = subprocess.run(["vercel", "deploy", "--prod", "--yes"], cwd=ROOT / "sprinto-dashboard",
                             capture_output=True, text=True, timeout=300)
        alias = re.search(r"Aliased\s+(https://\S+)", out.stdout + out.stderr)
        FLASH.append(f"Published: {alias.group(1)}" if alias else "Deploy finished; check the Vercel dashboard for the link.")
    except Exception as exc:
        FLASH.append(f"Deploy failed ({exc.__class__.__name__}).")
    return redirect(url_for("home"))


@app.get("/report/<slug>")
def report(slug: str):
    path = settings().output_dir / "company_reports" / f"{slugify(slug)}.md"
    if not path.exists():
        abort(404)
    return f"{HEAD}<main class='wrap'><p><a href='/'>← Back to the control panel</a></p><pre class='md'>{E(path.read_text())}</pre></main>"


@app.get("/status")
def status():
    return {"running": JOB["running"], "title": JOB["title"], "lines": JOB["lines"][-40:], "error": JOB["error"]}


# ---------------------------------------------------------------- page

HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signal Engine Control Panel</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter+Tight:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--paper:#f3eee6;--card:#fbf8f3;--ink:#2a1f1a;--soft:#6f625a;--line:#e2d9cc;--lime:#e4ff5c;--limeink:#1d2400;
--go:#1f6b4a;--gobg:#e3efe5;--flag:#8a5a00;--flagbg:#f8ecd2;--hold:#3e4f7a;--holdbg:#e6e9f3;--stop:#9b2c1f;--stopbg:#f6e2dd;
--serif:"Instrument Serif",Georgia,serif;--sans:"Inter Tight",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--paper:#16110e;--card:#1f1915;--ink:#f1e9df;--soft:#a8998c;--line:#342b25;--gobg:#16301f;--go:#8fd8ad;
--flagbg:#33270d;--flag:#f0c46a;--holdbg:#1d2438;--hold:#a9b8e8;--stopbg:#3a1913;--stop:#f29a8a}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans)}a{color:inherit}
.wrap{max-width:1100px;margin:0 auto;padding:20px 20px 80px}
header.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 20px;border-bottom:1px solid var(--line)}
.brand{font-weight:700;font-size:17px}.brand em{font-family:var(--serif);font-weight:400;font-size:19px}
.label{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}
h1{font-family:var(--serif);font-weight:400;font-size:clamp(34px,5vw,54px);line-height:1;margin:18px 0 6px}
h2{font-family:var(--serif);font-weight:400;font-size:30px;margin:0 0 4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;margin:16px 0}
.hint{color:var(--soft);font-size:13.5px;margin:2px 0 14px}
form.inline{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input[type=text],input[type=number],select,textarea{font:inherit;color:var(--ink);background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:11px 14px}
input[type=text]{min-width:220px;flex:1}textarea{width:100%;min-height:190px;resize:vertical;line-height:1.55}
.btn{font:600 14px var(--sans);border-radius:999px;padding:11px 18px;cursor:pointer;border:1px solid var(--ink);background:var(--ink);color:var(--paper);text-decoration:none;display:inline-block}
.btn.lime{background:var(--lime);color:var(--limeink);border-color:var(--lime)}.btn.ghost{background:transparent;color:var(--ink)}
.btn.small{padding:7px 13px;font-size:13px}.btn:disabled{opacity:.45;cursor:not-allowed}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.pill:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.go{color:var(--go);background:var(--gobg)}.flag{color:var(--flag);background:var(--flagbg)}.hold{color:var(--hold);background:var(--holdbg)}.stop{color:var(--stop);background:var(--stopbg)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:11.5px;color:var(--soft);text-transform:uppercase;letter-spacing:.06em}td.n{font-variant-numeric:tabular-nums;font-weight:600}
.tw{overflow-x:auto}.flash{background:var(--lime);color:var(--limeink);border-radius:14px;padding:12px 16px;margin:14px 0;font-weight:500}
.log{background:var(--ink);color:var(--paper);border-radius:14px;padding:14px 16px;font:12.5px/1.5 ui-monospace,Menlo,monospace;max-height:320px;overflow:auto;white-space:pre-wrap}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.lead{border-top:1px solid var(--line);padding:12px 0;display:grid;grid-template-columns:1fr auto;gap:10px}
.lead b{font-size:16px}.lead p{margin:2px 0;color:var(--soft);font-size:13.5px}.flags{background:var(--flagbg);border-radius:12px;padding:10px 14px;margin:8px 0;font-size:13.5px}
.draft{border-top:1px dashed var(--line);padding-top:16px;margin-top:16px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
pre.md{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;font:13.5px/1.55 ui-monospace,Menlo,monospace}
.muted{color:var(--soft)}
@media (max-width:760px){.grid2{grid-template-columns:1fr}}
</style></head><body>"""


@app.get("/")
def home():
    s = settings()
    pipe = Pipeline(s, None)
    runs = sorted(pipe.load_all(), key=lambda r: r.company.lower())
    reviews = {r["slug"]: r for r in review_gate.all_records(s.output_dir)}
    flashes = "".join(f"<div class='flash'>{E(m)}</div>" for m in FLASH)
    FLASH.clear()
    tok = f"<input type='hidden' name='token' value='{TOKEN}'>"
    busy = "disabled" if JOB["running"] else ""
    lockd = "disabled title='Local control panel only'" if PUBLIC else busy
    note = f"<p class='hint'>{LOCAL_ONLY}</p>" if PUBLIC else ""

    rows = ""
    for r in runs:
        q = r.qualification
        gate = q.gate_decision if q else ""
        contact = r.contact_selection.contact.full_name if r.contact_selection and r.contact_selection.contact else "Not found"
        rv = reviews.get(r.slug, {}).get("status", "")
        rows += (f"<tr><td><b>{E(r.company)}</b><br><span class='muted'>{E(r.domain)}</span></td>"
                 f"<td>{pill(GATE_LABEL.get(gate, 'Not scored'), GATE_TONE.get(gate, 'hold'))}</td>"
                 f"<td class='n'>{q.icp_fit_score if q else ''}</td><td class='n'>{q.buying_timing_score if q else ''}</td>"
                 f"<td>{E(contact)}</td><td>{E(rv or (r.dispatch.status.replace('_', ' ') if r.dispatch else ''))}</td>"
                 f"<td><a class='btn ghost small' href='/report/{E(r.slug)}'>Report</a> "
                 f"<form method='post' action='/rerun' style='display:inline'>{tok}<input type='hidden' name='slug' value='{E(r.slug)}'>"
                 f"<button class='btn small' {lockd}>Re-run</button></form></td></tr>")

    lead_html = ""
    for c in LEADS["items"]:
        lead_html += (f"<div class='lead'><div><b>{E(c.name)}</b> <span class='muted'>{E(c.domain)}</span>"
                      f"<p>{E(c.snippet)}</p><p>Found on <a href='{E(c.found_on)}' target='_blank' rel='noopener'>{E(c.found_on[:80])}</a></p></div>"
                      f"<form method='post' action='/research'>{tok}<input type='hidden' name='company' value='{E(c.name)}'>"
                      f"<input type='hidden' name='domain' value='{E(c.domain)}'><input type='hidden' name='keep' value='1'>"
                      f"<button class='btn lime small' {busy}>Research</button></form></div>")
    lead_notes = "".join(f"<p class='hint'>{E(n)}</p>" for n in LEADS["notes"])

    drafts = ""
    for r in runs:
        rec = reviews.get(r.slug)
        if not (r.email and rec):
            continue
        subject = rec.get("approved_subject") or r.email.subject
        body = rec.get("approved_body") or r.email.email_body
        try:
            subject, body = review_gate.read_edited(r.slug, s.output_dir)
        except Exception:
            pass
        flags = "".join(f"<li>{E(f)}</li>" for f in rec.get("flags", []))
        decided = rec["status"] != "pending" or PUBLIC
        drafts += f"""<div class='draft'><div class='row'><h3 style='margin:0;font-family:var(--serif);font-weight:400;font-size:26px'>{E(r.company)}</h3>
          {pill(rec['status'], 'go' if rec['status'] == 'approved' else 'stop' if rec['status'] == 'rejected' else 'hold')}
          <span class='muted'>to {E(r.contact_selection.contact.full_name)}, {E(r.contact_selection.contact.job_title)}</span></div>
          {f"<div class='flags'><b>Check before approving:</b><ul>{flags}</ul></div>" if flags else ''}
          <form method='post' action='/review'>{tok}<input type='hidden' name='slug' value='{E(r.slug)}'>
          <p class='label' style='margin:12px 0 6px'>Subject</p><input type='text' name='subject' value='{E(subject)}' style='width:100%' {'readonly' if decided else ''}>
          <p class='label' style='margin:12px 0 6px'>Body</p><textarea name='body' {'readonly' if decided else ''}>{E(body)}</textarea>
          {"" if decided else f'''<div class='row'><button class='btn lime' name='action' value='approve'>Approve</button>
          <button class='btn ghost' name='action' value='save'>Save edits</button>
          <input type='text' name='reason' placeholder='Reason (if rejecting)' style='min-width:200px'>
          <button class='btn ghost' name='action' value='reject'>Reject</button>
          <label class='muted'><input type='checkbox' name='send' value='1' {"disabled" if s.dry_run else ""}> also send a test to my inbox
          {"(turn off DRY_RUN in .env to enable)" if s.dry_run else ""}</label></div>'''}
          </form>{f"<p class='hint'>Reviewer changed {rec['change_ratio']:.0%} of the draft.</p>" if rec.get('change_ratio') is not None else ''}</div>"""

    options = "".join(f"<option value='{E(r.slug)}'>{E(r.company)}</option>" for r in runs)
    stages = "".join(f"<option>{st}</option>" for st in ALL_OUTCOMES)
    job_lines = E("\n".join(JOB["lines"][-40:])) or "No run yet."

    return f"""{HEAD}<header class='top'><span class='brand'>Sprinto <em>Signal Engine</em> · control panel</span>
<span class='muted'>{'Public demo · sandbox, nothing is ever sent' if PUBLIC else 'Local only'} · Claude {'on' if s.claude_enabled else 'off (fallback)'} · DRY_RUN {str(s.dry_run).lower()} · review gate on</span></header>
<main class='wrap'>
<span class='label'>(Control panel)</span><h1>Research a company, find more leads, <em>run it again.</em></h1>
{flashes}
<section class='card' id='research'><h2>Research a company</h2>
<p class='hint'>Type a company and its website. The full pipeline runs: website, enrichment, Evidence Map, contact, pain point, draft (waits for review).</p>
<form class='inline' method='post' action='/research'>{tok}
<input type='text' name='company' placeholder='Company name (e.g. Vanta)'><input type='text' name='domain' placeholder='Website (e.g. acme.com)' required>
{"" if PUBLIC else "<label class='muted'><input type='checkbox' name='keep' value='1' checked> add to my prospect list</label>"}
<button class='btn lime' {busy} onclick="this.textContent='Researching… about a minute';this.form.submit();this.disabled=true">Research it →</button></form>
{"<p class='hint'>Public demo: results go to a temporary sandbox and are not saved permanently. Up to 4 runs per hour per visitor. Nothing is ever emailed.</p>" if PUBLIC else ""}</section>

<section class='card' id='job'><div class='row' style='justify-content:space-between;margin:0'><h2>Current run</h2>
<span id='jstate'>{pill('Running' if JOB['running'] else 'Idle', 'flag' if JOB['running'] else 'go')}</span></div>
<p class='hint' id='jtitle'>{E(JOB['title'] or 'Nothing running.')}</p><div class='log' id='jlog'>{job_lines}</div></section>

<section class='card' id='leads'><h2>Find more leads</h2>
<p class='hint'>Searches the web for SaaS companies showing audit signals (working towards SOC 2, trust centres, first security hires).
Results are candidates, not qualified leads, until you research them.</p>
<form method='post' action='/leads'>{tok}<button class='btn' {'disabled' if (PUBLIC or not s.serper_api_key) else ''}>Search for leads</button>
{"<span class='muted'> Uses the operator's search API key, so it runs in the local control panel only.</span>" if PUBLIC else ('' if s.serper_api_key else "<span class='muted'> Add SERPER_API_KEY to .env to enable (free tier at serper.dev).</span>")}</form>
{lead_notes}{lead_html}</section>

<section class='card' id='prospects'><div class='row' style='justify-content:space-between;margin:0'><h2>Companies researched</h2>
<form method='post' action='/rerun'>{tok}<input type='hidden' name='slug' value='__all__'><button class='btn ghost small' {lockd}>Re-run all</button></form></div>
<div class='tw'><table><thead><tr><th>Company</th><th>Gate</th><th>ICP</th><th>Timing</th><th>Contact</th><th>Email</th><th></th></tr></thead>
<tbody>{rows or "<tr><td colspan=7 class='muted'>Nothing researched yet.</td></tr>"}</tbody></table></div></section>

<section class='card' id='review'><h2>Review drafts</h2>
<p class='hint'>Nothing is sent until you approve. Even then it only ever goes to your TEST_TO_EMAIL inbox, never the prospect.</p>
{"<p class='hint'>Public demo: drafts are read-only here. Approving happens in the local control panel.</p>" if PUBLIC else ""}
{drafts or "<p class='muted'>No drafts waiting.</p>"}</section>

<div class='grid2'>
<section class='card' id='outcomes'><h2>Log an outcome</h2><p class='hint'>Record what really happened after outreach. This drives the measured revenue numbers.</p>
<form method='post' action='/outcome' class='inline'>{tok}<select name='slug'>{options}</select><select name='stage'>{stages}</select>
<input type='number' name='deal_value' placeholder='Deal value' min='0' step='100' style='width:140px'><button class='btn' {lockd}>Log it</button></form>{note}</section>
<section class='card'><h2>Publish the dashboard</h2><p class='hint'>Rebuilds the public results page from the latest runs and deploys it to Vercel.</p>
<form method='post' action='/publish'>{tok}<button class='btn lime' {lockd}>Publish to Vercel</button></form>{note}
<p class='hint'><a href='https://sprinto-dashboard.vercel.app' target='_blank' rel='noopener'>Open the public dashboard ↗</a></p></section>
</div>
</main>
<script>
(function(){{
  var wasRunning = {str(JOB['running']).lower()};
  function poll(){{
    fetch('/status').then(function(r){{return r.json()}}).then(function(j){{
      document.getElementById('jlog').textContent = j.lines.join('\\n') || 'No run yet.';
      document.getElementById('jtitle').textContent = j.title || 'Nothing running.';
      document.getElementById('jstate').innerHTML = j.running ? '<span class="pill flag">Running</span>' : '<span class="pill go">Idle</span>';
      var log = document.getElementById('jlog'); log.scrollTop = log.scrollHeight;
      if (wasRunning && !j.running) {{ location.reload(); return; }}
      wasRunning = j.running; setTimeout(poll, j.running ? 1500 : 5000);
    }}).catch(function(){{ setTimeout(poll, 5000); }});
  }}
  poll();
}})();
</script></body></html>"""


if __name__ == "__main__":
    import logging
    # The page polls /status every few seconds for the live log; keep those lines out of the terminal.
    logging.getLogger("werkzeug").addFilter(lambda rec: "GET /status" not in rec.getMessage())
    print("Control panel: http://127.0.0.1:5050  (local only, Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=5050, debug=False)
