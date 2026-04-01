import os
import requests
import pandas as pd

def send_telegram_message(df, exchange_rate):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id: return

    # 통화별 분리
    usd_df = df[df['통화'] == 'USD']
    krw_df = df[df['통화'] == 'KRW']

    # USD 합계
    usd_eval = usd_df['평가금액($)'].sum()
    usd_profit = usd_df['평가손익($)'].sum()

    # KRW 합계
    krw_eval = krw_df['평가금액($)'].sum()
    krw_profit = krw_df['평가손익($)'].sum()

    # 통합 자산 계산 (원화 기준)
    total_eval_krw = (usd_eval * exchange_rate) + krw_eval
    
    msg = f"📊 자산관리 리포트 (환율: {exchange_rate:,.1f})\n\n"
    msg += f"[미국 주식]\n평가: ${usd_eval:,.2f} / 손익: ${usd_profit:,.2f}\n\n"
    msg += f"[국내 및 코인]\n평가: ₩{krw_eval:,.0f} / 손익: ₩{krw_profit:,.0f}\n\n"
    msg += f"💰 [통합 총 자산]\n₩{total_eval_krw:,.0f}"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": msg})