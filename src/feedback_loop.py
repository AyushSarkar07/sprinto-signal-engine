"""Learning log: write, react, log, distil, recall, use.

  Write     the pipeline drafts emails and answers the Evidence Map.
  React     a person reacts: edits a draft before approving it, rates it (thumbs plus reason tags), rejects it,
            overrides a gate decision, or logs what the prospect did.
  Log       every reaction is appended to output/feedback/signals.jsonl with its context.
  Distil    learn() distils repeated reactions into learnings (output/feedback/learnings.json):
              replace_sentence  reviewers swapped sentence A for B in 2+ approved drafts
              drop_sentence     reviewers deleted sentence A in 2+ approved drafts
              writer_note       the same verdict tick ("could be any company", "too wordy", ...) given 2+ times
              gate_pattern      humans dropped 2+ companies the rules had flagged for the same reason
                                (shown as a suggested rule, never applied automatically)
  Recall    before a draft is written, active learnings are loaded.
  Use       sentence swaps and deletions are applied to the new draft (never to the evidence hook), writer
            notes go into the Claude prompt, and every use is counted. The loop reports whether drafts that
            used learnings needed fewer reviewer edits than drafts that did not.

Learnings need repeated evidence (2+ independent signals) and can be retired; nothing is learned from one event.
"""

from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

MIN_SUPPORT = 2
RATING_TAGS = ["strong opening fact", "could be any company", "too wordy", "sounds salesy", "wrong person", "opening fact is weak", "something is wrong"]
SIGNAL_KINDS = ["draft_approved", "draft_rejected", "draft_rating", "override_qualify", "override_drop", "outcome"]


def _dir(out_dir: Path) -> Path:
    d = out_dir / "feedback"
    d.mkdir(parents=True, exist_ok=True)
    return d


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- signal + capture

def log_signal(out_dir: Path, kind: str, slug: str, company: str, data: dict | None = None, actor: str = "reviewer") -> dict:
    ev = {"ts": now(), "kind": kind, "slug": slug, "company": company, "actor": actor, "data": data or {}}
    with (_dir(out_dir) / "signals.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")
    return ev


def signals(out_dir: Path) -> list[dict]:
    p = _dir(out_dir) / "signals.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def rate(out_dir: Path, slug: str, company: str, thumbs: str, tags: list[str]) -> dict:
    if thumbs not in ("up", "down"):
        raise ValueError("Rating must be 'up' or 'down'.")
    tags = [t for t in tags if t in RATING_TAGS]
    return log_signal(out_dir, "draft_rating", slug, company, {"thumbs": thumbs, "tags": tags})


# ---------------------------------------------------------------- overrides (decision desk)

def overrides(out_dir: Path) -> dict:
    p = _dir(out_dir) / "overrides.json"
    return json.loads(p.read_text()) if p.exists() else {}


def set_override(out_dir: Path, slug: str, company: str, decision: str, reason: str, flagged_for: str = "") -> dict:
    decision = decision.upper()
    if decision not in ("QUALIFY", "DROP"):
        raise ValueError("Override must be QUALIFY or DROP.")
    if not reason.strip():
        raise ValueError("Give a reason.")
    data = overrides(out_dir)
    data[slug] = {"decision": decision, "reason": reason.strip()[:300], "ts": now(), "company": company, "flagged_for": flagged_for}
    (_dir(out_dir) / "overrides.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    log_signal(out_dir, f"override_{decision.lower()}", slug, company, {"reason": reason.strip()[:300], "flagged_for": flagged_for})
    return data[slug]


def apply_override(q, override: dict | None):
    """Force a human decision onto a Qualification, keeping the rules' original verdict visible."""
    if not override:
        return q
    was = q.gate_decision
    if override["decision"] == "QUALIFY":
        q.qualified, q.decision_status, q.recommended_action, q.gate_decision = True, "qualified", "outreach", "QUALIFY"
    else:
        q.qualified, q.decision_status, q.recommended_action, q.gate_decision = False, "not_qualified", "disqualify", "DROP"
    q.qualification_reasoning.insert(0, f"Human override → {override['decision']} (rules said {was}): {override['reason']}")
    q.review_flags = []
    return q


# ---------------------------------------------------------------- store (distil learnings)

def _sentences(body: str) -> list[str]:
    lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    if lines and re.match(r"^(hi|hello|hey)\b", lines[0], re.I):
        lines = lines[1:]
    out = []
    for l in lines:
        if re.match(r"^(best|thanks|cheers|regards)[,!.]?$", l, re.I):
            break
        out += [s.strip() for s in re.split(r"(?<=[.?!])\s+", l) if s.strip()]
    return out


def edit_ops(original: str, approved: str) -> list[tuple[str, str, str]]:
    """Sentence-level changes a reviewer made: ('replace', a, b), ('drop', a, ''), ('add', '', b)."""
    a, b = _sentences(original), _sentences(approved)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "replace":
            ops += _pair(a[i1:i2], b[j1:j2])
        elif tag == "delete":
            ops += [("drop", s, "") for s in a[i1:i2]]
        elif tag == "insert":
            ops += [("add", "", s) for s in b[j1:j2]]
    return ops


def _pair(old: list[str], new: list[str]) -> list[tuple[str, str, str]]:
    """Inside a changed block, decide which new sentence rewrote which old one. A rewrite either shares wording
    or plays the same role (a question replaced by a question, e.g. the call to action); the rest are drops/adds."""
    def score(x: str, y: str) -> float:
        same_role = 0.5 if x.rstrip().endswith("?") and y.rstrip().endswith("?") else 0.0
        return difflib.SequenceMatcher(None, x.lower(), y.lower()).ratio() + same_role
    ops, used = [], set()
    for y in new:
        best = max(((score(x, y), i) for i, x in enumerate(old) if i not in used), default=(0, None))
        if best[1] is not None and best[0] >= 0.55:
            used.add(best[1])
            ops.append(("replace", old[best[1]], y))
        else:
            ops.append(("add", "", y))
    return [("drop", x, "") for i, x in enumerate(old) if i not in used] + ops


ALLOWED_CAPS = {"SOC", "ISO", "GDPR", "HIPAA", "Sprinto", "I", "AI", "CTO", "CEO", "CISO", "GRC", "Type", "II"}


def is_generic(sentence: str) -> bool:
    """A reviewer's sentence may be reused on other accounts only if it states no account-specific fact:
    no numbers or money, and no proper names beyond compliance terms. Otherwise it could put one company's
    facts into another company's email, which the brief forbids (never invent company information)."""
    if re.search(r"[0-9$€£%]", sentence.replace("15-minute", "").replace("20-minute", "").replace("30-minute", "")):
        return False
    words = re.findall(r"\b[A-Z][a-zA-Z]+\b", sentence)[1:]  # ignore the sentence's first word
    return all(w in ALLOWED_CAPS for w in words)


def _lid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]


def load_learnings(out_dir: Path) -> list[dict]:
    p = _dir(out_dir) / "learnings.json"
    return json.loads(p.read_text()) if p.exists() else []


def _save_learnings(out_dir: Path, items: list[dict]) -> None:
    (_dir(out_dir) / "learnings.json").write_text(json.dumps(items, indent=2), encoding="utf-8")


def learn(out_dir: Path, reviews: list[dict]) -> list[dict]:
    """Distil learnings from approved drafts and signals. Keeps usage counts and retirements across runs."""
    old = {l["id"]: l for l in load_learnings(out_dir)}
    found: dict[str, dict] = {}

    swaps, drops = defaultdict(set), defaultdict(set)
    for r in reviews:
        if r.get("status") != "approved" or not r.get("approved_body"):
            continue
        for op, a, b in edit_ops(r["original_body"], r["approved_body"]):
            if op == "replace":
                swaps[(a, b)].add(r["slug"])
            elif op == "drop":
                drops[a].add(r["slug"])
    for (a, b), who in swaps.items():
        if len(who) >= MIN_SUPPORT and is_generic(b):
            found[_lid("replace", a, b)] = {"scope": "writer", "kind": "replace_sentence", "find": a, "replace": b,
                                            "lesson": f"Use “{b}” in place of “{a}”.", "support": len(who), "evidence": sorted(who)}
    for a, who in drops.items():
        if len(who) >= MIN_SUPPORT:
            found[_lid("drop", a)] = {"scope": "writer", "kind": "drop_sentence", "find": a, "replace": "",
                                      "lesson": f"Cut “{a}” (you removed it on {len(who)} accounts).",
                                      "support": len(who), "evidence": sorted(who)}

    sig = signals(out_dir)
    tags = Counter(t for s in sig if s["kind"] == "draft_rating" for t in s["data"].get("tags", []) if t != "strong opening fact")
    notes = {"could be any company": "Open with a fact only this account has, with its date if there is one.",
             "too wordy": "Aim for 90 words or fewer.", "sounds salesy": "Write as a peer: no superlatives, no hype.",
             "opening fact is weak": "Open with the newest dated signal rather than a general remark about growth.",
             "wrong person": "Match the person's role to the problem before writing.",
             "something is wrong": "Say nothing that is not quoted word for word in the evidence."}
    for tag, n in tags.items():
        if n >= MIN_SUPPORT and tag in notes:
            found[_lid("note", tag)] = {"scope": "writer", "kind": "writer_note", "find": "", "replace": "",
                                        "lesson": notes[tag], "support": n, "evidence": [f"rated “{tag}” {n}×"]}

    dropped = Counter(s["data"].get("flagged_for", "") for s in sig if s["kind"] == "override_drop" and s["data"].get("flagged_for"))
    for reason, n in dropped.items():
        if n >= MIN_SUPPORT:
            found[_lid("gate", reason)] = {"scope": "qualify", "kind": "gate_pattern", "find": reason, "replace": "",
                                           "lesson": f"You ruled out {n} accounts sent to your desk for “{reason}”. A rule could do this for you.",
                                           "support": n, "evidence": [f"{n} override drops"]}

    items = []
    for lid, l in found.items():
        prev = old.get(lid, {})
        items.append({"id": lid, **l, "status": prev.get("status", "active"), "used": prev.get("used", 0),
                      "created": prev.get("created", now()), "applies_to": "all drafts" if l["scope"] == "writer" else "gate review"})
    items += [dict(l, status="retired") for lid, l in old.items() if lid not in found and l.get("status") == "retired"]
    _save_learnings(out_dir, items)
    return items


def retire(out_dir: Path, lid: str) -> None:
    items = load_learnings(out_dir)
    for l in items:
        if l["id"] == lid:
            l["status"] = "retired"
    _save_learnings(out_dir, items)


# ---------------------------------------------------------------- retrieve + apply

def active_writer_learnings(out_dir: Path) -> list[dict]:
    return [l for l in load_learnings(out_dir) if l["status"] == "active" and l["scope"] == "writer"]


def apply_to_body(body: str, learnings: list[dict], protect: str = "") -> tuple[str, list[str]]:
    """Apply sentence swaps and deletions. `protect` (the evidence hook sentence) is never touched."""
    applied = []
    for l in learnings:
        a = l.get("find", "")
        if l["kind"] not in ("replace_sentence", "drop_sentence") or not a or a not in body or (protect and a in protect):
            continue
        body = body.replace(a, l["replace"]) if l["kind"] == "replace_sentence" else body.replace(" " + a, "").replace(a + " ", "").replace(a, "")
        applied.append(l["id"])
    body = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", body)).strip()
    return body, applied


def count_use(out_dir: Path, ids: list[str]) -> None:
    if not ids:
        return
    items = load_learnings(out_dir)
    for l in items:
        if l["id"] in ids:
            l["used"] = l.get("used", 0) + 1
    _save_learnings(out_dir, items)


def prompt_notes(learnings: list[dict]) -> str:
    lines = [f"- {l['lesson']}" for l in learnings]
    return ("Guidance from the person who signs off these emails:\n" + "\n".join(lines)) if lines else ""


# ---------------------------------------------------------------- loop health

def loop_stats(out_dir: Path, reviews: list[dict]) -> dict:
    sig = signals(out_dir)
    learns = load_learnings(out_dir)
    approved = [r for r in reviews if r.get("status") == "approved"]
    with_l = [r["change_ratio"] for r in approved if r.get("learnings_applied")]
    without = [r["change_ratio"] for r in approved if not r.get("learnings_applied")]
    avg = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    return {
        "act": len(reviews),
        "signal": len(sig),
        "capture": dict(Counter(s["kind"] for s in sig)),
        "store": sum(1 for l in learns if l["status"] == "active"),
        "retrieve": sum(l.get("used", 0) for l in learns),
        "apply": sum(1 for r in reviews if r.get("learnings_applied")),
        "edit_with": avg(with_l), "n_with": len(with_l), "edit_without": avg(without), "n_without": len(without),
        "stages_with_data": sum(1 for v in (len(reviews), len(sig), len(sig), len(learns),
                                           sum(l.get("used", 0) for l in learns),
                                           sum(1 for r in reviews if r.get("learnings_applied"))) if v),
    }
