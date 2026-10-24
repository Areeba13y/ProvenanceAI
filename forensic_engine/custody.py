"""Step 3: chain-of-custody log (SQLite).

Every entry stores the hash of the previous entry, so editing or deleting an
old entry breaks the chain and verify_chain() will report it.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

GENESIS = "0" * 64


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CustodyLog:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS evidence(
                evidence_id TEXT PRIMARY KEY, original_name TEXT, sha256 TEXT,
                size_bytes INTEGER, stored_path TEXT, received_at TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS custody(
                id INTEGER PRIMARY KEY AUTOINCREMENT, evidence_id TEXT,
                timestamp_utc TEXT, action TEXT, details TEXT,
                prev_hash TEXT, entry_hash TEXT)""")

    def _conn(self):
        return sqlite3.connect(self.db_path)

    # ---- evidence records -------------------------------------------------
    def next_evidence_id(self):
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        return f"EV-{n + 1:03d}"

    def add_evidence(self, evidence_id, original_name, sha256, size_bytes, stored_path):
        with self._conn() as c:
            c.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?)",
                      (evidence_id, original_name, sha256, size_bytes, str(stored_path), _now()))

    def find_by_hash(self, sha256):
        with self._conn() as c:
            row = c.execute("SELECT evidence_id FROM evidence WHERE sha256=?", (sha256,)).fetchone()
        return row[0] if row else None

    # ---- audit log --------------------------------------------------------
    @staticmethod
    def _entry_hash(prev, evidence_id, ts, action, details):
        payload = "|".join([prev, evidence_id, ts, action, details])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log(self, evidence_id, action, details=None):
        details_json = json.dumps(details or {}, sort_keys=True, ensure_ascii=False)
        ts = _now()
        with self._conn() as c:
            row = c.execute("SELECT entry_hash FROM custody ORDER BY id DESC LIMIT 1").fetchone()
            prev = row[0] if row else GENESIS
            h = self._entry_hash(prev, evidence_id, ts, action, details_json)
            c.execute("INSERT INTO custody(evidence_id,timestamp_utc,action,details,prev_hash,entry_hash)"
                      " VALUES (?,?,?,?,?,?)", (evidence_id, ts, action, details_json, prev, h))

    def entries(self, evidence_id=None):
        q = "SELECT id,evidence_id,timestamp_utc,action,details,entry_hash FROM custody"
        args = ()
        if evidence_id:
            q += " WHERE evidence_id=?"
            args = (evidence_id,)
        with self._conn() as c:
            rows = c.execute(q + " ORDER BY id", args).fetchall()
        return [{"seq": r[0], "evidence_id": r[1], "timestamp_utc": r[2], "action": r[3],
                 "details": json.loads(r[4]), "entry_hash": r[5]} for r in rows]

    def verify_chain(self):
        """Return (ok, broken_at_id). ok=False means the log was altered."""
        prev = GENESIS
        with self._conn() as c:
            rows = c.execute("SELECT id,evidence_id,timestamp_utc,action,details,prev_hash,entry_hash"
                             " FROM custody ORDER BY id").fetchall()
        for rid, ev, ts, action, details, p, h in rows:
            if p != prev or h != self._entry_hash(p, ev, ts, action, details):
                return False, rid
            prev = h
        return True, None
