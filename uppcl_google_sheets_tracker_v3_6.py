#!/usr/bin/env python3
"""
UPPCL Tracker v3.9 - TIMING FIX FOR CAPTCHA
Added delay and validation before submit
"""
import json
import os
import logging
import time
import re
import subprocess
from datetime import datetime, timedelta

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
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )

            credentials.refresh(Request())
            logger.info("[+] Credentials loaded")

            self.gs = gspread.authorize(credentials)
            spreadsheet = self.gs.open(self.sheet_name)
            logger.info(f"[+] Opened spreadsheet: {self.sheet_name}")

            self._setup_worksheets(spreadsheet)
            logger.info("[+] Google Sheets ready!")

        except Exception as e:
            logger.error(f"[!] Google Sheets error: {e}")
            raise

    def _setup_worksheets(self, spreadsheet):
        today = datetime.now().date()
        today_str = today.strftime('%Y-%m-%d')
        this_month_str = today.strftime('%B %Y')
        last_month = today - timedelta(days=today.day)
        last_month_str = last_month.strftime('%B %Y')

        sheet_names = {
            'today': f"Today ({today_str})",
            'this_month': f"This Month ({this_month_str})",
            'last_month': f"Last Month ({last_month_str})"
        }

        try:
            existing_sheets = [ws.title for ws in spreadsheet.worksheets()]

            for key, name in sheet_names.items():
                if name not in existing_sheets:
                    ws = spreadsheet.add_worksheet(title=name, rows=1000, cols=10)
                    self._add_headers(ws)
                    logger.info(f"[+] Created worksheet: {name}")
                else:
                    ws = spreadsheet.worksheet(name)
                    logger.info(f"[+] Using existing worksheet: {name}")

                self.worksheets[key] = ws

        except Exception as e:
            logger.error(f"[!] Worksheet setup error: {e}")
            raise

    def _add_headers(self, worksheet):
        headers = [
            'Timestamp', 'Hour', 'Current Day Units (kWh)', 'Hourly Consumption (kWh)',
            'Last Hour Units (kWh)', 'Benchmark (3-day avg)', 'Above Benchmark?',
            'Last Reading Time', 'Account Balance (Rs)', 'Source'
        ]
        worksheet.append_row(headers)
        logger.info("[+] Headers added")

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
            if result.returncode != 0:
                raise Exception("ChromeDriver not found")

            chromedriver_bin = result.stdout.strip()
            logger.info(f"[*] ChromeDriver: {chromedriver_bin}")

            chrome_result = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
            if chrome_result.returncode == 0:
                chrome_bin = chrome_result.stdout.strip()
                chrome_options.binary_location = chrome_bin
                logger.info(f"[*] Chrome: {chrome_bin}")

            service = Service(chromedriver_bin)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("[+] Chrome WebDriver ready")

        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            raise

    def solve_captcha(self):
        """Solve captcha and wait for validation"""
        logger.info("[*] Solving captcha...")
        try:
            captcha_div = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.ID, "captchaText"))
            )
            
            logger.info("[+] Captcha element found")
            
            data_answer = captcha_div.get_attribute('data-answer')
            
            logger.info(f"[DEBUG] data-answer: {data_answer}")
            
            if data_answer and data_answer.strip():
                logger.info(f"[+] Captcha answer found: {data_answer}")
                
                captcha_input = self.driver.find_element(By.ID, "captchaInput")
                captcha_input.clear()
                captcha_input.send_keys(data_answer)
                
                logger.info(f"[+] Sent captcha answer: {data_answer}")
                
                # FIXED: Wait longer for captcha validation to complete
                logger.info("[*] Waiting 2 seconds for captcha validation...")
                time.sleep(2)
                
                return True
            else:
                logger.warning("[*] Captcha element found but answer is empty")
                return True
                
        except Exception as e:
            logger.warning(f"[*] Captcha not found or error: {e}")
            return True

    def login(self):
        """Login to UPPCL portal"""
        try:
            logger.info("[*] Logging in...")
            self.driver.get("https://uppclmp.myxenius.com/login.html")

            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "name"))
            )
            username_field.send_keys(self.username)
            logger.info("[*] Username entered")

            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(self.password)
            logger.info("[*] Password entered")

            # Solve captcha BEFORE dismissing any alerts
            self.solve_captcha()
            logger.info("[*] Captcha solve complete")
            
            # CRITICAL: Dismiss ANY alert BEFORE clicking submit
            logger.info("[*] Waiting 1 second, then checking for pre-submit alerts...")
            time.sleep(1)
            
            try:
                alert = WebDriverWait(self.driver, 1).until(EC.alert_is_present())
                logger.info("[*] Pre-submit alert detected, dismissing...")
                alert.dismiss()
                logger.info("[*] Alert dismissed")
                time.sleep(1)
            except:
                logger.info("[*] No pre-submit alert found")

            # Now click submit
            logger.info("[*] Clicking submit button...")
            submit_button = self.driver.find_element(By.ID, "submitBtn")
            submit_button.click()
            logger.info("[*] Submit button clicked")
            
            # Wait a moment, then check for post-submit alert
            time.sleep(1)
            
            try:
                alert = WebDriverWait(self.driver, 1).until(EC.alert_is_present())
                logger.warning(f"[*] Post-submit alert detected: {alert.text}")
                alert.dismiss()
                logger.info("[*] Alert dismissed, retrying...")
                time.sleep(2)
            except:
                logger.info("[*] No post-submit alert found")

            # Wait for page to load
            logger.info("[*] Waiting for chart to load...")
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )

            logger.info("[+] Login successful!")
            return True

        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            return False

    def extract_source(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            h1 = soup.find('h1', class_='clearfix')
            if h1:
                text = h1.get_text()
                match = re.search(r'Source\s*:\s*(\w+)', text, re.IGNORECASE)
                if match:
                    source = match.group(1)
                    logger.info(f"[+] Source: {source}")
                    return source
            return "Unknown"
        except Exception as e:
            logger.error(f"[!] Source error: {e}")
            return "Unknown"

    def extract_current_day_units(self):
        try:
            day_of_month = datetime.now().day
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
                logger.info(f"[+] Units: {units} kWh")
                return float(units)
            return 0.0
        except Exception as e:
            logger.error(f"[!] Units error: {e}")
            return 0.0

    def extract_last_reading(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            text = soup.get_text()
            match = re.search(r'Last Reading As on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', text)
            if match:
                reading_time = match.group(1)
                logger.info(f"[+] Last reading: {reading_time}")
                return reading_time
            return "N/A"
        except Exception as e:
            logger.error(f"[!] Reading error: {e}")
            return "N/A"

    def extract_balance(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            text = soup.get_text()
            match = re.search(r'Updated Balance\s*:\s*Grid Bal:\s*Rs\.\s*([\d,]+\.?\d*)', text)
            if match:
                balance = match.group(1)
                logger.info(f"[+] Balance: Rs. {balance}")
                return balance
            return "N/A"
        except Exception as e:
            logger.error(f"[!] Balance error: {e}")
            return "N/A"

    def calculate_hourly_consumption(self, current_units, last_hour_units):
        if last_hour_units is None or last_hour_units == 0:
            return 0.0
        consumption = current_units - last_hour_units
        if consumption < 0:
            return 0.0
        logger.info(f"[+] Consumption: {consumption} kWh")
        return consumption

    def get_last_hour_units(self):
        try:
            today_ws = self.worksheets['today']
            all_rows = today_ws.get_all_values()
            if len(all_rows) > 1:
                last_row = all_rows[-1]
                last_units = float(last_row[2]) if last_row[2] else 0.0
                logger.info(f"[*] Last hour: {last_units} kWh")
                return last_units
            logger.info("[*] No previous data")
            return 0.0
        except Exception as e:
            logger.error(f"[!] Last hour error: {e}")
            return 0.0

    def calculate_benchmark(self, hour_of_day):
        try:
            this_month_ws = self.worksheets['this_month']
            consumptions = []
            current_date = datetime.now().date()

            for days_back in range(1, 4):
                check_date = current_date - timedelta(days=days_back)
                try:
                    all_rows = this_month_ws.get_all_values()
                    for row in all_rows[1:]:
                        if row and len(row) > 0:
                            try:
                                row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date()
                                row_hour = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').hour
                                if row_date == check_date and row_hour == hour_of_day:
                                    hourly_consumption = float(row[3]) if len(row) > 3 and row[3] else 0.0
                                    if hourly_consumption > 0:
                                        consumptions.append(hourly_consumption)
                            except:
                                continue
                except:
                    pass

            if consumptions:
                benchmark = sum(consumptions) / len(consumptions)
                logger.info(f"[+] Benchmark: {benchmark:.2f} kWh")
                return round(benchmark, 2)
            else:
                logger.info(f"[*] No benchmark data")
                return None

        except Exception as e:
            logger.error(f"[!] Benchmark error: {e}")
            return None

    def add_row_to_today_sheet(self, timestamp, hour, current_units, hourly_consumption,
                               last_hour_units, benchmark, last_reading, balance, source):
        try:
            utc_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            ist_time = utc_time + timedelta(hours=5, minutes=30)
            ist_timestamp = ist_time.strftime('%Y-%m-%d %H:%M:%S')
            ist_hour = ist_time.hour

            above_benchmark = "YES" if benchmark and hourly_consumption > benchmark else "NO"

            row = [
                ist_timestamp, ist_hour, current_units, hourly_consumption,
                last_hour_units, benchmark if benchmark else "N/A", above_benchmark,
                last_reading, balance, source
            ]

            today_ws = self.worksheets['today']
            today_ws.append_row(row)
            logger.info("[+] Row added to Google Sheets")

            return True

        except Exception as e:
            logger.error(f"[!] Append error: {e}")
            return False

    def archive_old_data(self):
        try:
            today_ws = self.worksheets['today']
            today = datetime.now().date()
            all_rows = today_ws.get_all_values()

            if len(all_rows) > 1:
                rows_to_move = []
                rows_to_keep = [all_rows[0]]

                for row in all_rows[1:]:
                    if row and len(row) > 0:
                        try:
                            row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date()
                            if row_date < today:
                                rows_to_move.append(row)
                            else:
                                rows_to_keep.append(row)
                        except:
                            rows_to_keep.append(row)

                if rows_to_move:
                    this_month_ws = self.worksheets['this_month']
                    for row in rows_to_move:
                        this_month_ws.append_row(row)
                    logger.info(f"[+] Archived {len(rows_to_move)} rows")

                    if len(rows_to_keep) > 1:
                        today_ws.clear()
                        today_ws.append_rows(rows_to_keep)

        except Exception as e:
            logger.error(f"[!] Archive error: {e}")

    def run_once(self):
        try:
            logger.info("[*] Starting tracker...")
            self.setup_chrome_driver()

            if not self.login():
                logger.error("[!] Login failed")
                return False

            time.sleep(2)

            utc_now = datetime.utcnow()
            timestamp = utc_now.strftime('%Y-%m-%d %H:%M:%S')

            ist_now = utc_now + timedelta(hours=5, minutes=30)
            hour = ist_now.hour
            logger.info(f"[*] Time: {ist_now.strftime('%Y-%m-%d %H:%M:%S IST')}")

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
            return False

        finally:
            if self.driver:
                self.driver.quit()


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
            return jsonify({'status': 'success', 'message': 'Tracker executed'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Tracker failed'}), 500

    except Exception as e:
        logger.error(f"[!] Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    logger.info(f"[*] Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)