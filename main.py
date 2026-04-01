import pandas as pd
import yfinance as yf
from google_sheet import GoogleSheetManager
from indicators import fetch_history_data, calculate_indicators
from telegram_bot import send_telegram_message

def get_exchange_rate():
    try:
        # 실시간 USD/KRW 환율 가져오기
        rate = yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1]
        return rate
    except:
        return 1350.0 # 실패 시 기본 환율

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    pd.options.display.float_format = '{:.2f}'.format
    
    exchange_rate = get_exchange_rate()
    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    df = sheet_manager.get_data()
    
    # 1. 숫자 데이터 전처리
    df['매수가($)'] = pd.to_numeric(df['매수가($)'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    # 2. 종목별 루프 (가격 및 지표 업데이트)
    for index, row in df.iterrows():
        ticker = str(row['티커']).strip()
        category = str(row['구분']).strip()
        
        if not ticker or ticker == 'nan': continue
            
        df_hist = fetch_history_data(category, ticker)
        ind_data = calculate_indicators(df_hist)
        
        if ind_data:
            for col, val in ind_data.items():
                if col in df.columns:
                    df.at[index, col] = val

    # 3. 수익률 및 평가금액 계산 (통화 컬럼 반영)
    df['현재가($)'] = pd.to_numeric(df['현재가($)'], errors='coerce').fillna(0)
    
    # 평가금액 및 평가손익 계산 (해당 종목의 로컬 통화 기준)
    df['평가금액($)'] = df['현재가($)'] * df['수량']
    df['평가손익($)'] = (df['현재가($)'] - df['매수가($)']) * df['수량']
    
    # 수익률(%) 계산 (같은 통화끼리의 계산이므로 환율 무관하게 정확함)
    df['수익률(%)'] = df.apply(
        lambda x: ((x['현재가($)'] - x['매수가($)']) / x['매수가($)'] * 100) if x['매수가($)'] > 0 else 0, 
        axis=1
    )

    # 4. 시트 업데이트 및 저장
    sheet_manager.update_main_sheet(df)
    sheet_manager.append_history(df)

    # 5. 텔레그램 발송 (환율 정보를 함께 넘겨서 통합 자산 계산)
    send_telegram_message(df, exchange_rate)
    
    print("🚀 모든 데이터가 시트에 업데이트 되었어!")

if __name__ == "__main__":
    main()