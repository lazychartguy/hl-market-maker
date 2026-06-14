# 🤖 HL Market Maker

Automated market making bot for **Hyperliquid XYZ builder-dex equity tokens**.
Designed for airdrop volume farming with minimal PnL impact.

## Quick Start (One Command)

```bash
git clone https://github.com/lazychartguy/hl-market-maker.git
cd hl-market-maker
pip install -r requirements.txt
python3 scripts/setup.py
```

The setup wizard walks you through everything: wallet setup, token selection, risk level, and a test run.

## Manual Setup

<details>
<summary>Prefer to do it yourself? Click here.</summary>

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

</details>

## Features

- **Spread capture**: Places limit buy/sell orders around mid price
- **Inventory management**: Auto-flattens when position exceeds threshold
- **Stop loss**: Closes positions at configurable loss percentage
- **Volatility guard**: Pauses quoting during volatile price swings
- **Volume tracking**: SQLite database of all fills and daily volume
- **Dry-run mode**: Test without real orders
- **Setup wizard**: Interactive configuration (python3 scripts/setup.py)
- **Alert integration**: Optional OpenClaw/Telegram alerts

## Configuration

Edit config.yaml to customize (or use the setup wizard):

| Parameter | Conservative | Balanced | Aggressive |
|-----------|-------------|----------|------------|
| spread_pct | 0.30% | 0.15% | 0.05% |
| order_size_usd | $100 | $200 | $400 |
| max_inventory | 2 units | 3 units | 5 units |
| stop_loss_pct | 1.5% | 2.0% | 3.0% |
| Volume/day | ~$5K | ~$15K | ~$40K+ |

## How It Works

1. Every 5 seconds, fetches best bid/ask for each token
2. Places limit buy below mid and sell above mid
3. When fills occur, logs volume and tracks inventory
4. If inventory exceeds limit, market-flattens immediately
5. If unrealized loss exceeds stop loss, closes the position

## AI Agent Support

Works with all major AI coding assistants:

| Platform | Config File | Auto-detected |
|----------|------------|---------------|
| OpenClaw | SKILL.md | Yes |
| Claude Code | CLAUDE.md | Yes |
| Codex | AGENTS.md | Yes |
| Cursor | .cursorrules | Yes |

Just open the repo in your AI tool and say "set up the market maker."

## Requirements

- Hyperliquid account with USDC in XYZ clearinghouse
- API wallet (agent key) at Settings then API Wallets
- Python 3.11+

## 💜 Referral

Use referral code **LAZY** when signing up for Hyperliquid — you'll get fee discounts and support this project.

👉 [Sign up with referral](https://app.hyperliquid.xyz/join/LAZY)


## License

MIT

## Disclaimer

This software is for educational purposes. Market making involves risk. Test with
dry-run mode first. Not financial advice.
