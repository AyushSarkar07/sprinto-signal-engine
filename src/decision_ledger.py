"""The Explainable Decision Ledger: six questions per prospect, each answered from referenced evidence.

WHY THIS COMPANY? · WHY NOW? · WHY THIS PERSON? · WHY THIS PAIN POINT? · WHY THIS EMAIL? ·
WHAT COULD MAKE THIS DECISION WRONG?
Answers cite evidence IDs that resolve to (finding, URL, verbatim excerpt) in the report appendix.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any

from src.models import Evidence


def _cite(ids: list[str], ev: dict[str, Evidence], n: int = 2) -> str:
    parts = []
    for i in ids[:n]:
        e = ev.get(i)
        if e:
            parts.append(f"[{i}] \"{e.excerpt[:110]}\" ({e.source_url})")
    return "; ".join(parts)


def build_ledger(run) -> dict[str, Any]:
    """`run` is a pipeline.CompanyRun. Returns the ledger entry (also embedded in the report)."""
    q, x = run.qualification, run.extraction
    ev = {e.id: e for e in x.all_evidence()} if x else {}
    entry: dict[str, Any] = {"company": run.company, "domain": run.domain,
                             "decision_status": q.decision_status if q else "not_evaluated",
                             "recommended_action": q.recommended_action if q else "manual_review",
                             "icp_fit_score": q.icp_fit_score if q else None,
                             "buying_timing_score": q.buying_timing_score if q else None,
                             "evidence_confidence": q.evidence_confidence if q else None,
                             "gate_decision": q.gate_decision if q else None,
                             "evidence_map": {a["key"]: a["answer"] for a in q.evidence_map} if q else {},
                             "review_flags": q.review_flags if q else [],
                             "provenance": x.provenance if x else None}
    if q:
        entry["why_this_company"] = [f"{c.criterion} +{c.points:g}/{c.max_points}: {c.rationale} {_cite(c.evidence_ids, ev)}".strip()
                                     for c in q.icp_breakdown if c.points > 0] or ["No ICP criteria were satisfied by evidence."]
        why_now = [f"{c.criterion} +{c.points:g}/{c.max_points}: {c.rationale} {_cite(c.evidence_ids, ev)}".strip()
                   for c in q.timing_breakdown if c.points > 0]
        why_now += [f"Buying moment — {m.signal}: {m.why_it_matters} ({m.source_url})" for m in x.potential_buying_moments[:3]]
        entry["why_now"] = why_now or ["No observable buying moment — timing unsupported."]
        entry["what_could_make_this_wrong"] = q.risks_and_uncertainty + q.penalties
    cs = run.contact_selection
    if cs:
        entry["why_this_person"] = [cs.selection_reasoning] + [
            f"Alternative: {a.contact.full_name} ({a.contact.job_title}) relevance {a.relevance_score} — {a.reasons[0]}"
            for a in cs.alternative_contacts[:3]]
    if run.pain_points:
        entry["why_this_pain_point"] = [f"{p.pain_point} [{p.basis}, confidence {p.confidence}]: {p.reasoning} "
                                        f"Evidence: {' | '.join(p.supporting_evidence[:2])}" for p in run.pain_points.pain_points]
    if run.email:
        entry["why_this_email"] = [f"Hook: {run.email.personalisation_hook} ({run.email.hook_source_url})",
                                   f"Pain point used: {run.email.pain_point_used}",
                                   run.email.why_this_email_was_written]
    return entry


def _table(rows: list[list[str]], header: list[str]) -> str:
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] +
                     ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows])


def render_company_report(run) -> str:
    q, x, rec = run.qualification, run.extraction, run.scrape
    L: list[str] = [f"# {run.company} — Sprinto Signal Engine research report", "",
                    f"*Domain:* `{run.domain}` · *Generated:* {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} · "
                    f"*Extraction:* {'Claude (AI)' if x and x.provenance == 'claude' else 'deterministic fallback — rule-based, not AI-verified'}", ""]
    if run.errors:
        L += ["> **Stage errors (pipeline continued):** " + "; ".join(f"{k}: {v}" for k, v in run.errors.items()), ""]
    if q:
        L += ["## Decision", "", f"**{q.decision_status.upper()}** → recommended action: **{q.recommended_action}**", "",
              _table([["ICP fit", f"{q.icp_fit_score}/100"], ["Buying timing", f"{q.buying_timing_score}/100"],
                      ["Evidence confidence", f"{q.evidence_confidence}"],
                      ["Secondary research", f"{q.research_rounds} round(s)"]], ["Dimension", "Value"]), "",
              *[f"- {r}" for r in q.qualification_reasoning], ""]
        if q.evidence_map:
            L += [f"### Evidence Map → **{q.gate_decision.replace('_', ' ')}**", "",
                  _table([[("**" if a["core"] else "") + a["question"] + ("**" if a["core"] else ""), a["answer"].upper(), a["basis"],
                           f"{a['tries_used']}/{a['limit']}", a["if_unanswered"], "<br>".join(a["evidence"]) or "—"]
                          for a in q.evidence_map],
                         ["Question (core in bold)", "Answer", "Basis", "Pages read / budget", "If unanswered", "Evidence"]), ""]
            if q.review_flags:
                L += ["**Review gate must check:**", *[f"- {f}" for f in q.review_flags], ""]
    L += ["## 1. Website intelligence", ""]
    if rec:
        L += [f"Scraping status: **{rec.scraping_status}** · pages read: {len(rec.ok_pages())} of {len(rec.pages_scraped)} attempted", "",
              _table([[p.category, p.status, p.url, p.rendered_with] for p in rec.pages_scraped], ["Type", "Status", "URL", "Fetched via"]), ""]
        if rec.errors:
            L += ["Errors: " + "; ".join(rec.errors[:6]), ""]
    if x:
        p = x.company_profile
        L += ["## 2. Extracted company profile", "",
              _table([["Business", p.business_description.excerpt[:160] if p.business_description else "unknown"],
                      ["SaaS?", f"{p.is_saas} ({p.business_model})"],
                      ["Funding stage", p.funding_stage.value or "not stated"], ["Headcount", p.employee_range.value or "not stated"],
                      ["Industries", ", ".join(e.finding.replace('Serves or targets ', '') for e in p.customer_industries) or "not identified"],
                      ["Tech stack (explicit only)", ", ".join(e.finding for e in p.tech_stack) or "none stated"],
                      ["Trust centre", str(x.compliance_signals.trust_centre)]], ["Field", "Value"]), "",
              "### Buying moments", ""]
        if x.potential_buying_moments:
            L += [_table([[m.signal, f"{m.confidence}", "yes" if m.requires_further_research else "no", m.why_it_matters,
                           f"\"{m.evidence[:120]}\" — {m.source_url}"] for m in x.potential_buying_moments],
                         ["Signal", "Conf.", "Needs research", "Why it matters commercially", "Evidence"]), ""]
        else:
            L += ["None observed. (No buying moment was invented.)", ""]
        if x.missing_information:
            L += ["**Missing information:** " + "; ".join(m.split(': ', 1)[-1] for m in x.missing_information), ""]
        if x.contradictory_information:
            L += ["**Contradictions:** " + "; ".join(x.contradictory_information), ""]
    if q:
        L += ["## 3. Qualification scoring", "", "### ICP fit", "",
              _table([[c.criterion, f"{c.points:g}/{c.max_points}", c.rationale, ", ".join(c.evidence_ids)] for c in q.icp_breakdown],
                     ["Criterion", "Points", "Rationale", "Evidence IDs"]), "", "### Buying timing", "",
              _table([[c.criterion, f"{c.points:g}/{c.max_points}", c.rationale, ", ".join(c.evidence_ids)] for c in q.timing_breakdown],
                     ["Criterion", "Points", "Rationale", "Evidence IDs"]), ""]
        if q.penalties:
            L += ["Penalties: " + "; ".join(q.penalties), ""]
    L += ["### Research agent log", ""]
    if run.research_rounds:
        for rr in run.research_rounds:
            L += [f"**Round {rr.round}** — open questions: {'; '.join(rr.missing_before)}", "",
                  *[f"- Targeted: {t}" for t in rr.pages_targeted],
                  f"- Readable: {len(rr.pages_successfully_read)} page(s)",
                  *[f"- New: {n}" for n in rr.new_findings[:8]],
                  f"- **What changed:** {rr.what_changed}", ""]
    L += [f"- {n}" for n in run.research_notes] + [""]
    L += ["## 4. Decision-maker", ""]
    cs = run.contact_selection
    if cs:
        L += [f"Status: **{cs.status}** · providers tried: {', '.join(cs.providers_tried) or 'none'}", "",
              *[f"- {n}" for n in cs.provider_notes], "", cs.selection_reasoning, ""]
        if cs.contact:
            c = cs.contact
            L += [_table([[c.full_name, c.job_title, c.email or "not available", c.source, c.source_url or ""]],
                         ["Name", "Title", "Email", "Source", "Source URL"]), ""]
        if cs.alternative_contacts:
            L += ["Alternatives considered:", "", _table([[a.contact.full_name, a.contact.job_title, f"{a.relevance_score}", a.reasons[0]]
                                                           for a in cs.alternative_contacts], ["Name", "Title", "Relevance", "Why"]), ""]
    else:
        L += ["Not attempted (company not qualified).", ""]
    if run.pain_points:
        L += ["## 5. Pain points", ""]
        for pp in run.pain_points.pain_points:
            L += [f"**{pp.pain_point}** — {pp.basis}, confidence {pp.confidence}", "", pp.reasoning, "",
                  *[f"- {s}" for s in pp.supporting_evidence], ""]
    if run.email:
        e = run.email
        L += ["## 6. Generated email", "", f"**Subject:** {e.subject}  ", f"*Candidates:* {' / '.join(e.subject_candidates)} — {e.subject_choice_reason}", "",
              "```", e.email_body, "```", "", f"Word count: {e.word_count} · quality checks: " +
              ", ".join(f"{k}={'pass' if v else 'FAIL'}" for k, v in e.quality_checks.items()), "", "### Evidence → email trace", "",
              _table([[t.sentence, t.purpose, t.evidence[:120], t.source_url] for t in e.evidence_to_email_trace],
                     ["Sentence", "Purpose", "Evidence", "Source"]), ""]
    if run.dispatch:
        L += ["## 7. Dispatch", "", f"Status: **{run.dispatch.status}** — {run.dispatch.detail}", f"Preview file: `{run.dispatch.preview_path}`", ""]
    ledger = run.ledger or build_ledger(run)
    L += ["## Decision ledger", ""]
    for key, title in [("why_this_company", "WHY THIS COMPANY?"), ("why_now", "WHY NOW?"), ("why_this_person", "WHY THIS PERSON?"),
                       ("why_this_pain_point", "WHY THIS PAIN POINT?"), ("why_this_email", "WHY THIS EMAIL?"),
                       ("what_could_make_this_wrong", "WHAT COULD MAKE THIS DECISION WRONG?")]:
        if ledger.get(key):
            L += [f"### {title}", "", *[f"- {s}" for s in ledger[key]], ""]
    if x:
        L += ["## Evidence appendix", "", _table([[e.id, e.category, e.finding, e.evidence_type, f"{e.confidence}", e.source_url, e.excerpt[:200]]
                                                  for e in x.all_evidence()], ["ID", "Category", "Finding", "Type", "Conf.", "URL", "Excerpt"]), ""]
    return "\n".join(L)


def write_outputs(runs: list, output_dir: Path) -> dict[str, Path]:
    (output_dir / "company_reports").mkdir(parents=True, exist_ok=True)
    ledger = []
    for r in runs:
        r.ledger = build_ledger(r)
        ledger.append(r.ledger)
        (output_dir / "company_reports" / f"{r.slug}.md").write_text(render_company_report(r), encoding="utf-8")
    (output_dir / "decision_ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    with (output_dir / "pipeline_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company", "domain", "scraping_status", "pages_read", "decision_status", "recommended_action", "icp_fit_score",
                    "buying_timing_score", "evidence_confidence", "research_rounds", "top_buying_moment", "contact", "contact_title",
                    "contact_email", "email_subject", "dispatch_status", "provenance", "errors"])
        for r in runs:
            q, x = r.qualification, r.extraction
            c = r.contact_selection.contact if r.contact_selection else None
            w.writerow([r.company, r.domain, r.scrape.scraping_status if r.scrape else "", len(r.scrape.ok_pages()) if r.scrape else 0,
                        q.decision_status if q else "", q.recommended_action if q else "", q.icp_fit_score if q else "",
                        q.buying_timing_score if q else "", q.evidence_confidence if q else "", q.research_rounds if q else "",
                        x.potential_buying_moments[0].signal if x and x.potential_buying_moments else "",
                        c.full_name if c else "", c.job_title if c else "", (c.email or "") if c else "",
                        r.email.subject if r.email else "", r.dispatch.status if r.dispatch else "",
                        x.provenance if x else "", "; ".join(f"{k}: {v}" for k, v in r.errors.items())])
    # consolidated report
    L = ["# Sprinto Signal Engine — pipeline report", "", f"Generated {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
         _table([[r.company, r.qualification.decision_status if r.qualification else "error",
                  str(r.qualification.icp_fit_score) if r.qualification else "", str(r.qualification.buying_timing_score) if r.qualification else "",
                  str(r.qualification.evidence_confidence) if r.qualification else "",
                  (r.contact_selection.contact.full_name if r.contact_selection and r.contact_selection.contact else "—"),
                  r.dispatch.status if r.dispatch else "—", f"[report](company_reports/{r.slug}.md)"] for r in runs],
                ["Company", "Decision", "ICP", "Timing", "Confidence", "Contact", "Email", "Report"]), ""]
    for r in runs:
        if r.qualification:
            L += [f"## {r.company}", "", *[f"- {s}" for s in r.qualification.qualification_reasoning[:2]], ""]
    (output_dir / "pipeline_report.md").write_text("\n".join(L), encoding="utf-8")
    return {"ledger": output_dir / "decision_ledger.json", "summary": output_dir / "pipeline_summary.csv",
            "report": output_dir / "pipeline_report.md"}
