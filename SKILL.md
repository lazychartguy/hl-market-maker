---
name: hl-market-maker
description: "Market making bot for Hyperliquid XYZ builder-dex equity tokens. Generates trading volume while capturing bid-ask spread. Use when: (1) farming airdrop volume on Hyperliquid, (2) running a passive market maker on XYZ equity perpetuals, (3) user says market maker, mm bot, volume farming, or build volume on Hyperliquid. Requires a Hyperliquid account with USDC deposited and an API wallet (agent key)."
---

# Hyperliquid XYZ Market Maker

Automated market making on Hyperliquid's builder-dex (XYZ) equity perpetuals.
Places limit buy/sell orders around mid price, manages inventory, and tracks
volume — designed for airdrop volume farming with minimal PnL impact.

## Requirements

- Python 3.11+
- `hyperliquid-python-sdk` (`pip install hyperliquid-python-sdk`)
- `eth-account`, `pyyaml`, `requests`
- Hyperliquid account with USDC in the XYZ (builder-dex) clearinghouse
- API wallet (agent key) — trading only, no withdrawal access

## Setup

1. **Create an API wallet** on Hyperliquid (Settings → API Wallets).
   Copy the wallet address and private key.

2. **Deposit USDC** to the XYZ clearinghouse (Portfolio → Transfer → XYZ).

3. **Create config file:**
   ```bash
   cp scripts/config.example.yaml config.yaml
   ```
   Edit `config.yaml` with your preferred tokens and parameters.

4. **Set environment variables:**
   ```bash
   export HL_WALLET="0xYOUR_MAIN_WALLET"
   export HL_PRIVATE_KEY="0xYOUR_API_KEY"
   ```

5. **Install dependencies:**
   ```bash
   pip install hyperliquid-python-sdk eth-account pyyaml requests
   ```

## Running

```bash
# Dry run first (no real orders)
python3 scripts/market_maker.py --dry-run

# Live trading
python3 market_maker.py --config config.yaml
```

## How It Works

**Core loop (every `cycle_seconds`):**
1. Fetch best bid/ask for each configured token
2. Cancel stale orders (older than `order_refresh_seconds`)
3. Place limit buy at `mid - spread_pct` and sell at `mid + spread_pct`
4. Process new fills and log volume
5. Check inventory and stop-loss limits

**Safety features:**
- **Inventory limit**: auto-flatten at ±`max_inventory_units` via market order
- **Stop loss**: close position if unrealized loss exceeds `stop_loss_pct`
- **Volatility guard**: pause quoting if price moves >`pause_on_volatility_pct` in 60s
- **Dry-run mode**: simulate without real orders

**Volume tracking:** All fills logged to `mm_volume.db` (SQLite). Daily volume
summary sent via OpenClaw alerts (if installed).

## Configuration Reference

See `scripts/config.example.yaml` for all options with comments.

**Key parameters by goal:**

| Goal | spread_pct | order_size_usd | max_inventory |
|------|-----------|----------------|---------------|
| Max volume (aggressive) | 0.05 | 400 | 5 |
| Balanced (default) | 0.15 | 200 | 3 |
| Conservative | 0.30 | 100 | 2 |

**Token selection:** Pick high-volume, low-volatility tokens. Run the scanner
in `references/token-scanner.md` to find candidates. Good starting points:
BRENTOIL, CL, INTC, NVDA, TSLA — commodities and large-cap stocks with tight
spreads and stable price action.

## Alert Integration

If OpenClaw is installed, alerts are sent for:
- Stop-loss triggers
- Inventory flatten events
- Volatility pauses
- Daily volume summaries

Set `TELEGRAM_CHAT_ID` env var to receive Telegram alerts. Otherwise alerts
are logged only.
