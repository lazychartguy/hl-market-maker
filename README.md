# 🤖 HL Market Maker

Automated market making bot for **Hyperliquid XYZ builder-dex equity tokens**.
Designed for airdrop volume farming with minimal PnL impact.

## Features

- **Spread capture**: Places limit buy/sell orders around mid price
- **Inventory management**: Auto-flattens when position exceeds threshold
- **Stop loss**: Closes positions at configurable loss percentage
- **Volatility guard**: Pauses quoting during volatile price swings
- **Volume tracking**: SQLite database of all fills and daily volume
- **Dry-run mode**: Test without real orders
- **Alert integration**: Optional OpenClaw/Telegram alerts

## Quick Start

```bash
# Install dependencies
pip install hyperliquid-python-sdk eth-account pyyaml requests

# Set your wallet credentials
export HL_WALLET="0xYOUR_MAIN_WALLET"
export HL_PRIVATE_KEY="0xYOUR_API_KEY"

# Copy and edit config
cp scripts/config.example.yaml config.yaml

# Dry run first!
python3 scripts/market_maker.py --dry-run

# Live trading
python3 scripts/market_maker.py
```

## Configuration

Edit `config.yaml` to customize:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `tokens` | BRENTOIL, CL, INTC | XYZ tokens to market make |
| `spread_pct` | 0.15 | Distance from mid price per side (%) |
| `order_size_usd` | 200 | Notional size per order ($) |
| `max_inventory_units` | 3 | Max position before auto-flatten |
| `stop_loss_pct` | 2.0 | Close at this unrealized loss (%) |
| `cycle_seconds` | 5 | Quote refresh interval |
| `pause_on_volatility_pct` | 1.5 | Pause threshold for price moves |

See `scripts/config.example.yaml` for full documentation.

## How It Works

1. Every `cycle_seconds`, fetches best bid/ask for each token
2. Places limit buy at `mid * (1 - spread)` and sell at `mid * (1 + spread)`
3. When fills occur, logs volume and tracks inventory
4. If inventory exceeds `max_inventory_units`, market-flattens immediately
5. If unrealized loss exceeds `stop_loss_pct`, closes the position

## Requirements

- Hyperliquid account with USDC in XYZ clearinghouse
- API wallet (agent key) — create at Settings → API Wallets
- Python 3.11+

## License

MIT

## Disclaimer

This software is for educational purposes. Market making involves risk. Test with
dry-run mode first. Not financial advice.
