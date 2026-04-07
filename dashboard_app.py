import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import state_store
from general_quoter_models import TradeRow, PositionRow, TradesResponse

class DashboardServer:
    def __init__(self, auth, dashboard_port=7340):
        self.auth = auth
        self.dashboard_port = dashboard_port
        self._price_lock = threading.Lock()
        self._latest_prices = {}  # Map ticker to latest mid/vwap if we want live PnL

    def start(self):
        # Start REST order sync daemon
        threading.Thread(target=self._order_sync_daemon, daemon=True, name="order-sync").start()
        self._start_http_server()

    def update_price(self, ticker: str, cents: float):
        with self._price_lock:
            self._latest_prices[ticker] = cents

    def _order_sync_daemon(self):
        import requests
        BASE = "https://api.elections.kalshi.com"

        while True:
            time.sleep(10)
            try:
                orders = state_store.load_orders()
                if not orders:
                    continue

                path = "/trade-api/v2/portfolio/fills"
                hdrs = self.auth.get_headers("GET", path)
                resp = requests.get(BASE + path, params={"limit": 500}, headers=hdrs, timeout=5)
                if resp.status_code != 200:
                    continue

                fills_data = resp.json().get("fills", [])
                fills_by_order = defaultdict(list)
                for f in fills_data:
                    fills_by_order[f.get("order_id")].append(f)

                for order in orders:
                    if not order.order_id:
                        continue

                    ofills = fills_by_order.get(order.order_id)
                    if not ofills:
                        continue

                    price_key = "yes_price_dollars" if order.side == "yes" else "no_price_dollars"
                    tq = sum(float(f.get("count_fp", 0)) for f in ofills)

                    if tq > order.filled_count:
                        wavg = sum(float(f.get(price_key, 0)) * float(f.get("count_fp", 0)) for f in ofills) / tq
                        fill_cents = round(wavg * 100)
                        filled_count = round(tq)
                        state_store.patch_order(order.order_id, fill_cents=fill_cents, filled_count=filled_count)

            except Exception:
                pass

    def _start_http_server(self):
        server_instance = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send_json(self, payload: bytes):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path == "/data":
                    self._send_json(json.dumps({
                        "totals": {}, "net_flow": {}, "totals_5m": {}, "net_flow_5m": {}, "tickers": []
                    }).encode())

                elif self.path == "/api/trades":
                    now = time.time()

                    def _ts(ts):
                        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%H:%M:%S")

                    orders = state_store.load_orders()
                    with server_instance._price_lock:
                        price_snapshot = dict(server_instance._latest_prices)

                    all_trades: list[TradeRow] = []
                    for order in orders:
                        raw_ticker = order.ticker
                        fc = order.filled_count if order.filled_count else order.count

                        # Dashboard filter: Hide unfilled passive liquidity
                        if fc == 0:
                            continue

                        cur_yes = price_snapshot.get(raw_ticker)
                        fill_c = order.fill_cents if order.fill_cents else order.limit_cents

                        if order.side == "yes":
                            cur_v = cur_yes if cur_yes is not None else fill_c
                        else:
                            cur_v = (100 - cur_yes) if cur_yes is not None else fill_c

                        fee_c = round(7.0 * (fill_c / 100.0) * (1.0 - fill_c / 100.0) * fc) if fc > 0 else 0
                        pnl_c = (cur_v - fill_c) * fc - fee_c if fc > 0 and cur_v is not None else 0

                        ticker_type = "Esports Match"
                        game_matchup = order.game if order.game else raw_ticker
                        exec_type = "Sweep" if order.intent_count > 0 else "Resting"

                        # Try parsing nice team names if conventional format CS2
                        parts = raw_ticker.split('-')
                        if len(parts) >= 2:
                            s = parts[-1]
                            if len(s) == 6 or len(s) == 5:
                                game_matchup = f"{s[:len(s)//2]} vs {s[len(s)//2:]}"

                        display_ts = order.ts if order.ts else now

                        ticker_short_parts = raw_ticker.split('-')
                        ticker_short = ticker_short_parts[-1] if ticker_short_parts else raw_ticker

                        all_trades.append(TradeRow(
                            ts_str=_ts(display_ts),
                            game_matchup=game_matchup.upper(),
                            ticker_type=ticker_type,
                            ticker_short=ticker_short,
                            ticker=raw_ticker,
                            exec_type=exec_type,
                            side=order.side,
                            limit_cents=order.limit_cents,
                            fill_cents=fill_c,
                            count=order.intent_count if order.intent_count else fc,
                            filled_count=fc,
                            current_cents=cur_v,
                            pnl_cents=pnl_c,
                            fee_cents=fee_c,
                        ))

                    all_trades.sort(key=lambda t: t.ts_str, reverse=True)

                    net_lots: dict[str, int] = {}
                    for order in orders:
                        if order.filled_count == 0:
                            continue
                        delta = order.filled_count if order.side == "yes" else -order.filled_count
                        net_lots[order.ticker] = net_lots.get(order.ticker, 0) + delta

                    positions: list[PositionRow] = []
                    for ticker, net in sorted(net_lots.items()):
                        if net == 0:
                            continue
                        cur_yes = price_snapshot.get(ticker)
                        d = "YES" if net > 0 else "NO"
                        cv = cur_yes if d == "YES" else (100 - cur_yes if cur_yes is not None else None)
                        positions.append(PositionRow(
                            ticker_suffix=ticker.split("-")[-1],
                            direction=d,
                            lots=abs(net),
                            current_cents=cv,
                        ))

                    total_pnl = sum(t.pnl_cents for t in all_trades if t.pnl_cents is not None)
                    total_fees = sum(t.fee_cents for t in all_trades)

                    # Group games
                    games_set = set(t.game_matchup for t in all_trades)
                    per_game_pnl = {g: sum(t.pnl_cents for t in all_trades if t.game_matchup == g) for g in games_set}
                    per_game_fees = {g: sum(t.fee_cents for t in all_trades if t.game_matchup == g) for g in games_set}

                    response = TradesResponse(
                        trades=all_trades,
                        positions=positions,
                        pnl_cents=total_pnl,
                        fee_cents=total_fees,
                        games=sorted(games_set),
                        per_game_pnl=per_game_pnl,
                        per_game_fees=per_game_fees,
                        timestamp=_ts(now),
                    )
                    self._send_json(json.dumps(response.to_dict()).encode())

                elif self.path == "/api/config":
                    self._send_json(json.dumps({}).encode())
                elif self.path == "/api/game-state":
                    self._send_json(json.dumps({"games": []}).encode())
                elif self.path == "/trading" or self.path == "/trading/esports" or self.path == "/":
                    td_html = Path("/Users/bradleyguan/Documents/Coding/kalshi_nhl_tracker/dashboard/trading_dashboard.html")
                    try:
                        html = td_html.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(html)))
                        self.end_headers()
                        self.wfile.write(html)
                    except FileNotFoundError:
                        self.send_error(404, "trading_dashboard.html not found! Hardcoded path may be wrong.")
                elif self.path == "/api/clear":
                    state_store.clear()
                    self._send_json(json.dumps({"ok": True}).encode())
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path == "/api/clear":
                    state_store.clear()
                    self._send_json(json.dumps({"ok": True}).encode())
                else:
                    self.send_error(404)

        try:
            server = ThreadingHTTPServer(("localhost", self.dashboard_port), Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(f"  \033[96m\033[1m🌐 Esports Dashboard:\033[0m http://localhost:{self.dashboard_port}/trading")
        except OSError as ex:
            if "Address already in use" in str(ex):
                print(f"  \033[2m📡 Dashboard port {self.dashboard_port} in use.\033[0m")
            else:
                raise
