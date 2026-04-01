import os
import requests
import pandas as pd

def send_telegram_message(df, exchange_rate):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id: return

    # 통화 분리
    df['통화'] = df['통화'].astype(str).str.strip().str.upper()
    usd_df = df[df['통화'] == 'USD']
    krw_df = df[df['통화'] != 'USD'] 

    # 달러 합계 및 수익률 계산
    usd_eval = pd.to_numeric(usd_df['평가금액($)'], errors='coerce').fillna(0).sum()
    usd_profit = pd.to_numeric(usd_df['평가손익($)'], errors='coerce').fillna(0).sum()
    usd_principal = usd_eval - usd_profit
    usd_yield = (usd_profit / usd_principal * 100) if usd_principal > 0 else 0

    # 원화 합계 및 수익률 계산
    krw_eval = pd.to_numeric(krw_df['평가금액($)'], errors='coerce').fillna(0).sum()
    krw_profit = pd.to_numeric(krw_df['평가손익($)'], errors='coerce').fillna(0).sum()
    krw_principal = krw_eval - krw_profit
    krw_yield = (krw_profit / krw_principal * 100) if krw_principal > 0 else 0

    # 통합 총 자산 계산
    total_eval_krw = (usd_eval * exchange_rate) + krw_eval
    total_profit_krw = (usd_profit * exchange_rate) + krw_profit
    total_principal = total_eval_krw - total_profit_krw
    total_yield = (total_profit_krw / total_principal * 100) if total_principal > 0 else 0

    # 수익률 꾸미기 함수 (+, - 부호 및 이모지)
    def format_yield(y):
        sign = "+" if y > 0 else ""
        emoji = "🔴" if y > 0 else "🔵" if y < 0 else "⚫"
        return f"{emoji} {sign}{y:.2f}%"

    msg = f"📊 일일 자산 리포트 (환율: {exchange_rate:,.1f}원)\n\n"
    msg += f"🇺🇸 [달러 자산]\n💰 평가: ${usd_eval:,.2f}\n📈 손익: ${usd_profit:,.2f}\n📊 수익률: {format_yield(usd_yield)}\n\n"
    msg += f"🇰🇷 [원화 자산 (코인/국내)]\n💰 평가: ₩{krw_eval:,.0f}\n📈 손익: ₩{krw_profit:,.0f}\n📊 수익률: {format_yield(krw_yield)}\n\n"
    msg += f"🔥 [통합 총 자산 가치]\n총액: ₩{total_eval_krw:,.0f}\n총 손익: ₩{total_profit_krw:,.0f}\n총 수익률: {format_yield(total_yield)}\n\n"
    msg += "👉 상세 리포트는 GitHub Pages 확인!"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": msg})
    except Exception as e:
        print(f"❌ 텔레그램 전송 에러: {e}")
