"""
general_quoter_config.py
Configuration parameters for the General Quoter Algorithm.
"""

from dataclasses import dataclass
import csv
import logging
from pathlib import Path

log = logging.getLogger("general_quoter")
_CONFIG_FILE = Path(__file__).parent / "general_quoter_config.csv"

_KEY_MAP: dict[str, tuple[str, type]] = {
    "quoting.max_market_width":            ("MAX_MARKET_WIDTH", float),
    "quoting.typical_market_volume":       ("TYPICAL_MARKET_VOLUME", int),
    "quoting.order_volume_multiplier":     ("ORDER_VOLUME_MULTIPLIER", float),
    "quoting.min_edge_at_50c":             ("MIN_EDGE_AT_50C", float),
    "quoting.absolute_min_edge":           ("ABSOLUTE_MIN_EDGE", float),
    "quoting.max_edge":                    ("MAX_EDGE", float),
    "quoting.min_levels":                  ("MIN_LEVELS", int),
    "quoting.sweep_levels":                ("SWEEP_LEVELS", int),
    "quoting.sweep_cooldown_seconds":      ("SWEEP_COOLDOWN_SECONDS", int),
    "quoting.reprice_bounds":              ("REPRICE_BOUNDS", float),
    "quoting.poll_interval_seconds":       ("POLL_INTERVAL_SECONDS", float),
    "quoting.price_bound_low":             ("PRICE_BOUND_LOW", float),
    "quoting.price_bound_high":            ("PRICE_BOUND_HIGH", float),
    
    "risk.max_position_per_side":          ("MAX_POSITION_PER_SIDE", int),
    "risk.skew_start_fraction":            ("SKEW_START_FRACTION", float),
    "risk.skew_max_shift_cents":           ("SKEW_MAX_SHIFT_CENTS", float),
    "risk.halt_unhedged_threshold":        ("HALT_UNHEDGED_THRESHOLD", int),
    
    "execution.trading_enabled":           ("TRADING_ENABLED", lambda v: v.lower() in ("true", "1", "yes")),
}

@dataclass
class GeneralQuoterConfig:
    # ── Quoting Parameters ──
    MAX_MARKET_WIDTH: float = 10.0
    TYPICAL_MARKET_VOLUME: int = 100
    ORDER_VOLUME_MULTIPLIER: float = 1.0
    MIN_EDGE_AT_50C: float = 3.0
    ABSOLUTE_MIN_EDGE: float = 1.0
    MAX_EDGE: float = 5.0
    MIN_LEVELS: int = 3
    SWEEP_LEVELS: int = 3
    SWEEP_COOLDOWN_SECONDS: int = 15
    REPRICE_BOUNDS: float = 1.0
    POLL_INTERVAL_SECONDS: float = 1.0
    PRICE_BOUND_LOW: float = 3.0
    PRICE_BOUND_HIGH: float = 97.0

    # ── Risk Parameters ──
    MAX_POSITION_PER_SIDE: int = 500
    SKEW_START_FRACTION: float = 0.5
    SKEW_MAX_SHIFT_CENTS: float = 3.0
    HALT_UNHEDGED_THRESHOLD: int = 200

    # ── Execution ──
    TRADING_ENABLED: bool = True

def _parse_csv(path: Path) -> dict[str, str]:
    raw: dict[str, str] = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#") or len(row) < 2:
                continue
            raw[row[0].strip()] = row[1].strip()
    return raw

def _apply_raw(cfg: GeneralQuoterConfig, raw: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for csv_key, (field_name, converter) in _KEY_MAP.items():
        if csv_key not in raw:
            continue
        try:
            new_val = converter(raw[csv_key])
            old_val = getattr(cfg, field_name)
            if new_val != old_val:
                setattr(cfg, field_name, new_val)
                changed.append(field_name)
        except (ValueError, TypeError) as e:
            log.warning("CONFIG | bad value for %s: %r (%s)", csv_key, raw[csv_key], e)
    return changed

def load_general_quoter_config(path: Path | None = None) -> GeneralQuoterConfig:
    cfg_path = path or _CONFIG_FILE
    cfg = GeneralQuoterConfig()
    if not cfg_path.exists():
        log.warning("CONFIG | %s not found, using defaults", cfg_path)
        return cfg
    raw = _parse_csv(cfg_path)
    _apply_raw(cfg, raw)
    log.info("CONFIG LOAD | %s", cfg_path)
    return cfg

def reload_general_quoter_config(cfg: GeneralQuoterConfig, path: Path | None = None) -> bool:
    cfg_path = path or _CONFIG_FILE
    if not cfg_path.exists():
        return False
    try:
        raw = _parse_csv(cfg_path)
        changed = _apply_raw(cfg, raw)
        if changed:
            log.info("CONFIG RELOAD | changed: %s", ", ".join(changed))
            return True
        return False
    except Exception:
        log.exception("CONFIG RELOAD ERROR")
        return False
