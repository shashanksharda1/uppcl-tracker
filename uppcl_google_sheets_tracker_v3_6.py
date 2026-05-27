#!/usr/bin/env python3
"""
UPPCL Tracker - TIMEZONE DEBUG
Detailed IST vs UTC analysis
"""
import json
import os
import logging
import time
import re
import subprocess
from datetime import datetime, timedelta
import pytz

from flask import Flask, jsonify
import gspread
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class UPPCLTracker:
    def __init__(self, username, password, sheet_name):
        self.username = username
        self.password = password
        self.sheet_name = sheet_name
        self.gs = None
        self.worksheets = {}
        self.driver = None

    def init_google_sheets(self):
        logger.info("[*] Initializing Google Sheets...")
        try:
            service_account_json = os.environ.get('SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                raise ValueError("SERVICE_ACCOUNT_JSON environment variable not set")

            service_account_info = json.loads(service_account_json)
            credentials = Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
            credentials.refresh(Request())
            self.gs = gspread.authorize(credentials)
            spreadsheet = self.gs.open(self.sheet_name)
            self._setup_worksheets(spreadsheet)
            logger.info("[+] Google Sheets ready!")
        except Exception as e:
            logger.error(f"[!] Google Sheets error: {e}")
            raise

    def _setup_worksheets(self, spreadsheet):
        sheet_names = {'today': 'Today', 'this_month': 'This Month', 'last_month': 'Last Month'}
        try:
            existing_sheets = {ws.title: ws for ws in spreadsheet.worksheets()}
            for key, name in sheet_names.items():
                if name not in existing_sheets:
                    ws = spreadsheet.add_worksheet(title=name, rows=2000, cols=10)
                    self._add_headers(ws)
                else:
                    ws = existing_sheets[name]
                self.worksheets[key] = ws
        except Exception as e:
            logger.error(f"[!] Worksheet setup error: {e}")
            raise

    def _add_headers(self, worksheet):
        headers = ['Timestamp (IST)', 'Hour (IST)', 'Current Day Units (kWh)', 'Hourly Consumption (kWh)',
                   'Last Hour Units (kWh)', 'Benchmark (3-day avg)', 'Above Benchmark?',
                   'Last Reading Time', 'Account Balance (Rs)', 'Source']
        worksheet.append_row(headers)

    def debug_timezones(self):
        """CRITICAL: Debug all timezone calculations"""
        logger.info("\n" + "="*80)
        logger.info("TIMEZONE DEBUG - CRITICAL ANALYSIS")
        logger.info("="*80)
        
        # Get all timezone representations
        utc_now = datetime.utcnow()
        ist_manual = utc_now + timedelta(hours=5, minutes=30)
        
        # Using pytz
        utc_tz = pytz.UTC
        ist_tz = pytz.timezone('Asia/Kolkata')
        
        utc_aware = utc_tz.localize(utc_now)
        ist_aware = utc_aware.astimezone(ist_tz)
        
        logger.info("[DEBUG] METHOD 1: datetime.utcnow() + timedelta(hours=5, minutes=30)")
        logger.info(f"        UTC:  {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"        IST:  {ist_manual.strftime('%Y-%m-%d %H:%M:%S')}")
        
        logger.info("[DEBUG] METHOD 2: pytz.timezone('Asia/Kolkata')")
        logger.info(f"        UTC:  {utc_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"        IST:  {ist_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        logger.info("[DEBUG] COMPARISON:")
        logger.info(f"        Method 1 hour: {ist_manual.hour} | Method 2 hour: {ist_aware.hour}")
        
        if ist_manual.hour != ist_aware.hour:
            logger.error(f"[!] ⚠️  TIMEZONE MISMATCH! {ist_manual.hour} vs {ist_aware.hour}")
        else:
            logger.info(f"[+] ✓ Timezones match: Both show {ist_manual.hour}")
        
        logger.info("[DEBUG] MIDNIGHT CHECK:")
        logger.info(f"        ist_manual.hour < 6? {ist_manual.hour < 6}")
        logger.info(f"        ist_aware.hour < 6? {ist_aware.hour < 6}")
        
        logger.info("="*80 + "\n")
        
        return ist_manual, ist_aware

    def setup_chrome_driver(self):
        logger.info("[*] Setting up Chrome WebDriver...")
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
            chromedriver_bin = result.stdout.strip()
            
            chrome_result = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
            if chrome_result.returncode == 0:
                chrome_options.binary_location = chrome_result.stdout.strip()

            service = Service(chromedriver_bin)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("[+] Chrome WebDriver ready")
        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            raise

    def solve_captcha(self):
        logger.info("[*] Solving captcha...")
        try:
            captcha_div = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.ID, "captchaText"))
            )
            
            data_answer = captcha_div.get_attribute('data-answer')
            
            if data_answer and data_answer.strip():
                logger.info(f"[+] Using data-answer: '{data_answer}'")
                captcha_answer = data_answer.strip()
            else:
                text_via_js = self.driver.execute_script(
                    "return document.getElementById('captchaText').textContent.trim();"
                )
                logger.info(f"[+] Using textContent: '{text_via_js}'")
                captcha_answer = text_via_js
            
            captcha_input = self.driver.find_element(By.ID, "captchaInput")
            captcha_input.clear()
            captcha_input.send_keys(captcha_answer)
            
            logger.info(f"[+] Sent captcha: '{captcha_answer}'")
            time.sleep(2)
            return True
        except Exception as e:
            logger.warning(f"[*] Captcha error: {e}")
            return True

    def login(self):
        try:
            logger.info("[*] Logging in...")
            self.driver.get("https://uppclmp.myxenius.com/login.html")

            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "name"))
            )
            username_field.send_keys(self.username)

            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(self.password)

            self.solve_captcha()
            time.sleep(1)
            
            try:
                alert = WebDriverWait(self.driver, 1).until(EC.alert_is_present())
                alert.dismiss()
                time.sleep(1)
            except:
                pass

            submit_button = self.driver.find_element(By.ID, "submitBtn")
            submit_button.click()
            
            time.sleep(2)
            
            try:
                alert = WebDriverWait(self.driver, 1).until(EC.alert_is_present())
                alert.dismiss()
                time.sleep(2)
                return False
            except:
                pass

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )

            logger.info("[+] Login successful!")
            return True

        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            return False

    def extract_current_day_units(self):
        try:
            # CRITICAL: Use the SAME timezone method as the skip check!
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            day_of_month = ist_now.day
            
            logger.info(f"[DEBUG] Extracting for day {day_of_month} (IST hour: {ist_now.hour})")
            
            script = """
            var chart = Highcharts.charts[0];
            if (chart && chart.series && chart.series.length > 0) {
                var seriesData = chart.series[0].data;
                var dayIndex = arguments[0] - 1;
                if (seriesData && seriesData[dayIndex]) {
                    return seriesData[dayIndex].y;
                }
            }
            return null;
            """
            units = self.driver.execute_script(script, day_of_month)
            if units:
                logger.info(f"[+] Units: {units}")
                return float(units)
            return 0.0
        except Exception as e:
            logger.error(f"[!] Extraction error: {e}")
            return 0.0

    def extract_last_reading(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            match = re.search(r'Last Reading As on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', soup.get_text())
            return match.group(1) if match else "N/A"
        except:
            return "N/A"

    def extract_balance(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            match = re.search(r'Grid Bal:\s*Rs\.\s*([\d,]+\.?\d*)', soup.get_text())
            return match.group(1) if match else "N/A"
        except:
            return "N/A"

    def extract_source(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            h1 = soup.find('h1', class_='clearfix')
            if h1:
                match = re.search(r'Source\s*:\s*(\w+)', h1.get_text(), re.IGNORECASE)
                if match:
                    return match.group(1)
            return "Unknown"
        except:
            return "Unknown"

    def calculate_hourly_consumption(self, current_units, last_hour_units):
        if last_hour_units is None or last_hour_units == 0:
            return 0.0
        return max(0.0, current_units - last_hour_units)

    def get_last_hour_units(self):
        try:
            all_rows = self.worksheets['today'].get_all_values()
            if len(all_rows) > 1:
                return float(all_rows[-1][2]) if all_rows[-1][2] else 0.0
            return 0.0
        except:
            return 0.0

    def calculate_benchmark(self, hour_of_day):
        try:
            this_month_ws = self.worksheets['this_month']
            consumptions = []
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            current_date = ist_now.date()

            for days_back in range(1, 4):
                check_date = current_date - timedelta(days=days_back)
                for row in this_month_ws.get_all_values()[1:]:
                    if row and len(row) > 3:
                        try:
                            row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date()
                            row_hour = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').hour
                            if row_date == check_date and row_hour == hour_of_day:
                                consumption = float(row[3]) if row[3] else 0.0
                                if consumption > 0:
                                    consumptions.append(consumption)
                        except:
                            pass

            return round(sum(consumptions) / len(consumptions), 2) if consumptions else None
        except Exception as e:
            logger.error(f"[!] Benchmark error: {e}")
            return None

    def add_row_to_today_sheet(self, timestamp, hour, current_units, hourly_consumption, last_hour_units, benchmark, last_reading, balance, source):
        try:
            row = [timestamp, hour, current_units, hourly_consumption, last_hour_units,
                   benchmark if benchmark else "N/A", "YES" if benchmark and hourly_consumption > benchmark else "NO",
                   last_reading, balance, source]
            self.worksheets['today'].append_row(row)
            logger.info("[+] Row added to Today tab")
            return True
        except Exception as e:
            logger.error(f"[!] Append error: {e}")
            return False

    def archive_old_data(self):
        try:
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            today_date = ist_now.date()
            
            today_ws = self.worksheets['today']
            this_month_ws = self.worksheets['this_month']
            all_rows = today_ws.get_all_values()
            
            rows_to_move = []
            rows_to_keep = [all_rows[0]]
            
            for row in all_rows[1:]:
                if row and len(row) > 0:
                    try:
                        if datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date() < today_date:
                            rows_to_move.append(row)
                        else:
                            rows_to_keep.append(row)
                    except:
                        rows_to_keep.append(row)
            
            if rows_to_move:
                for row in rows_to_move:
                    this_month_ws.append_row(row)
                today_ws.clear()
                today_ws.append_rows(rows_to_keep)
        except Exception as e:
            logger.error(f"[!] Archive error: {e}")

    def run_once(self):
        try:
            logger.info("\n" + "="*80)
            logger.info("UPPCL TRACKER RUN - TIMEZONE DEBUG")
            logger.info("="*80)
            
            # DEBUG TIMEZONES FIRST!
            ist_manual, ist_aware = self.debug_timezones()
            
            self.setup_chrome_driver()

            if not self.login():
                logger.error("[!] Login failed")
                return False

            time.sleep(2)

            # Use the same ist_now as in debug
            ist_now = ist_manual
            timestamp = ist_now.strftime('%Y-%m-%d %H:%M:%S')
            hour = ist_now.hour

            logger.info(f"[*] IST Time: {timestamp}, Hour: {hour}")

            current_units = self.extract_current_day_units()
            last_hour_units = self.get_last_hour_units()
            hourly_consumption = self.calculate_hourly_consumption(current_units, last_hour_units)
            benchmark = self.calculate_benchmark(hour)
            last_reading = self.extract_last_reading()
            balance = self.extract_balance()
            source = self.extract_source()

            success = self.add_row_to_today_sheet(
                timestamp, hour, current_units, hourly_consumption,
                last_hour_units, benchmark, last_reading, balance, source
            )

            if success:
                self.archive_old_data()
                logger.info("[+] Tracker completed successfully")

            return success

        except Exception as e:
            logger.error(f"[!] Tracker error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

        finally:
            if self.driver:
                self.driver.quit()
            logger.info("="*80 + "\n")


@app.route('/', methods=['GET', 'POST'])
def trigger():
    logger.info("[*] HTTP request received")
    try:
        tracker = UPPCLTracker(
            os.getenv('UPPCL_USERNAME'),
            os.getenv('UPPCL_PASSWORD'),
            os.getenv('GOOGLE_SHEETS_NAME', 'UPPCL Consumption Tracker')
        )

        tracker.init_google_sheets()
        success = tracker.run_once()

        if success:
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'error'}), 500

    except Exception as e:
        logger.error(f"[!] Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)