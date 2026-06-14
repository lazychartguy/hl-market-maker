"""
Market Maker for Hyperliquid XYZ equity tokens.

Goal: Generate trading volume for airdrop farming while capturing bid-ask spread.
Strategy: Place limit buy/sell orders around mid price, refresh as fills come in.

Usage:
    python3 market_maker.py
    python3 market_maker.py --dry-run
    python3 market_maker.py --config config.yaml
"""
import argparse
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, date
from typing import Dict, List, Optional, Tuple

import requests
import yaml
from eth_account import Account

# Reuse signing helpers from the SDK
from hyperliquid.utils.signing import (
    sign_l1_action,
    order_request_to_order_wire,
    order_wires_to_order_action,
    OrderRequest,
)

BUILDER_ADDRESS = "0x0000000000000000000000000000000000000001"
BUILDER_FEE_INT = 0

log = logging.getLogger("market_maker")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_timestamp_ms() -> int:
    return int(time.time() * 1000)


def load_env(path: str = ".env"):
    """Load simple KEY=value env file."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def send_openclaw(message: str):
    """Send alert via OpenClaw (same pattern as position_monitor.py)."""
    try:
        import subprocess
        result = subprocess.run(
            ["openclaw", "message", "send", "--channel", "telegram",
             "--target", os.environ.get("TELEGRAM_CHAT_ID", "6340257441"),
             "--message", message],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception as e:
        log.error(f"OpenClaw send failed: {e}")
        return False


def alert(message: str):
    """Log + send alert."""
    log.info(f"ALERT: {message}")
    send_openclaw(message)


# ─────────────────────────────────────────────────────────────────────────────
# Hyperliquid Client (minimal, focused on MM needs)
# ─────────────────────────────────────────────────────────────────────────────

class HLClient:
    """Minimal HL client for market making — place/cancel orders, fetch books/fills."""

    def __init__(self, wallet_address: str, private_key: str, base_url: str = "https://api.hyperliquid.xyz", dex: str = "xyz"):
        self.base_url = base_url
        self.wallet_address = wallet_address
        self.dex = dex
        self.wallet = Account.from_key(private_key)
        self._session = requests.Session()
        # asset name -> index in universe
        self._asset_map: Dict[str, int] = {}
        self._sz_decimals: Dict[str, int] = {}
        self._refresh_metadata()

    # ── Metadata ────────────────────────────────────────────────────────────

    def _refresh_metadata(self):
        for attempt in range(3):
            try:
                r = self._session.post(self.base_url + "/info",
                    json={"type": "metaAndAssetCtxs", "dex": self.dex}, timeout=15)
                r.raise_for_status()
                data = r.json()
                universe = data[0].get("universe", [])
                for i, info in enumerate(universe):
                    name = info.get("name", "").upper()
                    bare = name.replace(f"{self.dex.upper()}:", "")
                    self._asset_map[bare] = i
                    self._sz_decimals[bare] = int(info.get("szDecimals", 0))
                log.info(f"Loaded {len(self._asset_map)} {self.dex} asset mappings")
                return
            except Exception as e:
                log.warning(f"Metadata fetch attempt {attempt+1} failed: {e}")
                time.sleep(1)
        log.error("Failed to refresh metadata after 3 attempts")

    def _asset_id(self, symbol: str) -> int:
        sym = symbol.upper().replace(f"{self.dex.upper()}:", "")
        # Try both bare and prefixed forms
        if sym in self._asset_map:
            return 110000 + self._asset_map[sym]
        prefixed = f"{self.dex.upper()}:{sym}"
        if prefixed in self._asset_map:
            return 110000 + self._asset_map[prefixed]
        raise ValueError(f"Unknown symbol: {symbol}")

    def _coin_wire(self, symbol: str) -> str:
        """Normalize to wire format: xyz:COIN."""
        s = symbol.upper()
        if ":" in s:
            prefix, rest = s.split(":", 1)
            return f"{prefix.lower()}:{rest}"
        return f"{self.dex.lower()}:{s}"

    def _get_sz_decimals(self, symbol: str) -> int:
        sym = symbol.upper().replace(f"{self.dex.upper()}:", "")
        for key in [sym, f"{self.dex.upper()}:{sym}"]:
            if key in self._sz_decimals:
                return self._sz_decimals[key]
        return 0

    def _round_size(self, symbol: str, size: float) -> int:
        """XYZ equity tokens all use integer share sizes."""
        return int(round(size))

    def _round_price(self, price: float) -> float:
        """Round price to 2 decimal places (safe for all XYZ tokens)."""
        return round(price, 2)

    # ── Queries ─────────────────────────────────────────────────────────────

    def get_l2_book(self, symbol: str) -> Optional[Tuple[float, float, float]]:
        """Returns (best_bid, best_ask, mid) or None."""
        try:
            r = self._session.post(self.base_url + "/info",
                json={"type": "l2Book", "coin": self._coin_wire(symbol), "dex": self.dex},
                timeout=5)
            data = r.json()
            levels = data.get("levels", [[], []])
            if not levels[0] or not levels[1]:
                return None
            best_bid = float(levels[0][0]["px"])
            best_ask = float(levels[1][0]["px"])
            mid = (best_bid + best_ask) / 2
            return best_bid, best_ask, mid
        except Exception as e:
            log.debug(f"l2Book error for {symbol}: {e}")
            return None

    def get_open_orders(self) -> List[dict]:
        try:
            r = self._session.post(self.base_url + "/info",
                json={"type": "frontendOpenOrders", "user": self.wallet_address, "dex": self.dex},
                timeout=10)
            return r.json() or []
        except Exception as e:
            log.debug(f"open orders error: {e}")
            return []

    def get_positions(self) -> Dict[str, float]:
        """Returns {symbol: signed_size}."""
        try:
            r = self._session.post(self.base_url + "/info",
                json={"type": "clearinghouseState", "user": self.wallet_address, "dex": self.dex},
                timeout=10)
            positions = {}
            for p in r.json().get("assetPositions", []):
                pos = p.get("position", {})
                coin = pos.get("coin", "").upper().replace(f"{self.dex.upper()}:", "")
                size = float(pos.get("szi", 0))
                if size != 0:
                    positions[coin] = size
            return positions
        except Exception as e:
            log.debug(f"positions error: {e}")
            return {}

    def get_recent_fills(self, since_ms: int) -> List[dict]:
        try:
            r = self._session.post(self.base_url + "/info",
                json={"type": "userFills", "user": self.wallet_address, "dex": self.dex},
                timeout=10)
            fills = r.json() or []
            return [f for f in fills if int(f.get("time", 0)) > since_ms]
        except Exception as e:
            log.debug(f"fills error: {e}")
            return []

    # ── Actions ─────────────────────────────────────────────────────────────

    def _sign_action(self, action: dict) -> dict:
        """Sign L1 action. vaultAddress=None for agent key (it IS the account)."""
        timestamp = get_timestamp_ms()
        signature = sign_l1_action(
            self.wallet, action,
            None,  # vault_address=None for agent key
            timestamp,
            None,  # expires_after
            True,  # is_mainnet
        )
        return {
            "action": action,
            "nonce": timestamp,
            "signature": signature,
            "vaultAddress": None,
            "expiresAfter": None,
        }

    def _post_exchange(self, payload: dict) -> dict:
        r = self._session.post(self.base_url + "/exchange", json=payload, timeout=10)
        return r.json()

    def place_limit(self, symbol: str, side: str, size: int, price: float, tif: str = "Gtc", reduce_only: bool = False) -> dict:
        """Place a limit order. Returns HL response."""
        is_buy = side.lower() == "buy"
        asset_id = self._asset_id(symbol)
        coin = self._coin_wire(symbol)

        order_req: OrderRequest = {
            "coin": coin,
            "is_buy": is_buy,
            "sz": size,
            "limit_px": self._round_price(price),
            "order_type": {"limit": {"tif": tif}},
            "reduce_only": reduce_only,
        }

        order_wire = order_request_to_order_wire(order_req, asset_id)
        builder_info = {"b": BUILDER_ADDRESS.lower(), "f": BUILDER_FEE_INT}
        action = order_wires_to_order_action([order_wire], builder_info, "na")

        payload = self._sign_action(action)
        return self._post_exchange(payload)

    def cancel_order(self, symbol: str, oid: str) -> dict:
        asset_id = self._asset_id(symbol)
        action = {
            "type": "cancel",
            "cancels": [{"a": asset_id, "o": int(oid)}],
        }
        payload = self._sign_action(action)
        return self._post_exchange(payload)

    def cancel_all_for_symbol(self, symbol: str) -> bool:
        """Cancel all our open orders for a symbol."""
        coin_wire = self._coin_wire(symbol)
        open_orders = self.get_open_orders()
        cancelled = 0
        for o in open_orders:
            if o.get("coin", "").lower() == coin_wire.lower():
                oid = o.get("oid")
                try:
                    self.cancel_order(symbol, str(oid))
                    cancelled += 1
                except Exception as e:
                    log.debug(f"Cancel failed for {symbol} oid={oid}: {e}")
        return cancelled > 0

    def market_close(self, symbol: str, current_size: float) -> bool:
        """Flatten position via aggressive IOC order at market."""
        if abs(current_size) < 0.001:
            return True
        side = "sell" if current_size > 0 else "buy"
        # Use a wide price to ensure fill (IOC = immediate or cancel)
        book = self.get_l2_book(symbol)
        if not book:
            log.error(f"Cannot market close {symbol}: no book")
            return False
        best_bid, best_ask, _ = book
        # Sell at bid, buy at ask (aggressive)
        price = best_bid if side == "sell" else best_ask
        try:
            result = self.place_limit(symbol, side, abs(int(current_size)), price, tif="Ioc", reduce_only=True)
            status = result.get("response", {}).get("type")
            return status == "order" or result.get("status") == "ok"
        except Exception as e:
            log.error(f"Market close failed for {symbol}: {e}")
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Volume Tracker (sqlite)
# ─────────────────────────────────────────────────────────────────────────────

VOLUME_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS mm_volume (
    ts INTEGER NOT NULL,
    day TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    size REAL NOT NULL,
    price REAL NOT NULL,
    notional REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mm_volume_day ON mm_volume(day);
CREATE INDEX IF NOT EXISTS idx_mm_volume_symbol ON mm_volume(symbol);
"""

class VolumeTracker:
    def __init__(self, db_path: str = "mm_volume.db"):
        self.db_path = db_path
        conn = sqlite3.connect(db_path)
        conn.executescript(VOLUME_DB_SCHEMA)
        conn.commit()
        conn.close()

    def record_fill(self, symbol: str, side: str, size: float, price: float):
        now = int(time.time())
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        notional = size * price
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO mm_volume (ts, day, symbol, side, size, price, notional) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, day, symbol, side, size, price, notional),
        )
        conn.commit()
        conn.close()

    def daily_volume(self, day: str = None) -> Tuple[float, Dict[str, float]]:
        day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT symbol, SUM(notional) FROM mm_volume WHERE day=? GROUP BY symbol",
            (day,),
        ).fetchall()
        conn.close()
        per_token = {r[0]: r[1] for r in rows}
        return sum(per_token.values()), per_token

    def total_volume(self) -> float:
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COALESCE(SUM(notional), 0) FROM mm_volume").fetchone()[0]
        conn.close()
        return total


# ─────────────────────────────────────────────────────────────────────────────
# Market Maker Bot
# ─────────────────────────────────────────────────────────────────────────────

class MarketMaker:
    def __init__(self, config: dict, dry_run: bool = False):
        mm_cfg = config.get("market_maker", {})
        self.tokens: List[str] = [t.upper() for t in mm_cfg.get("tokens", ["BRENTOIL", "CL", "INTC"])]
        self.spread_pct: float = mm_cfg.get("spread_pct", 0.15) / 100.0  # convert to decimal
        self.order_size_usd: float = mm_cfg.get("order_size_usd", 200.0)
        self.max_inventory_units: int = mm_cfg.get("max_inventory_units", 5)
        self.cycle_seconds: float = mm_cfg.get("cycle_seconds", 5)
        self.order_refresh_seconds: int = mm_cfg.get("order_refresh_seconds", 30)
        self.leverage: int = mm_cfg.get("leverage", 5)
        self.dry_run: bool = dry_run or mm_cfg.get("dry_run", False)
        self.pause_on_volatility_pct: float = mm_cfg.get("pause_on_volatility_pct", 1.5) / 100.0
        self.pause_minutes: int = mm_cfg.get("pause_minutes", 10)
        self.stop_loss_pct: float = mm_cfg.get("stop_loss_pct", 2.0) / 100.0  # 2% SL
        self.sl_cooldown_minutes: int = mm_cfg.get("sl_cooldown_minutes", 30)  # pause after SL hit
        # Token paused until (timestamp)
        self._paused: Dict[str, float] = defaultdict(float)
        # Last mid price per token (for volatility guard)
        self._last_mid: Dict[str, float] = {}
        self._last_mid_time: Dict[str, float] = {}
        # Track our resting orders: {(symbol, side): (oid, placed_at)}
        self._resting: Dict[Tuple[str, str], Tuple[str, float]] = {}
        # Last fill timestamp (for incremental fill queries)
        self._last_fill_check: int = get_timestamp_ms()
        # Trackers
        self.client = HLClient(
            wallet_address=os.environ["HL_FUNDING_WALLET"],
            private_key=os.environ["HL_FUNDING_KEY"],
            dex="xyz",
        )
        self.tracker = VolumeTracker()
        # Daily summary tracking
        self._last_summary_day: str = ""

        log.info("=" * 60)
        log.info("MARKET MAKER INITIALIZED")
        log.info(f"  Tokens: {self.tokens}")
        log.info(f"  Spread: {self.spread_pct*100:.2f}% per side ({self.spread_pct*200:.2f}% total)")
        log.info(f"  Order size: ${self.order_size_usd:.0f} notional")
        log.info(f"  Max inventory: ±{self.max_inventory_units} units per token")
        log.info(f"  Cycle: {self.cycle_seconds}s, refresh: {self.order_refresh_seconds}s")
        log.info(f"  Volatility guard: pause if >{self.pause_on_volatility_pct*100:.1f}% move in {self.cycle_seconds}s")
        log.info(f"  Stop loss: {self.stop_loss_pct*100:.1f}% per position, {self.sl_cooldown_minutes}min cooldown after SL hit")
        log.info(f"  Dry run: {self.dry_run}")
        log.info("=" * 60)

    def run(self):
        """Main loop."""
        log.info("Starting market maker loop. Ctrl+C to stop.")
        try:
            while True:
                self._cycle()
                time.sleep(self.cycle_seconds)
        except KeyboardInterrupt:
            log.info("Shutting down — cancelling all orders...")
            for sym in self.tokens:
                self.client.cancel_all_for_symbol(sym)
            log.info("Done.")

    def _cycle(self):
        """One pass through all tokens."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        log.info(f"\n--- MM cycle {now} ---")

        # Daily summary at day rollover
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._last_summary_day and self._last_summary_day != today:
            self._send_daily_summary(self._last_summary_day)
        self._last_summary_day = today

        # Process new fills first
        self._process_fills()

        # Run MM for each token
        for symbol in self.tokens:
            try:
                self._market_make_token(symbol)
            except Exception as e:
                log.error(f"MM error for {symbol}: {e}")

        # Status log
        daily_total, per_token = self.tracker.daily_volume()
        positions = self.client.get_positions()
        inv_summary = " ".join(f"{s}={v:+.0f}" for s, v in positions.items() if any(s == t or s.endswith(t) for t in self.tokens))
        log.info(f"Vol today: ${daily_total:,.0f} | Total: ${self.tracker.total_volume():,.0f} | Inventory: {inv_summary or 'flat'}")


    def _get_position_info(self, symbol: str) -> dict:
        """Fetch position details from clearinghouseState for a single token."""
        try:
            r = self.client._session.post(self.client.base_url + "/info",
                json={"type": "clearinghouseState", "user": self.client.wallet_address, "dex": "xyz"},
                timeout=10)
            for p in r.json().get("assetPositions", []):
                pos = p.get("position", {})
                coin = pos.get("coin", "").upper().replace("XYZ:", "")
                if coin == symbol.upper():
                    size = float(pos.get("szi", 0))
                    entry = float(pos.get("entryPx", 0))
                    upnl = float(pos.get("unrealizedPnl", 0))
                    upnl_pct = (upnl / (abs(size) * entry) * 100) if entry > 0 and abs(size) > 0 else None
                    return {'size': size, 'entry': entry, 'upnl': upnl, 'upnl_pct': upnl_pct}
            return {'size': 0.0, 'entry': 0, 'upnl': 0, 'upnl_pct': None}
        except Exception as e:
            log.debug(f"Position info error for {symbol}: {e}")            
            return {'size': 0.0, 'entry': 0, 'upnl': 0, 'upnl_pct': None}

    def _market_make_token(self, symbol: str):
        """Place/refresh quotes for one token."""
        sym = symbol.upper()

        # Volatility guard
        if self._is_paused(sym):
            return

        book = self.client.get_l2_book(symbol)
        if not book:
            return
        best_bid, best_ask, mid = book

        # Update volatility tracker
        self._check_volatility(sym, mid)

        # If volatility tripped, pause
        if self._is_paused(sym):
            self.client.cancel_all_for_symbol(sym)
            self._resting = {k: v for k, v in self._resting.items() if k[0] != sym}
            return

        # Get position info (size + entry price + unrealized PnL)
        pos_info = self._get_position_info(sym)
        inv = pos_info.get('size', 0.0)

        # Stop-loss check
        if abs(inv) > 0.1 and pos_info.get('upnl_pct', 0) is not None:
            upnl_pct = pos_info['upnl_pct']
            if upnl_pct <= -(self.stop_loss_pct * 100):
                log.warning(f"{sym} STOP LOSS triggered: {upnl_pct*100:.2f}% <= -{self.stop_loss_pct*100:.1f}%")
                self.client.cancel_all_for_symbol(sym)
                self._resting = {k: v for k, v in self._resting.items() if k[0] != sym}
                ok = self.client.market_close(symbol, inv)
                if ok:
                    alert(f"🛑 MM STOP LOSS {sym}: {upnl_pct*100:.2f}%, closing position, cooldown {self.sl_cooldown_minutes}min")
                    self._paused[sym] = time.time() + self.sl_cooldown_minutes * 60
                return

        # ── Smart inventory management ──
        # Instead of market-flattening, suppress the side that adds to inventory.
        # Let it unwind naturally through limit orders only.
        soft_limit = self.max_inventory_units - 1
        suppress_buy = inv >= soft_limit   # too long — stop buying
        suppress_sell = inv <= -soft_limit # too short — stop selling

        if suppress_buy or suppress_sell:
            suppressed_side = "BUY" if suppress_buy else "SELL"
            log.debug(f"{sym} inv={inv:+.1f} — suppressing {suppressed_side} (soft limit {soft_limit})")

        # Compute quote prices
        size = max(1, int(self.order_size_usd / mid))
        buy_price = self._round(mid * (1 - self.spread_pct))
        sell_price = self._round(mid * (1 + self.spread_pct))

        # Skip if spread is inverted (mid outside market)
        if buy_price >= best_ask or sell_price <= best_bid:
            return

        # Cancel any suppressed side that's still resting
        if suppress_buy and (sym, "buy") in self._resting:
            oid, _ = self._resting.pop((sym, "buy"))
            try: self.client.cancel_order(symbol, oid)
            except: pass
        if suppress_sell and (sym, "sell") in self._resting:
            oid, _ = self._resting.pop((sym, "sell"))
            try: self.client.cancel_order(symbol, oid)
            except: pass

        # Quote only non-suppressed sides
        now = time.time()
        sides_to_quote = []
        if not suppress_buy:
            sides_to_quote.append(("buy", buy_price))
        if not suppress_sell:
            sides_to_quote.append(("sell", sell_price))

        for side, want_price in sides_to_quote:
            key = (sym, side)
            if key in self._resting:
                oid, placed_at = self._resting[key]
                age = now - placed_at
                if age < self.order_refresh_seconds:
                    continue
                try:
                    self.client.cancel_order(symbol, oid)
                except Exception as e:
                    log.debug(f"Cancel stale {sym} {side} failed: {e}")
                self._resting.pop(key, None)

            if self.dry_run:
                log.info(f"[DRY] {side.upper()} {sym} {size} @ ${want_price:.2f}")
                self._resting[key] = ("dry_run", now)
                continue

            try:
                result = self.client.place_limit(symbol, side, size, want_price, tif="Gtc")
                resp = result.get("response", {})
                if resp.get("type") == "order":
                    data = resp.get("data", {})
                    statuses = data.get("statuses", [])
                    if statuses and "resting" in statuses[0]:
                        new_oid = statuses[0]["resting"].get("oid")
                        self._resting[key] = (str(new_oid), now)
                        log.info(f"Placed {sym} {side.upper()} {size} @ ${want_price:.2f} oid={new_oid}")
                    elif statuses and "filled" in statuses[0]:
                        log.info(f"Filled immediately {sym} {side.upper()} {size} @ ${want_price:.2f}")
                    elif statuses and "error" in statuses[0]:
                        log.warning(f"Order rejected {sym} {side.upper()}: {statuses[0]['error']}")
                elif result.get("status") == "err":
                    err = result.get("response", "unknown")
                    log.warning(f"Place failed {sym} {side}: {err}")
            except Exception as e:
                log.error(f"Order error {sym} {side}: {e}")

    def _process_fills(self):
        """Detect new fills and record them."""
        now_ms = get_timestamp_ms()
        fills = self.client.get_recent_fills(self._last_fill_check)
        self._last_fill_check = now_ms
        for f in fills:
            try:
                sym = f.get("coin", "").upper().replace("XYZ:", "")
                side = f.get("side", "").lower()
                size = float(f.get("sz", 0))
                price = float(f.get("px", 0))
                if size > 0 and price > 0:
                    self.tracker.record_fill(sym, side, size, price)
                    log.info(f"FILL: {sym} {side} {size} @ ${price:.4f} (${size*price:.2f})")
                    # Clear resting state for filled side
                    self._resting.pop((sym, "buy" if side == "b" or side == "buy" else "sell"), None)
            except Exception as e:
                log.debug(f"Fill parse error: {e}")

    # ── Volatility Guard ────────────────────────────────────────────────────

    def _check_volatility(self, sym: str, mid: float):
        last = self._last_mid.get(sym)
        last_t = self._last_mid_time.get(sym, 0)
        now = time.time()
        if last and last > 0 and (now - last_t) <= 60:
            change_pct = abs(mid - last) / last
            if change_pct > self.pause_on_volatility_pct:
                pause_until = now + self.pause_minutes * 60
                self._paused[sym] = pause_until
                log.warning(f"{sym} moved {change_pct*100:.2f}% in {now-last_t:.0f}s — pausing for {self.pause_minutes}min")
                alert(f"⚠️ MM PAUSE {sym}: {change_pct*100:.2f}% move in {now-last_t:.0f}s, pausing {self.pause_minutes}min")
        self._last_mid[sym] = mid
        self._last_mid_time[sym] = now

    def _is_paused(self, sym: str) -> bool:
        return time.time() < self._paused.get(sym, 0)

    def _round(self, x: float) -> float:
        return round(x, 4)

    def _send_daily_summary(self, day: str):
        total, per_token = self.tracker.daily_volume(day)
        breakdown = " ".join(f"{s}=${v:,.0f}" for s, v in per_token.items())
        grand = self.tracker.total_volume()
        msg = f"📊 MM Daily Summary ({day})\nVolume: ${total:,.0f}\nBreakdown: {breakdown}\nAll-time: ${grand:,.0f}"
        alert(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="XYZ Market Maker")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually place orders")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    load_env()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    mm = MarketMaker(config, dry_run=args.dry_run)
    mm.run()


if __name__ == "__main__":
    main()
