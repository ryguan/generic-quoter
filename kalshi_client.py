import time
import requests

from general_quoter_models import MarketData, PlacedOrder

KALSHI_API_BASE = "https://api.elections.kalshi.com"

class KalshiClient:
    def __init__(self, auth):
        self.auth = auth

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{KALSHI_API_BASE}{path}"
        headers = self.auth.get_headers("GET", path)
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception as e:
            print(f"Error GET {path}: {e}")
            return {}

    def _post(self, path: str, body: dict) -> dict:
        url = f"{KALSHI_API_BASE}{path}"
        headers = self.auth.get_headers("POST", path)
        headers["Content-Type"] = "application/json"
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=5.0)
            if resp.status_code in (200, 201):
                return resp.json()
            print(f"Error POST {path}: {resp.status_code} - {resp.text}")
            return {}
        except Exception as e:
            print(f"Error POST {path}: {e}")
            return {}

    def get_market(self, ticker: str) -> dict:
        path = f"/trade-api/v2/markets/{ticker}"
        return self._get(path)

    def get_orderbook(self, ticker: str) -> MarketData:
        path = f"/trade-api/v2/markets/{ticker}/orderbook"
        raw = self._get(path)

        raw_yes = raw.get("orderbook", {}).get("yes", [])
        raw_no = raw.get("orderbook", {}).get("no", [])

        if not raw_yes:
            fp_yes = raw.get("orderbook_fp", {}).get("yes_dollars", [])
            raw_yes = [(int(round(float(p) * 100)), int(float(v))) for p, v in fp_yes]
        if not raw_no:
            fp_no = raw.get("orderbook_fp", {}).get("no_dollars", [])
            raw_no = [(int(round(float(p) * 100)), int(float(v))) for p, v in fp_no]

        yes_ob = [(int(p), int(q)) for p, q in raw_yes]
        no_ob = [(int(p), int(q)) for p, q in raw_no]
        yes_ob.sort(key=lambda x: x[0], reverse=True)
        no_ob.sort(key=lambda x: x[0], reverse=True)

        return MarketData(ticker=ticker, yes_ob=yes_ob, no_ob=no_ob)

    def place_order(self, client_order_id: str, ticker: str, side: str, count: int, limit_cents: int, time_in_force: str = "fill_or_kill") -> PlacedOrder:
        """
        side: 'yes' or 'no'
        limit_cents: integer from 1 to 99
        count: number of contracts to buy
        time_in_force: 'fill_or_kill' or 'immediate_or_cancel' or 'gtc'
        """
        path = "/trade-api/v2/portfolio/orders"
        body = {
            "action": "buy",
            "side": side.lower(),
            "count": count,
            "ticker": ticker,
            "type": "limit",
            "client_order_id": client_order_id,
            "time_in_force": time_in_force,
            "sell_position_cap": 0
        }
        
        if time_in_force in ("fill_or_kill", "immediate_or_cancel"):
            body["time_in_force"] = time_in_force
        else:
            # Omit time_in_force for standard resting quotes to use Kalshi default
            if "time_in_force" in body:
                del body["time_in_force"]
            
        if side.lower() == "yes":
            body["yes_price"] = limit_cents
        else:
            body["no_price"] = limit_cents

        return PlacedOrder.from_api_response(self._post(path, body))

    def place_order_batch(self, orders: list[dict]) -> dict:
        """
        Submit up to 20 orders in a single batch request.
        Each entry in `orders` should be a dict with keys:
          client_order_id, ticker, side, count, limit_cents, time_in_force
        Returns: {"orders": [{client_order_id, order, error}, ...]}
        """
        path = "/trade-api/v2/portfolio/orders/batched"
        batch_body = {"orders": []}
        for o in orders:
            entry = {
                "action": "buy",
                "side": o["side"].lower(),
                "count": o["count"],
                "ticker": o["ticker"],
                "type": "limit",
                "client_order_id": o["client_order_id"],
                "sell_position_cap": 0,
            }
            if "time_in_force" in o:
                entry["time_in_force"] = o["time_in_force"]
            if o.get("time_in_force") == "good_til_date":
                entry["expiration_ts"] = int(time.time()) + o.get("expiration_seconds", 60)
            if o["side"].lower() == "yes":
                entry["yes_price"] = o["limit_cents"]
            else:
                entry["no_price"] = o["limit_cents"]
            batch_body["orders"].append(entry)
        return self._post(path, batch_body)

    def get_order(self, order_id: str) -> dict:
        """GET /trade-api/v2/portfolio/orders/{order_id}. Returns order dict."""
        path = f"/trade-api/v2/portfolio/orders/{order_id}"
        return self._get(path)

    def get_fills(self, order_id: str) -> list[dict]:
        """GET /trade-api/v2/portfolio/fills?order_id=X. Returns list of fill dicts."""
        path = "/trade-api/v2/portfolio/fills"
        resp = self._get(path, params={"order_id": order_id})
        return resp.get("fills", [])

    def cancel_order(self, order_id: str) -> bool:
        """DELETE /trade-api/v2/portfolio/orders/{order_id}. Returns True on success."""
        path = f"/trade-api/v2/portfolio/orders/{order_id}"
        url = f"{KALSHI_API_BASE}{path}"
        headers = self.auth.get_headers("DELETE", path)
        try:
            resp = requests.delete(url, headers=headers, timeout=5.0)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Error DELETE {path}: {e}")
            return False

    def cancel_order_batch(self, order_ids: list[str]) -> dict:
        """Cancel multiple orders in a single batch request."""
        path = "/trade-api/v2/portfolio/orders/batched"
        body = {"order_ids": order_ids}
        url = f"{KALSHI_API_BASE}{path}"
        headers = self.auth.get_headers("DELETE", path)
        headers["Content-Type"] = "application/json"
        try:
            resp = requests.delete(url, json=body, headers=headers, timeout=5.0)
            if resp.status_code in (200, 204):
                return resp.json() if resp.content else {}
            print(f"Error batch cancel: {resp.status_code} - {resp.text}")
            return {}
        except Exception as e:
            print(f"Error batch cancel: {e}")
            return {}
