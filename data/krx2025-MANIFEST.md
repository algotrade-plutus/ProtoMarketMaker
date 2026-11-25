# Data manifest: ProtoMarketMaker window `krx2025`

- Window: 2025-04-01 .. 2025-05-30 (40 sessions; 20 before and 20 from 2025-05-05: KRX matching/margin cutover 2025-05-05 (primary))
- Source: book/tape `db`, daily bands `db`, via `plutus-simulator/scripts/rivf26_extract.py declared --request` (slices `rivf26/data/mm-krx2025-tick/` and `mm-krx2025-daily/`; their DATA-MANIFEST.md and request.json carry the untrimmed sha256s)
- Trimmed here to trading hours 08:45:00..14:46:00 for tick/book tables (drops the end-of-day 00:00:00 row); daily tables copied unchanged.
- Prices are VN30F index points (1 point = 100,000 dong per contract).

| file | rows (slice -> repo) | bytes | sha256 |
|---|--:|--:|---|
| data/band/krx2025/quote_ceil.parquet | 80 -> 80 | 1560 | `f3ff1f0a3a1ba1c0b06ed5eb24f4f5186447e7771e1339c6c9e4a5f562d409e0` |
| data/band/krx2025/quote_close.parquet | 120 -> 120 | 1792 | `d01f48cb6a912902ed48f7a26426db91da69cb47b6e4eeaf7632e3faaed125a9` |
| data/band/krx2025/quote_floor.parquet | 80 -> 80 | 1568 | `c97fa97a9c16f083567b1f1d72c83615a9b20de7942571f1169dd0fe3d74198a` |
| data/band/krx2025/quote_reference.parquet | 80 -> 80 | 1560 | `7ea9641a620a0aeee56521f2bda3ba2569cbdb4a39a81b23d7e147f21017c6f5` |
| data/band/krx2025/quote_ticker.parquet | 4 -> 4 | 1879 | `722b3ed7b70c6a7b8eaecda358473cbe7729d6de59ea226abc01779c8fbabec3` |
| data/l2/krx2025/local_quote_askprice.parquet | 579833 -> 579833 | 1631341 | `4dbac7d83b12f1c6c8cc3eadeb339123305744d27825cfff78575c07a93d82f5` |
| data/l2/krx2025/local_quote_asksize.parquet | 1094467 -> 1094467 | 4089466 | `0d135f7028ebfdfcc50cf6f8c541240f0b601d2aef0b0ea49d839a0b853faf45` |
| data/l2/krx2025/local_quote_bidprice.parquet | 566375 -> 566375 | 1610202 | `eaac7b7068e24d50647b7dece2eaf047d9a27c2f647977f01a304fef1592e8c4` |
| data/l2/krx2025/local_quote_bidsize.parquet | 1083873 -> 1083873 | 4266338 | `271325ca7481c92a04c9a5dcb023179f4d5c7a41092af063ff4d3f76fe3edb46` |
| data/l2/krx2025/local_quote_matched.parquet | 343840 -> 343840 | 1677831 | `1f19f3ecae1f8bef6fb5b890862ae07c63ae935cb90540303dad7cc7aa8bfc04` |
| data/l2/krx2025/local_quote_total.parquet | 571605 -> 571597 | 3062829 | `e8cbad842ddfe2a0f44acc7bd7dc06c7583789c1015a207957a0165a0ce07bb1` |
| data/market/krx2025/futurecontractcode.csv | 80 | 2353 | `2f3d6c53cd0392800e465a40b8c0375856e427d14b526ee2249fad96ffc1ba71` |

Total: 16348719 bytes (15.59 MiB).

## Why this window is minimal

20 sessions either side of the 2025-05-05 KRX cutover, the low end of the handoff's 20-30: enough for A to quote and carry inventory under both dated margin regimes (pre_margin, then QD 26's two layers) a non-trivial number of times on each side. MM has no look-back, so no warm-up. Only the contract the signal trades each day carries book and tape; VN30F2M otherwise contributes matched prices, closes and daily bands (bands for both contracts on every session, so a roll can close F1 and open F2). Depth 1-3 is all the DB holds and all the book walk reads. The VN30 index close (one row per session in quote_close) is what the engine's post-KRX CCP margin layer reads (QD 26 Phu luc 2 margins on the underlying's close); without it every post-cutover night with a position is INDETERMINATE.

## Size flag

Over 3 MiB: L2 depth 1-3 with sizes plus the sized tape is what the queue claims read; 40 sessions is the handoff's floor, so this is irreducible without shortening the window. The growth over the first extraction (+0.11 MiB im2022, +0.52 MiB krx2025) comes only from the roll days and the session after each roll, where book and sized tape now cover both contracts A holds or trades (see ``touched``); bands grew by the F2M rows.
