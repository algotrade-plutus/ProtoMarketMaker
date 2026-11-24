### im2022: markouts (all 40 sessions, first 6; price path: tape)

| arm | sessions | contracts | taker share | taker price impr. (median, pts) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | trading (M đ) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| N0 | 6 | 29 | 0% |  | -0.21 | -1.34 | +2.49 | +11.0 | +4.3 | +6.7 |
| N3 | 6 | 29 | 0% |  | -0.73 | -1.86 | +1.98 | +8.8 | +4.3 | +4.6 |
| F-opt | 6 | 39 | 59% | +0.40 | -0.54 | -0.92 | +3.68 | +20.2 | +6.3 | +13.9 |

Markouts: mean per contract, index points, + = good for A (1 point = 100,000 đ per contract). Taker share: contracts filled as taker among those with a liquidity side. Carry = previous end positions x close-to-close move; trading = the rest.

- F-opt: 39 fills had no contract and were assigned one (0 ambiguous).

Inputs:

- N0: naive trace run by this module
- N3: naive trace run by this module
- F-opt: `fills_opt6.json` (sha256 `7d953daec3f2b69f…`); equity from `result/mm_faithful_a/im2022_optimistic.json`
