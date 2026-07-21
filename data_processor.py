import pandas as pd
import yfinance as yf
import datetime
import pytz
import holidays
from indicators import fetch_history_data, calculate_indicators

def check_market_open(category):
    """해당 시장이 오늘(현지 시간 기준) 열리는지 주말/공휴일을 확인하는 함수"""
    if category == '코인':
        return True # 코인은 365일 무휴
        
    today_kr = datetime.datetime.now(pytz.timezone('Asia/Seoul'))
    today_ny = datetime.datetime.now(pytz.timezone('America/New_York'))
    
    if category in ['연금저축', '한국ETF', '국내주식']:
        # 주말(토=5, 일=6) 이거나 한국 공휴일이면 휴장
        if today_kr.weekday() >= 5 or today_kr.strftime('%Y-%m-%d') in holidays.KR(years=today_kr.year):
            return False
        return True
        
    elif category == '해외주식':
        # 주말 이거나 미국 공휴일이면 휴장
        if today_ny.weekday() >= 5 or today_ny.strftime('%Y-%m-%d') in holidays.US(years=today_ny.year):
            return False
        return True
        
    return True

def get_exchange_rate():
    """야후 파이낸스에서 실시간 USD/KRW 환율을 가져오는 함수"""
    try:
        rate = float(yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1])
        return rate
    except:
        return 1350.0 # API 실패 시 기본값

def process_asset_df(df, category, is_usd=False, is_open=True):
    """각 시트의 데이터를 읽어와서 지표를 붙이고, 평가손익을 계산하는 핵심 함수"""
    if df.empty: return df, 0.0, 0.0
    
    df = df.loc[:, ~df.columns.duplicated()].copy()
    rename_dict = {}
    for col in df.columns:
        col_str = str(col).strip()
        if '매수가' in col_str and '매수가' not in rename_dict.values(): rename_dict[col] = '매수가'
        elif '현재가' in col_str and '현재가' not in rename_dict.values(): rename_dict[col] = '현재가'
        elif '수량' in col_str and '수량' not in rename_dict.values(): rename_dict[col] = '수량'
        elif ('티커' in col_str or '종목코드' in col_str) and '티커' not in rename_dict.values(): rename_dict[col] = '티커'
        
    df.rename(columns=rename_dict, inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    if '매수가' not in df.columns: df['매수가'] = 0.0
    if '수량' not in df.columns: df['수량'] = 0.0
    if '티커' not in df.columns: df['티커'] = ''

    # [핵심 수정 1] 콤마(,) 완벽 제거! (기존 데이터 읽을 때 에러 방지)
    df['매수가'] = pd.to_numeric(df['매수가'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0.0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0.0)
    
    num_cols = ['현재가', 'RSI', 'EMA5', 'EMA20', 'EMA50', 'EMA100', 'BB상단', 'BB하단', 'MACD', 'MACD히스토그램', 'OBV', '거래량강도(%)']
    for col in num_cols:
        if col not in df.columns: df[col] = 0.0
        # 구글 시트에 있는 '현재가'에 콤마가 있어도 0원이 되지 않도록 안전하게 변환
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0.0).astype(float)

    text_cols = ['추세상태', 'OBV추세']
    for col in text_cols:
        if col not in df.columns: df[col] = ''
        df[col] = df[col].astype(str)

    if not is_open:
        print(f"💤 [{category}] 현지 시장 휴일입니다. 기존 시트 데이터를 유지합니다.")
        
    # [핵심 수정 2] 휴장일이더라도 현재가가 0원이면(주말에 새로 샀을 때 등) 전 영업일 데이터를 강제로 한 번 긁어옴!
    for index, row in df.iterrows():
        ticker = str(row.get('티커', '')).strip()
        if not ticker or ticker == 'nan': continue
            
        if is_open or df.at[index, '현재가'] == 0.0:
            df_hist = fetch_history_data(category, ticker)
            ind_data = calculate_indicators(df_hist)
            
            if ind_data:
                current_price = ind_data.pop('현재가($)', 0.0)
                df.at[index, '현재가'] = round(float(current_price), 2) if is_usd else round(float(current_price), 0)
                
                for col, val in ind_data.items():
                    if col in df.columns:
                        df.at[index, col] = val
            else:
                # 🚀 [추가된 방어 로직] SPCX처럼 상장된 지 얼마 안 돼서 장기 지표(EMA100 등) 계산에 실패하더라도 현재가는 무조건 긁어오기!
                try:
                    if df_hist is not None and not df_hist.empty:
                        if 'Close' in df_hist.columns:
                            current_price = float(df_hist['Close'].iloc[-1])
                        elif 'close' in df_hist.columns:
                            current_price = float(df_hist['close'].iloc[-1])
                        else:
                            current_price = 0.0
                        
                        if current_price > 0:
                            df.at[index, '현재가'] = round(current_price, 2) if is_usd else round(current_price, 0)
                            print(f"⚠️ [{ticker}] 과거 데이터 부족으로 보조지표는 생략하고 현재가만 가져왔습니다.")
                except Exception as e:
                    print(f"❌ [{ticker}] 현재가 방어 로직 실패: {e}")


    # 평가금액 및 총합 계산
    if is_usd:
        df['평가금액(USD)'] = (df['현재가'] * df['수량']).round(2)
        df['평가손익(USD)'] = ((df['현재가'] - df['매수가']) * df['수량']).round(2)
        invest_total = float((df['매수가'] * df['수량']).sum())
        eval_total = float(df['평가금액(USD)'].sum())
    else:
        df['평가금액(KRW)'] = (df['현재가'] * df['수량']).round(0)
        df['평가손익(KRW)'] = ((df['현재가'] - df['매수가']) * df['수량']).round(0)
        invest_total = float((df['매수가'] * df['수량']).sum())
        eval_total = float(df['평가금액(KRW)'].sum())
        
    df['수익률'] = df.apply(lambda x: float((x['현재가'] - x['매수가']) / x['매수가']) if x['매수가'] > 0 else 0.0, axis=1)
    
    return df, invest_total, eval_total
