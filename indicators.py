import pandas as pd
import pandas_ta as ta
import yfinance as yf
import FinanceDataReader as fdr
import pyupbit
import re

def fetch_history_data(category, ticker):
    try:
        if '한국ETF' in category or '국내주식' in category or 'ISA' in category:
            match = re.search(r'\d{6}', ticker)
            if match:
                return fdr.DataReader(match.group(), "2023-01-01")
                
        elif category == '해외주식':
            return yf.Ticker(ticker).history(period="1y")
            
        elif category == '코인':
            df = pyupbit.get_ohlcv(f"KRW-{ticker}", count=200)
            if df is not None:
                # pandas-ta가 인식할 수 있게 컬럼명 영문 첫글자 대문자로 변경
                df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume'}, inplace=True)
                return df
            else:
                ticker_usd = ticker + '-USD' if not ticker.endswith('-USD') else ticker
                return yf.Ticker(ticker_usd).history(period="1y")
                
    except Exception as e:
        print(f"[{ticker}] 데이터 수집 실패: {e}")
    return pd.DataFrame()

def calculate_indicators(df_hist):
    # 데이터가 너무 적으면 계산 안 함
    if df_hist is None or df_hist.empty or len(df_hist) < 20:
        return {}
    
    df_hist['Close'] = df_hist['Close'].astype(float)
    
    # 지표 계산 (pandas-ta 활용)
    rsi = ta.rsi(df_hist['Close'], length=14)
    ema5 = ta.ema(df_hist['Close'], length=5)
    ema20 = ta.ema(df_hist['Close'], length=20)
    ema50 = ta.ema(df_hist['Close'], length=50)
    ema100 = ta.ema(df_hist['Close'], length=100)
    bb = ta.bbands(df_hist['Close'], length=20, std=2)
    macd = ta.macd(df_hist['Close'])
    
    if 'Volume' in df_hist.columns:
        obv = ta.obv(df_hist['Close'], df_hist['Volume'])
    else:
        obv = pd.Series([0]*len(df_hist))

    # 최신(마지막 행) 값만 뽑아서 딕셔너리로 반환
    return {
        '현재가($)': df_hist['Close'].iloc[-1],
        'RSI': rsi.iloc[-1] if rsi is not None else 0,
        'EMA5': ema5.iloc[-1] if ema5 is not None else 0,
        'EMA20': ema20.iloc[-1] if ema20 is not None else 0,
        'EMA50': ema50.iloc[-1] if ema50 is not None else 0,
        'EMA100': ema100.iloc[-1] if ema100 is not None else 0,
        'BB상단': bb['BBU_20_2.0'].iloc[-1] if bb is not None and 'BBU_20_2.0' in bb.columns else 0,
        'BB하단': bb['BBL_20_2.0'].iloc[-1] if bb is not None and 'BBL_20_2.0' in bb.columns else 0,
        'MACD': macd['MACD_12_26_9'].iloc[-1] if macd is not None and 'MACD_12_26_9' in macd.columns else 0,
        'OBV': obv.iloc[-1] if obv is not None else 0
    }