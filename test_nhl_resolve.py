import os
import requests
from dotenv import load_dotenv, find_dotenv
from typing import Tuple, List, Dict
from kalshi_auth import KalshiAuth

load_dotenv(find_dotenv(usecwd=True))
auth = KalshiAuth(os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))
KALSHI_API_BASE = "https://api.elections.kalshi.com"

def resolve_market_tickers(ticker: str, auth) -> Tuple[List[str], List[Dict]]:
    upper = ticker.upper()
    list_path = "/trade-api/v2/markets" 

    # 1. Direct
    mkt_path = f"{list_path}/{upper}"
    r = requests.get(
        KALSHI_API_BASE + mkt_path,
        headers=auth.get_headers("GET", mkt_path),
        timeout=8,
    )
    print("Direct Code:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        if "market" in data:
            return [data["market"]["ticker"]], [data["market"]]

    # 2. Event
    r2 = requests.get(
        KALSHI_API_BASE + list_path,
        params={"event_ticker": upper, "limit": 100},
        headers=auth.get_headers("GET", list_path),
        timeout=8,
    )
    print("Event Code:", r2.status_code)
    try: print("Event Resp:", r2.json())
    except: pass
    if r2.status_code == 200:
        markets = r2.json().get("markets", [])
        if markets:
            return [m["ticker"] for m in markets], list(markets)

    # 3. Series
    r3 = requests.get(
        KALSHI_API_BASE + list_path,
        params={"series_ticker": upper, "limit": 100},
        headers=auth.get_headers("GET", list_path),
        timeout=8,
    )
    print("Series Code:", r3.status_code)
    if r3.status_code == 200:
        markets = r3.json().get("markets", [])
        if markets:
            return [m["ticker"] for m in markets], list(markets)

    return [ticker], []

print("Running resolve...")
tickers, _ = resolve_market_tickers("KXCS2GAME-26APR061700CRAPAINA", auth)
print("Resolved Tickers:", tickers)
