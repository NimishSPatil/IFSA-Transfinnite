"""
reviews.py - the decision queue. Every recommendation is a review candidate; nothing is executed.

Status: Pending (default) / Approved / Rejected / Deferred / Escalated (to COO, case F67).
A rationale is required for every status change. Records are appended, never overwritten, so the
history of each item is kept (state/reviews.jsonl).
"""
import json
from datetime import datetime

from .controls import STATE, _ensure

STATUSES = ["Pending", "Approved", "Rejected", "Deferred", "Escalated"]
ROLES = ["Planning", "Procurement", "Production", "Logistics", "Marketing", "Supply chain manager", "COO"]


def _path():
    _ensure()
    return STATE / "reviews.jsonl"


def history():
    p = _path()
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def latest():
    """rec_id -> latest decision record."""
    out = {}
    for r in history():
        out[r["rec_id"]] = r
    return out


def status_of(rec_id):
    r = latest().get(rec_id)
    return r["status"] if r else "Pending"


def record(rec_id, status, rationale, role, title="", scenario=""):
    if status not in STATUSES:
        raise ValueError("unknown status")
    if not rationale or len(rationale.strip()) < 5:
        raise ValueError("a rationale of at least a few words is required")
    if role not in ROLES:
        raise ValueError("unknown role")
    r = dict(ts=datetime.now().isoformat(timespec="seconds"), rec_id=rec_id, status=status,
             rationale=rationale.strip(), role=role, title=title, scenario=scenario, executed=False)
    with open(_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(r) + "\n")
    return r


def annotate(recs):
    """Attach the current status and last decision to a list of recommendation dicts (each has 'id')."""
    lt = latest()
    for r in recs:
        d = lt.get(r["id"])
        r["status"] = d["status"] if d else "Pending"
        r["decision"] = d
    return recs
