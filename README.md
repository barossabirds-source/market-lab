# Market Lab

Paper-trading research lab for systematic US ETF strategies.

## Version 1
- ETF universe: SPY, QQQ, IWM, DIA, XLK, XLF, XLE, XLI, XLV, XLY, XLP, XLU
- Pair discovery from correlations
- Z-score mean-reversion signals
- Cost-aware paper trading
- Dashboard for P&L, drawdown, win rate and open positions

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Safety
This project is research software. It does not place live orders.
