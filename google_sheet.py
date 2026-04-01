import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import pandas as pd
from datetime import datetime

class GoogleSheetManager:
    def __init__(self, spreadsheet_id):
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_json = os.environ.get('GCP_CREDENTIALS')
        if not creds_json:
            raise ValueError("❌ GCP_CREDENTIALS 환경 변수가 없어!")
        
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        self.client = gspread.authorize(creds)
        self.doc = self.client.open_by_key(spreadsheet_id)

   def get_sheet_data(self, sheet_name):
        """특정 탭(시트)의 데이터를 가져옴 (빈칸/중복 헤더 에러 방지)"""
        try:
            worksheet = self.doc.worksheet(sheet_name)
            # get_all_records() 대신 get_all_values()를 써서 헤더 에러를 피함
            values = worksheet.get_all_values()
            
            if not values:
                return pd.DataFrame(), worksheet
                
            # 첫 번째 줄을 헤더로, 나머지를 데이터로 사용
            df = pd.DataFrame(values[1:], columns=values[0])
            
            # 빈 문자열 헤더 처리 (중복 방지)
            df.columns = [str(col).strip() if str(col).strip() != '' else f"Unnamed_{i}" for i, col in enumerate(df.columns)]
            
            return df, worksheet
            
        except gspread.exceptions.WorksheetNotFound:
            print(f"⚠️ '{sheet_name}' 탭을 찾을 수 없어. 구글 시트에 탭을 만들어줘!")
            return pd.DataFrame(), None

    def update_sheet(self, worksheet, df):
        """특정 탭(시트)의 데이터를 통째로 덮어씌움"""
        if worksheet is None or df.empty: return
        df.fillna('', inplace=True)
        update_data = [df.columns.tolist()] + df.values.tolist()
        worksheet.clear() # 깔끔하게 지우고 새 데이터로 덮어쓰기
        worksheet.update(values=update_data, range_name='A1')

    def get_latest_history(self):
        """History 탭에서 가장 최근(어제) 기록을 가져옴"""
        df, _ = self.get_sheet_data('History')
        if not df.empty:
            return df.iloc[-1] # 마지막 행 반환
        return None

    def append_to_history(self, row_data_dict):
        """History 탭에 오늘 날짜의 자산 요약 데이터를 한 줄 추가"""
        try:
            worksheet = self.doc.worksheet('History')
            # 시트가 비어있으면 헤더(키값) 먼저 추가
            if len(worksheet.get_all_values()) == 0:
                worksheet.append_row(list(row_data_dict.keys()))
            worksheet.append_row(list(row_data_dict.values()))
            print("✅ History 탭 데이터 누적 완료!")
        except Exception as e:
            print(f"⚠️ History 탭 업데이트 실패: {e}")
