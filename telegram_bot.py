import os
import requests
import pandas as pd

def send_telegram_message(df, exchange_rate):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id: return

    # 시트의 '통화' 컬럼을 기준으로 USD와 KRW(나머지 전부)를 안전하게 분리
    df['통화'] = df['통화'].astype(str).str.strip().str.upper()
    usd_df = df[df['통화'] == 'USD']
    krw_df = df[df['통화'] != 'USD'] # USD가 아닌 건 전부 KRW로 간주

    # 통화별 평가금액 / 평가손익 합산
    usd_eval = pd.to_numeric(usd_df['평가금액($)'], errors='coerce').fillna(0).sum()
    usd_profit = pd.to_numeric(usd_df['평가손익($)'], errors='coerce').fillna(0).sum()

    krw_eval = pd.to_numeric(krw_df['평가금액($)'], errors='coerce').fillna(0).sum()
    krw_profit = pd.to_numeric(krw_df['평가손익($)'], errors='coerce').fillna(0).sum()

    # 통합 총 자산 (달러 자산 * 현재 환율 + 원화 자산)
    total_eval_krw = (usd_eval * exchange_rate) + krw_eval
    
    msg = f"📊 일일 자산 리포트 업데이트 (환율: {exchange_rate:,.1f}원)\n\n"
    msg += f"🇺🇸 [달러 자산]\n💰 평가금액: ${usd_eval:,.2f}\n📈 평가손익: ${usd_profit:,.2f}\n\n"
    msg += f"🇰🇷 [원화 자산 (코인/국내)]\n💰 평가금액: ₩{krw_eval:,.0f}\n📈 평가손익: ₩{krw_profit:,.0f}\n\n"
    msg += f"🔥 [통합 총 자산 가치]\n총액: ₩{total_eval_krw:,.0f}\n\n"
    msg += "👉 상세 리포트는 GitHub Pages 확인!"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": msg})
    except Exception as e:
        print(f"❌ 텔레그램 전송 에러: {e}")
