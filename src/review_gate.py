"""Human review gate: Draft → (human reviews / edits) → Send.

Nothing is dispatched until a person approves it. Each draft is written to output/review/<slug>.txt for
the reviewer to edit in place, alongside the Evidence Map flags they must check. Approving measures how
much the reviewer changed: if more than half of the email was rewritten (word-level), the draft counts as a
heavy edit. That rate is the generator's quality metric, and it is reported by email angle.
"""

from __future__ import annotations

import datetime as dt
import difflib
import json
from pathlib import Path
from typing import Optional

HEAVY_EDIT = 0.5
MARK = "----- EDIT BELOW THIS LINE (keep the 'Subject:' line) -----"


def _dir(out_dir: Path) -> Path:
    d = out_dir / "review"
    d.mkdir(parents=True, exist_ok=True)
    return d


def change_ratio(before: str, after: str) -> float:
    """Share of the email that changed, 0 (untouched) – 1 (rewritten), measured on words."""
    a, b = before.split(), after.split()
    if not a and not b:
        return 0.0
    return round(1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 3)


def load(slug: str, out_dir: Path) -> Optional[dict]:
    p = _dir(out_dir) / f"{slug}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _save(rec: dict, out_dir: Path) -> None:
    (_dir(out_dir) / f"{rec['slug']}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")


def submit(slug: str, company: str, email, flags: list[str], pain_family: str, out_dir: Path) -> dict:
    """Queue a draft for review (idempotent: an existing decision is never overwritten)."""
    existing = load(slug, out_dir)
    if existing and existing["status"] != "pending":
        return existing
    rec = {"slug": slug, "company": company, "status": "pending", "created": dt.datetime.now().isoformat(timespec="seconds"),
           "learnings_applied": list(getattr(email, "learnings_applied", []) or []),
           "original_subject": email.subject, "original_body": email.email_body, "flags": flags, "pain_family": pain_family,
           "hook_source_url": email.hook_source_url}
    header = [f"REVIEW DRAFT — {company}", "Approve:  python main.py --approve \"" + company + "\"",
              "Reject:   python main.py --reject \"" + company + "\" --reason \"...\"", ""]
    header += ["CHECK BEFORE APPROVING:"] + [f"  ! {f}" for f in flags] if flags else ["No Evidence Map flags."]
    header += [f"Hook source: {email.hook_source_url}", "", MARK]
    (_dir(out_dir) / f"{slug}.txt").write_text("\n".join(header + [f"Subject: {email.subject}", "", email.email_body, ""]),
                                                encoding="utf-8")
    _save(rec, out_dir)
    return rec


def write_edited(slug: str, out_dir: Path, subject: str, body: str) -> None:
    """Save a reviewer's edits (e.g. from the control panel) in the same file the CLI reviewer edits."""
    path = _dir(out_dir) / f"{slug}.txt"
    head = path.read_text(encoding="utf-8").split(MARK, 1)[0] if path.exists() else ""
    clean = lambda s: s.replace("\r\n", "\n").strip()
    path.write_text(head + MARK + f"\nSubject: {clean(subject).splitlines()[0] if clean(subject) else ''}\n\n{clean(body)}\n",
                    encoding="utf-8")


def read_edited(slug: str, out_dir: Path) -> tuple[str, str]:
    text = (_dir(out_dir) / f"{slug}.txt").read_text(encoding="utf-8")
    text = text.split(MARK, 1)[-1].strip("\n")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("Subject:"):
        raise ValueError("The draft must start with a 'Subject:' line below the edit marker.")
    return lines[0][len("Subject:"):].strip(), "\n".join(lines[1:]).strip()


def approve(slug: str, out_dir: Path, reviewer: str = "") -> dict:
    rec = load(slug, out_dir)
    if not rec:
        raise ValueError("No draft is waiting for review for that company.")
    subject, body = read_edited(slug, out_dir)
    if not body:
        raise ValueError("The email body is empty.")
    ratio = change_ratio(rec["original_subject"] + " " + rec["original_body"], subject + " " + body)
    rec.update(status="approved", approved_subject=subject, approved_body=body, change_ratio=ratio,
               heavy_edit=ratio > HEAVY_EDIT, decided=dt.datetime.now().isoformat(timespec="seconds"), reviewer=reviewer)
    _save(rec, out_dir)
    from src.feedback_loop import edit_ops, log_signal
    log_signal(out_dir, "draft_approved", slug, rec["company"],
               {"change_ratio": ratio, "edits": [list(o) for o in edit_ops(rec["original_body"], body)][:12],
                "learnings_applied": rec.get("learnings_applied", [])})
    return rec


def withdraw(slug: str, out_dir: Path, reason: str) -> Optional[dict]:
    """The account no longer qualifies (new evidence or a rule change): take its pending draft off the desk."""
    rec = load(slug, out_dir)
    if not rec or rec["status"] != "pending":
        return None
    rec.update(status="withdrawn", reason=reason, decided=dt.datetime.now().isoformat(timespec="seconds"))
    _save(rec, out_dir)
    return rec


def reject(slug: str, out_dir: Path, reason: str) -> dict:
    rec = load(slug, out_dir)
    if not rec:
        raise ValueError("No draft is waiting for review for that company.")
    rec.update(status="rejected", reason=reason or "not given", decided=dt.datetime.now().isoformat(timespec="seconds"))
    _save(rec, out_dir)
    from src.feedback_loop import log_signal
    log_signal(out_dir, "draft_rejected", slug, rec["company"], {"reason": rec["reason"]})
    return rec


def all_records(out_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(_dir(out_dir).glob("*.json"))]


def stats(out_dir: Path) -> dict:
    recs = all_records(out_dir)
    recs = [r for r in recs if r["status"] != "withdrawn"]
    decided = [r for r in recs if r["status"] in ("approved", "rejected")]
    approved = [r for r in recs if r["status"] == "approved"]
    by_family: dict[str, list[float]] = {}
    for r in approved:
        by_family.setdefault(r.get("pain_family", "other"), []).append(r["change_ratio"])
    return {
        "drafts": len(recs), "pending": sum(1 for r in recs if r["status"] == "pending"),
        "approved": len(approved), "rejected": len(decided) - len(approved),
        "approval_rate": len(approved) / len(decided) if decided else None,
        "avg_change": round(sum(r["change_ratio"] for r in approved) / len(approved), 3) if approved else None,
        "heavy_edit_rate": sum(1 for r in approved if r["heavy_edit"]) / len(approved) if approved else None,
        "heavy_edit_by_family": {k: {"approved": len(v), "heavy": sum(1 for x in v if x > HEAVY_EDIT),
                                     "avg_change": round(sum(v) / len(v), 3)} for k, v in by_family.items()},
    }
