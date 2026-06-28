![Static Badge](https://img.shields.io/badge/PLUTUS-75%25-darkgreen)
![Static Badge](https://img.shields.io/badge/PLUTUS-Sample-darkblue)
![Static Badge](https://img.shields.io/badge/PLUTUS-PROTO-%23880A88) 

# PROTO:Market Maker

## Place bid-ask base on inventory
> Place limit order in two sides base on current inventory quantity

## Abstract
In this project, we utilize inventory quantities to simultaneously place both bid and ask orders. The prices of these orders are adjusted dynamically in response to changes in the matched market price. Forced sale scenarios and asset expiration dates are accounted for by incorporating additional fees into the asset's valuation.

## Introduction
In market making, one common approach to liquidity provision involves simultaneously placing bid and ask orders based on the current inventory levels held by the market maker. This strategy dynamically adjusts order prices in response to changes in the matched market price, allowing the market maker to maintain balanced exposure while capturing the bid-ask spread. The positions are held overnight.

## Hypothesis
We place bid and ask price with our formula:
- $$bid = (price - step) - step * max(inventory, 0) * 0.02$$
- $$ask = (price + step) - step * min(inventory, 0) * 0.02$$

The step size should exceed the sum of the transaction fee and slippage. Bid and ask prices are updated either every 15 seconds or upon the execution of a position.

## Data
- Data source: Algotrade database
- Data period: from 2022-01-01 to 2025-04-29
- Each sell or buy side will be charge 0.4 / 2 fee.
### Data Preparation
#### Daily closing price data
- The daily close price, bid, ask and tick price are collected from Algotrade database using SQL queries. 
- The data is collected using the script `data_loader.py` 
- The data is stored in the `data/is/` and `data/os/` folders. 

## Setup & run

```bash
uv sync                 # create the env from the committed uv.lock
uv run pmm-load-data    # pull data (needs DB secrets in .env)
uv run pmm-optimize     # optimization study
uv run pmm-backtest     # in-sample backtest
uv run pmm-evaluate     # out-of-sample evaluation
```

Dependencies are pinned by the committed `uv.lock` (currently on the latest
major lines — pandas 3.x, numpy 2.x); `uv sync` restores them exactly.

## Reproducibility (PLUTUS Standard v2025)

This repo follows the **PLUTUS Standard v2025** nine-step taxonomy and ships a
`.plutus/manifest.yaml` that declares the environment, data sources, steps, and
expected metrics. Results are verified in an isolated Docker container with
[plutus-verify](https://github.com/algotrade-plutus/plutus-verify) **v0.5.0**,
installed straight from the public release wheel — no build-from-source needed:

```bash
# Requires Docker running and Python >= 3.11
python -m venv .plutus-venv && source .plutus-venv/bin/activate
pip install "plutus-verify[runner] @ https://github.com/algotrade-plutus/plutus-verify/releases/download/v0.5.0/plutus_verify-0.5.0-py3-none-any.whl"

plutus check .     # build -> run each step in-container -> compare vs baseline
```

The `[runner]` extra brings Docker, repo2docker, and gdown, so `plutus check`
builds the image, downloads the dataset from the declared Google Drive source,
installs this package and runs each step's console script in-container, then
compares the produced metrics and charts against the committed baseline in
`.plutus/expected/`. Exit code `0` = reproduced (within tolerance), `1` =
partial, `2` = failed.

## Implementation
### Environment Setup
1. (OPTIONAL) Create `.env` file in the root directory of the project and fill in the required information. The `.env` file is used to store environment variables that are used in the project. The following is an example of a `.env` file:
```env
DB_NAME=<database name>
DB_USER=<database user name>
DB_PASSWORD=<database password>
DB_HOST=<host name or IP address>
DB_PORT=<database port>
```
### Data Preparation
#### Option 1. Download from Google Drive
Data can be download directly from [Google Drive](https://drive.google.com/drive/folders/181d7JcfHilIvviLgEuaDt2VqwZLYnYUF?usp=sharing). The data files are stored in the `data` folder with the following folder structure:
```
data
├── is
│   ├── VN30F1M_data.csv
│   └── VN30F2M_data.csv
└── os
    ├── VN30F1M_data.csv
    └── VN30F2M_data.csv
```
You should place this folder to the current ```PYTHONPATH``` for the following steps.
#### Option 2. Run codes to collect data
To collect data from database, run this command below in the root directory:
```bash
uv run pmm-load-data
```
The result will be stored in the `data/is/` and `data/os/`
### In-sample Backtesting
Specify period and parameters in `parameter/backtesting_parameter.json` file.
```bash
uv run pmm-backtest
```
The results are stored in the `result/backtest/` folder.

### Optimization
To run the optimization, execute the command in the root folder:
```bash
uv run pmm-optimize
```
The optimization parameter are store in `parameter/optimization_parameter.json`. After optimizing, the optimized parameters are stored in `parameter/optimized_parameter.json`.

### Out-of-sample Backtesting
To run the out-of-sample backtesting results, execute this command
```bash
uv run pmm-evaluate
```
[TODO: change the name of optimization folder to out-of-sample-backtesting or something like that]: #
The script will get value from `parameter/optimized_parameter.json` to execute. The results are stored in the `result/optimization` folder.

## In-sample Backtesting
Running the in-sample backtesting by execute the command:
```bash
uv run pmm-backtest
```
### Evaluation Metrics
- Backtesting results are stored in the `result/backtest/` folder. 
- Used metrics: 
  - Sharpe ratio (SR)
  - Sortino ratio (SoR)
  - Maximum drawdown (MDD)
- We use a risk-free rate of 6% per annum, equivalent to approximately 0.023% per day, as a benchmark for evaluating the Sharpe Ratio (SR) and Sortino Ratio (SoR).
### Parameters
### In-sample Backtesting Result
- The backtesting results are constructuted from 2022-01-01 to 2023-01-01.
```
| Metric                 | Value                              |
|------------------------|------------------------------------|
| Sharpe Ratio           | 0.9516                             |
| Sortino Ratio          | 1.3490                             |
| Maximum Drawdown (MDD) | -0.2010                            |
| HPR (%)                | 29.92                              |
| Monthly return (%)     | 1.81                               |
| Annual return (%)      | 17.10                              |
```
- The HPR chart. The chart is located at: `result/backtest/hpr.svg`
![HPR chart with VNINDEX benchmark](result/backtest/hpr.svg)
- Drawdown chart. The chart is located at `result/backtest/drawdown.svg`
![Drawdown chart](result/backtest/drawdown.svg)
- Daily inventory. The chart is located at `result/backtest/inventory.svg`
![Inventory chart](result/backtest/inventory.svg)

## Optimization
The configuration of optimization is stored in `parameter/optimization_parameter.json` you can adjust the range of parameters. Random seed is used for reconstructing the optimization process. The optimized parameter is stored in `parameter/optimized_parameter.json`
The optimization process can be reproduced by executing the command:
```bash
uv run pmm-optimize
```
The currently found optimized parameters with the seed `2025` are:
```json
{
    "step": 3.1
}
```
## Out-of-sample Backtesting
- Specify the out-sample period and parameters in `parameter/backtesting_parameter.json` file.
- The out-sample data is loaded on the previous step. Refer to section [Data](#data) for more information.
- To evaluate the out-sample data run the command below
```bash
uv run pmm-evaluate
```
### Out-of-sample Backtesting Result
- The out-sample backtesting results are constructuted from 2024-01-02 to 2025-04-29.
```
| Metric                 | Value                              |
|------------------------|------------------------------------|
| Sharpe Ratio           | 0.0815                             |
| Sortino Ratio          | 0.1183                             |
| Maximum Drawdown (MDD) | -0.1028                            |
| HPR (%)                | 8.02                               |
| Monthly return (%)     | 0.57                               |
| Annual return (%)      | 6.21                               |
```
- The HPR chart. The chart is located at `result/optimization/hpr.svg`.
![HPR chart with VNINDEX benchmark](result/optimization/hpr.svg)
- Drawdown chart. The chart is located at `result/optimization/drawdown.svg`.
![Drawdown chart](result/optimization/drawdown.svg)
- Daily inventory. The chart is located at `result/optimization/inventory.svg`
![Inventory chart](result/optimization/inventory.svg)

## Reference
[1] ALGOTRADE, Algorithmic Trading Theory and Practice - A Practical Guide with Applications on the Vietnamese Stock Market, 1st ed. DIMI BOOK, 2023, pp. 52–53. Accessed: May 12, 2025. [Online]. Available: [Link](https://hub.algotrade.vn/knowledge-hub/market-making-strategy/)
