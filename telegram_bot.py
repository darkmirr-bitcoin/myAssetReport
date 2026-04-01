import os
import requests
import pandas as pd

def send_telegram_message(df_today, exchange_rate):
    """Today 요약 데이터를 예쁜 텍스트로 가공해서 텔레그램으로 쏘는 함수"""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ 텔레그램 토큰이나 챗 ID가 없어서 알림 발송은 건너뛸게.")
        return

    print("📱 텔레그램 알림 발송 중...")
    
    # '총 자산' 행만 뽑아내서 데이터 추출
    total_row = df_today[df_today['자산군'] == '총 자산'].iloc[0]
    total_eval = total_row['평가금액(₩)']
    total_profit = total_row['평가손익(₩)']
    total_rate = total_row['수익률(%)'] * 100
    daily_diff = total_row['전일대비 변동폭(₩)']
    
    # 메시지 이모지 세팅
    sign = "🔴" if total_profit > 0 else "🔵" if total_profit < 0 else "⚪"
    diff_sign = "📈" if daily_diff > 0 else "📉" if daily_diff < 0 else "➖"

    # 전송할 텍스트 조합
    msg = f"📊 *일일 자산 리포트*\n\n"
    msg += f"💵 환율: {exchange_rate:,.2f}원\n"
    msg += f"💰 총 자산: {total_eval:,.0f}원\n"
    msg += f"{sign} 총 손익: {total_profit:,.0f}원 ({total_rate:.2f}%)\n"
    msg += f"{diff_sign} 전일 대비: {daily_diff:,.0f}원\n\n"
    msg += f"🌐 상세 리포트 (https://darkmirr-bitcoin.github.io/myAssetReport/)" # 나중에 네 깃헙 주소로 바꿔!

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': msg,
        'parse_mode': 'Markdown'
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("✅ 텔레그램 메시지 발송 완료!")
    except Exception as e:
        print(f"❌ 텔레그램 발송 실패: {e}")
