import yfinance as yf
import concurrent.futures
import time

tickers = ["ADVANC.BK", "AOT.BK", "CPALL.BK", "PTT.BK", "KBANK.BK"] * 5  # 25 requests

def fetch(t):
    try:
        s = yf.Ticker(t)
        return s.info['currentPrice']
    except Exception as e:
        return str(e)

print("Starting burst requests...")
start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(fetch, tickers))
    
for t, r in zip(tickers, results):
    print(f"{t}: {r}")
    
print(f"Time: {time.time() - start:.2f}s")
