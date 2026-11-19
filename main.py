"""Sprinto Signal Engine — command-line entry point.

    python main.py --input data/prospects.csv
    python main.py --input data/prospects.csv --limit 3
    python main.py --input data/prospects.csv --dry-run
    python main.py --input data/prospects.csv --resume
    python main.py --input data/prospects.csv --send-test      # needs DRY_RUN=false + Gmail/SMTP creds
    python main.py --gmail-auth                                # one-time Gmail OAuth consent
    python main.py --check                                     # verify credentials (no email sent)
    python main.py --revenue                                   # revenue & conversion report from saved runs
    python main.py --review                                    # list drafts waiting at the human review gate
    python main.py --approve "Rootly" [--send-test]            # approve (after editing output/review/<slug>.txt)
    python main.py --reject "Rootly" --reason "hook too weak"
    python main.py --record-outcome "Rootly" replied           # log a real outcome (stages: contacted, replied,
    python main.py --record-outcome "Rootly" won --deal-value 12000   #   meeting, opportunity, won, lost)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import ROOT, load_settings, setup_logging
from src.llm import make_llm
from src.pipeline import Pipeline, read_prospects

BOLD, DIM, RESET = ("\033[1m", "\033[2m", "\033[0m") if sys.stdout.isatty() else ("", "", "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evidence-driven outbound intelligence for Sprinto")
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "prospects.csv")
    ap.add_argument("--limit", type=int, default=None, help="Process only the first N companies")
    ap.add_argument("--company", default=None, help="Process only companies whose name or domain contains this text")
    ap.add_argument("--dry-run", action="store_true", help="Force dry run (never send) regardless of .env")
    ap.add_argument("--send-test", action="store_true", help="Explicit test-send mode: deliver previews to TEST_TO_EMAIL only")
    ap.add_argument("--resume", action="store_true", help="Reuse completed stages from a previous run")
    ap.add_argument("--no-claude", action="store_true", help="Use the deterministic fallback even if Claude is configured")
    ap.add_argument("--contacts", type=Path, default=None, help="Manual contact mapping CSV")
    ap.add_argument("--output", type=Path, default=None, help="Output directory (default: output/)")
    ap.add_argument("--gmail-auth", action="store_true", help="Run the one-time Gmail OAuth consent flow and exit")
    ap.add_argument("--check", action="store_true", help="Test every configured credential with read-only calls and exit")
    ap.add_argument("--revenue", action="store_true", help="Rebuild the revenue & conversion report from saved runs and exit")
    ap.add_argument("--record-outcome", nargs=2, metavar=("COMPANY", "STAGE"),
                    help="Append a real prospect outcome to data/outcomes.csv and refresh the revenue report")
    ap.add_argument("--review", action="store_true", help="List drafts waiting at the human review gate and exit")
    ap.add_argument("--approve", metavar="COMPANY", help="Approve a reviewed draft (edits in output/review/<slug>.txt are kept)")
    ap.add_argument("--reject", metavar="COMPANY", help="Reject a draft at the review gate")
    ap.add_argument("--reason", default="", help="Reason for --reject")
    ap.add_argument("--deal-value", type=float, default=None, help="Deal value for --record-outcome (opportunity / won)")
    args = ap.parse_args(argv)

    s = load_settings()
    if args.dry_run:
        s.dry_run = True
    if args.no_claude:
        s.use_claude = False
    if args.contacts:
        s.contacts_csv = args.contacts
    if args.output:
        s.output_dir = args.output if args.output.is_absolute() else ROOT / args.output
    setup_logging(s)

    if args.gmail_auth:
        from src.email_dispatcher import gmail_authorize
        print(f"Gmail token saved to {gmail_authorize(s)}")
        return 0

    if args.check:
        return run_preflight(s)
    if args.record_outcome:
        from src.revenue_tracker import record_outcome
        company, stage = args.record_outcome
        known = {r.company.lower(): r for r in Pipeline(s, None).load_all()}
        run = known.get(company.lower())
        if not run:
            print(f"Note: '{company}' has no saved pipeline run; the outcome is logged but cannot be joined to an email angle.")
        try:
            row = record_outcome(s.outcomes_csv, run.company if run else company, stage, args.deal_value,
                                 domain=run.domain if run else "")
        except ValueError as exc:
            print(f"Not recorded: {exc}")
            return 2
        print(f"Recorded: {row['company']} → {row['stage']}" + (f" ({row['deal_value']})" if row["deal_value"] else ""))
        return run_revenue(s)
    if args.revenue:
        return run_revenue(s)
    if args.review or args.approve or args.reject:
        return run_review(s, args)

    print(f"\n{BOLD}SPRINTO SIGNAL ENGINE{RESET}\n" + "-" * 42)
    for k, v in s.describe().items():
        print(f"{k:<22} {v}")
    if args.send_test and s.dry_run:
        print(f"{DIM}--send-test given but DRY_RUN is true → previews only. Set DRY_RUN=false in .env to send.{RESET}")
    print("-" * 42)

    if not args.input.exists():
        print(f"Input file not found: {args.input}")
        return 2
    prospects = read_prospects(args.input)
    if args.company:
        prospects = [p for p in prospects if args.company.lower() in (p[0] + p[1]).lower()]
    if args.limit:
        prospects = prospects[: args.limit]

    llm = make_llm(s)
    if llm is None:
        print(f"{DIM}Claude not configured → deterministic fallback (results labelled, not AI-verified).{RESET}")
    pipe = Pipeline(s, llm, send_test=args.send_test, on_event=print)
    runs, paths = pipe.run(prospects, resume=args.resume)

    q = [r.qualification for r in runs if r.qualification]
    scraped = sum(1 for r in runs if r.scrape and r.scrape.scraping_status != "failed")
    contacts = sum(1 for r in runs if r.contact_selection and r.contact_selection.status == "selected")
    review = sum(1 for r in runs if r.contact_selection and r.contact_selection.status == "needs_review")
    emails = sum(1 for r in runs if r.email)
    sent = sum(1 for r in runs if r.dispatch and r.dispatch.status == "sent")
    previews = sum(1 for r in runs if r.dispatch and r.dispatch.status in ("dry_run_preview", "blocked_missing_credentials"))
    guarded = sum(1 for r in runs if r.dispatch and r.dispatch.status == "blocked_by_guard")
    review_wait = sum(1 for r in runs if r.dispatch and r.dispatch.status == "pending_review")
    flagged = sum(1 for x in q if x.gate_decision == "QUALIFY_AND_FLAG")
    errors = sum(1 for r in runs if r.errors)
    rows = [
        ("Companies received", len(runs)), ("Successfully scraped", scraped),
        ("Qualified companies", sum(1 for x in q if x.decision_status == "qualified")),
        ("  of which qualify-and-flag", flagged),
        ("Nurture (wrong time)", sum(1 for x in q if x.gate_decision == "NURTURE")),
        ("Not qualified", sum(1 for x in q if x.decision_status == "not_qualified")),
        ("Insufficient evidence", sum(1 for x in q if x.decision_status == "insufficient_data")),
        ("", ""), ("Contacts identified", contacts), ("Contacts needing review", review),
        ("Personalised emails", emails), ("Waiting at review gate", review_wait), ("Test emails delivered", sent), ("Previews saved (not sent)", previews),
        ("Blocked by recipient guard", guarded),
        ("", ""), ("Claude calls made", llm.calls if llm else 0), ("Companies with stage errors", errors),
        ("Research completed", "YES" if all("research" in r.stages_completed for r in runs if r.scrape) else "PARTIAL"),
        ("Decision ledger created", "YES" if paths["ledger"].exists() else "NO"),
    ]
    print("\n" + "-" * 42 + f"\n{BOLD}RESULTS{RESET}")
    for k, v in rows:
        print(f"{k + ':' if k else '':<28}{v}")
    print("-" * 42)
    run_revenue(s, pipe.load_all(), header=False)
    print(f"Ledger:  {paths['ledger'].relative_to(ROOT)}\nSummary: {paths['summary'].relative_to(ROOT)}\n"
          f"Report:  {paths['report'].relative_to(ROOT)}\nPer-company reports: output/company_reports/\n")
    return 0


def run_review(s, args) -> int:
    from src import review_gate
    pipe = Pipeline(s, None, send_test=args.send_test)
    runs = {r.company.lower(): r for r in pipe.load_all()}
    if args.review:
        recs = review_gate.all_records(s.output_dir)
        pending = [r for r in recs if r["status"] == "pending"]
        print(f"\n{BOLD}REVIEW GATE{RESET}: {len(pending)} pending, {len(recs) - len(pending)} decided")
        for r in pending:
            print(f"- {r['company']}: output/review/{r['slug']}.txt" + "".join(f"\n    ! {f}" for f in r["flags"]))
        st = review_gate.stats(s.output_dir)
        if st["approved"]:
            print(f"Approved {st['approved']}, rejected {st['rejected']}; average change {st['avg_change']:.0%}; "
                  f"heavy edits (>50% rewritten) {st['heavy_edit_rate']:.0%}")
        return 0
    name = args.approve or args.reject
    run = runs.get(name.lower())
    if not run:
        print(f"No saved run for '{name}'. Known: {', '.join(r.company for r in runs.values())}")
        return 2
    try:
        if args.reject:
            rec = review_gate.reject(run.slug, s.output_dir, args.reason)
            from src.models import DispatchResult
            run.dispatch = DispatchResult(status="rejected_at_review", detail=f"Rejected at review: {rec['reason']}")
            pipe._save(run)
            print(f"Rejected {run.company}: {rec['reason']}")
            return 0
        rec = review_gate.approve(run.slug, s.output_dir)
    except ValueError as exc:
        print(f"Not done: {exc}")
        return 2
    print(f"Approved {run.company}: {rec['change_ratio']:.0%} of the draft changed"
          + (" — HEAVY EDIT (>50%), counted against the generator." if rec["heavy_edit"] else "."))
    if args.send_test and s.dry_run:
        print(f"{DIM}--send-test given but DRY_RUN is true → preview only.{RESET}")
    res = pipe.send_reviewed(run)
    pipe._save(run)
    print(f"Dispatch: {res.status} — {res.detail}")
    return 0


def run_revenue(s, runs=None, header: bool = True) -> int:
    from src.revenue_tracker import Assumptions, analyse, read_outcomes, recommendations, write_revenue_outputs
    runs = runs if runs is not None else Pipeline(s, None).load_all()
    if not runs:
        print("No saved pipeline runs yet — run the pipeline first.")
        return 1
    from src import review_gate
    rep = analyse(runs, read_outcomes(s.outcomes_csv), Assumptions.load(s.revenue_assumptions),
                  review_gate.stats(s.output_dir) if s.review_gate else None)
    paths = write_revenue_outputs(rep, s.output_dir)
    cur, rev, conv = rep["currency"], rep["revenue"], rep["conversion"]
    if header:
        print(f"\n{BOLD}REVENUE & CONVERSION{RESET}")
    print(("-" * 42 + "\n" if header else "") + f"{BOLD}REVENUE{RESET}  (measured = logged outcomes; estimated = assumptions)")
    for k, v in [("Won revenue (measured)", f"{cur} {rev['won_revenue']:,.0f} from {rev['deals_won']} deals"),
                 ("Open pipeline (measured)", f"{cur} {rev['open_pipeline_value']:,.0f}"),
                 ("Expected revenue (est.)", f"{cur} {rev['expected_revenue']:,.0f}"),
                 ("Blocked: no contact (est.)", f"{cur} {rev['blocked_no_contact']:,.0f}"),
                 ("Qualification rate", f"{conv['qualification_rate']:.0%}"),
                 ("Contacted → opened", conv["open_rate"]),
                 ("Contacted → reply", conv["contacted_to_reply"]),
                 ("Contacted → won", f"{conv['contacted_to_won_observed']} observed, {conv['contacted_to_won_estimated']:.2%} est."),
                 ("Outcomes recorded", rep["outcomes_recorded"]),
                 ("Angle optimiser", "ACTIVE" if rep["optimizer_active"] else f"learning (needs {rep['min_sends_to_learn']} contacted)")]:
        print(f"{k + ':':<28}{v}")
    print(f"{BOLD}Top actions{RESET}")
    for i, r in enumerate(recommendations(rep)[:3], 1):
        print(f" {i}. {r}")
    print(f"Revenue report: {paths['report'].relative_to(ROOT) if paths['report'].is_relative_to(ROOT) else paths['report']}")
    return 0


def run_preflight(s) -> int:
    from src.preflight import ready_to_send, run_checks
    mark = {"ok": "OK  ", "fail": "FAIL", "skipped": "--  "}
    print(f"\n{BOLD}CREDENTIAL PREFLIGHT{RESET} (read-only calls; nothing is sent)\n" + "-" * 42)
    results = run_checks(s)
    for r in results:
        print(f"[{mark[r.status]}] {r.name:<17} {r.detail}")
    print("-" * 42)
    send_ok = ready_to_send(results, s)
    print(f"Live test send possible: {'YES' if send_ok else 'NO'}"
          + (" (also needs DRY_RUN=false and --send-test)" if send_ok and s.dry_run else ""))
    return 1 if any(r.status == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
