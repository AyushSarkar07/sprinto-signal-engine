"""Run history: one record per pipeline run, so each run's performance can be compared with the last.

Measures (per run):
  hit rate          qualified / researched
  flag rate         share of researched companies that needed a human (qualify-and-flag, hand-to-human, no contact)
  pages per company average pages read, against the page budget
  ruled out by      the question that ruled each account out
  human reasons     why a person had to look (unknown core answer, unreadable site, no decision-maker)
  learnings applied drafts in this run that used reviewer learnings
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path


def drop_reason(q) -> str:
    for a in q.evidence_map:
        if a.get("short_circuit_hit"):
            return a["question"]
    no = [a["question"] for a in q.evidence_map if a.get("core") and a["answer"] == "no"]
    if q.qualification_reasoning and q.qualification_reasoning[0].startswith("Human override"):
        return "Human override"
    return no[0] if no else "Other"


def human_reasons(run) -> list[str]:
    q = run.qualification
    out = []
    if not q:
        return ["Site could not be read"]
    if q.gate_decision == "HAND_TO_HUMAN":
        out.append("Site could not be read" if (run.scrape and run.scrape.scraping_status == "failed") else "Too few core answers")
    for a in q.evidence_map:
        if q.gate_decision == "QUALIFY_AND_FLAG" and a.get("core") and a["answer"] == "unknown":
            out.append(f"Unknown: {a['question']}")
    if q.qualified and run.contact_selection and run.contact_selection.status != "selected":
        out.append("No decision-maker found")
    return out


def summarise(runs: list, budget: int, llm_calls: int = 0) -> dict:
    scored = [r for r in runs if r.qualification]
    q = [r for r in scored if r.qualification.qualified]
    drops = Counter(drop_reason(r.qualification) for r in scored if r.qualification.gate_decision == "DROP")
    humans = Counter(h for r in runs for h in human_reasons(r))
    needing_human = sum(1 for r in runs if human_reasons(r))
    pages = [len(r.scrape.ok_pages()) for r in runs if r.scrape]
    return {
        "companies": [r.company for r in runs],
        "researched": len(runs), "qualified": len(q),
        "nurture": sum(1 for r in scored if r.qualification.gate_decision == "NURTURE"),
        "dropped": sum(drops.values()), "needs_human": needing_human,
        "hit_rate": round(len(q) / len(runs), 3) if runs else 0,
        "flag_rate": round(needing_human / len(runs), 3) if runs else 0,
        "pages_per_company": round(sum(pages) / len(pages), 1) if pages else 0, "page_budget": budget,
        "drop_reasons": dict(drops), "human_reasons": dict(humans),
        "drafts": sum(1 for r in runs if r.email),
        "learnings_applied": sum(1 for r in runs if r.email and r.email.learnings_applied),
        "llm_calls": llm_calls,
    }


def record(out_dir: Path, runs: list, budget: int, llm_calls: int, mode: str = "batch") -> dict:
    path = out_dir / "runs.jsonl"
    n = sum(1 for _ in path.open()) + 1 if path.exists() else 1
    entry = {"run": n, "at": dt.datetime.now().isoformat(timespec="seconds"), "mode": mode, **summarise(runs, budget, llm_calls)}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(out_dir: Path) -> list[dict]:
    path = out_dir / "runs.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
