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
        df_hist['Volume'] = pd.to_numeric(df_hist['Volume'], errors='coerce').ffill() # Volume 데이터도 에러 방지용 추가
        
        # 기존 지표
        rsi = ta.rsi(df_hist['Close'], length=14)
        ema5 = ta.ema(df_hist['Close'], length=5)
        ema20 = ta.ema(df_hist['Close'], length=20)
        ema50 = ta.ema(df_hist['Close'], length=50)
        ema100 = ta.ema(df_hist['Close'], length=100)
        bb = ta.bbands(df_hist['Close'], length=20, std=2)
        
        # ⭐ 신규 지표 추가 (MACD, OBV, 거래강도)
        macd_df = ta.macd(df_hist['Close'], fast=12, slow=26, signal=9)
        obv = ta.obv(df_hist['Close'], df_hist['Volume'])
        sma_volume = df_hist['Volume'].rolling(window=20).mean()
        vol_strength = (df_hist['Volume'] / sma_volume) * 100
        
        # ⭐ 소수점 싹 날리는 헬퍼 함수로 변경 (round 처리)
        def get_val(series):
            if series is not None and not series.empty and not pd.isna(series.iloc[-1]):
                return round(float(series.iloc[-1]), 0) # 여기서 0자리로 반올림해서 소수점 제거!
            return 0.0

        # 볼린저 밴드 컬럼 유연하게 찾기
        bb_upper, bb_lower = 0.0, 0.0
        if bb is not None and not bb.empty:
            for col in bb.columns:
                if col.startswith('BBU'): bb_upper = get_val(bb[col])
                elif col.startswith('BBL'): bb_lower = get_val(bb[col])
                
        # MACD 컬럼 유연하게 찾기
        macd_val = 0.0
        if macd_df is not None and not macd_df.empty:
            for col in macd_df.columns:
                if col.startswith('MACD_'): 
                    macd_val = get_val(macd_df[col])
                    break

        # 결과 딕셔너리
        res = {
            '현재가($)': float(df_hist['Close'].iloc[-1]), # 현재가는 달러/원화 소수점 유지가 필요할 수 있어서 남겨둠
            'RSI': get_val(rsi),
            'EMA5': get_val(ema5),
            'EMA20': get_val(ema20),
            'EMA50': get_val(ema50),
            'EMA100': get_val(ema100),
            'BB상단': bb_upper,
            'BB하단': bb_lower,
            'MACD': macd_val,
            'OBV': get_val(obv),
            '거래강도(%)': get_val(vol_strength)
        }
        return res
    except Exception as e:
        print(f"지표 계산 중 오류: {e}")
        return {}
