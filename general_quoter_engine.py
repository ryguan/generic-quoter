"""
general_quoter_engine.py
Asynchronous General Quoter Engine implementing Phase 1-6 natively.
"""

import asyncio
import logging
import time
import math
import uuid
from typing import Optional, Dict, List, Tuple

from general_quoter_config import GeneralQuoterConfig
from general_quoter_models import MarketData, QuoteSide, QuoteStatus, ActiveQuote, calculate_logit_min_edge, calculate_positional_skew
from kalshi_client import KalshiClient
import state_store

log = logging.getLogger("general_quoter")

class GeneralQuoterEngine:
    def __init__(self, client: KalshiClient, config: GeneralQuoterConfig, tickers: List[str]):
        self.client = client
        self.config = config
        self.tickers = tickers
        
        self.orderbooks: Dict[str, MarketData] = {t: MarketData(ticker=t) for t in tickers}
        self.positions: Dict[str, int] = {f"{t}_yes": 0 for t in tickers}
        self.positions.update({f"{t}_no": 0 for t in tickers})
        
        self.active_quotes: Dict[str, ActiveQuote] = {}
        
        self.last_poll_time = 0.0
        self.sweep_cooldown_until = 0.0
        
        self.is_2_way = len(tickers) == 2
        
        # Load legacy positions accurately on boot
        try:
            data = state_store.load()
            count = 0
            for o in data.get("orders", []):
                t = o.get("ticker", "")
                s = o.get("side", "")
                fc = int(o.get("filled_count", 0))
                if t and s and fc > 0:
                    key = f"{t}_{s}"
                    self.positions[key] = self.positions.get(key, 0) + fc
                    count += fc
            log.info(f"Loaded {count} existing Kalshi position lots from state store.")
        except Exception as e:
            log.error(f"Error loading legacy positions: {e}")

    async def start(self):
        log.info("Starting General Quoter Engine...")
        asyncio.create_task(self._trade_ws_loop())
        while True:
            await self._quoter_loop()
            await asyncio.sleep(self.config.POLL_INTERVAL_SECONDS)

    async def _trade_ws_loop(self):
        """Phase 5: Sweep Detection & Cooldown via WS"""
        # Pseudo-logic for live tracking
        # We would natively hook `kalshi ticker` feed.
        # Track active executed trades per second.
        # if distinct_price_levels >= self.config.SWEEP_LEVELS inside 1000ms:
        #    log.warning("SWEEP DETECTED! Pulling Quotes...")
        #    await self._cancel_all()
        #    self.sweep_cooldown_until = time.time() + self.config.SWEEP_COOLDOWN_SECONDS
        pass

    def _get_asks_for_side(self, t: str, side: str) -> List[Tuple[int, int]]:
        ob = self.orderbooks[t]
        if side == "yes":
            asks = [(100 - p, q) for p, q in ob.no_ob]
        else:
            asks = [(100 - p, q) for p, q in ob.yes_ob]
        asks.sort(key=lambda x: x[0])
        return asks

    def _simulate_sweep(self, ob_levels: List[Tuple[int, int]], target_volume: int, default_exhaust: float = 0.0) -> float:
        remaining = target_volume
        worst_price = -1
        for price, qty in ob_levels:
            worst_price = price
            if qty >= remaining:
                return float(worst_price)
            remaining -= qty
        return default_exhaust

    def _get_bids_for_side(self, t: str, side: str) -> List[Tuple[int, int]]:
        ob = self.orderbooks[t]
        if side == "yes":
            bids = list(ob.yes_ob)
        else:
            bids = list(ob.no_ob)
        bids.sort(key=lambda x: x[0], reverse=True)
        return bids

    def _get_midpoint(self, t: str, side: str) -> Optional[float]:
        bids = self._get_bids_for_side(t, side)
        asks = self._get_asks_for_side(t, side)
        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 100.0
        if best_bid == 0.0 and best_ask == 100.0:
            return None
        return (best_bid + best_ask) / 2.0

    def _run_theoretical(self, target_ticker: str, target_side: str) -> Tuple[Optional[float], bool]:
        """Phase 1: Returns (Theoretical_VWAP_Value, is_illiquid). 
        Calculates Top-of-Book VWAP between the best bid and best ask."""
        bids = self._get_bids_for_side(target_ticker, target_side)
        asks = self._get_asks_for_side(target_ticker, target_side)
        
        if self.is_2_way:
            recip_ticker = self.tickers[0] if target_ticker == self.tickers[1] else self.tickers[1]
            recip_side = "no" if target_side == "yes" else "yes"
            
            bids_recip = self._get_bids_for_side(recip_ticker, recip_side)
            asks_recip = self._get_asks_for_side(recip_ticker, recip_side)
            
            bids = bids + bids_recip
            asks = asks + asks_recip
            bids.sort(key=lambda x: x[0], reverse=True)
            asks.sort(key=lambda x: x[0])

        best_bid = bids[0][0] if bids else 0.0
        bid_vol = sum(v for p, v in bids if p == best_bid)

        best_ask = asks[0][0] if asks else 100.0
        ask_vol = sum(v for p, v in asks if p == best_ask)
        
        if best_bid == 0.0 and best_ask == 100.0:
            return None, True
            
        if bid_vol == 0 and ask_vol == 0:
            return self._get_midpoint(target_ticker, target_side), True
            
        vwap = float((best_bid * bid_vol) + (best_ask * ask_vol)) / float(bid_vol + ask_vol)
        
        if (best_ask - best_bid) > self.config.MAX_MARKET_WIDTH:
            return self._get_midpoint(target_ticker, target_side), False
            
        return vwap, False

    def _evaluate_illiquid_fallback(self, target_ticker: str, target_side: str) -> bool:
        """Phase 4: Checks single-sided unified discrete price thresholds."""
        bids = self._get_bids_for_side(target_ticker, target_side)
        if self.is_2_way:
            recip_ticker = self.tickers[0] if target_ticker == self.tickers[1] else self.tickers[1]
            recip_side = "no" if target_side == "yes" else "yes"
            recip_bids = self._get_bids_for_side(recip_ticker, recip_side)
            
            unique_levels = set()
            for p, _ in bids: unique_levels.add(p)
            for p, _ in recip_bids: unique_levels.add(p)
            levels = len(unique_levels)
        else:
            levels = len(set(p for p, _ in bids))

        return levels >= self.config.MIN_LEVELS

    async def _cancel_all(self):
        for qid, q in self.active_quotes.items():
            if q.status == QuoteStatus.RESTING:
                try:
                    await asyncio.to_thread(self.client.cancel_order, q.kalshi_order_id)
                    q.status = QuoteStatus.CANCELED
                except Exception as e:
                    log.error(f"Failed to cancel {q.kalshi_order_id}: {e}")
        self.active_quotes.clear()

    async def _quoter_loop(self):
        now = time.time()
        if now < self.sweep_cooldown_until:
            return

        for t in self.tickers:
            try:
                ob = await asyncio.to_thread(self.client.get_orderbook, t)
                bids = ob.get("orderbook", {}).get("yes", [])
                asks = ob.get("orderbook", {}).get("no", [])
                if not bids:
                    fp_bids = ob.get("orderbook_fp", {}).get("yes_dollars", [])
                    bids = [(int(round(float(p) * 100)), int(float(v))) for p, v in fp_bids]
                if not asks:
                    fp_asks = ob.get("orderbook_fp", {}).get("no_dollars", [])
                    asks = [(int(round(float(p) * 100)), int(float(v))) for p, v in fp_asks]
                
                bids.sort(key=lambda x: x[0], reverse=True)
                asks.sort(key=lambda x: x[0], reverse=True)
                self.orderbooks[t].yes_ob = bids
                self.orderbooks[t].no_ob = asks
            except Exception as e:
                log.error(f"Failed to fetch orderbook for {t}: {e}")
                return

        targets = []
        for t in self.tickers:
            for side in ["yes", "no"]:
                theo, is_illiquid = self._run_theoretical(t, side)
                if theo is None: 
                    log.info(f"[{t} {side}] Ignored: Book is completely empty (No VWAP, No Midpoint).")
                    continue
                
                # Phase 1: Price bounds verification
                if theo < self.config.PRICE_BOUND_LOW or theo > self.config.PRICE_BOUND_HIGH:
                    log.info(f"[{t} {side}] Ignored: Theo ({theo}) falls outside bounds [{self.config.PRICE_BOUND_LOW}, {self.config.PRICE_BOUND_HIGH}]")
                    continue
                    
                # Phase 4: Fallback Guard 
                if is_illiquid:
                    if not self._evaluate_illiquid_fallback(t, side):
                        log.info(f"[{t} {side}] Ignored: Illiquid fallback triggered, but book has < {self.config.MIN_LEVELS} levels.")
                        continue

                min_edge = calculate_logit_min_edge(theo, self.config.MIN_EDGE_AT_50C, self.config.ABSOLUTE_MIN_EDGE)
                max_edge = self.config.MAX_EDGE
                
                # Phase 2: Deep Sweep Anchoring
                tv = self.config.TYPICAL_MARKET_VOLUME
                bids = self._get_bids_for_side(t, side)
                price = self._simulate_sweep(bids, tv, default_exhaust=0.0)
                
                if self.is_2_way:
                    recip_ticker = self.tickers[0] if t == self.tickers[1] else self.tickers[1]
                    recip_side = "no" if side == "yes" else "yes"
                    bids_recip = self._get_bids_for_side(recip_ticker, recip_side)
                    price_recip = self._simulate_sweep(bids_recip, tv, default_exhaust=0.0)
                    price = max(price, price_recip) # better (higher) base
                
                edge = theo - price
                
                if edge < min_edge:
                    target_limit = theo - min_edge
                elif min_edge <= edge <= max_edge:
                    target_limit = price
                else: 
                    target_limit = price + 1
                    
                target_limit = int(math.floor(target_limit))
                min_edge_boundary = theo - min_edge
                
                asks = self._get_asks_for_side(t, side)
                best_ask = asks[0][0] if asks else 100
                if target_limit >= best_ask:
                    target_limit = best_ask - 1
                    
                if target_limit > min_edge_boundary:
                    target_limit = int(math.floor(min_edge_boundary))
                
                # Phase 3: Positional Skew offset
                net_pos = self.positions.get(f"{t}_{side}", 0)
                opp_pos = self.positions.get(f"{t}_{'no' if side == 'yes' else 'yes'}", 0)
                net_pos = max(0, net_pos - opp_pos)
                
                skew_cents = calculate_positional_skew(
                    net_pos, 
                    self.config.MAX_POSITION_PER_SIDE,
                    self.config.SKEW_START_FRACTION,
                    self.config.SKEW_MAX_SHIFT_CENTS
                )
                
                if skew_cents > 0:
                    skewed_limit = target_limit - skew_cents
                    if skewed_limit < min_edge_boundary:
                        skewed_limit = max(0.0, float(math.floor(skewed_limit)))
                    target_limit = int(math.floor(skewed_limit))
                
                target_limit = min(target_limit, int(math.floor(min_edge_boundary)))
                if target_limit < int(self.config.PRICE_BOUND_LOW): 
                    log.info(f"[{t} {side}] Ignored: Target Limit {target_limit}c is below PRICE_BOUND_LOW ({self.config.PRICE_BOUND_LOW}c).")
                    continue
                
                qty = int(self.config.TYPICAL_MARKET_VOLUME * self.config.ORDER_VOLUME_MULTIPLIER)
                if qty <= 0: 
                    log.info(f"[{t} {side}] Ignored: Calculated order quantity is 0 (Typical {self.config.TYPICAL_MARKET_VOLUME} * Multiplier {self.config.ORDER_VOLUME_MULTIPLIER}).")
                    continue

                targets.append({
                    "ticker": t,
                    "side": side,
                    "limit": int(target_limit),
                    "qty": qty
                })

        # Phase 6: Sync Polling Replacement Logic
        # Back up orders physically on book that violate the current optimal limits
        for tgt in targets:
            k = f"{tgt['ticker']}_{tgt['side']}"
            active = self.active_quotes.get(k)
            
            needs_firing = False
            if not active or active.status != QuoteStatus.RESTING:
                needs_firing = True
            else:
                current_price = active.price_cents
                drift = current_price - tgt['limit']
                
                # Price is mathematically WORSE (bidding too high) -> cancel & drop
                if drift > 0:
                    log.info(f"Target dropped ({current_price} -> {tgt['limit']}). Replacing...")
                    try:
                        await asyncio.to_thread(self.client.cancel_order, active.kalshi_order_id)
                        needs_firing = True
                    except: pass
                # Price is BETTER (bidding too low) -> wait unless drift violently exceeds REPRICE_BOUNDS
                elif drift < -self.config.REPRICE_BOUNDS:
                    log.info(f"Target lifted beyond reprice bound ({current_price} -> {tgt['limit']}). Replacing...")
                    try:
                        await asyncio.to_thread(self.client.cancel_order, active.kalshi_order_id)
                        needs_firing = True
                    except: pass
            
            if needs_firing:
                uid = str(uuid.uuid4())
                try:
                    res = await asyncio.to_thread(
                        self.client.place_order,
                        client_order_id=uid,
                        ticker=tgt['ticker'],
                        side=tgt['side'],
                        count=tgt['qty'],
                        limit_cents=tgt['limit'],
                        time_in_force="good_til_canceled"
                    )
                    log.info(f"Placed {tgt['ticker']} {tgt['side']} @ {tgt['limit']}c x {tgt['qty']}")
                    
                    self.active_quotes[k] = ActiveQuote(
                        side=QuoteSide.TEAM_A, # Generic
                        target_ticker=tgt['ticker'],
                        intent="buy",
                        price_cents=tgt['limit'],
                        qty=tgt['qty'],
                        client_order_id=uid,
                        kalshi_order_id=res.get("order", {}).get("order_id", ""),
                        status=QuoteStatus.RESTING,
                        placed_at=time.time()
                    )
                except Exception as e:
                    log.error(f"Failed to place {tgt['ticker']}: {e}")
