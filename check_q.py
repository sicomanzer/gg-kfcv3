import yfinance as yf
import sys

# Force UTF-8 for output to handle encoding on Windows nicely or just perform logic check
sys.stdout.reconfigure(encoding='utf-8')

def check_quarterly(ticker):
    print(f"Checking {ticker}...")
    stock = yf.Ticker(ticker)
    try:
        q_fin = stock.quarterly_financials
        if not q_fin.empty:
            print(f"FOUND {ticker} Quarterly Financials:")
            print(q_fin.head(2).index)
        else:
            print(f"NOT FOUND {ticker} No Quarterly Financials.")
    except Exception as e:
        print(f"ERROR {ticker}: {e}")

check_quarterly("AOT.BK")
