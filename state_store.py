"""
state_store.py
--------------
Persistent shared state for the Kalshi esports trading dashboard.
Writes to `.kalshi_state.json`.
"""

import fcntl
import json
from pathlib import Path
from typing import Any

from general_quoter_models import OrderRecord

_DIR   = Path(__file__).parent
_STORE = _DIR / ".kalshi_state.json"
_LOCK  = _DIR / ".kalshi_state.lock"

def _load_raw() -> dict:
    try:
        return json.loads(_STORE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"orders": [], "sweeps": []}

def _save_raw(data: dict) -> None:
    tmp = _STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(_STORE)

class _Lock:
    def __enter__(self):
        self._fh = open(_LOCK, "w")
        fcntl.flock(self._fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_):
        fcntl.flock(self._fh, fcntl.LOCK_UN)
        self._fh.close()

def load() -> dict:
    return _load_raw()

def load_orders() -> list[OrderRecord]:
    d = _load_raw()
    return [OrderRecord.from_dict(o) for o in d.get("orders", [])]

def append_order(rec: OrderRecord) -> None:
    with _Lock():
        d = _load_raw()
        d["orders"].append(rec.to_dict())
        _save_raw(d)

def patch_order(order_id: str, **updates: Any) -> None:
    with _Lock():
        d = _load_raw()
        for o in d["orders"]:
            if o.get("order_id") == order_id:
                o.update(updates)
                break
        _save_raw(d)

def clear() -> None:
    with _Lock():
        _save_raw({"orders": [], "sweeps": []})


# ── Quoter state ─────────────────────────────────────────────────────────

def save_quoter_state(snapshot: dict) -> None:
    """Overwrite the quoter snapshot (position, quotes, hedges, risk)."""
    with _Lock():
        d = _load_raw()
        d["quoter"] = snapshot
        _save_raw(d)


def load_quoter_state() -> dict:
    d = _load_raw()
    return d.get("quoter", {})
