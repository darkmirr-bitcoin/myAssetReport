import pandas as pd
import yfinance as yf
from datetime import datetime
from google_sheet import GoogleSheetManager
from indicators import fetch_history_data, calculate_indicators
# from telegram_bot import send_telegram_message # 필요시 주석 해제

def get_exchange_rate():
    try:
        rate = yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1]
        return rate
    except:
        return 1350.0

# 공통 데이터 처리 및 지표 업데이트 함수
def process_asset_df(df, category, is_usd=False):
    if df.empty: return df, 0, 0
    
    # [핵심 수정] 시트에 '매수가($)'나 '매수가(₩)'로 되어있어도 알아서 '매수가'로 통일해서 인식
    rename_dict = {}
    for col in df.columns:
        col_str = str(col).strip()
        if '매수가' in col_str: rename_dict[col] = '매수가'
        elif '현재가' in col_str: rename_dict[col] = '현재가'
        elif '수량' in col_str: rename_dict[col] = '수량'
        elif '티커' in col_str or '종목' in col_str: rename_dict[col] = '티커'
        
    df.rename(columns=rename_dict, inplace=True)

    # 혹시라도 필수 컬럼이 아예 누락됐을 경우 에러 방지용으로 빈 칸 생성
    if '매수가' not in df.columns: df['매수가'] = 0
    if '수량' not in df.columns: df['수량'] = 0
    if '티커' not in df.columns: df['티커'] = ''

    # 숫자형 전처리 및 지표 컬럼 초기화
    df['매수가'] = pd.to_numeric(df['매수가'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    indicator_cols = ['현재가', 'RSI', 'EMA5', 'EMA20', 'EMA50', 'EMA100', 'BB상단', 'BB하단', 'MACD', 'OBV', '거래강도(%)']
    for col in indicator_cols:
        if col not in df.columns: df[col] = 0.0
        else: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # 지표 및 현재가 업데이트
    for index, row in df.iterrows():
        ticker = str(row.get('티커', '')).strip()
        if not ticker or ticker == 'nan': continue
            
        df_hist = fetch_history_data(category, ticker)
        ind_data = calculate_indicators(df_hist)
        
        if ind_data:
            # 현재가는 달러면 소수점 유지, 원화면 반올림
            current_price = ind_data.pop('현재가($)', 0)
            df.at[index, '현재가'] = round(current_price, 2) if is_usd else round(current_price, 0)
            
            for col, val in ind_data.items():
                if col in df.columns:
                    df.at[index, col] = val

    # 평가금액 및 손익 계산
    if is_usd:
        df['평가금액(USD)'] = (df['현재가'] * df['수량']).round(2)
        df['평가손익(USD)'] = ((df['현재가'] - df['매수가']) * df['수량']).round(2)
        invest_total = (df['매수가'] * df['수량']).sum()
        eval_total = df['평가금액(USD)'].sum()
    else:
        df['평가금액(KRW)'] = (df['현재가'] * df['수량']).round(0)
        df['평가손익(KRW)'] = ((df['현재가'] - df['매수가']) * df['수량']).round(0)
        invest_total = (df['매수가'] * df['수량']).sum()
        eval_total = df['평가금액(KRW)'].sum()
        
    # 구글 시트 % 서식 충돌 방지 (* 100 제거)
    df['수익률'] = df.apply(lambda x: (x['현재가'] - x['매수가']) / x['매수가'] if x['매수가'] > 0 else 0, axis=1)
    
    return df, invest_total, eval_total

    # 평가금액 및 손익 계산
    if is_usd:
        df['평가금액(USD)'] = (df['현재가'] * df['수량']).round(2)
        df['평가손익(USD)'] = ((df['현재가'] - df['매수가']) * df['수량']).round(2)
        invest_total = (df['매수가'] * df['수량']).sum()
        eval_total = df['평가금액(USD)'].sum()
    else:
        df['평가금액(KRW)'] = (df['현재가'] * df['수량']).round(0)
        df['평가손익(KRW)'] = ((df['현재가'] - df['매수가']) * df['수량']).round(0)
        invest_total = (df['매수가'] * df['수량']).sum()
        eval_total = df['평가금액(KRW)'].sum()
        
    # 구글 시트 % 서식 충돌 방지 (* 100 제거)
    df['수익률'] = df.apply(lambda x: (x['현재가'] - x['매수가']) / x['매수가'] if x['매수가'] > 0 else 0, axis=1)
    
    return df, invest_total, eval_total

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    exchange_rate = get_exchange_rate()
    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    
    # ---------------------------------------------------------
    # 1. 각 탭별 데이터 처리 및 업데이트
    # ---------------------------------------------------------
    # [해외주식 탭] - USD 기준
    df_us, ws_us = sheet_manager.get_sheet_data('해외주식')
    df_us, us_invest_usd, us_eval_usd = process_asset_df(df_us, '해외주식', is_usd=True)
    if ws_us: sheet_manager.update_sheet(ws_us, df_us)
    
    # [COIN 탭] - KRW 기준
    df_coin, ws_coin = sheet_manager.get_sheet_data('COIN')
    df_coin, coin_invest_krw, coin_eval_krw = process_asset_df(df_coin, '코인', is_usd=False)
    if ws_coin: sheet_manager.update_sheet(ws_coin, df_coin)

    # [개인연금 탭] - KRW 기준
    df_pen, ws_pen = sheet_manager.get_sheet_data('개인연금')
    df_pen, pen_invest_krw, pen_eval_krw = process_asset_df(df_pen, '한국ETF', is_usd=False)
    if ws_pen: sheet_manager.update_sheet(ws_pen, df_pen)

    # ---------------------------------------------------------
    # 2. 통합 자산 원화(KRW) 환산
    # ---------------------------------------------------------
    us_invest_krw = us_invest_usd * exchange_rate
    us_eval_krw = us_eval_usd * exchange_rate

    total_invest_krw = us_invest_krw + coin_invest_krw + pen_invest_krw
    total_eval_krw = us_eval_krw + coin_eval_krw + pen_eval_krw
    
    # ---------------------------------------------------------
    # 3. 전일 대비 변동폭 계산 (History 탭 읽어오기)
    # ---------------------------------------------------------
    last_history = sheet_manager.get_latest_history()
    
    def get_diff(current_val, history_key):
        if last_history is not None and history_key in last_history:
            try:
                # 콤마 제거 후 숫자로 변환
                past_val = float(str(last_history[history_key]).replace(',', ''))
                return current_val - past_val
            except: pass
        return 0.0

    diff_us = get_diff(us_eval_krw, '해외주식(₩)')
    diff_coin = get_diff(coin_eval_krw, 'COIN(₩)')
    diff_pen = get_diff(pen_eval_krw, '개인연금(₩)')
    diff_total = get_diff(total_eval_krw, '총자산(₩)')

    # ---------------------------------------------------------
    # 4. Today 탭 데이터 생성 및 업데이트
    # ---------------------------------------------------------
    today_data = {
        '자산군': ['해외주식 (USD 변환)', 'COIN', '개인연금', '총 자산'],
        '투자원금(₩)': [round(us_invest_krw, 0), round(coin_invest_krw, 0), round(pen_invest_krw, 0), round(total_invest_krw, 0)],
        '평가금액(₩)': [round(us_eval_krw, 0), round(coin_eval_krw, 0), round(pen_eval_krw, 0), round(total_eval_krw, 0)],
        '평가손익(₩)': [round(us_eval_krw - us_invest_krw, 0), round(coin_eval_krw - coin_invest_krw, 0), round(pen_eval_krw - pen_invest_krw, 0), round(total_eval_krw - total_invest_krw, 0)],
        '수익률(%)': [
            (us_eval_krw - us_invest_krw) / us_invest_krw if us_invest_krw > 0 else 0,
            (coin_eval_krw - coin_invest_krw) / coin_invest_krw if coin_invest_krw > 0 else 0,
            (pen_eval_krw - pen_invest_krw) / pen_invest_krw if pen_invest_krw > 0 else 0,
            (total_eval_krw - total_invest_krw) / total_invest_krw if total_invest_krw > 0 else 0
        ],
        '전일대비 변동폭(₩)': [round(diff_us, 0), round(diff_coin, 0), round(diff_pen, 0), round(diff_total, 0)]
    }
    
    df_today = pd.DataFrame(today_data)
    _, ws_today = sheet_manager.get_sheet_data('Today')
    if ws_today:
        sheet_manager.update_sheet(ws_today, df_today)
        print("✅ Today 탭 요약 완료!")

    # ---------------------------------------------------------
    # 5. History 탭 데이터 누적
    # ---------------------------------------------------------
    history_row = {
        '일자': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '적용환율': round(exchange_rate, 2),
        '해외주식(₩)': round(us_eval_krw, 0),
        'COIN(₩)': round(coin_eval_krw, 0),
        '개인연금(₩)': round(pen_eval_krw, 0),
        '총자산(₩)': round(total_eval_krw, 0)
    }
    sheet_manager.append_to_history(history_row)
    
    print("🚀 모든 작업이 성공적으로 끝났어!")

if __name__ == "__main__":
    main()
