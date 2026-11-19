"""Orchestrates the seven stages per company with per-stage isolation and resumable state.

Each company's progress is checkpointed to output/state/<slug>.json after every stage. With --resume,
completed companies are skipped and partially completed ones restart at the first unfinished stage;
scraping and Claude calls are additionally served from disk caches.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel

from src.contact_discovery import discover_contact
from src.decision_ledger import write_outputs
from src.email_dispatcher import Dispatcher, render_preview
from src.email_generator import generate_email
from src.external_sources import add_external_pages
from src import feedback_loop, review_gate, run_history
from src.revenue_tracker import pain_family
from src.llm import ClaudeJSON
from src.models import (ContactSelection, DispatchResult, ExtractionResult, GeneratedEmail, PainPointResult, Qualification,
                        ResearchRound, ScrapeRecord)
from src.pain_point_engine import identify_pain_points
from src.qualification_engine import critic_review, qualify
from src.research_agent import investigate, make_search_provider
from src.revenue_tracker import Assumptions, VariantOptimizer, load_optimizer
from src.scraper import Scraper, normalise_domain, scrape_company
from src.signal_extractor import extract_signals

log = logging.getLogger(__name__)
STAGES = ["scrape", "extract", "qualify", "research", "contact", "pain_points", "email", "dispatch"]


class CompanyRun(BaseModel):
    company: str
    domain: str
    slug: str
    stages_completed: list[str] = []
    scrape: Optional[ScrapeRecord] = None
    extraction: Optional[ExtractionResult] = None
    extraction_notes: list[str] = []
    qualification: Optional[Qualification] = None
    research_rounds: list[ResearchRound] = []
    research_notes: list[str] = []
    contact_selection: Optional[ContactSelection] = None
    pain_points: Optional[PainPointResult] = None
    email: Optional[GeneratedEmail] = None
    dispatch: Optional[DispatchResult] = None
    errors: dict[str, str] = {}
    ledger: Optional[dict] = None

    @property
    def complete(self) -> bool:
        return "dispatch" in self.stages_completed or (
            "research" in self.stages_completed and self.qualification is not None and not self.qualification.qualified)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "company"


def read_prospects(path: Path) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(r for r in f if r.strip() and not r.lstrip().startswith("#")))
    out = []
    for r in rows:
        dom = (r.get("domain") or "").strip()
        if dom:
            out.append(((r.get("company") or dom).strip(), normalise_domain(dom)))
    return out


class Pipeline:
    def __init__(self, settings, llm: Optional[ClaudeJSON], send_test: bool = False, scraper: Optional[Scraper] = None,
                 on_event: Optional[Callable[[str], None]] = None):
        self.s = settings
        self.llm = llm
        self.scraper = scraper or Scraper(settings.cache_dir, settings.request_timeout, settings.request_delay, settings.use_playwright)
        self.dispatcher = Dispatcher(settings, send_enabled=send_test)
        self.search = make_search_provider(settings)
        self.state_dir = settings.output_dir / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.emit = on_event or (lambda msg: None)
        self.optimizer: Optional[VariantOptimizer] = None

    def _save(self, run: CompanyRun) -> None:
        (self.state_dir / f"{run.slug}.json").write_text(run.model_dump_json(indent=1), encoding="utf-8")

    def _load(self, slug: str) -> Optional[CompanyRun]:
        p = self.state_dir / f"{slug}.json"
        if p.exists():
            try:
                return CompanyRun.model_validate_json(p.read_text())
            except Exception:
                return None
        return None

    def send_reviewed(self, run: CompanyRun) -> DispatchResult:
        """Dispatch the approved (possibly edited) version — or the draft itself when the gate is disabled."""
        email = run.email
        rec = review_gate.load(run.slug, self.s.output_dir) if self.s.review_gate else None
        if rec and rec["status"] == "approved":
            email = run.email.model_copy(update={"subject": rec["approved_subject"], "email_body": rec["approved_body"]})
        cs, q = run.contact_selection, run.qualification
        preview = render_preview(email, run.company, cs.contact.full_name, cs.contact.email, q.qualification_reasoning,
                                 cs.selection_reasoning, run.pain_points.pain_points[0].reasoning)
        if rec and rec["status"] == "approved":
            preview += f"\nReviewed by a human: {rec['change_ratio']:.0%} of the draft changed" + \
                       (" (heavy edit — counted against the generator)." if rec["heavy_edit"] else ".")
        run.dispatch = self.dispatcher.dispatch(email, run.slug, preview, run.company)
        self.emit(f"  · dispatch: {run.dispatch.status}")
        return run.dispatch

    def load_all(self) -> list[CompanyRun]:
        return [r for p in sorted(self.state_dir.glob("*.json")) if (r := self._load(p.stem))]

    def _stage(self, run: CompanyRun, name: str, fn: Callable[[], None]) -> bool:
        if name in run.stages_completed:
            return True
        try:
            fn()
            run.stages_completed.append(name)
            run.errors.pop(name, None)
            return True
        except Exception as exc:  # one stage failing for one company never stops the pipeline
            log.exception("Stage %s failed for %s", name, run.domain)
            run.errors[name] = f"{exc.__class__.__name__}: {str(exc)[:200]}"
            return False
        finally:
            self._save(run)

    def run_company(self, company: str, domain: str, resume: bool = False) -> CompanyRun:
        slug = slugify(domain)
        run = (self._load(slug) if resume else None) or CompanyRun(company=company, domain=domain, slug=slug)
        if resume and run.scrape and run.scrape.scraping_status == "failed":
            run = CompanyRun(company=company, domain=domain, slug=slug)  # unreachable last time: retry from scratch
        elif resume and run.complete:
            self.emit(f"  ↺ {company}: already complete — reused saved results")
            return run
        elif resume and run.stages_completed:
            self.emit(f"  ↺ resuming after: {', '.join(run.stages_completed)}")
        if normalise_domain(domain) == "sprinto.com":
            run.errors["scrape"] = "Skipped: this is Sprinto itself."
            return run
        s = self.s

        def do_scrape():
            run.scrape = scrape_company(self.scraper, company, domain, s.initial_page_budget)
            for note in add_external_pages(run.scrape, company, s):
                self.emit(f"  · {note}")
            self.emit(f"  · scraped {len(run.scrape.ok_pages())} page(s) [{run.scrape.scraping_status}]")

        def do_extract():
            run.extraction, run.extraction_notes = extract_signals(run.scrape, self.llm, s.prompts_dir)
            self.emit(f"  · extracted {len(run.extraction.all_evidence())} evidence item(s), "
                      f"{len(run.extraction.potential_buying_moments)} buying moment(s) [{run.extraction.provenance}]")

        def do_qualify():
            run.qualification = qualify(run.extraction, run.scrape)

        def do_research():
            run.scrape, run.extraction, run.qualification, run.research_rounds, run.research_notes = investigate(
                run.scrape, run.extraction, run.qualification, self.scraper, self.llm, s.prompts_dir,
                s.max_research_rounds, s.research_page_budget, self.search)
            run.qualification = critic_review(run.qualification, run.extraction, self.llm, s.prompts_dir)
            override = feedback_loop.overrides(s.output_dir).get(run.slug)
            if override:
                run.qualification = feedback_loop.apply_override(run.qualification, override)
                self.emit(f"  · human override applied: {override['decision']} ({override['reason']})")
            q = run.qualification
            self.emit(f"  · {q.decision_status.upper()} (ICP {q.icp_fit_score}, timing {q.buying_timing_score}, "
                      f"confidence {q.evidence_confidence}, research rounds {q.research_rounds})")

        for name, fn in [("scrape", do_scrape), ("extract", do_extract), ("qualify", do_qualify), ("research", do_research)]:
            if not self._stage(run, name, fn):
                return run
        if not run.qualification.qualified:
            if review_gate.withdraw(run.slug, s.output_dir, f"No longer qualifies: {run.qualification.gate_decision}"):
                self.emit("  · pending draft withdrawn: the account no longer qualifies")
            return run

        def do_contact():
            run.contact_selection = discover_contact(run.scrape, run.extraction, s)
            c = run.contact_selection.contact
            self.emit(f"  · contact: {c.full_name + ', ' + c.job_title if c else 'none — flagged for review'}")

        def do_pain():
            cs = run.contact_selection
            run.pain_points = identify_pain_points(run.extraction, cs.contact, cs.role_family, self.llm, s.prompts_dir)

        def do_email():
            cs = run.contact_selection
            if self.optimizer and self.optimizer.active:
                before = run.pain_points.pain_points[0].pain_point if run.pain_points.pain_points else ""
                run.pain_points.pain_points = self.optimizer.rank(run.pain_points.pain_points)
                if run.pain_points.pain_points and run.pain_points.pain_points[0].pain_point != before:
                    self.emit("  · optimiser: leading with the better-converting evidence-backed angle")
            lessons = feedback_loop.active_writer_learnings(s.output_dir)
            run.email = generate_email(run.extraction, cs.contact, cs.role_family, run.pain_points.pain_points, self.llm,
                                       s.prompts_dir, s.sender_name, learnings=lessons)
            if run.email and run.email.learnings_applied:
                feedback_loop.count_use(s.output_dir, run.email.learnings_applied)
                self.emit(f"  · applied {len(run.email.learnings_applied)} reviewer learning(s) to the draft")
            if run.email:
                self.emit(f"  · email drafted: \"{run.email.subject}\" ({run.email.word_count} words)")
            else:
                self.emit("  · no grounded hook or pain point — email NOT generated")

        def do_dispatch():
            if not run.email:
                run.dispatch = DispatchResult(status="skipped", detail="No email generated.")
                return
            if s.review_gate:
                rec = review_gate.submit(slug, company, run.email, run.qualification.review_flags,
                                         pain_family(run.email.pain_point_used), s.output_dir)
                if rec["status"] != "approved":
                    run.dispatch = DispatchResult(status="pending_review" if rec["status"] == "pending" else "rejected_at_review",
                                                  preview_path=str(s.output_dir / "review" / f"{slug}.txt"),
                                                  detail="Waiting for a human at the review gate." if rec["status"] == "pending"
                                                  else f"Rejected at review: {rec.get('reason', '')}")
                    self.emit(f"  · review gate: {run.dispatch.status}"
                              + (f" ({len(rec['flags'])} flag(s) to check)" if rec["flags"] else ""))
                    return
            self.send_reviewed(run)

        if not self._stage(run, "contact", do_contact):
            return run
        if run.contact_selection.status != "selected":
            return run
        for name, fn in [("pain_points", do_pain), ("email", do_email), ("dispatch", do_dispatch)]:
            if not self._stage(run, name, fn):
                return run
        return run

    def run(self, prospects: list[tuple[str, str]], resume: bool = False, mode: str = "batch") -> tuple[list[CompanyRun], dict]:
        runs = []
        feedback_loop.learn(self.s.output_dir, review_gate.all_records(self.s.output_dir))  # store step, before any drafting
        self.optimizer = load_optimizer(self.load_all(), self.s.outcomes_csv, Assumptions.load(self.s.revenue_assumptions))
        for i, (company, domain) in enumerate(prospects, 1):
            self.emit(f"[{i}/{len(prospects)}] {company} ({domain})")
            runs.append(self.run_company(company, domain, resume))
        for r in runs:
            self._save(r)
        entry = run_history.record(self.s.output_dir, runs, self.s.initial_page_budget + self.s.research_page_budget,
                                   self.llm.calls if self.llm else 0, mode)
        self.emit(f"Run {entry['run']}: {entry['qualified']}/{entry['researched']} qualified, "
                  f"{entry['needs_human']} need a human, {entry['dropped']} dropped")
        # Consolidated reports always cover every company researched so far, not just this batch.
        everything = self.load_all()
        paths = write_outputs(everything, self.s.output_dir)
        for r in everything:
            self._save(r)
        return runs, paths
