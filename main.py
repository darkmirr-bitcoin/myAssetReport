import os
import pytz
import pandas as pd
from datetime import datetime
from google_sheet import GoogleSheetManager
from data_processor import get_exchange_rate, process_asset_df, check_market_open
from report_generator import generate_reports
from telegram_bot import send_telegram_message

# [추가] 내가 만든 매크로 지표 모듈 불러오기!
from macro_data import get_treasury_yields, get_fear_and_greed, get_market_indices, fetch_telegram_macro 

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    exchange_rate = get_exchange_rate()
    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

    # 1. 기준 날짜 세팅 (뉴욕 시간 기준)
    tz_ny = pytz.timezone('America/New_York')
    now_ny = datetime.now(tz_ny)
    us_date_str = now_ny.strftime("%Y-%m-%d")

    print(f"🚀 자산 리포트 파이프라인 가동 시작 ({us_date_str})")


    # ------------------------------------
    # 2. 매크로 데이터 수집 (순서 중요!)
    # ------------------------------------
    print("📊 매크로 데이터 및 전문가 뷰 수집 중...")
    indices_data = get_market_indices()         # 먼저 지수 데이터 수집
    yields_data = get_treasury_yields()         # 그 다음 금리 데이터 수집
    
    # 지수와 금리 데이터를 공포탐욕 함수에 넘겨서 AI가 종합 분석하게 만듦!
    fng_data = get_fear_and_greed(indices_data, yields_data) 

    # 💡 텔레그램 매크로 데이터 수집 추가
    telegram_text = fetch_telegram_macro()


    macro_data = {
        'indices': indices_data,
        'yields': yields_data,
        'fng': fng_data,
        'telegram': telegram_text # 💡 매크로 데이터 딕셔너리에 텔레그램 텍스트 추가
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
    df_coin['기록일자'] = now_str
    df_pen['기록일자'] = now_str
    
    history_cols = ['기록일자', '티커', '현재가', '수량', '수익률(%)']
    df_all = pd.concat([df_us[history_cols], df_coin[history_cols], df_pen[history_cols]], ignore_index=True)
    
    # History 탭에 상세 데이터 누적
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

    # 6. 리포트 생성 및 전송 
    print("🧠 퀀트 AI 분석 및 액션 시그널 추출 중...")
    
    # 💡 us_date_str 추가 전달 및 full_report 반환 받도록 변경
    # (주의: report_generator.py의 generate_reports 함수도 이를 받을 수 있도록 수정 필요)
    full_report, telegram_summary = generate_reports(df_today, exchange_rate, macro_data, us_date_str)
    
    
    # 7. 웹 리포트 HTML 렌더링 (신호등 배지 & 액션 보드 적용)
    print("🎨 HTML 웹 리포트 렌더링 중...")
    
    if full_report:
        # 텍스트 태그를 시각적인 컬러 배지로 치환
        styled_text = full_report.replace(
            '[전량 매도]', '<span style="background-color: #ff4d4d; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.9em; box-shadow: 1px 1px 3px rgba(0,0,0,0.2);">[전량 매도]</span>'
        ).replace(
            '[분할 익절]', '<span style="background-color: #ff9933; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.9em; box-shadow: 1px 1px 3px rgba(0,0,0,0.2);">[분할 익절]</span>'
        ).replace(
            '[매수]', '<span style="background-color: #3399ff; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.9em; box-shadow: 1px 1px 3px rgba(0,0,0,0.2);">[매수]</span>'
        ).replace(
            '[홀딩]', '<span style="background-color: #2eb82e; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.9em; box-shadow: 1px 1px 3px rgba(0,0,0,0.2);">[홀딩]</span>'
        )

        # 줄바꿈 마크다운을 HTML 태그로 변환
        styled_text = styled_text.replace('\n', '<br>')

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>📊 퀀트 자산관리 리포트 ({us_date_str})</title>
            <style>
                body {{ font-family: 'Pretendard', 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 900px; margin: auto; color: #333; background-color: #f8f9fa; }}
                h1, h2, h3 {{ color: #1a1a1a; }}
                /* 최상단 액션 보드 스타일 */
                .action-board {{ 
                    background-color: #ffffff; 
                    padding: 25px; 
                    border-left: 8px solid #ff4d4d; 
                    border-radius: 12px; 
                    margin-bottom: 30px; 
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                }}
                .action-board h2 {{ margin-top: 0; color: #d32f2f; font-size: 1.5em; }}
                .action-board p {{ font-size: 1.05em; color: #555; margin-bottom: 0; }}
                /* 메인 콘텐츠 영역 스타일 */
                .content-area {{ 
                    background-color: #ffffff; 
                    padding: 30px; 
                    border-radius: 12px; 
                    border: 1px solid #eaeaea; 
                    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
                }}
            </style>
        </head>
        <body>
            <div class="action-board">
                <h2>🚨 오늘의 핵심 액션 플랜</h2>
                <p><strong>감정을 철저히 배제하고 시스템의 신호를 따릅니다. 아래 본문의 시그널을 확인하고 즉시 포트폴리오를 리밸런싱하세요.</strong></p>
            </div>

            <div class="content-area">
                {styled_text}
            </div>
        </body>
        </html>
        """
        
        # index.html 파일 생성 및 저장
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print("✅ 웹 리포트(index.html) 빌드 완료!")

    # 8. 텔레그램 발송 (기존 텔레그램 발송 함수 연결)
    print("📨 텔레그램 메시지 발송 중...")
    send_telegram_message(df_today, exchange_rate) # 💡 필요에 따라 telegram_summary를 활용하도록 수정 가능
    
    print("🎯 모든 프로세스 정상 종료! 깃허브에서 확인해봐.")

if __name__ == "__main__":
    main()
