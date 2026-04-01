import pandas as pd
import pandas_ta as ta
import yfinance as yf
import FinanceDataReader as fdr
import pyupbit
import re

def fetch_history_data(category, ticker):
    try:
        if any(keyword in category for keyword in ['한국ETF', '국내주식', 'ISA']):
            match = re.search(r'\d{6}', ticker)
            if match:
                return fdr.DataReader(match.group())
                
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
        # 빈 값이 있으면 이전 값으로 채워서 에러 방지 (ffill)
        df_hist['Close'] = pd.to_numeric(df_hist['Close'], errors='coerce').ffill()
        
        rsi = ta.rsi(df_hist['Close'], length=14)
        ema5 = ta.ema(df_hist['Close'], length=5)
        ema20 = ta.ema(df_hist['Close'], length=20)
        ema50 = ta.ema(df_hist['Close'], length=50)
        ema100 = ta.ema(df_hist['Close'], length=100)
        bb = ta.bbands(df_hist['Close'], length=20, std=2)
        
        # 안전하게 값을 꺼내오는 헬퍼 함수
        def get_val(series):
            if series is not None and not series.empty and not pd.isna(series.iloc[-1]):
                return float(series.iloc[-1])
            return 0.0

        # ⭐ 볼린저 밴드 컬럼을 유연하게 찾는 로직 (BBU_20_2.0 에러 해결)
        bb_upper, bb_lower = 0.0, 0.0
        if bb is not None and not bb.empty:
            for col in bb.columns:
                if col.startswith('BBU'): bb_upper = get_val(bb[col])
                elif col.startswith('BBL'): bb_lower = get_val(bb[col])

        res = {
            '현재가($)': float(df_hist['Close'].iloc[-1]),
            'RSI': get_val(rsi),
            'EMA5': get_val(ema5),
            'EMA20': get_val(ema20),
            'EMA50': get_val(ema50),
            'EMA100': get_val(ema100),
            'BB상단': bb_upper,
            'BB하단': bb_lower
        }
        return res
    except Exception as e:
        print(f"지표 계산 중 오류: {e}")
        return {}
