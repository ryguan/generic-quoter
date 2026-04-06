import os
from kalshi_client import KalshiClient
from kalshi_auth import KalshiAuth
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
auth = KalshiAuth(os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))
client = KalshiClient(auth)

resp = client._get("/series")
for s in resp.get("series", []):
    title = str(s.get("title", "")).lower()
    if "counter" in title or "strike" in title or "cs2" in title or "cs" in title:
        print("MATCHED SERIES:", s.get("ticker"), "|", s.get("title"))
