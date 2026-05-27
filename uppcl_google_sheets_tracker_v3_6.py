#!/usr/bin/env python3
"""
UPPCL Tracker - CHART DEBUG
Capture page state and element details when extraction fails
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
        sheet_names = {
            'today': 'Today',
            'this_month': 'This Month',
            'last_month': 'Last Month'
        }

        try:
            existing_sheets = {ws.title: ws for ws in spreadsheet.worksheets()}

            for key, name in sheet_names.items():
                if name not in existing_sheets:
                    ws = spreadsheet.add_worksheet(title=name, rows=2000, cols=10)
                    self._add_headers(ws)
                    logger.info(f"[+] Created worksheet: {name}")
                else:
                    ws = existing_sheets[name]
                    logger.info(f"[+] Using existing worksheet: {name}")

                self.worksheets[key] = ws

        except Exception as e:
            logger.error(f"[!] Worksheet setup error: {e}")
            raise

    def _add_headers(self, worksheet):
        headers = [
            'Timestamp (IST)', 'Hour (IST)', 'Current Day Units (kWh)', 'Hourly Consumption (kWh)',
            'Last Hour Units (kWh)', 'Benchmark (3-day avg)', 'Above Benchmark?',
            'Last Reading Time', 'Account Balance (Rs)', 'Source'
        ]
        worksheet.append_row(headers)

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

            chrome_result = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
            if chrome_result.returncode == 0:
                chrome_bin = chrome_result.stdout.strip()
                chrome_options.binary_location = chrome_bin

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

            logger.info("[*] Waiting for chart container...")
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )

            logger.info("[+] Login successful!")
            return True

        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            return False

    def debug_chart_state(self):
        """Debug what's in the page and chart"""
        logger.info("[DEBUG] ========== PAGE STATE DEBUG ==========")
        
        try:
            # Check page title
            title = self.driver.title
            logger.info(f"[DEBUG] Page title: {title}")
            
            # Check for chart container
            try:
                chart_container = self.driver.find_element(By.ID, "chartContainerHourly")
                logger.info(f"[DEBUG] Chart container found: {chart_container.is_displayed()}")
            except:
                logger.warning("[DEBUG] Chart container NOT found")
            
            # Check for Highcharts
            charts_count = self.driver.execute_script("return Highcharts.charts.length;")
            logger.info(f"[DEBUG] Highcharts instances: {charts_count}")
            
            # Check series data
            try:
                series_data = self.driver.execute_script("""
                    if (Highcharts.charts.length > 0) {
                        var chart = Highcharts.charts[0];
                        if (chart && chart.series && chart.series.length > 0) {
                            return {
                                seriesCount: chart.series.length,
                                firstSeriesLength: chart.series[0].data.length,
                                firstSeriesName: chart.series[0].name,
                                firstValue: chart.series[0].data[0] ? chart.series[0].data[0].y : null
                            };
                        }
                    }
                    return null;
                """)
                if series_data:
                    logger.info(f"[DEBUG] Series data: {series_data}")
                else:
                    logger.warning("[DEBUG] No series data found in chart")
            except Exception as e:
                logger.warning(f"[DEBUG] Could not check series: {e}")
            
            # Check page HTML for "Current Month Consumption"
            page_source = self.driver.page_source
            if "Current Month Consumption" in page_source:
                logger.info("[DEBUG] ✓ 'Current Month Consumption' text found on page")
            else:
                logger.warning("[DEBUG] ✗ 'Current Month Consumption' text NOT found")
            
            # Check for month label
            if "May-2026" in page_source or "2026" in page_source:
                logger.info("[DEBUG] ✓ Month/year label found on page")
            else:
                logger.warning("[DEBUG] ✗ Month/year label NOT found")
            
            # List all divs with "chart" in id
            chart_elements = self.driver.find_elements(By.XPATH, "//*[contains(@id, 'chart')]")
            logger.info(f"[DEBUG] Found {len(chart_elements)} elements with 'chart' in id:")
            for elem in chart_elements[:5]:  # First 5
                logger.info(f"[DEBUG]   - ID: {elem.get_attribute('id')}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Error during debug: {e}")
        
        logger.info("[DEBUG] ======================================")

    def take_screenshot(self, name="debug"):
        """Take a screenshot for inspection"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"/tmp/{name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            logger.info(f"[DEBUG] Screenshot saved: {filename}")
            return filename
        except Exception as e:
            logger.warning(f"[!] Screenshot error: {e}")
            return None

    def extract_current_day_units(self):
        """Extract with detailed debugging"""
        try:
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            day_of_month = ist_now.day
            
            logger.info(f"[*] Extracting units for day {day_of_month}...")
            
            # First debug the chart state
            self.debug_chart_state()
            
            # Try extraction
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
            else:
                logger.warning(f"[!] Could not extract units for day {day_of_month}")
                logger.warning("[!] Possible reasons:")
                logger.warning("    - Chart not fully loaded")
                logger.warning("    - Day index out of range")
                logger.warning("    - Data structure different than expected")
                
                # Take screenshot for manual inspection
                self.take_screenshot("extraction_failed")
                return 0.0
                
        except Exception as e:
            logger.error(f"[!] Units error: {e}")
            self.take_screenshot("extraction_error")
            return 0.0

    def extract_source(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            h1 = soup.find('h1', class_='clearfix')
            if h1:
                text = h1.get_text()
                match = re.search(r'Source\s*:\s*(\w+)', text, re.IGNORECASE)
                if match:
                    return match.group(1)
            return "Unknown"
        except:
            return "Unknown"

    def extract_last_reading(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            text = soup.get_text()
            match = re.search(r'Last Reading As on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', text)
            if match:
                return match.group(1)
            return "N/A"
        except:
            return "N/A"

    def extract_balance(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            text = soup.get_text()
            match = re.search(r'Updated Balance\s*:\s*Grid Bal:\s*Rs\.\s*([\d,]+\.?\d*)', text)
            if match:
                return match.group(1)
            return "N/A"
        except:
            return "N/A"

    def calculate_hourly_consumption(self, current_units, last_hour_units):
        if last_hour_units is None or last_hour_units == 0:
            return 0.0
        consumption = current_units - last_hour_units
        return max(0.0, consumption)

    def get_last_hour_units(self):
        try:
            today_ws = self.worksheets['today']
            all_rows = today_ws.get_all_values()
            if len(all_rows) > 1:
                last_row = all_rows[-1]
                last_units = float(last_row[2]) if last_row[2] else 0.0
                return last_units
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
                return round(sum(consumptions) / len(consumptions), 2)
            return None

        except Exception as e:
            logger.error(f"[!] Benchmark error: {e}")
            return None

    def add_row_to_today_sheet(self, timestamp, hour, current_units, hourly_consumption,
                               last_hour_units, benchmark, last_reading, balance, source):
        try:
            row = [
                timestamp, hour, current_units, hourly_consumption,
                last_hour_units, benchmark if benchmark else "N/A", 
                "YES" if benchmark and hourly_consumption > benchmark else "NO",
                last_reading, balance, source
            ]

            today_ws = self.worksheets['today']
            today_ws.append_row(row)
            logger.info("[+] Row added to Today tab")
            return True

        except Exception as e:
            logger.error(f"[!] Append error: {e}")
            return False

    def archive_old_data(self):
        logger.info("[*] Checking for data to archive...")
        try:
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            today_date = ist_now.date()
            current_month = ist_now.month
            current_year = ist_now.year
            
            today_ws = self.worksheets['today']
            this_month_ws = self.worksheets['this_month']
            
            all_rows = today_ws.get_all_values()
            rows_to_move = []
            rows_to_keep = [all_rows[0]]
            
            for row in all_rows[1:]:
                if row and len(row) > 0:
                    try:
                        row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date()
                        if row_date < today_date:
                            rows_to_move.append(row)
                        else:
                            rows_to_keep.append(row)
                    except:
                        rows_to_keep.append(row)
            
            if rows_to_move:
                logger.info(f"[*] Moving {len(rows_to_move)} rows to This Month...")
                for row in rows_to_move:
                    this_month_ws.append_row(row)
                today_ws.clear()
                today_ws.append_rows(rows_to_keep)
                logger.info("[+] Day archived")
        
        except Exception as e:
            logger.error(f"[!] Archive error: {e}")

    def run_once(self):
        try:
            logger.info("\n" + "="*80)
            logger.info("TRACKER RUN STARTED")
            logger.info("="*80)
            
            self.setup_chrome_driver()

            if not self.login():
                logger.error("[!] Login failed")
                return False

            time.sleep(3)  # Extra time for page to settle
            
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            timestamp = ist_now.strftime('%Y-%m-%d %H:%M:%S')
            hour = ist_now.hour

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
            logger.info("="*80)
            logger.info("TRACKER RUN ENDED")
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
            return jsonify({'status': 'success', 'message': 'Tracker executed'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Tracker failed'}), 500

    except Exception as e:
        logger.error(f"[!] Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)