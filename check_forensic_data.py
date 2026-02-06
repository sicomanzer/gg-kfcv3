import yfinance as yf
import pandas as pd

ticker = "CPALL.BK"
stock = yf.Ticker(ticker)

print(f"--- Balance Sheet Index ({ticker}) ---")
try:
    print(stock.balance_sheet.index.tolist())
except Exception as e:
    print(e)
    
print(f"\n--- Financials Index ({ticker}) ---")
try:
    print(stock.financials.index.tolist())
except Exception as e:
    print(e)

print(f"\n--- Cash Flow Index ({ticker}) ---")
try:
    print(stock.cashflow.index.tolist())
except Exception as e:
    print(e)
