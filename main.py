import pandas as pd
import yfinance as yf
from datetime import datetime
from google_sheet import GoogleSheetManager
from indicators import fetch_history_data, calculate_indicators
# from telegram_bot import send_telegram_message # 필요시 주석 해제

def get_exchange_rate():
    try:
        rate = float(yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1])
        return rate
    except:
        return 1350.0

# 공통 데이터 처리 및 지표 업데이트 함수
def process_asset_df(df, category, is_usd=False):
    if df.empty: return df, 0.0, 0.0
    
    # [핵심 방어 1] 구글 시트에 중복된 열 이름이 있으면 첫 번째만 남기고 전부 무시 (Series 덩어리 생성 방지)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    
    rename_dict = {}
    for col in df.columns:
        col_str = str(col).strip()
        if '매수가' in col_str and '매수가' not in rename_dict.values(): rename_dict[col] = '매수가'
        elif '현재가' in col_str and '현재가' not in rename_dict.values(): rename_dict[col] = '현재가'
        elif '수량' in col_str and '수량' not in rename_dict.values(): rename_dict[col] = '수량'
        elif ('티커' in col_str or '종목코드' in col_str) and '티커' not in rename_dict.values(): rename_dict[col] = '티커'
        
    df.rename(columns=rename_dict, inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy() # 이름 바꾼 후에도 중복 한 번 더 제거

    if '매수가' not in df.columns: df['매수가'] = 0.0
    if '수량' not in df.columns: df['수량'] = 0.0
    if '티커' not in df.columns: df['티커'] = ''

    df['매수가'] = pd.to_numeric(df['매수가'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0.0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0.0)
    
    num_cols = ['현재가', 'RSI', 'EMA5', 'EMA20', 'EMA50', 'EMA100', 'BB상단', 'BB하단', 'MACD', 'MACD히스토그램', 'OBV', '거래량강도(%)']
    for col in num_cols:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)

    text_cols = ['추세상태', 'OBV추세']
    for col in text_cols:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].astype(str)

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

    # [핵심 방어 2] sum() 결과를 무조건 순수 파이썬 float 타입으로 강제 변환
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

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    exchange_rate = float(get_exchange_rate())
    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    
    # 1. 탭별 데이터 처리
    df_us, ws_us = sheet_manager.get_sheet_data('해외주식')
    df_us, us_invest_usd, us_eval_usd = process_asset_df(df_us, '해외주식', is_usd=True)
    if ws_us: sheet_manager.update_sheet(ws_us, df_us)
    
    df_coin, ws_coin = sheet_manager.get_sheet_data('COIN')
    df_coin, coin_invest_krw, coin_eval_krw = process_asset_df(df_coin, '코인', is_usd=False)
    if ws_coin: sheet_manager.update_sheet(ws_coin, df_coin)

    df_pen, ws_pen = sheet_manager.get_sheet_data('개인연금')
    df_pen, pen_invest_krw, pen_eval_krw = process_asset_df(df_pen, '연금저축', is_usd=False)
    if ws_pen: sheet_manager.update_sheet(ws_pen, df_pen)

    # 2. 통합 자산 원화(KRW) 환산
    us_invest_krw = float(us_invest_usd * exchange_rate)
    us_eval_krw = float(us_eval_usd * exchange_rate)

    total_invest_krw = float(us_invest_krw + coin_invest_krw + pen_invest_krw)
    total_eval_krw = float(us_eval_krw + coin_eval_krw + pen_eval_krw)
    
    # 3. 전일 대비 변동폭 계산
    last_history = sheet_manager.get_latest_history()
    
    def get_diff(current_val, history_key):
        if last_history is not None and history_key in last_history:
            try:
                val = last_history[history_key]
                # 혹시라도 Series 덩어리면 첫 번째 값만 추출
                if isinstance(val, pd.Series): val = val.iloc[0]
                past_val = float(str(val).replace(',', ''))
                return float(current_val - past_val)
            except: pass
        return 0.0

    diff_us = get_diff(us_eval_krw, '해외주식(₩)')
    diff_coin = get_diff(coin_eval_krw, 'COIN(₩)')
    diff_pen = get_diff(pen_eval_krw, '개인연금(₩)')
    diff_total = get_diff(total_eval_krw, '총자산(₩)')

    # [핵심 방어 3] Today 시트에 들어가는 모든 값을 int(), float()로 100% 코팅해서 JSON 에러 완전 차단
    today_data = {
        '자산군': ['해외주식 (USD 변환)', 'COIN', '개인연금', '총 자산'],
        '투자원금(₩)': [int(us_invest_krw), int(coin_invest_krw), int(pen_invest_krw), int(total_invest_krw)],
        '평가금액(₩)': [int(us_eval_krw), int(coin_eval_krw), int(pen_eval_krw), int(total_eval_krw)],
        '평가손익(₩)': [int(us_eval_krw - us_invest_krw), int(coin_eval_krw - coin_invest_krw), int(pen_eval_krw - pen_invest_krw), int(total_eval_krw - total_invest_krw)],
        '수익률(%)': [
            float((us_eval_krw - us_invest_krw) / us_invest_krw) if us_invest_krw > 0 else 0.0,
            float((coin_eval_krw - coin_invest_krw) / coin_invest_krw) if coin_invest_krw > 0 else 0.0,
            float((pen_eval_krw - pen_invest_krw) / pen_invest_krw) if pen_invest_krw > 0 else 0.0,
            float((total_eval_krw - total_invest_krw) / total_invest_krw) if total_invest_krw > 0 else 0.0
        ],
        '전일대비 변동폭(₩)': [int(diff_us), int(diff_coin), int(diff_pen), int(diff_total)]
    }
    
    df_today = pd.DataFrame(today_data)
    _, ws_today = sheet_manager.get_sheet_data('Today')
    if ws_today:
        # JSON 직렬화 전 데이터 타입을 다시 한번 검증
        sheet_manager.update_sheet(ws_today, df_today)
        print("✅ Today 탭 요약 완료!")

    # 5. History 탭 데이터 누적
    history_row = {
        '일자': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '적용환율': float(exchange_rate),
        '해외주식(₩)': int(us_eval_krw),
        'COIN(₩)': int(coin_eval_krw),
        '개인연금(₩)': int(pen_eval_krw),
        '총자산(₩)': int(total_eval_krw)
    }
    sheet_manager.append_to_history(history_row)
    
    print("🚀 모든 작업이 성공적으로 끝났어!")

if __name__ == "__main__":
    main()
