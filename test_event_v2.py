import os
from kalshi_client import KalshiClient
from kalshi_auth import KalshiAuth
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
auth = KalshiAuth(os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))
client = KalshiClient(auth)

# Method 1
print("Trying /events/...")
r1 = client._get("/events/KXCS2GAME-26APR061700CRAPAINA")
print(r1.keys())
print("Markets in r1:", r1.get("event", {}).get("markets", "N/A"))

# Method 2
print("\nTrying /markets with list limit...")
r2 = client._get("/markets", params={"event_ticker": "KXCS2GAME-26APR061700CRAPAINA", "limit": 100})
print("Markets in r2:", r2.get("markets", "N/A"))
