import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
import pyupbit
import re
import os
import requests
import json  # 추가됨: 환경 변수의 JSON 문자열을 파싱하기 위해 필요
from datetime import datetime

# 판다스 숫자 출력 포맷 설정 (지수표현식 e+02 방지)
pd.options.display.float_format = '{:.2f}'.format

# 1. 구글 시트 연결
print("구글 시트에 연결 중...")
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# 깃허브 Secrets(또는 로컬 환경 변수)에서 인증 정보 불러오기
gcp_creds_json = os.environ.get('GCP_CREDENTIALS')

if not gcp_creds_json:
    raise ValueError("❌ GCP_CREDENTIALS 환경 변수가 설정되지 않았어!")

# JSON 문자열을 딕셔너리로 변환 후 인증
creds_dict = json.loads(gcp_creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
doc = client.open_by_key(SPREADSHEET_ID)
sheet = doc.sheet1 

# --- (이 아래로는 기존 코드와 동일하게 유지) ---
data = sheet.get_all_records()
# ...
df = pd.DataFrame(data)

# 모든 컬럼 이름의 앞뒤 공백 제거
df.columns = df.columns.str.strip()

print("시트 데이터 불러오기 완료!")

# ==========================================
# 2. 데이터 가공 및 현재가 수집
# ==========================================
print("현재가 수집 및 계산 중...")

# 숫자 변환
df['매수가($)'] = pd.to_numeric(df['매수가($)'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

def get_current_price(row):
    category = str(row['구분']).strip()
    ticker = str(row['티커']).strip()
    
    if not ticker or pd.isna(ticker) or ticker == 'nan' or ticker == '':
        return 0.0
        
    try:
        match = re.search(r'\d{6}', ticker)
        if match:
            clean_ticker = match.group()
            history = fdr.DataReader(clean_ticker)
            if not history.empty:
                return history.iloc[-1]['Close']

        elif category == '해외주식':
            history = yf.Ticker(ticker).history(period="1d")
            if not history.empty:
                return history['Close'].iloc[-1]
            
        elif category == '코인':
            price = pyupbit.get_current_price(f"KRW-{ticker}")
            if price:
                return price
            else:
                ticker_usd = ticker + '-USD' if not ticker.endswith('-USD') else ticker
                history = yf.Ticker(ticker_usd).history(period="1d")
                if not history.empty:
                    return history['Close'].iloc[-1]

    except Exception as e:
        print(f"[{ticker}] 가격 조회 실패: {e}")
        
    return 0.0

df['현재가($)'] = df.apply(get_current_price, axis=1)

# ==========================================
# 3. 수익률 및 평가금액 계산
# ==========================================
df['평가금액($)'] = df['현재가($)'] * df['수량']
df['평가손익($)'] = (df['현재가($)'] - df['매수가($)']) * df['수량']

df['수익률(%)'] = df.apply(lambda x: ((x['현재가($)'] - x['매수가($)']) / x['매수가($)'] * 100) if x['매수가($)'] > 0 else 0, axis=1)

df['현재가($)'] = df['현재가($)'].round(2)
df['평가금액($)'] = df['평가금액($)'].round(2)
df['평가손익($)'] = df['평가손익($)'].round(2)
df['수익률(%)'] = df['수익률(%)'].round(2)

# ==========================================
# 4. 구글 시트 업데이트 및 히스토리 저장
# ==========================================
print("구글 시트에 계산 결과 업데이트 및 히스토리 저장 중...")

# NaN이나 결측치를 빈 문자열로 변경 (구글 시트 에러 방지)
df.fillna('', inplace=True)

# 4-1. 원본 시트(sheet1) 덮어쓰기 업데이트
update_data = [df.columns.tolist()] + df.values.tolist()
sheet.update(values=update_data, range_name='A1')

# 4-2. history 시트에 누적 저장하기
try:
    history_sheet = doc.worksheet('history')
    
    # 히스토리용 데이터프레임 복사 및 현재 날짜/시간 추가
    df_history = df.copy()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df_history.insert(0, '기록일시', current_time)
    
    # 히스토리 시트가 완전히 비어있다면 헤더(컬럼명) 먼저 추가
    if len(history_sheet.get_all_values()) == 0:
        history_sheet.append_row(df_history.columns.tolist())
        
    # 데이터 추가 (append_rows는 맨 아래 빈 줄에 데이터를 이어서 써줌)
    history_data = df_history.values.tolist()
    history_sheet.append_rows(history_data)
    print("✅ 시트 업데이트 및 히스토리 저장 완료!")
except Exception as e:
    print(f"⚠️ 히스토리 시트 저장 실패 (history 탭이 있는지 확인해): {e}")


# ==========================================
# 5. HTML 리포트 생성 (index.html)
# ==========================================
print("웹 리포트(HTML) 생성 중...")
html_style = """
<style>
    body { font-family: 'Malgun Gothic', sans-serif; padding: 20px; background-color: #f8f9fa; }
    h2 { color: #333; }
    table { border-collapse: collapse; width: 100%; background-color: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
    th, td { border: 1px solid #ddd; padding: 12px; text-align: right; font-size: 14px; }
    th { background-color: #4CAF50; color: white; text-align: center; }
    tr:nth-child(even) { background-color: #f2f2f2; }
</style>
"""

result_df = df[['구분', '티커', '매수가($)', '수량', '현재가($)', '평가손익($)', '수익률(%)', '평가금액($)']]
html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>일일 자산관리 리포트</title>
    {html_style}
</head>
<body>
    <h2>📊 일일 자산관리 리포트</h2>
    <p>업데이트 시간: {pd.Timestamp.now('Asia/Seoul').strftime('%Y-%m-%d %H:%M:%S')}</p>
    {result_df.to_html(index=False, classes='asset-table')}
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

# ==========================================
# 6. 텔레그램 알림 전송
# ==========================================
print("텔레그램 알림 전송 준비 중...")
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ 텔레그램 토큰이나 Chat ID가 설정되지 않아 건너뜀.")
else:
    # 문자열로 된 숫자가 있을 수 있으니 float로 변환 후 합산
    total_asset = pd.to_numeric(df['평가금액($)'], errors='coerce').fillna(0).sum()
    total_profit = pd.to_numeric(df['평가손익($)'], errors='coerce').fillna(0).sum()

    message = f"📊 일일 자산 리포트 업데이트 완료!\n\n"
    message += f"💰 총 평가금액: {total_asset:,.2f}\n"
    message += f"📈 총 평가손익: {total_profit:,.2f}\n\n"
    message += "상세 리포트: https://[너의깃허브ID].github.io/[레포지토리이름]/"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print("✅ 텔레그램 메시지 전송 성공!")
    except Exception as e:
        print(f"❌ 텔레그램 전송 에러: {e}")