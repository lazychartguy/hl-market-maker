# CLAUDE.md - HL Market Maker

## Project Overview
Automated market making bot for Hyperliquid XYZ builder-dex equity tokens.
Generates trading volume while capturing bid-ask spread. Designed for airdrop farming.

## Architecture
- `scripts/market_maker.py` — Main bot (single file, ~600 lines)
- `scripts/config.example.yaml` — Configuration template
- `references/token-scanner.md` — How to find good MM tokens

## How to Help Users
1. **Setup**: User needs `HL_WALLET` and `HL_PRIVATE_KEY` env vars, USDC in XYZ clearinghouse
2. **Config**: Copy `scripts/config.example.yaml` to `config.yaml`, edit tokens/params
3. **Test**: Always run `--dry-run` first
4. **Monitor**: Bot logs to stdout, volume tracked in `mm_volume.db` (SQLite)

## Key Technical Details
- Uses `hyperliquid-python-sdk` for order signing (L1 actions)
- Builder-dex tokens need asset ID offset: `110000 + index`
- All XYZ equity tokens use integer share sizes (0 szDecimals)
- Prices rounded to 2 decimal places
- Agent key signs with `vaultAddress=None`
- HL API: `POST https://api.hyperliquid.xyz/info` (queries), `/exchange` (actions)

## Safety Features
- Stop loss: configurable % (default 2%)
- Inventory auto-flatten: at ±max_inventory_units
- Volatility pause: if price moves >1.5% in 60s
- Dry-run mode for testing

## Dependencies
```
hyperliquid-python-sdk
eth-account
pyyaml
requests
```
