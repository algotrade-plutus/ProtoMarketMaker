# Data manifest: ProtoMarketMaker window `krx2025`

- Window: 2025-04-01 .. 2025-05-30 (40 sessions; 20 before and 20 from 2025-05-05: KRX matching/margin cutover 2025-05-05 (primary))
- Source: book/tape `db`, daily bands `db`, via `plutus-simulator/scripts/rivf26_extract.py declared --request` (slices `rivf26/data/mm-krx2025-tick/` and `mm-krx2025-daily/`; their DATA-MANIFEST.md and request.json carry the untrimmed sha256s)
- Trimmed here to trading hours 08:45:00..14:46:00 for tick/book tables (drops the end-of-day 00:00:00 row); daily tables copied unchanged.
- Prices are VN30F index points (1 point = 100,000 dong per contract).

| file | rows (slice -> repo) | bytes | sha256 |
|---|--:|--:|---|
| data/band/krx2025/quote_ceil.parquet | 40 -> 40 | 1381 | `73281207e9de0b64987efac57bbff15af0d05f2b61c042b8baec2b799e79f82d` |
| data/band/krx2025/quote_close.parquet | 80 -> 80 | 1559 | `7df64b37bd54d518297c91b8f7a6ecda6752f6072d5d87b4871f179e90da635d` |
| data/band/krx2025/quote_floor.parquet | 40 -> 40 | 1387 | `a6b67ce7b7203655a441fcca37b1b5ff3c30b783d5713aea4b8b94f993986b08` |
| data/band/krx2025/quote_reference.parquet | 40 -> 40 | 1373 | `3c6a74b157d4d82631d8f3f6e4711c41575435a6a01db14e2c88df5eab03fe71` |
| data/band/krx2025/quote_ticker.parquet | 3 -> 3 | 1869 | `91cd7860a527a0b3287384fe2991dd2170d99ecdcfd09794fb2b93bcc93b326c` |
| data/l2/krx2025/local_quote_askprice.parquet | 560235 -> 560235 | 1590970 | `3ed8b419cf647a7454c290d568e8c1d762498b01bdd9ea711ad374d3d5912af6` |
| data/l2/krx2025/local_quote_asksize.parquet | 1063401 -> 1063401 | 3956300 | `6778d3b78add461ef7c0d909533defabcdf2bc2916a55c15fe0adcf8cacc4f94` |
| data/l2/krx2025/local_quote_bidprice.parquet | 551474 -> 551474 | 1571821 | `e279194e4c1977174f4e1d9aff0a3fea370faaded2252c587d21ab3daededc16` |
| data/l2/krx2025/local_quote_bidsize.parquet | 1056601 -> 1056601 | 4141847 | `39a0bfa1051588ee6e018c913bac0a881bfdd9cba3018619f9eb07fd216d5969` |
| data/l2/krx2025/local_quote_matched.parquet | 343840 -> 343840 | 1677831 | `1f19f3ecae1f8bef6fb5b890862ae07c63ae935cb90540303dad7cc7aa8bfc04` |
| data/l2/krx2025/local_quote_total.parquet | 522343 -> 522335 | 2858217 | `899c0b66a8c19fc80ea1a4abc5fcabf38d622479ce8d988cff35076811bac93e` |
| data/market/krx2025/futurecontractcode.csv | 80 | 2353 | `2f3d6c53cd0392800e465a40b8c0375856e427d14b526ee2249fad96ffc1ba71` |

Total: 15806908 bytes (15.07 MiB).
## Why this window is minimal

20 sessions either side of the 2025-05-05 KRX cutover, the low end of the handoff's 20-30: enough for the regime guard to act on every post-cutover session and for both arms to quote a non-trivial number of times on each side. MM has no look-back, so no warm-up. Only the contract the signal trades each day carries book and tape; VN30F2M otherwise contributes only matched prices and closes (read by the naive engine's F1/F2 merge). Depth 1-3 is all the DB holds and all the book walk reads.

## Size flag

Over 3 MiB: L2 depth 1-3 with sizes plus the sized tape is what the queue claims read; 40 sessions is the handoff's floor, so this is irreducible without shortening the window.
