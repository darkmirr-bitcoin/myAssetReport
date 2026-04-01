import pandas as pd
import pandas_ta as ta
import yfinance as yf
import FinanceDataReader as fdr
import pyupbit
import re

def fetch_history_data(category, ticker):
    """카테고리에 맞춰 알맞은 거래소/API에서 종목의 과거 차트 데이터를 긁어오는 함수"""
    try:
        # 국내 주식, ETF, 연금저축은 fdr (FinanceDataReader) 사용 (숫자 6자리 추출)
        if any(keyword in category for keyword in ['한국ETF', '국내주식', 'ISA', '연금저축']):
            match = re.search(r'\d{6}', ticker)
            if match:
                return fdr.DataReader(match.group())
                
        # 미국 주식은 야후 파이낸스(yfinance) 사용
        elif category == '해외주식':
            return yf.Ticker(ticker).history(period="1y")
            
        # 코인은 1차로 업비트 시도, 실패하면 야후에서 달러 기준 코인 탐색
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
    """가져온 차트 데이터를 바탕으로 RSI, MACD 등의 기술적 지표를 계산하는 함수"""
    # 과거 데이터가 30일치 이하면 계산 불가로 패스
    if df_hist is None or df_hist.empty or len(df_hist) < 30:
        return {}
    
    try:
        # 중간에 거래정지 등으로 빈칸(NaN)이 있으면 이전 날짜 값으로 덮어씀 (ffill)
        df_hist['Close'] = pd.to_numeric(df_hist['Close'], errors='coerce').ffill()
        df_hist['Volume'] = pd.to_numeric(df_hist['Volume'], errors='coerce').ffill()
        
        # pandas_ta 라이브러리로 기본 지표들 뚝딱 계산
        rsi = ta.rsi(df_hist['Close'], length=14)
        ema5 = ta.ema(df_hist['Close'], length=5)
        ema20 = ta.ema(df_hist['Close'], length=20)
        ema50 = ta.ema(df_hist['Close'], length=50)
        ema100 = ta.ema(df_hist['Close'], length=100)
        bb = ta.bbands(df_hist['Close'], length=20, std=2)
        macd_df = ta.macd(df_hist['Close'], fast=12, slow=26, signal=9)
        obv = ta.obv(df_hist['Close'], df_hist['Volume'])
        
        # 거래강도 (최근 20일 평균 대비 오늘 거래량의 비율)
        sma_vol = df_hist['Volume'].rolling(window=20).mean()
        vol_strength = (df_hist['Volume'] / sma_vol) * 100

        def get_val(series, round_n=0):
            """시리즈 데이터 맨 끝(오늘) 값을 안전하게 뽑아주는 헬퍼 함수"""
            if series is not None and not series.empty and not pd.isna(series.iloc[-1]):
                val = float(series.iloc[-1])
                return round(val, round_n) if round_n > 0 else round(val)
            return 0.0

        # 볼린저밴드 컬럼명 유연하게 캐치
        bb_upper, bb_lower = 0.0, 0.0
        if bb is not None and not bb.empty:
            for col in bb.columns:
                if col.startswith('BBU'): bb_upper = get_val(bb[col])
                elif col.startswith('BBL'): bb_lower = get_val(bb[col])

        # 추세 판별 (현재가가 20일 이평선 위에 있으면 상승)
        current_price = float(df_hist['Close'].iloc[-1])
        current_ema20 = get_val(ema20, 2)
        trend_status = "▲ 상승" if current_price > current_ema20 else "▼ 하락"

        # OBV 추세 판별 (현재 OBV가 5일 평균 OBV를 뚫었으면 돌파)
        obv_sma5 = obv.rolling(window=5).mean()
        obv_trend = "🚩 돌파" if get_val(obv) > get_val(obv_sma5) else "➖ 정체"

        # MACD 히스토그램 컬럼 찾기
        macd_h = 0.0
        if macd_df is not None:
            h_col = [c for c in macd_df.columns if c.startswith('MACDh')]
            if h_col: macd_h = get_val(macd_df[h_col[0]], 2)

        # 구글 시트의 헤더 텍스트와 100% 일치하는 딕셔너리로 반환
        res = {
            '현재가($)': current_price,
            '추세상태': trend_status,
            'RSI': get_val(rsi),
            'EMA5': get_val(ema5),
            'EMA20': current_ema20,
            'EMA50': get_val(ema50),
            'EMA100': get_val(ema100),
            'BB상단': bb_upper,
            'BB하단': bb_lower,
            'MACD': get_val(macd_df['MACD_12_26_9'] if macd_df is not None else None, 2),
            'MACD히스토그램': macd_h,
            'OBV': get_val(obv),
            'OBV추세': obv_trend,
            '거래량강도(%)': get_val(vol_strength)
        }
        return res
    except Exception as e:
        print(f"지표 계산 오류: {e}")
        return {}
