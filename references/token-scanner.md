# Token Scanner

Find the best XYZ equity tokens for market making by scanning for high volume and tight spreads.

## Quick Scan Script

```python
import requests, time

r = requests.post("https://api.hyperliquid.xyz/info",
    json={"type":"metaAndAssetCtxs","dex":"xyz"}, timeout=15)
data = r.json()
meta, ctxs = data[0], data[1]

tokens = []
for m, c in zip(meta.get('universe', []), ctxs):
    sym = m.get('name','')
    mid_str = c.get('midPx')
    if not mid_str: continue
    mid = float(mid_str)
    day_vol = float(c.get('dayNtlVlm') or 0)
    if mid <= 0 or day_vol < 5000:
        continue
    tokens.append({'symbol': sym, 'mid': mid, 'day_vol': day_vol})

tokens.sort(key=lambda t: t['day_vol'], reverse=True)

print(f"{'Symbol':<16} | {'Price':>8} | {'Day Vol':>12} | {'Spread':>8} | {'Spread%':>8}")
print("-" * 65)
for t in tokens[:20]:
    try:
        r2 = requests.post("https://api.hyperliquid.xyz/info",
            json={"type":"l2Book","coin": t['symbol']}, timeout=5)
        levels = r2.json().get('levels', [[], []])
        if levels[0] and levels[1]:
            spread = float(levels[1][0]['px']) - float(levels[0][0]['px'])
            spread_pct = spread / t['mid'] * 100
            print(f"{t['symbol']:<16} | ${t['mid']:>7.2f} | ${t['day_vol']:>11,.0f} | ${spread:>7.4f} | {spread_pct:>6.3f}%")
    except: pass
    time.sleep(0.1)
```

## What Makes a Good MM Token

| Criteria | Good | Bad |
|----------|------|-----|
| Daily volume | >$10M | <$1M |
| Spread % | <0.02% | >0.05% |
| Intraday volatility | <1% | >3% |
| Sector | Commodities, indices | Meme stocks, low-cap |

**Best sectors:** Commodities (BRENTOIL, CL, GOLD, SILVER), indices (SP500, SPCX), large-cap tech (NVDA, INTC, TSLA).

**Avoid:** Meme stocks (GME), low-volume tokens, tokens with frequent gaps or news catalysts.
