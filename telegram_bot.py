import os
import requests
import pandas as pd

def send_telegram_message(df):
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레그램 설정이 없어서 알림 발송 건너뜀.")
        return

    # 통화별로 분리해서 계산 (수익률 짬뽕 방지)
    df_usd = df[df['통화'] == 'USD']
    df_krw = df[df['통화'] != 'USD'] # USD가 아닌 건 전부 KRW(원화)로 간주

    usd_asset = pd.to_numeric(df_usd['평가금액($)'], errors='coerce').fillna(0).sum()
    usd_profit = pd.to_numeric(df_usd['평가손익($)'], errors='coerce').fillna(0).sum()
    
    krw_asset = pd.to_numeric(df_krw['평가금액($)'], errors='coerce').fillna(0).sum()
    krw_profit = pd.to_numeric(df_krw['평가손익($)'], errors='coerce').fillna(0).sum()

    message = f"📊 일일 자산 리포트 업데이트 완료!\n\n"
    message += f"[🇺🇸 USD 자산]\n💰 총 평가금액: ${usd_asset:,.2f}\n📈 총 평가손익: ${usd_profit:,.2f}\n\n"
    message += f"[🇰🇷 KRW 자산]\n💰 총 평가금액: ₩{krw_asset:,.0f}\n📈 총 평가손익: ₩{krw_profit:,.0f}\n\n"
    message += "상세 리포트: https://[너의깃허브ID].github.io/[레포지토리이름]/"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
        print("✅ 텔레그램 메시지 전송 성공!")
    except Exception as e:
        print(f"❌ 텔레그램 전송 에러: {e}")