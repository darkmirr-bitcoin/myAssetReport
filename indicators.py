import pandas as pd
import pandas_ta as ta
import yfinance as yf
import FinanceDataReader as fdr
import pyupbit
import re

def fetch_history_data(category, ticker):
    try:
        # 한국 ETF / 국내주식 (ISA 포함)
        if any(keyword in category for keyword in ['한국ETF', '국내주식', 'ISA']):
            match = re.search(r'\d{6}', ticker)
            if match:
                clean_ticker = match.group()
                # 최근 100일치 데이터 (지표 계산용)
                df = fdr.DataReader(clean_ticker)
                return df
                
        elif category == '해외주식':
            return yf.Ticker(ticker).history(period="1y")
            
        elif category == '코인':
            df = pyupbit.get_ohlcv(f"KRW-{ticker}", count=200, interval="day")
            if df is not None:
                df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume'}, inplace=True)
                return df
            else:
                ticker_usd = ticker + '-USD' if not ticker.endswith('-USD') else ticker
                return yf.Ticker(ticker_usd).history(period="1y")
                
    except Exception as e:
        print(f"[{ticker}] 데이터 수집 에러: {e}")
    return pd.DataFrame()

def calculate_indicators(df_hist):
    if df_hist is None or df_hist.empty or len(df_hist) < 20:
        return {}
    
    try:
        df_hist['Close'] = pd.to_numeric(df_hist['Close'], errors='coerce')
        
        # 지표 계산
        rsi = ta.rsi(df_hist['Close'], length=14)
        ema5 = ta.ema(df_hist['Close'], length=5)
        ema20 = ta.ema(df_hist['Close'], length=20)
        ema50 = ta.ema(df_hist['Close'], length=50)
        ema100 = ta.ema(df_hist['Close'], length=100)
        bb = ta.bbands(df_hist['Close'], length=20, std=2)
        
        # 결과 딕셔너리 생성 (시트 컬럼명과 정확히 일치시켜야 함)
        res = {
            '현재가($)': float(df_hist['Close'].iloc[-1]),
            'RSI': float(rsi.iloc[-1]) if rsi is not None else 0,
            'EMA5': float(ema5.iloc[-1]) if ema5 is not None else 0,
            'EMA20': float(ema20.iloc[-1]) if ema20 is not None else 0,
            'EMA50': float(ema50.iloc[-1]) if ema50 is not None else 0,
            'EMA100': float(ema100.iloc[-1]) if ema100 is not None else 0,
            'BB상단': float(bb['BBU_20_2.0'].iloc[-1]) if bb is not None else 0,
            'BB하단': float(bb['BBL_20_2.0'].iloc[-1]) if bb is not None else 0
        }
        return res
    except Exception as e:
        print(f"지표 계산 중 오류: {e}")
        return {}