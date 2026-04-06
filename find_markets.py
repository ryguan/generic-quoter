import os
from kalshi_client import KalshiClient
from kalshi_auth import KalshiAuth
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
auth = KalshiAuth(os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))
client = KalshiClient(auth)

# Query events matching string
resp = client._get("/events", params={"series_ticker": "KXCS2GAME"})
for event in resp.get("events", []):
    ticker = event.get("event_ticker", "")
    if "26APR061700" in ticker:
        print("Found Event:", ticker)
        
        # Query its markets
        markets_resp = client._get("/markets", params={"event_ticker": ticker})
        for m in markets_resp.get("markets", []):
            print(" -> Market Ticker:", m.get("ticker"))
            ob = client.get_orderbook(m.get("ticker"))
            bids = ob.get("orderbook_fp", {}).get("yes_dollars", [])
            print("    -> Level Count:", len(bids))
