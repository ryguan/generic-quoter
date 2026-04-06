"""
general_quoter_models.py
Data structures and mathematical bounded calculators for the General Quoter Algorithm.
"""

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
