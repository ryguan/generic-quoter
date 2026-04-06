"""
test_general_quoter.py
Sanity checks for the General Quoter logic.
"""

from general_quoter_config import load_general_quoter_config
from general_quoter_models import calculate_logit_min_edge, calculate_positional_skew
from general_quoter_engine import GeneralQuoterEngine
import asyncio

class MockKalshiClient:
    def get_orderbook(self, ticker):
        return {
            "orderbook": {
                "yes": [[40, 500], [39, 200]],
                "no": [[58, 100], [59, 200]]  # Asks for YES at 42c and 41c
            }
        }

async def run_tests():
    print("--- 1. Testing Config Load ---")
    config = load_general_quoter_config()
    print("MAX_MARKET_WIDTH:", config.MAX_MARKET_WIDTH)
    print("TYPICAL_MARKET_VOLUME:", config.TYPICAL_MARKET_VOLUME)
    print("MIN_EDGE_AT_50C:", config.MIN_EDGE_AT_50C)
    assert config.MAX_MARKET_WIDTH > 0.0
    print("Config wire-up SUCCESS.\n")

    print("--- 2. Testing Logit Edge Scaling ---")
    edge_50c = calculate_logit_min_edge(50, 3.0, 1.0)
    edge_90c = calculate_logit_min_edge(90, 3.0, 1.0)
    edge_99c = calculate_logit_min_edge(99, 3.0, 1.0)
    print(f"Edge @ 50c: {edge_50c:.2f} (Expected 3.0)")
    print(f"Edge @ 90c: {edge_90c:.2f} (Expected slightly below 3.0)")
    print(f"Edge @ 99c: {edge_99c:.2f} (Expected near 1.0)")
    assert math.isclose(edge_50c, 3.0)
    assert edge_99c < edge_90c < edge_50c
    print("Logit Edge Scaling SUCCESS.\n")

    print("--- 3. Testing Positional Skew Scaling ---")
    skew_0 = calculate_positional_skew(100, 500, 0.5, 3.0)
    skew_med = calculate_positional_skew(375, 500, 0.5, 3.0)
    skew_max = calculate_positional_skew(500, 500, 0.5, 3.0)
    print(f"Skew @ 100 lots (Start 250): {skew_0:.2f}c")
    print(f"Skew @ 375 lots (Start 250): {skew_med:.2f}c (Expected 1.5)")
    print(f"Skew @ 500 lots (Start 250): {skew_max:.2f}c (Expected 3.0)")
    assert skew_0 == 0.0
    assert math.isclose(skew_med, 1.5)
    assert math.isclose(skew_max, 3.0)
    print("Positional Skew SUCCESS.\n")

    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    import math
    asyncio.run(run_tests())
