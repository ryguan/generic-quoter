"""
main_general.py
Entry point for the General Quoter.
"""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv, find_dotenv
import os

from general_quoter_config import load_general_quoter_config
from general_quoter_engine import GeneralQuoterEngine
from kalshi_client import KalshiClient
from kalshi_auth import KalshiAuth

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

def load_auth() -> KalshiAuth:
    load_dotenv(find_dotenv(usecwd=True))
    api_key_id = os.getenv("KALSHI_API_KEY_ID", "").strip()
    private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "").strip()
    if not api_key_id or not private_key_path:
        log.error("Missing Auth keys.")
        sys.exit(1)
    return KalshiAuth(api_key_id, private_key_path)

async def async_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", required=True, help="List of tickers or event URLs to quote.")
    args = parser.parse_args()

    auth = load_auth()
    client = KalshiClient(auth)
    config = load_general_quoter_config()

    final_tickers = []
    
    # URL parsing loop
    for query in args.tickers:
        raw_query = query.strip()
        if "kalshi.com" in raw_query or "/" in raw_query:
            # Extract trailing segment
            event_id = raw_query.strip("/").split("/")[-1].upper()
            
            try:
                log.info(f"Resolving Kalshi Event: {event_id} ...")
                # Query all markets matching this event
                resp = client._get("/trade-api/v2/markets", params={"event_ticker": event_id, "limit": 100})
                markets = resp.get("markets", [])
                if not markets:
                    log.info(f" - No nested markets found, treating {event_id} directly as a Ticker.")
                    if event_id not in final_tickers:
                        final_tickers.append(event_id)
                else:
                    for m in markets:
                        t = m.get("ticker")
                        if t and t not in final_tickers:
                            final_tickers.append(t)
                            log.info(f" - Found underlying Ticker: {t}")
            except Exception as e:
                log.error(f"Failed resolving URL Event {event_id}: {e}")
                # Fallback natively treating the query as a ticker if Event throws 404
                if event_id not in final_tickers:
                    final_tickers.append(event_id)
        else:
            final_tickers.append(raw_query.upper())

    if not final_tickers:
        log.error("No valid tickers resolved! Exiting.")
        sys.exit(1)
        
    engine = GeneralQuoterEngine(client, config, final_tickers)
    await engine.start()

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
