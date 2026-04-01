import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
import pyupbit
import requests

# 판다스 숫자 출력 포맷 설정 (지수표현식 e+02 방지)
pd.options.display.float_format = '{:.2f}'.format

# 1. 구글 시트 연결
print("구글 시트에 연결 중...")
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
doc = client.open_by_key(SPREADSHEET_ID)
sheet = doc.sheet1 

data = sheet.get_all_records()
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
        # [수정 1] 티커에 6자리 숫자가 포함되어 있으면 무조건 한국 주식/ETF로 간주 ('ISA' 등 카테고리 이름 무관)
        match = re.search(r'\d{6}', ticker)
        if match:
            clean_ticker = match.group()
            history = fdr.DataReader(clean_ticker)
            if not history.empty:
                return history.iloc[-1]['Close']

        # 해외 주식
        elif category == '해외주식':
            history = yf.Ticker(ticker).history(period="1d")
            if not history.empty:
                return history['Close'].iloc[-1]
            
        # [수정 2] 코인 (업비트 원화 기준)
        elif category == '코인':
            price = pyupbit.get_current_price(f"KRW-{ticker}")
            if price:
                return price
            else:
                # 업비트에 없는 경우 야후 파이낸스 달러 조회 시도
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

# 수익률 계산
df['수익률(%)'] = df.apply(lambda x: ((x['현재가($)'] - x['매수가($)']) / x['매수가($)'] * 100) if x['매수가($)'] > 0 else 0, axis=1)

# 컬럼명에 ($)가 있지만, 실제로는 시트의 '통화' 기준 데이터임. 
# 보기 좋게 소수점 반올림
df['현재가($)'] = df['현재가($)'].round(2)
df['평가금액($)'] = df['평가금액($)'].round(2)
df['평가손익($)'] = df['평가손익($)'].round(2)
df['수익률(%)'] = df['수익률(%)'].round(2)

print("✅ 계산 완료! 결과 확인:")
result_df = df[['구분', '티커', '매수가($)', '수량', '현재가($)', '평가손익($)', '수익률(%)', '평가금액($)']]
print(result_df.head(10))

# ==========================================
# 4. HTML 리포트 생성 (index.html)
# ==========================================
print("웹 리포트(HTML) 생성 중...")

# 웹페이지 기본 스타일 (CSS)
html_style = """
<style>
    body { font-family: 'Malgun Gothic', sans-serif; padding: 20px; background-color: #f8f9fa; }
    h2 { color: #333; }
    table { border-collapse: collapse; width: 100%; background-color: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
    th, td { border: 1px solid #ddd; padding: 12px; text-align: right; font-size: 14px; }
    th { background-color: #4CAF50; color: white; text-align: center; }
    tr:nth-child(even) { background-color: #f2f2f2; }
    .positive { color: red; font-weight: bold; }
    .negative { color: blue; font-weight: bold; }
</style>
"""

# HTML 구조 조립
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

# index.html 파일로 저장
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("✅ index.html 파일 생성 완료!")


# ==========================================
# 5. 텔레그램 알림 전송
# ==========================================
print("텔레그램 알림 전송 준비 중...")

# 깃허브 Secrets(환경 변수)에서 값 불러오기
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ 텔레그램 토큰이나 Chat ID가 설정되지 않아서 알림 전송은 건너뛸게.")
else:
    # 알림으로 보낼 요약 데이터 계산
    total_asset = df['평가금액($)'].sum()
    total_profit = df['평가손익($)'].sum()

    # 메시지 내용 구성
    message = f"📊 일일 자산 리포트 업데이트 완료!\n\n"
    message += f"💰 총 평가금액: {total_asset:,.2f}\n"
    message += f"📈 총 평가손익: {total_profit:,.2f}\n\n"
    message += "상세 리포트는 아래 링크에서 확인해.\n"
    message += "👉 https://[너의깃허브ID].github.io/[레포지토리이름]/"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print("✅ 텔레그램 메시지 전송 성공!")
        else:
            print(f"❌ 텔레그램 전송 실패: {response.status_code}\n{response.text}")
    except Exception as e:
        print(f"❌ 텔레그램 전송 중 에러 발생: {e}")