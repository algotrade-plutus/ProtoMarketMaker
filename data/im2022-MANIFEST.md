# Data manifest: ProtoMarketMaker window `im2022`

- Window: 2022-11-17 .. 2023-01-12 (40 sessions; 20 before and 20 from 2022-12-15: VSD initial margin 13% -> 17% on 2022-12-15 (robustness))
- Source: book/tape `archive`, daily bands `db`, via `plutus-simulator/scripts/rivf26_extract.py declared --request` (slices `rivf26/data/mm-im2022-tick/` and `mm-im2022-daily/`; their DATA-MANIFEST.md and request.json carry the untrimmed sha256s)
- Trimmed here to trading hours 08:45:00..14:46:00 for tick/book tables (drops the end-of-day 00:00:00 row); daily tables copied unchanged.
- Prices are VN30F index points (1 point = 100,000 dong per contract).

| file | rows (slice -> repo) | bytes | sha256 |
|---|--:|--:|---|
| data/band/im2022/quote_ceil.parquet | 73 -> 73 | 1531 | `9d24c5787199d16ad2804da1d63503f11121850ef40ba77864735039117eaafa` |
| data/band/im2022/quote_close.parquet | 80 -> 80 | 1545 | `47bd430db4ff84f69c1313ce58b8647fa5bd58e76e340fb890e9f9e92d666fd5` |
| data/band/im2022/quote_floor.parquet | 73 -> 73 | 1541 | `f140b9e852ea45f7e3f82c61376528e3672a4829f7f1c548dd75de6efa36aa9e` |
| data/band/im2022/quote_reference.parquet | 80 -> 80 | 1543 | `6c3db4a9df382fa3d64df9e1e0b79457e80be7bc35a195c1968a7fc5b6913c1c` |
| data/band/im2022/quote_ticker.parquet | 4 -> 4 | 1882 | `ea769f7692fe749491f6f6bf67df0ea08c8dd4138e1c5df66efee8edd16106c4` |
| data/l2/im2022/local_quote_askprice.parquet | 349753 -> 349750 | 1265203 | `35ec97596f65dd3fe56c2842764fefe3ffe4d1cc044e709de75de37665f6f0b2` |
| data/l2/im2022/local_quote_asksize.parquet | 489017 -> 489012 | 1858142 | `2815292d2b450f2aa2fa2d3c38e2afd29fea8b922cac413eaef2ac14774b9f21` |
| data/l2/im2022/local_quote_bidprice.parquet | 351002 -> 350999 | 1272259 | `83c7390cc6ee9565f1c119216d05ead4aac4aa6e0c1252ca690dc2f71da4da1e` |
| data/l2/im2022/local_quote_bidsize.parquet | 492563 -> 492558 | 1892789 | `4f6ac362afa9646ae2bf9162bb074964d294e325d3b9587b7f64d5fbcedf3fc6` |
| data/l2/im2022/local_quote_matched.parquet | 151958 -> 151955 | 969510 | `8c73257be751feab9b1ac57133e5f2f83a2dd9a1a239f42d1d3e090473ec1b15` |
| data/l2/im2022/local_quote_total.parquet | 183139 -> 183137 | 1454648 | `f10e5fa2b001ad648c6bdafed87a16b694cf94dbad3fa55836cd1e525ae111c8` |
| data/market/im2022/futurecontractcode.csv | 80 | 2353 | `749f74982b6d80e0fd74d5e2cd2ceb915c7988bdda0353a3810ea7fad635cfa1` |

Total: 8722946 bytes (8.32 MiB).

## Why this window is minimal

20 sessions either side of the 2022-12-15 VSD IM step 13% -> 17%, so one deposit is margined at both ratios inside one run. Book sizes from the archive (the DB has none before 2023-01-03); daily bands from the DB. Same per-day contract rule and fields as krx2025. ceil/floor are missing (DB and archive) for VN30F2212 on 2022-12-02, 12-05, 12-06 and for VN30F2301 on 2022-12-01..12-06 (reference is present): a data gap, not filled. Bands cover both VN30F1M and VN30F2M on every session, so every roll day carries both contracts' bands.

## Size flag

Over 3 MiB: L2 depth 1-3 with sizes plus the sized tape is what the queue claims read; 40 sessions is the handoff's floor, so this is irreducible without shortening the window. The growth over the first extraction (+0.11 MiB im2022, +0.52 MiB krx2025) comes only from the roll days and the session after each roll, where book and sized tape now cover both contracts A holds or trades (see ``touched``); bands grew by the F2M rows.
