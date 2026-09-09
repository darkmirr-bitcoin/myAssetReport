import os
import pytz
import pandas as pd
from datetime import datetime
import google.generativeai as genai  # 💡 AI 분석을 위한 라이브러리 추가!

from google_sheet import GoogleSheetManager
from data_processor import get_exchange_rate, process_asset_df, check_market_open
from report_generator import generate_reports
from telegram_bot import send_telegram_message

# 내가 만든 매크로 지표 모듈 불러오기
from macro_data import get_treasury_yields, get_fear_and_greed, get_market_indices, fetch_telegram_macro 

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    exchange_rate = get_exchange_rate()
    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    
    # 💡 [오타 수정 완료] 한국 시간 기준 현재 (History 기록용)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

    # 1. 기준 날짜 세팅 (뉴욕 시간 기준, 리포트 타이틀용)
    tz_ny = pytz.timezone('America/New_York')
    now_ny = datetime.now(tz_ny)
    us_date_str = now_ny.strftime("%Y-%m-%d")

    print(f"🚀 자산 리포트 파이프라인 가동 시작 ({us_date_str})")

    # ------------------------------------
    # 2. 매크로 데이터 수집
    # ------------------------------------
    print("📊 매크로 데이터 및 전문가 뷰 수집 중...")
    indices_data = get_market_indices()         
    yields_data = get_treasury_yields()         
    fng_data = get_fear_and_greed(indices_data, yields_data) 
    
    # 텔레그램 매크로 데이터 크롤링
    telegram_text = fetch_telegram_macro()

    macro_data = {
        'indices': indices_data,
        'yields': yields_data,
        'fng': fng_data,
        'telegram': telegram_text 
    }
    # ------------------------------------

    # 휴장일 체크
    is_us_open = check_market_open('해외주식')
    is_kr_open = check_market_open('연금저축')

    # 3. 각 탭 데이터 처리 및 업데이트
    df_us, ws_us = sheet_manager.get_sheet_data('해외주식')
    df_us, us_inv_usd, us_eval_usd = process_asset_df(df_us, '해외주식', is_usd=True, is_open=is_us_open)
    if ws_us: sheet_manager.update_sheet(ws_us, df_us)
    
    df_coin, ws_coin = sheet_manager.get_sheet_data('COIN')
    df_coin, coin_inv_krw, coin_eval_krw = process_asset_df(df_coin, '코인', is_usd=False, is_open=True)
    if ws_coin: sheet_manager.update_sheet(ws_coin, df_coin)

    df_pen, ws_pen = sheet_manager.get_sheet_data('개인연금')
    df_pen, pen_inv_krw, pen_eval_krw = process_asset_df(df_pen, '연금저축', is_usd=False, is_open=is_kr_open)
    if ws_pen: sheet_manager.update_sheet(ws_pen, df_pen)

    # 4. History 누적용 전체 데이터 합치기
    df_us['기록일자'] = now_str
    df_coin['기록일자'] = now_str  # 💡 '제' 오타 제거 완벽히 처리됨!
    df_pen['기록일자'] = now_str
    
    history_cols = ['기록일자', '티커', '현재가', '수량', '수익률(%)']
    df_all = pd.concat([df_us[history_cols], df_coin[history_cols], df_pen[history_cols]], ignore_index=True)
    
    sheet_manager.append_rows_to_history(df_all)

    # 5. 요약 데이터 계산 (Today 탭용)
    us_inv_krw = float(us_inv_usd * exchange_rate)
    us_eval_krw = float(us_eval_usd * exchange_rate)
    total_inv_krw = float(us_inv_krw + coin_inv_krw + pen_inv_krw)
    total_eval_krw = float(us_eval_krw + coin_eval_krw + pen_eval_krw)

    last_today_summary = sheet_manager.get_latest_history_summary()
    
    def get_diff_from_today(current_val, asset_name):
        if last_today_summary is not None and not last_today_summary.empty:
            try:
                row = last_today_summary[last_today_summary['자산군'] == asset_name]
                if not row.empty:
                    past_val_str = str(row.iloc[0]['평가금액(₩)']).replace(',', '').replace('₩', '')
                    past_val = float(past_val_str)
                    return float(current_val - past_val)
            except: pass
        return 0.0

    diff_us = get_diff_from_today(us_eval_krw, '해외주식 (USD 변환)')
    diff_coin = get_diff_from_today(coin_eval_krw, 'COIN')
    diff_pen = get_diff_from_today(pen_eval_krw, '개인연금')
    diff_total = get_diff_from_today(total_eval_krw, '총 자산')

    today_data = {
        '자산군': ['해외주식 (USD 변환)', 'COIN', '개인연금', '총 자산'],
        '투자원금(₩)': [int(us_inv_krw), int(coin_inv_krw), int(pen_inv_krw), int(total_inv_krw)],
        '평가금액(₩)': [int(us_eval_krw), int(coin_eval_krw), int(pen_eval_krw), int(total_eval_krw)],
        '평가손익(₩)': [int(us_eval_krw - us_inv_krw), int(coin_eval_krw - coin_inv_krw), int(pen_eval_krw - pen_inv_krw), int(total_eval_krw - total_inv_krw)],
        '수익률(%)': [
            float((us_eval_krw - us_inv_krw) / us_inv_krw) if us_inv_krw > 0 else 0.0,
            float((coin_eval_krw - coin_inv_krw) / coin_inv_krw) if coin_inv_krw > 0 else 0.0,
            float((pen_eval_krw - pen_inv_krw) / pen_inv_krw) if pen_inv_krw > 0 else 0.0,
            float((total_eval_krw - total_inv_krw) / total_inv_krw) if total_inv_krw > 0 else 0.0
        ],
        '전일대비 변동폭(₩)': [int(diff_us), int(diff_coin), int(diff_pen), int(diff_total)]
    }
    df_today = pd.DataFrame(today_data)
    
    _, ws_today = sheet_manager.get_sheet_data('Today')
    if ws_today:
        sheet_manager.update_sheet(ws_today, df_today)
        print("✅ Today 탭 업데이트 완료!")

    # 6. 제미나이 AI 퀀트 분석 엔진 가동 (텔레그램 요약 + 액션 플랜 HTML 생성)
    print("🧠 퀀트 AI 분석 및 텔레그램 요약 중...")
    ai_action_html = ""
    telegram_summary = telegram_text # 기본값은 길고 복잡한 원본
    
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # AI에게 던져줄 내 포트폴리오(종목명과 수익률) 문자열 조립
            portfolio_str = f"해외주식:\n{df_us[['티커', '수익률(%)']].to_string(index=False) if not df_us.empty else '없음'}\n\n코인:\n{df_coin[['티커', '수익률(%)']].to_string(index=False) if not df_coin.empty else '없음'}"
            
            prompt = f"""
            너는 내 자산을 관리하는 냉철한 퀀트 AI야. 
            아래 [데이터]를 바탕으로 텔레그램 시황을 3줄로 요약하고, 내 종목들에 대한 매매 시그널을 HTML 리스트로 만들어줘.
            
            [텔레그램 시황 원본]
            {telegram_text}
            
            [내 포트폴리오]
            {portfolio_str}
            
            출력은 반드시 아래와 같이 '---구분선---'을 기준으로 위에는 텍스트 요약, 아래는 HTML 태그를 작성해.
            (마크다운 코드블록은 절대 쓰지 마)

            - 텔레그램 요약 (3~4줄 팩트 위주)
            ---구분선---
            <ul>
                <li><span style="background-color: #ff4d4d; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9em;">[전량 매도]</span> <strong>SUI</strong> - 단기 추세 이탈, 손절 권고</li>
                <li><span style="background-color: #ff9933; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9em;">[분할 익절]</span> <strong>NVDA</strong> - 과열 구간 진입, 수익 실현</li>
                <li><span style="background-color: #3399ff; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9em;">[매수]</span> <strong>MSTR</strong> - 공포 지수 하락 및 역발상 진입 가능 구간</li>
                <li><span style="background-color: #2eb82e; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9em;">[홀딩]</span> <strong>나머지 자산</strong> - 추세 유지 중</li>
            </ul>
            """
            
            response = model.generate_content(prompt)
            # 마크다운 찌꺼기(```html 등)가 섞여 있으면 깨지므로 제거
            result = response.text.replace('```html', '').replace('```', '')
            
            if "---구분선---" in result:
                parts = result.split("---구분선---")
                telegram_summary = parts[0].strip()  # AI가 예쁘게 3줄 요약한 텍스트
                ai_action_html = parts[1].strip()    # AI가 만든 신호등 배지 HTML
            else:
                ai_action_html = result
                
            # 요약된 내용을 다시 macro_data에 덮어씌워서 깔끔하게 출력되도록 함!
            macro_data['telegram'] = telegram_summary
    except Exception as e:
        print(f"❌ AI 분석 에러: {e}")

    # 7. HTML 웹 리포트 렌더링 
    print("🎨 HTML 웹 리포트 렌더링 중...")
    # 💡 텅 비워뒀던 자리에 드디어 AI 분석 결과를 담아서 보냄
    generate_reports(df_today, exchange_rate, macro_data, us_date_str, ai_action_html=ai_action_html)
    
    # 8. 텔레그램 발송 
    print("📨 텔레그램 메시지 발송 중...")
    send_telegram_message(df_today, exchange_rate) 
    
    print("🎯 모든 프로세스 정상 종료! 깃허브에서 확인해봐.")

if __name__ == "__main__":
    main()
