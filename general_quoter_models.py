"""
general_quoter_models.py
Data structures and mathematical bounded calculators for the General Quoter Algorithm.
"""

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math
import uuid

class QuoteSide(Enum):
    TEAM_A = "TEAM_A"
    TEAM_B = "TEAM_B"
    TIE = "TIE"

class QuoteStatus(Enum):
    PENDING = "PENDING"
    RESTING = "RESTING"
    CANCELED = "CANCELED"
    FILLED = "FILLED"
    FAILED = "FAILED"

@dataclass
class ActiveQuote:
    side: QuoteSide
    target_ticker: str
    intent: str
    price_cents: int
    qty: int
    client_order_id: str
    kalshi_order_id: str
    status: QuoteStatus
    placed_at: float
    filled_qty: int = 0

@dataclass
class MarketData:
    ticker: str
    yes_ob: list[tuple[int, int]] = field(default_factory=list) # [(price_cents, qty), ...]
    no_ob: list[tuple[int, int]] = field(default_factory=list)

@dataclass
class QuoteCalculation:
    side: QuoteSide
    target_ticker: str
    vwap_price: float
    penny_jump_level: Optional[int]
    worse_level: Optional[int]
    base_limit: int
    skew_shift_cents: float
    final_limit: int
    qty: int
    reason: str

@dataclass
class QuoteTarget:
    """Ephemeral pricing target computed each poll cycle."""
    ticker: str
    side: str
    limit: int
    qty: int

@dataclass
class OrderRecord:
    """Persistent order record for state store serialization."""
    order_id: str
    client_order_id: str
    ticker: str
    side: str
    limit_cents: int
    count: int
    filled_count: int = 0
    fill_cents: int = 0
    ts: float = 0.0
    game: str = ""
    intent_count: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'OrderRecord':
        return cls(
            order_id=d.get("order_id", ""),
            client_order_id=d.get("client_order_id", ""),
            ticker=d.get("ticker", ""),
            side=d.get("side", ""),
            limit_cents=int(d.get("limit_cents", 0)),
            count=int(d.get("count", 0)),
            filled_count=int(d.get("filled_count", 0)),
            fill_cents=int(d.get("fill_cents", 0)),
            ts=float(d.get("ts", 0.0)),
            game=d.get("game", ""),
            intent_count=int(d.get("intent_count", 0)),
        )

@dataclass
class PlacedOrder:
    """Typed response from the Kalshi place-order API."""
    order_id: str

    @classmethod
    def from_api_response(cls, resp: dict) -> 'PlacedOrder':
        return cls(order_id=resp.get("order", {}).get("order_id", ""))

@dataclass
class TradeRow:
    """Single trade row for dashboard display."""
    ts_str: str
    game_matchup: str
    ticker_type: str
    ticker_short: str
    ticker: str
    exec_type: str
    side: str
    limit_cents: int
    fill_cents: int
    count: int
    filled_count: int
    pnl_cents: float
    fee_cents: float
    current_cents: Optional[float] = None
    mature: bool = False
    mark_30s_cents: Optional[int] = None
    mark_120s_cents: Optional[int] = None
    pnl_30s_cents: Optional[float] = None
    pnl_120s_cents: Optional[float] = None
    dry_run: bool = False
    sweep_id: str = ""

@dataclass
class PositionRow:
    """Net position for dashboard display."""
    ticker_suffix: str
    direction: str
    lots: int
    current_cents: Optional[float] = None

@dataclass
class TradesResponse:
    """Full /api/trades JSON response."""
    trades: list[TradeRow]
    positions: list[PositionRow]
    pnl_cents: float
    fee_cents: float
    games: list[str]
    per_game_pnl: dict
    per_game_fees: dict
    timestamp: str = ""
    sweeps: list = field(default_factory=list)
    per_sweep_pnl: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

def calculate_logit_min_edge(cents_price: float, min_edge_50c: float, absolute_min_edge: float) -> float:
    """
    Calculates the MIN_EDGE dynamically based on how deep into the extremes the price is.
    Centers at 50c (returns min_edge_50c), and flattens out at 1c or 99c to absolute_min_edge.
    """
    prob = cents_price / 100.0
    if prob <= 0 or prob >= 1:
        return absolute_min_edge
        
    dist_from_50 = abs(prob - 0.5)
    
    # scale goes from 0.0 to 1.0 at the absolute extremes
    scale = dist_from_50 / 0.5 
    
    # Apply a non-linear curvature
    scale = scale ** 2
    
    edge_diff = min_edge_50c - absolute_min_edge
    calculated_edge = min_edge_50c - (edge_diff * scale)
    
    return max(absolute_min_edge, calculated_edge)

def calculate_positional_skew(
    position_lots: int,
    max_position: int,
    start_fraction: float,
    max_shift_cents: float
) -> float:
    """
    Calculates the linear step-off skew penalty when our position starts reaching capacity.
    Returns the cents (magnitude) we should shift our edge away from the market.
    """
    shift_threshold = max_position * start_fraction
    if position_lots <= shift_threshold:
        return 0.0
        
    if shift_threshold >= max_position:
        return 0.0 # Safety
        
    utilization_above_threshold = (position_lots - shift_threshold) / (max_position - shift_threshold)
    utilization_above_threshold = min(1.0, max(0.0, utilization_above_threshold))
    
    skew = utilization_above_threshold * max_shift_cents
    return skew
