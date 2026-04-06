import os
import json
from kalshi_client import KalshiClient
from kalshi_auth import KalshiAuth
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
auth = KalshiAuth(os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))
client = KalshiClient(auth)

resp = client._get("/events", params={"limit": 500, "status": "active"})
events = resp.get("events", [])

# Let's search inside the events
print(f"Total active events fetched: {len(events)}")
for e in events:
    # URL might be in the event, or we just look for string matches
    target = "crap"
    if target in str(e).lower() or "kxcs" in str(e).lower():
        print("======== EVENT ========")
        print(f"Ticker: {e.get('event_ticker')}")
        print(f"URL: {e.get('mutually_exclusive')}")
        # fetch markets
        m_resp = client._get("/markets", params={"event_ticker": e.get('event_ticker')})
        for m in m_resp.get("markets", []):
             print(f"  -> Market: {m.get('ticker')}")
