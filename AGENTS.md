# AGENTS.md - HL Market Maker

## What This Is
Market making bot for Hyperliquid XYZ equity tokens. Farms airdrop volume by
placing limit orders around mid price on builder-dex perpetuals.

## Agent Instructions

### When user wants to run the bot
1. Check Python 3.11+ is installed
2. Install: `pip install hyperliquid-python-sdk eth-account pyyaml requests`
3. Help them set env vars: `HL_WALLET` (main wallet address) and `HL_PRIVATE_KEY` (API wallet key)
4. Copy `scripts/config.example.yaml` → `config.yaml`, edit tokens and params
5. ALWAYS dry-run first: `python3 scripts/market_maker.py --dry-run`
6. If dry-run looks good, run live: `python3 scripts/market_maker.py`

### When user wants to customize
- Read `scripts/market_maker.py` to understand the code
- Read `scripts/config.example.yaml` for all options
- Key params: `spread_pct` (wider=safer, tighter=more volume), `max_inventory_units`, `stop_loss_pct`
- Use `references/token-scanner.md` to help pick tokens

### When user reports issues
- Check if funds are in XYZ clearinghouse (not spot or regular perps)
- Verify API wallet is created and has trading permission
- Check bot logs for API errors
- Common issue: "Must deposit before performing actions" = no USDC in XYZ clearinghouse

## HL API Quick Reference
- L2 Book: `POST /info {"type":"l2Book","coin":"xyz:BRENTOIL","dex":"xyz"}`
- Place order: uses SDK `order_request_to_order_wire` + `order_wires_to_order_action`
- Asset IDs: `110000 + universe_index`
- All XYZ tokens: integer sizes, 2 decimal price precision
