import os
import json
from kalshi_client import KalshiClient
from kalshi_auth import KalshiAuth
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
auth = KalshiAuth(os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))
client = KalshiClient(auth)

resp = client._get("/markets", params={"limit": 500, "status": "active"})
markets = resp.get("markets", [])

found = []
for m in markets:
    t = m.get("ticker", "")
    if "KXCS2" in t or "CRAP" in t or "AINA" in t:
        found.append(t)

print("Matched active tickers:", found)
