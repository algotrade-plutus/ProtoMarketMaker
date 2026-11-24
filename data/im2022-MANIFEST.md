# Data manifest: ProtoMarketMaker window `im2022`

- Window: 2022-11-17 .. 2023-01-12 (40 sessions; 20 before and 20 from 2022-12-15: VSD initial margin 13% -> 17% on 2022-12-15 (robustness))
- Source: book/tape `archive`, daily bands `db`, via `plutus-simulator/scripts/rivf26_extract.py declared --request` (slices `rivf26/data/mm-im2022-tick/` and `mm-im2022-daily/`; their DATA-MANIFEST.md and request.json carry the untrimmed sha256s)
- Trimmed here to trading hours 08:45:00..14:46:00 for tick/book tables (drops the end-of-day 00:00:00 row); daily tables copied unchanged.
- Prices are VN30F index points (1 point = 100,000 dong per contract).

| file | rows (slice -> repo) | bytes | sha256 |
|---|--:|--:|---|
| data/band/im2022/quote_ceil.parquet | 37 -> 37 | 1363 | `d332f907b79494c86ef37b27b64699c3846fd99e737b10255f5fa979e8c6b95d` |
| data/band/im2022/quote_close.parquet | 80 -> 80 | 1545 | `47bd430db4ff84f69c1313ce58b8647fa5bd58e76e340fb890e9f9e92d666fd5` |
| data/band/im2022/quote_floor.parquet | 37 -> 37 | 1363 | `d67989ad9ad7b1079a20410e2f9d452821af46c577b11ce98ee8569ce3d5aed4` |
| data/band/im2022/quote_reference.parquet | 40 -> 40 | 1372 | `fa6b7d7218ea608b69be8b652c315c702d5ea4e327e9e86f9f4a5010eeec466c` |
| data/band/im2022/quote_ticker.parquet | 2 -> 2 | 1857 | `cb85736298520e33b970656682ef2d27c2e3c693de8aef4827f93ec2e427111b` |
| data/l2/im2022/local_quote_askprice.parquet | 344346 -> 344343 | 1244972 | `b674acbe197e6e73b927dc66f17eaadc12ad34d62b8a7deae1f134f70f85b59c` |
| data/l2/im2022/local_quote_asksize.parquet | 481381 -> 481376 | 1845284 | `e1fdc639a52eca39485d0f26cca635684eafe8845417a4b970f32b108604f19f` |
| data/l2/im2022/local_quote_bidprice.parquet | 345334 -> 345331 | 1253249 | `096cfdc95ee3b2c80a637c2ba03e702f4917135f9f6f31b18ed290ea6b3cdf59` |
| data/l2/im2022/local_quote_bidsize.parquet | 484260 -> 484255 | 1873084 | `18f930251682427607a8859e3ff4d323421dc8382894b416a0583b44b988782d` |
| data/l2/im2022/local_quote_matched.parquet | 151958 -> 151955 | 969510 | `8c73257be751feab9b1ac57133e5f2f83a2dd9a1a239f42d1d3e090473ec1b15` |
| data/l2/im2022/local_quote_total.parquet | 171017 -> 171015 | 1407647 | `d7afe6b4307f71c93382aa880b75acd96df5cc1e123301c6bf7eb01b142387ec` |
| data/market/im2022/futurecontractcode.csv | 80 | 2353 | `749f74982b6d80e0fd74d5e2cd2ceb915c7988bdda0353a3810ea7fad635cfa1` |

Total: 8603599 bytes (8.21 MiB).
## Why this window is minimal

20 sessions either side of the 2022-12-15 VSD IM step 13% -> 17%, so one deposit is margined at both ratios inside one run. Book sizes from the archive (the DB has none before 2023-01-03); daily bands from the DB. Same per-day contract rule and fields as krx2025. ceil/floor are missing (DB and archive) for VN30F2212 on 2022-12-02, 12-05, 12-06: a data gap, not filled.

## Size flag

Over 3 MiB: L2 depth 1-3 with sizes plus the sized tape is what the queue claims read; 40 sessions is the handoff's floor, so this is irreducible without shortening the window.
