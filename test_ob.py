import os
import sys
from general_quoter_models import MarketData
from kalshi_client import KalshiClient
from kalshi_auth import KalshiAuth
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
auth = KalshiAuth(os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))
client = KalshiClient(auth)

ticker = "KXCS2GAME-26APR061700CRAPAINA"
ob = client.get_orderbook(ticker)
print("Keys in response:", ob.keys())
print("Orderbook structure:", ob.get("orderbook", "NO ORDERBOOK KEY"))

# Test get_market to see if it even exists
market = client.get_market(ticker)
print("Orderbook_FP keys:", ob.get("orderbook_fp", {}).keys())
print("FP YES:", ob.get("orderbook_fp", {}).get("yes_dollars"))
