"""Revenue and conversion tracking, plus expected-value optimisation.

Two kinds of numbers are kept strictly apart:
  * MEASURED — counts the pipeline produced (scraped, qualified, contact found, email ready) and outcomes a
    human recorded in data/outcomes.csv (contacted, replied, meeting, opportunity, won/lost, deal value).
    This tool never contacts prospects, so market outcomes can only come from that file.
  * ESTIMATED — expected revenue = P(win) x ACV. ACV and the stage-conversion priors are planning assumptions
    from data/revenue_assumptions.json and are labelled as such everywhere they appear. Each stage rate is a
    Beta posterior: the prior is overridden as recorded outcomes accumulate.

"Maximising" means: rank outreach by expected revenue, quantify the revenue blocked at each pipeline gap,
and (once enough outcomes exist) use Thompson sampling to favour the email angle that converts best, but
only among pain points the evidence already supports.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MARKET_STAGES = ["contacted", "replied", "meeting", "opportunity", "won"]
ALL_OUTCOMES = MARKET_STAGES + ["opened", "lost"]   # "opened" is tracked as a rate, not a win-chain stage
LEARNED = ["replied", "meeting", "opportunity", "won"]  # each is P(stage | previous stage)
OUTCOME_FIELDS = ["date", "company", "domain", "stage", "deal_value", "notes"]

# Pain points are free text (Claude may phrase them differently), so group them into stable families.
PAIN_FAMILIES = [
    ("audit_evidence", r"evidence collection|pulling engineers|audit evidence"),
    ("questionnaires", r"questionnaire|vendor review|security review"),
    ("continuous_readiness", r"audit-ready|continuously|re-evidenc"),
    ("multi_framework", r"second framework|iso 27001 / gdpr|duplicat"),
    ("programme_setup", r"before a dedicated|standing up|programme"),
    ("regulated_buyers", r"regulated"),
]


def pain_family(text: str) -> str:
    for name, rx in PAIN_FAMILIES:
        if re.search(rx, text or "", re.I):
            return name
    return "other"


# ---------------------------------------------------------------- assumptions & outcomes

@dataclass
class Assumptions:
    currency: str = "USD"
    default_acv: float = 10000
    acv_by_employees: list = field(default_factory=lambda: [[50, 6000], [200, 12000], [1000, 25000]])
    stage_priors: dict = field(default_factory=lambda: {"replied": [1, 19], "meeting": [1, 1], "opportunity": [1, 1], "won": [1, 2]})
    timing_lift: dict = field(default_factory=lambda: {"enabled": True, "min": 0.5, "max": 2.0})
    min_sends_to_learn: int = 10

    @classmethod
    def load(cls, path: Path) -> "Assumptions":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})


def read_outcomes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("company") or r.get("domain"))]
    out = []
    for r in rows:
        stage = (r.get("stage") or "").strip().lower()
        if stage not in ALL_OUTCOMES:
            continue
        try:
            value = float(r.get("deal_value") or 0)
        except ValueError:
            value = 0.0
        out.append({**r, "stage": stage, "deal_value": value, "key": _key(r.get("company", ""), r.get("domain", ""))})
    return out


def record_outcome(path: Path, company: str, stage: str, deal_value: Optional[float] = None, domain: str = "",
                   notes: str = "") -> dict:
    stage = stage.strip().lower()
    if stage not in ALL_OUTCOMES:
        raise ValueError(f"stage must be one of {ALL_OUTCOMES}")
    if deal_value is not None and deal_value < 0:
        raise ValueError("deal_value cannot be negative")
    new = not path.exists() or not path.read_text().strip()
    row = {"date": dt.date.today().isoformat(), "company": company, "domain": domain, "stage": stage,
           "deal_value": "" if deal_value is None else f"{deal_value:g}", "notes": notes}
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def _key(company: str, domain: str) -> str:
    return (domain or company).strip().lower()


def company_status(outcomes: list[dict]) -> dict[str, dict]:
    """Furthest market stage per company (a later stage implies the earlier ones), lost flag, deal value."""
    st: dict[str, dict] = {}
    for o in outcomes:
        s = st.setdefault(o["key"], {"reached": -1, "lost": False, "opened": False, "deal_value": 0.0, "company": o.get("company", "")})
        if o["stage"] == "lost":
            s["lost"] = True
        elif o["stage"] == "opened":
            s["opened"] = True
            s["reached"] = max(s["reached"], 0)
        else:
            s["reached"] = max(s["reached"], MARKET_STAGES.index(o["stage"]))
        if o["deal_value"]:
            s["deal_value"] = o["deal_value"]
    return st


# ---------------------------------------------------------------- conversion model

def beta_counts(statuses: list[dict]) -> dict[str, tuple[int, int]]:
    """(successes, trials) for each transition. A trial is decided once the company reached the next stage or
    was marked lost; companies still in progress are not counted against the rate."""
    out = {}
    for stage in LEARNED:
        i = MARKET_STAGES.index(stage)
        succ = sum(1 for s in statuses if s["reached"] >= i)
        trials = succ + sum(1 for s in statuses if s["reached"] == i - 1 and s["lost"])
        out[stage] = (succ, trials)
    return out


def stage_rates(a: Assumptions, counts: dict[str, tuple[int, int]]) -> dict[str, dict]:
    rates = {}
    for stage in LEARNED:
        pa, pb = a.stage_priors.get(stage, [1, 1])
        succ, trials = counts.get(stage, (0, 0))
        rates[stage] = {"posterior_mean": (pa + succ) / (pa + pb + trials), "prior_mean": pa / (pa + pb),
                        "observed": f"{succ}/{trials}" if trials else "no data", "trials": trials}
    return rates


def p_win_from(stage_index: int, rates: dict[str, dict]) -> float:
    """P(won | company has reached MARKET_STAGES[stage_index]); stage_index -1 = not yet contacted."""
    p = 1.0
    for stage in LEARNED:
        if MARKET_STAGES.index(stage) > max(stage_index, 0):
            p *= rates[stage]["posterior_mean"]
    return p


def estimate_acv(run, a: Assumptions) -> tuple[float, str]:
    prof = run.extraction.company_profile if run.extraction else None
    emp = prof.employee_range.value if prof else None
    m = re.search(r"\d[\d,]*", emp or "")
    if m:
        n = int(m.group(0).replace(",", ""))
        for ceiling, acv in a.acv_by_employees:
            if n <= ceiling:
                return float(acv), f"assumed ACV for ≤{ceiling} employees (site says '{emp}')"
        return float(a.acv_by_employees[-1][1]), f"assumed ACV for the largest band (site says '{emp}')"
    return float(a.default_acv), "default assumed ACV (headcount not found on site)"


def timing_lift(run, a: Assumptions) -> float:
    """Heuristic until segment data exists: stronger buying-timing evidence → proportionally higher reply odds."""
    if not a.timing_lift.get("enabled") or not run.qualification:
        return 1.0
    lift = 0.5 + run.qualification.buying_timing_score / 50
    return max(a.timing_lift.get("min", 0.5), min(a.timing_lift.get("max", 2.0), lift))


# ---------------------------------------------------------------- variant optimisation (Thompson sampling)

class VariantOptimizer:
    """Learns reply rate per pain-point family from recorded outcomes and reorders an email's candidate pain
    points by a Thompson sample. Only engages once `min_sends_to_learn` contacted outcomes exist; it can only
    choose between pain points the evidence engine already produced (never invents an angle)."""

    def __init__(self, family_stats: dict[str, tuple[int, int]], min_sends: int, prior=(1, 19), rng=None):
        self.stats, self.min_sends, self.prior = family_stats, min_sends, prior
        self.rng = rng or random.Random()

    @property
    def active(self) -> bool:
        return sum(t for _, t in self.stats.values()) >= self.min_sends

    def rank(self, pains: list, min_confidence: float = 0.5) -> list:
        if not self.active or len(pains) < 2:
            return pains
        eligible = [p for p in pains if p.confidence >= min_confidence] or pains[:1]
        rest = [p for p in pains if p not in eligible]

        def sample(p):
            s, t = self.stats.get(pain_family(p.pain_point), (0, 0))
            return self.rng.betavariate(self.prior[0] + s, self.prior[1] + t - s)

        return sorted(eligible, key=sample, reverse=True) + rest


def family_stats(runs, statuses: dict[str, dict]) -> dict[str, tuple[int, int]]:
    """(replies, contacted) per pain-point family, joining outcomes to the email each company was sent."""
    stats: dict[str, list[int]] = {}
    for r in runs:
        st = statuses.get(_key(r.company, r.domain)) or statuses.get(r.company.lower())
        if not (r.email and st and st["reached"] >= 0):
            continue
        fam = stats.setdefault(pain_family(r.email.pain_point_used), [0, 0])
        fam[1] += 1
        fam[0] += st["reached"] >= 1
    return {k: (v[0], v[1]) for k, v in stats.items()}


def load_optimizer(runs, outcomes_path: Path, a: Assumptions, rng=None) -> VariantOptimizer:
    statuses = company_status(read_outcomes(outcomes_path))
    return VariantOptimizer(family_stats(runs, statuses), a.min_sends_to_learn, tuple(a.stage_priors["replied"]), rng)


# ---------------------------------------------------------------- report

def analyse(runs, outcomes: list[dict], a: Assumptions, review: Optional[dict] = None) -> dict:
    statuses = company_status(outcomes)
    status_by_run = {}
    for r in runs:
        status_by_run[r.slug] = statuses.get(_key(r.company, r.domain)) or statuses.get(r.company.lower())
    rates = stage_rates(a, beta_counts(list(statuses.values())))

    q = [r for r in runs if r.qualification and r.qualification.qualified]
    funnel = [
        ("Prospects", len(runs)),
        ("Scraped", sum(1 for r in runs if r.scrape and r.scrape.scraping_status != "failed")),
        ("Qualified", len(q)),
        ("Decision-maker found", sum(1 for r in q if r.contact_selection and r.contact_selection.status == "selected")),
        ("Email ready", sum(1 for r in q if r.email)),
    ] + ([("Approved at review", review["approved"])] if review else []) \
      + [(s.capitalize(), sum(1 for st in statuses.values() if st["reached"] >= i)) for i, s in enumerate(MARKET_STAGES)]
    opened = sum(1 for st in statuses.values() if st["opened"] or st["reached"] >= 1)  # a reply implies an open
    funnel.insert(funnel.index(next(x for x in funnel if x[0] == "Contacted")) + 1, ("Opened", opened))

    queue, blocked = [], {"no_contact": 0.0, "no_email": 0.0}
    for r in q:
        st = status_by_run[r.slug]
        if st and (st["lost"] or st["reached"] >= MARKET_STAGES.index("won")):
            continue
        acv, acv_basis = estimate_acv(r, a)
        reached = st["reached"] if st else -1
        lift = timing_lift(r, a) if reached < 1 else 1.0  # once they replied, the timing heuristic no longer applies
        p = min(1.0, p_win_from(reached, rates) * lift)
        value = st["deal_value"] if st and st["deal_value"] else acv
        ev = p * value
        has_contact = bool(r.contact_selection and r.contact_selection.status == "selected")
        if not has_contact:
            blocked["no_contact"] += ev
            action = "Find a decision-maker (manual CSV or Hunter) — revenue is blocked here"
        elif not r.email:
            blocked["no_email"] += ev
            action = "No grounded hook for an email yet — research further before outreach"
        elif reached < 0:
            action = "Contact now (email ready)"
        else:
            action = f"Follow up — currently at '{MARKET_STAGES[reached]}'"
        queue.append({"company": r.company, "domain": r.domain, "stage": MARKET_STAGES[reached] if reached >= 0 else "not contacted",
                      "icp": r.qualification.icp_fit_score, "timing": r.qualification.buying_timing_score,
                      "acv": value, "acv_basis": "recorded deal value" if st and st["deal_value"] else acv_basis,
                      "p_win": round(p, 4), "expected_revenue": round(ev, 2), "timing_lift": round(lift, 2),
                      "next_action": action})
    queue.sort(key=lambda x: x["expected_revenue"], reverse=True)

    won = [s for s in statuses.values() if s["reached"] == MARKET_STAGES.index("won")]
    open_opps = [s for s in statuses.values() if s["reached"] == MARKET_STAGES.index("opportunity") and not s["lost"]]
    contacted = sum(1 for s in statuses.values() if s["reached"] >= 0)
    fam = family_stats(runs, statuses)
    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "currency": a.currency,
        "funnel": funnel,
        "stage_rates": rates,
        "revenue": {
            "won_revenue": sum(s["deal_value"] for s in won),
            "deals_won": len(won),
            "open_pipeline_value": sum(s["deal_value"] for s in open_opps),
            "expected_revenue": round(sum(x["expected_revenue"] for x in queue), 2),
            "blocked_no_contact": round(blocked["no_contact"], 2),
            "blocked_no_email": round(blocked["no_email"], 2),
            "avg_deal_size": (sum(s["deal_value"] for s in won) / len(won)) if won else None,
        },
        "conversion": {
            "qualification_rate": len(q) / len(runs) if runs else 0,
            "contacted_to_reply": rates["replied"]["observed"],
            "open_rate": f"{opened}/{contacted}" if contacted else "no data",
            "contacted_to_won_observed": f"{len(won)}/{contacted}" if contacted else "no data",
            "contacted_to_won_estimated": round(p_win_from(0, rates), 4),
        },
        "variants": {k: {"replies": s, "contacted": t, "reply_rate": round(s / t, 3) if t else None} for k, (s, t) in fam.items()},
        "optimizer_active": sum(t for _, t in fam.values()) >= a.min_sends_to_learn,
        "min_sends_to_learn": a.min_sends_to_learn,
        "priority_queue": queue,
        "outcomes_recorded": len(outcomes),
        "review": review or {},
    }


def recommendations(rep: dict) -> list[str]:
    cur, rev = rep["currency"], rep["revenue"]
    recs = []
    ready = [x for x in rep["priority_queue"] if x["next_action"].startswith("Contact now")]
    if ready:
        top = ready[0]
        recs.append(f"Contact {top['company']} first: highest expected revenue among ready emails "
                    f"({cur} {top['expected_revenue']:,.0f} = P(win) {top['p_win']:.1%} × ACV {top['acv']:,.0f}).")
    if rev["blocked_no_contact"]:
        names = ", ".join(x["company"] for x in rep["priority_queue"] if x["next_action"].startswith("Find"))
        recs.append(f"Biggest lever: {cur} {rev['blocked_no_contact']:,.0f} of expected revenue is blocked because no decision-maker "
                    f"was found ({names}). Add them to data/contacts_override.csv or enable Hunter.")
    if rev["blocked_no_email"]:
        recs.append(f"{cur} {rev['blocked_no_email']:,.0f} is blocked by missing email hooks: research those companies further.")
    leaks = [(s, r) for s, r in rep["stage_rates"].items() if r["trials"] >= 5 and r["posterior_mean"] < 0.75 * r["prior_mean"]]
    for s, r in leaks:
        recs.append(f"Funnel leak at '{s}': {r['observed']} observed vs {r['prior_mean']:.0%} planned — review that step first.")
    if rep["optimizer_active"]:
        best = max(rep["variants"].items(), key=lambda kv: (kv[1]["reply_rate"] or 0))
        recs.append(f"Best-converting angle so far: '{best[0]}' ({best[1]['replies']}/{best[1]['contacted']} replies); "
                    "the email generator now favours it via Thompson sampling when the evidence supports it.")
    else:
        recs.append(f"Angle optimisation is off until {rep['min_sends_to_learn']} contacted outcomes are recorded "
                    f"(currently {sum(v['contacted'] for v in rep['variants'].values())}). Log outcomes with --record-outcome.")
    rv = rep.get("review") or {}
    if rv.get("heavy_edit_rate") is not None and rv["heavy_edit_rate"] > 0.3:
        worst = max(rv["heavy_edit_by_family"].items(), key=lambda kv: kv[1]["avg_change"])
        recs.append(f"Reviewers rewrote more than half of {rv['heavy_edit_rate']:.0%} of approved drafts; the weakest angle is "
                    f"'{worst[0]}' ({worst[1]['avg_change']:.0%} changed on average). Fix that template/prompt before scaling sends.")
    if rv.get("pending"):
        recs.append(f"{rv['pending']} draft(s) are waiting at the review gate — revenue cannot move until they are approved (--review).")
    if not rep["outcomes_recorded"]:
        recs.append("All conversion and revenue figures below are ESTIMATES from planning assumptions — no real outcomes recorded yet.")
    return recs


def write_revenue_outputs(rep: dict, out_dir: Path) -> dict[str, Path]:
    out = out_dir / "revenue"
    out.mkdir(parents=True, exist_ok=True)
    (out / "revenue_metrics.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    with (out / "priority_queue.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["company", "domain", "stage", "icp", "timing", "acv", "acv_basis", "timing_lift", "p_win", "expected_revenue", "next_action"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rep["priority_queue"])
    cur, rev, conv = rep["currency"], rep["revenue"], rep["conversion"]
    rv = rep.get("review") or {}
    L = ["# Revenue & conversion report", "", f"Generated {rep['generated']} · outcomes recorded: {rep['outcomes_recorded']}", "",
         "> **Measured** = pipeline counts and outcomes you logged. **Estimated** = planning assumptions from "
         "`data/revenue_assumptions.json` updated by those outcomes. Estimates are never presented as results.", "",
         "## What to do next (maximising expected revenue)", "", *[f"{i}. {r}" for i, r in enumerate(recommendations(rep), 1)], "",
         "## Revenue", "", "| Metric | Value | Type |", "|---|---|---|",
         f"| Won revenue | {cur} {rev['won_revenue']:,.0f} ({rev['deals_won']} deals) | measured |",
         f"| Open opportunity value | {cur} {rev['open_pipeline_value']:,.0f} | measured |",
         f"| Expected revenue (qualified, not closed) | {cur} {rev['expected_revenue']:,.0f} | estimated |",
         f"| Blocked: no decision-maker | {cur} {rev['blocked_no_contact']:,.0f} | estimated |",
         f"| Blocked: no grounded email | {cur} {rev['blocked_no_email']:,.0f} | estimated |",
         f"| Open rate (opened / contacted) | {conv['open_rate']} | measured (log 'opened'; pixel tracking is not used) |",
         f"| Average deal size | {cur + ' ' + format(rev['avg_deal_size'], ',.0f') if rev['avg_deal_size'] else 'no won deals yet'} | measured |", "",
         "## Funnel", "", "| Stage | Count | Step conversion | From prospects |", "|---|---|---|---|"]
    base = rep["funnel"][0][1] or 1
    prev = None
    for name, n in rep["funnel"]:
        step = f"{n / prev:.0%}" if prev else "—"
        L.append(f"| {name} | {n} | {step} | {n / base:.0%} |")
        prev = n if n else None
    L += ["", "## Stage conversion model (Beta posterior)", "", "| Transition | Observed | Planned prior | Current estimate |",
          "|---|---|---|---|"]
    for s, r in rep["stage_rates"].items():
        L.append(f"| → {s} | {r['observed']} | {r['prior_mean']:.0%} | {r['posterior_mean']:.1%} |")
    L += ["", f"Contacted → won: observed {conv['contacted_to_won_observed']}, estimated {conv['contacted_to_won_estimated']:.2%}.", "",
          "## Priority queue (sorted by expected revenue)", "",
          "| # | Company | Stage | ICP | Timing | ACV | P(win) | Expected | Next action |", "|---|---|---|---|---|---|---|---|---|"]
    for i, x in enumerate(rep["priority_queue"], 1):
        L.append(f"| {i} | {x['company']} | {x['stage']} | {x['icp']} | {x['timing']} | {x['acv']:,.0f} | {x['p_win']:.2%} | "
                 f"{x['expected_revenue']:,.0f} | {x['next_action']} |")
    L += ["", "ACV basis per company is in `priority_queue.csv`. P(win) before a reply includes a timing lift "
          "(0.5 + timing/50, capped) — a heuristic that should be replaced by segment data once outcomes exist.", ""]
    if rv.get("drafts"):
        L += ["## Review gate (email quality)", "", "| Metric | Value |", "|---|---|",
              f"| Drafts | {rv['drafts']} ({rv['pending']} pending) |", f"| Approved / rejected | {rv['approved']} / {rv['rejected']} |",
              f"| Average share changed by reviewer | {'—' if rv['avg_change'] is None else format(rv['avg_change'], '.0%')} |",
              f"| Heavy edits (>50% rewritten) | {'—' if rv['heavy_edit_rate'] is None else format(rv['heavy_edit_rate'], '.0%')} |", ""]
    if rep["variants"]:
        L += ["## Email angle performance", "", "| Pain-point family | Contacted | Replies | Reply rate |", "|---|---|---|---|"]
        for k, v in sorted(rep["variants"].items(), key=lambda kv: -(kv[1]["reply_rate"] or 0)):
            L.append(f"| {k} | {v['contacted']} | {v['replies']} | {v['reply_rate']:.0%} |")
    (out / "revenue_report.md").write_text("\n".join(L), encoding="utf-8")
    return {"report": out / "revenue_report.md", "queue": out / "priority_queue.csv", "metrics": out / "revenue_metrics.json"}
