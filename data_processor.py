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
    
    # 1. 중복 열 방어 및 이름 통일
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

    df['매수가'] = pd.to_numeric(df['매수가'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0.0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0.0)
    
    # 2. 지표 컬럼 타입 세팅
    num_cols = ['현재가', 'RSI', 'EMA5', 'EMA20', 'EMA50', 'EMA100', 'BB상단', 'BB하단', 'MACD', 'MACD히스토그램', 'OBV', '거래량강도(%)']
    for col in num_cols:
        if col not in df.columns: df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)

    text_cols = ['추세상태', 'OBV추세']
    for col in text_cols:
        if col not in df.columns: df[col] = ''
        df[col] = df[col].astype(str)

    # 3. 휴장일이 아닐 때만 API를 호출하여 데이터 업데이트!
    if is_open:
        for index, row in df.iterrows():
            ticker = str(row.get('티커', '')).strip()
            if not ticker or ticker == 'nan': continue
                
            df_hist = fetch_history_data(category, ticker)
            ind_data = calculate_indicators(df_hist)
            
            if ind_data:
                current_price = ind_data.pop('현재가($)', 0.0)
                df.at[index, '현재가'] = round(float(current_price), 2) if is_usd else round(float(current_price), 0)
                
                for col, val in ind_data.items():
                    if col in df.columns:
                        df.at[index, col] = val
    else:
        print(f"💤 [{category}] 현지 시장 휴일입니다. API 호출을 생략하고 기존 시트 데이터를 유지합니다.")

    # 4. 평가금액 및 총합 계산 (휴장일이어도 기존 가격 * 현재 수량 * 환율로 KST 자산은 계속 업데이트 됨)
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

def get_exchange_rate():
    """야후 파이낸스에서 실시간 USD/KRW 환율을 가져오는 함수"""
    try:
        rate = float(yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1])
        return rate
    except:
        return 1350.0 # API 실패 시 기본값

def process_asset_df(df, category, is_usd=False):
    """각 시트의 데이터를 읽어와서 지표를 붙이고, 평가손익을 계산하는 핵심 함수"""
    if df.empty: return df, 0.0, 0.0
    
    # 1. 중복 열 방어 및 이름 통일 (시트 헤더가 꼬여도 방어함)
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

    # 필수 컬럼이 없으면 0.0으로 뚫어두기
    if '매수가' not in df.columns: df['매수가'] = 0.0
    if '수량' not in df.columns: df['수량'] = 0.0
    if '티커' not in df.columns: df['티커'] = ''

    # 문자열에 섞인 콤마(,)나 기호 빼고 순수 숫자로 변환
    df['매수가'] = pd.to_numeric(df['매수가'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0.0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0.0)
    
    # 2. 지표가 들어갈 컬럼들 타입 세팅 (숫자는 float, 텍스트는 str)
    num_cols = ['현재가', 'RSI', 'EMA5', 'EMA20', 'EMA50', 'EMA100', 'BB상단', 'BB하단', 'MACD', 'MACD히스토그램', 'OBV', '거래량강도(%)']
    for col in num_cols:
        if col not in df.columns: df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)

    text_cols = ['추세상태', 'OBV추세']
    for col in text_cols:
        if col not in df.columns: df[col] = ''
        df[col] = df[col].astype(str)

    # 3. 각 종목별로 과거 데이터를 가져와서 지표 계산 후 병합
    for index, row in df.iterrows():
        ticker = str(row.get('티커', '')).strip()
        if not ticker or ticker == 'nan': continue
            
        df_hist = fetch_history_data(category, ticker)
        ind_data = calculate_indicators(df_hist)
        
        if ind_data:
            current_price = ind_data.pop('현재가($)', 0.0)
            df.at[index, '현재가'] = round(float(current_price), 2) if is_usd else round(float(current_price), 0)
            
            for col, val in ind_data.items():
                if col in df.columns:
                    df.at[index, col] = val

    # 4. JSON 에러 방지를 위해 총합을 계산할 때 순수 float으로 강제 변환
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
