# General Quoter — Robustness Improvements

## 1. Circuit Breakers & Self-Healing (High Priority)

- **Consecutive API failure breaker**: If N consecutive API calls fail (network blip, rate limit), pause quoting and retry with exponential backoff rather than blindly looping. Currently errors are caught but the loop keeps firing.
- **Stale orderbook guard**: If an orderbook fetch returns the same data for >N polls, assume the feed is stale and pull quotes. A frozen book can mask a violent move.
- **Max loss per session**: A configurable `MAX_SESSION_LOSS_CENTS` that halts quoting if cumulative realized + unrealized PnL crosses a threshold. The position limit helps but doesn't cap dollar loss.

## 2. WebSocket Trade Feed (High Priority — Currently Stubbed)

Phase 5 sweep detection is a stub. Without real-time trade data, the quoter is blind to sweeps and can get picked off. This is the single biggest gap. The implementation should:
- Maintain a persistent WebSocket connection with auto-reconnect
- Buffer trades in a rolling 1-second deque
- Trigger sweep protection synchronously (not waiting for the next poll cycle)

## 3. Graceful Shutdown (High Priority)

- Trap `SIGINT`/`SIGTERM`, cancel all resting orders before exit. Currently if the process dies, orphaned orders sit in the book with no management. A `try/finally` or signal handler calling `_cancel_all()` is cheap insurance.

## 4. Order Reconciliation (Medium Priority)

- On boot and periodically, query Kalshi for all open orders and reconcile against `active_quotes`. Drift can happen from partial fills, race conditions, or unclean shutdowns. Any unrecognized resting order should be cancelled.

## 5. Configurable Per-Market Overrides (Medium Priority)

- The CSV config is global. For a multi-market deployment, per-ticker overrides would be valuable (e.g., tighter `MAX_EDGE` for liquid NFL markets, wider for obscure events). A simple hierarchy: `default → series override → ticker override` in the CSV keeps it configurable without complexity.

## 6. Rate Limit Awareness (Medium Priority)

- Kalshi has API rate limits. Track request counts and preemptively throttle rather than eating 429s. A simple token-bucket in `KalshiClient` would prevent cascade failures during high-activity periods.

## 7. Fill Notification & Alerting (Low Priority, High QoL)

- Push notifications (webhook, Telegram, Discord) on significant events: fills above a threshold, sweep detected, circuit breaker triggered, position approaching max. The dashboard is great but requires active monitoring.

## 8. Inventory Decay / Time-Based Skew (Low Priority)

- As an event approaches expiry, positions become harder to exit. A time-decay multiplier on `SKEW_MAX_SHIFT_CENTS` that widens skew as time-to-close shrinks would reduce the risk of being stuck with large positions near settlement.

## 9. Dry-Run / Paper Trading Mode (Low Priority, Useful for Testing)

- `TRADING_ENABLED` exists but isn't wired into the engine. Fully implement it: run the entire pipeline, log what would be placed, but don't hit the API. Essential for validating config changes safely.

## Gap Summary

| Gap | Risk | Effort |
|-----|------|--------|
| WebSocket trade feed (sweep detection) | High — blind to adverse selection | Medium |
| Graceful shutdown (cancel on exit) | High — orphaned orders | Low |
| Circuit breaker on API failures | Medium — runaway error loops | Low |
| Order reconciliation on boot | Medium — position drift | Low |
| Stale book detection | Medium — quoting on stale data | Low |
| Max session loss limit | Medium — unbounded loss | Low |
| Rate limit handling | Medium — cascade failure | Low |
| Per-market config overrides | Low — operational flexibility | Medium |
| Fill alerting | Low — monitoring gap | Medium |
| Dry-run mode | Low — testing safety | Low |
