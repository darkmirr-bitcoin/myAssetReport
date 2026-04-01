import pandas as pd
import pandas_ta as ta
import yfinance as yf
import FinanceDataReader as fdr
import pyupbit
import re

def fetch_history_data(category, ticker):
    try:
        if any(keyword in category for keyword in ['한국ETF', '국내주식', 'ISA', '연금저축']):
            match = re.search(r'\d{6}', ticker)
            if match: return fdr.DataReader(match.group())
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
    if df_hist is None or df_hist.empty or len(df_hist) < 30: # 데이터가 충분해야 지표가 나옴
        return {}
    
    try:
        df_hist['Close'] = pd.to_numeric(df_hist['Close'], errors='coerce').ffill()
        df_hist['Volume'] = pd.to_numeric(df_hist['Volume'], errors='coerce').ffill()
        
        # 기본 지표 계산
        rsi = ta.rsi(df_hist['Close'], length=14)
        ema20 = ta.ema(df_hist['Close'], length=20)
        macd_df = ta.macd(df_hist['Close'], fast=12, slow=26, signal=9)
        obv = ta.obv(df_hist['Close'], df_hist['Volume'])
        
        # 거래강도 (20일 평균 거래량 대비 현재 거래량)
        sma_vol = df_hist['Volume'].rolling(window=20).mean()
        vol_strength = (df_hist['Volume'] / sma_vol) * 100

        def get_val(series, round_n=0):
            if series is not None and not series.empty and not pd.isna(series.iloc[-1]):
                return round(float(series.iloc[-1]), round_n)
            return 0.0

        # 추세 판별 로직
        current_price = float(df_hist['Close'].iloc[-1])
        current_ema20 = get_val(ema20, 2)
        trend_status = "▲ 상승" if current_price > current_ema20 else "▼ 하락"

        # OBV 추세 판별 (5일 이동평균 돌파 여부)
        obv_sma5 = obv.rolling(window=5).mean()
        obv_trend = "🚩 돌파" if get_val(obv) > get_val(obv_sma5) else "➖ 정체"

        # MACD 히스토그램 추출 (컬럼명 유연하게 매칭)
        macd_h = 0.0
        if macd_df is not None:
            h_col = [c for c in macd_df.columns if c.startswith('MACDh')]
            if h_col: macd_h = get_val(macd_df[h_col[0]], 2)

       res = {
            '현재가($)': current_price,
            '추세상태': trend_status,
            'RSI': get_val(rsi),
            'EMA20': current_ema20,
            'MACD': get_val(macd_df['MACD_12_26_9'] if macd_df is not None else None, 2),
            'MACD히스토그램': macd_h,       # 띄어쓰기 없앰
            'OBV': get_val(obv),
            'OBV추세': obv_trend,          # 띄어쓰기 없앰
            '거래량강도(%)': get_val(vol_strength) # '거래강도'를 '거래량강도'로 변경
        }
        return res
    except Exception as e:
        print(f"지표 계산 오류: {e}")
        return {}
