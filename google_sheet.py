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
        self.sheet = self.doc.sheet1

    def get_data(self):
        df = pd.DataFrame(self.sheet.get_all_records())
        df.columns = df.columns.str.strip()
        return df

    def update_main_sheet(self, df):
        df.fillna('', inplace=True)
        update_data = [df.columns.tolist()] + df.values.tolist()
        self.sheet.update(values=update_data, range_name='A1')

    def append_history(self, df):
        # 대소문자 상관없이 History 시트 찾기
        try:
            history_sheet = self.doc.worksheet('History')
        except gspread.exceptions.WorksheetNotFound:
            try:
                history_sheet = self.doc.worksheet('history')
            except gspread.exceptions.WorksheetNotFound:
                print("⚠️ History 탭을 찾을 수 없어서 히스토리 저장은 건너뛸게.")
                return

        df_history = df.copy()
        df_history.insert(0, '기록일시', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # 시트가 비어있으면 헤더(컬럼명) 추가
        if len(history_sheet.get_all_values()) == 0:
            history_sheet.append_row(df_history.columns.tolist())
            
        history_sheet.append_rows(df_history.values.tolist())
        print("✅ History 탭 데이터 누적 완료!")