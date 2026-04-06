# General Quoter Implementation Plan

This document outlines the architecture and execution logic for a new General Quoter algorithm. The engine uses a VWAP-driven theoretical benchmark, executes physical VWAP sweeps against a cleaned liquidity view, and algorithmically manages position skew and limit pricing while honoring illiquid-market safety parameters.



## Variables & Configuration Schema
- `MAX_MARKET_WIDTH`: The top-of-book spread bound. If exceeded, theoretical calculation defaults to Midpoint rather than VWAP.
- `TYPICAL_MARKET_VOLUME`: Target volume configuration per market used to run the theoretical market-order sweep.
- `ORDER_VOLUME_MULTIPLIER`: Multiplied against typical volume to derive our actual resting quote size.
- `MIN_EDGE_AT_50C` & `ABSOLUTE_MIN_EDGE`: `MIN_EDGE` relies on a logit scale curving out from the `0.50` baseline. At extremes, it safely flattens to `ABSOLUTE_MIN_EDGE` instead of approaching infinity/zero.
- `MAX_EDGE`: The maximum structural edge we are willing to "give up" into the book before stepping back.
- `MIN_LEVELS`: Requisite number of active price tiers to consider an illiquid side active.
- `SWEEP_LEVELS`: The threshold of distinct price levels consumed by trades within a single second to qualify as a "Sweep".
- `SWEEP_COOLDOWN_SECONDS`: Duration to completely suspend all quoting activity if a Sweep is detected.
- `PRICE_BOUNDS`: (e.g. `[0.03, 0.97]`). If the overall *Theoretical VWAP* lands outside these bounds, we do not participate in the market. (Note: we *can* quote outside these bounds, as long as the theoretical seed itself sits inside it).
- `REPRICE_BOUNDS`: Cent tolerance allowed before updating limits on favorable edge shifts.
- **`SKEW_PARAMETERS`** (Ported from Esports Config):
  - `MAX_POSITION_PER_SIDE`: Maximum lots held on a single intent before quoting is completely halted.
  - `SKEW_START_FRACTION`: The threshold point (e.g. 0.5 or 50% capacity) at which position leaning triggers.
  - `SKEW_MAX_SHIFT_CENTS`: The maximum magnitude of skew (in cents) applied linearly once the start fraction is exceeded.
  - `HALT_UNHEDGED_THRESHOLD`: Global unhedged cutoff limit.

## Quoting Logic Execution Map

### Phase 1: Market Execution Clean & Theoretical Limit Simulation
1. Define our benchmark Theoretical price objectively as the immediate **VWAP between the two best levels** cross-book.
   - **Immediately Validate `PRICE_BOUNDS`**: If the calculated baseline VWAP is outside the configurable `[0.03, 0.97]` limits, perfectly halt any further execution. The engine completely aborts quoting for this round.
2. We then evaluate the realistic cost to quote. For 2-Team markets: Evaluate sweeping `TYPICAL_MARKET_VOLUME` continuously on `Yes Team A` and `No Team B` **independently**.
3. We record the **"worst price"** physically traded for each of those isolated sweep simulations.
4. We take the **BETTER of those two worst-prices**. This resulting value acts as the fundamental baseline for what price we are natively attempting to quote at.
5. *Note: Multi-team markets (like Soccer) bypass reciprocal equivalents and run independent isolated sweeps without netting.*

### Phase 2: Edge Evaluation & Base Limit Derivation
Define `Target_Bid` & `Target_Ask` natively against the calculated VWAP offset by the logit-scaled `MIN_EDGE` and configured `MAX_EDGE`. We ensure our baseline sweep limit conforms to edge guards against the physical resting orderbook:

1. **Calculate Theoretical Boundary**: Determine our optimal pricing zones bounded by `VWAP ± Max_Edge` and clamped tightly by `VWAP ± Min_Edge`. 
2. **Penny Jump Conditions**: When dictating our placement, if our desired limit lands directly into (or past) hostile depth, we will aggressively Penny Jump exactly 1c. `Penny Jumping` strictly translates to:
   - Undercutting the Best Ask by exactly 1 cent.
   - Stepping directly in front of the Best Bid by exactly 1 cent.
3. **The "Worse Level" Guard**: We compare our `Max_Edge Target` against the `Best Resting Book Level`. To prevent violently improving a shallow book by 20-30c, we default to the **worse level** between our boundary and the current best book. However, we do not "Join" the worse level—we will *at best* **Penny Jump the worse level** by 1c to safely establish priority.
4. **Min Edge Guard**: If the logic (either from Penny Jumping or Skewing) mathematically compresses our price tighter than the logit-scaled `MIN_EDGE` boundary to the VWAP, we refuse to push further and statically snap the limit flat at `VWAP ± MIN_EDGE`.

### Phase 3: Positional Skew Execution
Once our base limit is defined, we evaluate positional exposure using the `SKEW_PARAMETERS`:
1. Define specific lots currently accumulated for this specific targeted side.
2. Target `Shift_Threshold = MAX_POSITION_PER_SIDE * SKEW_START_FRACTION`. (e.g., 50% full).
3. If Position > Shift_Threshold: we calculate a proportional step-off.
   - `Utilization = (Position - Shift_Threshold) / (MAX_POSITION_PER_SIDE - Shift_Threshold)`
   - `Skew_Delta = Utilization * SKEW_MAX_SHIFT_CENTS`
4. Apply this `Skew_Delta` to lean *away* from accumulating more depth (e.g., if we are heavily long, we aggressively drop our BID by `-Skew_Delta` cents).
5. If this new Skewed Limit violates the Min Edge Guard, we revert to quoting the strictly bound `MIN_EDGE`.
6. **For 2-Team Markets:** Broadcast the identical exact limit size into *both* corresponding counterparts seamlessly (e.g., place `Yes Team A @ 45c` AND `No Team B @ 45c`).

### Phase 4: Illiquid Book Fallback
If the theoretical VWAP depth simulation fails (i.e., `Total Available Volume < TYPICAL_MARKET_VOLUME`):
- Fallback dynamically triggers on a **single-sided** basis parsing the *Unified* Orderbook.
- If the Bid natively yields `>= MIN_LEVELS`, but the Ask natively yields `< MIN_LEVELS`: **Quote only the Bid**.
- The fallback quotation limit reverts exactly to the conservative Phase 2 ceiling logic.

### Phase 5: Trade Sweep Detection & Cooldown
Maintain a 1-second rolling block of `trade` events sourced from the Kalshi ticker feed:
- If trades executed across >= `SWEEP_LEVELS` distinct price levels inside a single 1000ms window, trigger **Sweep Protection**.
- Immediately issue a `Cancel All Orders` command.
- Enter a strict sleep interval for `SWEEP_COOLDOWN_SECONDS` where no quotes will be emitted. 

### Phase 6: Repricing & Maintenance
Manage active limits smoothly over a 60-second synchronized polling interval:
- **Price is WORSE than Model**: If our resting quote is mathematically *more aggressive* (giving away more edge than desired), forcefully **"back up"** the quote to the new `Target_Bid` or `Target_Ask` natively immediately.
- **Price is BETTER than Model**: If our resting quote is *more profitable* (reaping excess edge), wait. Do not trigger a cancellation unless the mathematical difference physically exceeds `REPRICE_BOUNDS` from the new `Target_Bid` or `Target_Ask`. 

## Structural Implementation Plan
1. **[NEW] `general_quoter_config.py` & `general_quoter_models.py`**
   - Create foundational bounds logic (Logit Scaling helper function).
2. **[NEW] `general_quoter_engine.py`**
   - Assemble Phase 1 - 5 mapping sequentially. 
   - Integrate Unified Book aggregation uniquely differentiating 2-Way from N-Way logic.
3. **[NEW] `main_general.py`**
   - Deploy as a generalized standalone boot script mirroring the auth structure.
