#!/usr/bin/env python3
"""
UPPCL Tracker v3.9 - Based on last working v3.7
Only 2 changes made on top of working code:

CHANGE 1: extract_current_day_units()
  - OLD: Highcharts.charts[0]  ← hardcoded, can be null or previous-month chart
  - NEW: Walk Highcharts.charts[], find first non-null = always current month chart
  - Also returns debug info (chartIndex, barIndex, source) in logs

CHANGE 2: get_last_hour_units()
  - OLD: Returns all_rows[-1] blindly ← at midnight returns YESTERDAY's last row
  - NEW: Filters rows by today's IST date string first, then picks last matching row
         If no row for today yet → returns 0.0 (correct: fresh day start)

Everything else is IDENTICAL to the last working v3.7 code.
"""

import json
import os
import logging
import time
import re
import subprocess
import traceback
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
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

IST = pytz.timezone('Asia/Kolkata')


class UPPCLTracker:

    def __init__(self, username, password, sheet_name):
        self.username = username
        self.password = password
        self.sheet_name = sheet_name
        self.gs = None
        self.worksheets = {}
        self.driver = None

    # =========================================================
    # TIMEZONE HELPERS
    # =========================================================

    def get_ist_now(self):
        return datetime.now(IST)

    # =========================================================
    # GOOGLE SHEETS  (unchanged from v3.7)
    # =========================================================

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

            self.gs = gspread.authorize(credentials)

            spreadsheet = self.gs.open(self.sheet_name)

            self._setup_worksheets(spreadsheet)

            logger.info("[+] Google Sheets ready!")

        except Exception as e:
            logger.error(f"[!] Google Sheets error: {e}")
            logger.error(traceback.format_exc())
            raise

    def _setup_worksheets(self, spreadsheet):

        sheet_names = {
            'today': 'Today',
            'this_month': 'This Month',
            'last_month': 'Last Month'
        }

        existing_sheets = {ws.title: ws for ws in spreadsheet.worksheets()}

        for key, name in sheet_names.items():

            if name not in existing_sheets:
                ws = spreadsheet.add_worksheet(
                    title=name,
                    rows=2000,
                    cols=10
                )
                self._add_headers(ws)
            else:
                ws = existing_sheets[name]

            self.worksheets[key] = ws

    def _add_headers(self, worksheet):

        headers = [
            'Timestamp (IST)',
            'Hour (IST)',
            'Current Day Units (kWh)',
            'Hourly Consumption (kWh)',
            'Last Hour Units (kWh)',
            'Benchmark (3-day avg)',
            'Above Benchmark?',
            'Last Reading Time',
            'Account Balance (Rs)',
            'Source'
        ]

        worksheet.append_row(headers)

    # =========================================================
    # CHROME DRIVER  (unchanged from v3.7)
    # =========================================================

    def setup_chrome_driver(self):

        logger.info("[*] Setting up Chrome WebDriver...")

        try:
            chrome_options = Options()

            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--window-size=1920,1080')

            chrome_options.add_argument(
                'user-agent=Mozilla/5.0 '
                '(Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 '
                '(KHTML, like Gecko) '
                'Chrome/125.0.0.0 Safari/537.36'
            )

            result = subprocess.run(
                ['which', 'chromedriver'],
                capture_output=True,
                text=True
            )

            chromedriver_bin = result.stdout.strip()

            chrome_result = subprocess.run(
                ['which', 'google-chrome'],
                capture_output=True,
                text=True
            )

            if chrome_result.returncode == 0:
                chrome_options.binary_location = chrome_result.stdout.strip()

            service = Service(chromedriver_bin)

            self.driver = webdriver.Chrome(
                service=service,
                options=chrome_options
            )

            self.driver.delete_all_cookies()

            logger.info("[+] Chrome WebDriver ready")

        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            logger.error(traceback.format_exc())
            raise

    # =========================================================
    # CAPTCHA  (unchanged from v3.7)
    # =========================================================

    def solve_captcha(self):

        logger.info("[*] Solving captcha...")

        try:
            captcha_div = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "captchaText"))
            )

            data_answer = captcha_div.get_attribute('data-answer')

            logger.info(f"[*] Captcha data-answer: {data_answer}")

            if data_answer and data_answer.strip():
                captcha_answer = data_answer.strip()
            else:
                captcha_answer = self.driver.execute_script(
                    "return document.getElementById('captchaText').textContent.trim();"
                )

            logger.info(f"[+] Captcha Answer: {captcha_answer}")

            captcha_input = self.driver.find_element(By.ID, "captchaInput")
            captcha_input.clear()
            captcha_input.send_keys(captcha_answer)

            time.sleep(2)

            return True

        except Exception as e:
            logger.error(f"[!] Captcha error: {e}")
            logger.error(traceback.format_exc())
            return False

    # =========================================================
    # DEBUG  (unchanged from v3.7)
    # =========================================================

    def save_debug_files(self, prefix="debug"):

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/tmp/{prefix}_{timestamp}.png"
            html_path = f"/tmp/{prefix}_{timestamp}.html"

            self.driver.save_screenshot(screenshot_path)

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)

            logger.error(f"[!] Screenshot saved: {screenshot_path}")
            logger.error(f"[!] HTML saved: {html_path}")

        except Exception as e:
            logger.error(f"[!] Failed saving debug files: {e}")

    # =========================================================
    # LOGIN  (unchanged from v3.7)
    # =========================================================

    def login(self):

        try:
            logger.info("[*] Opening login page...")

            self.driver.get("https://uppclmp.myxenius.com/login.html")

            logger.info(f"[*] Current URL: {self.driver.current_url}")

            username_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "name"))
            )

            password_field = self.driver.find_element(By.ID, "password")

            username_field.clear()
            username_field.send_keys(self.username)

            password_field.clear()
            password_field.send_keys(self.password)

            logger.info("[+] Username & password entered")

            captcha_success = self.solve_captcha()

            if not captcha_success:
                logger.error("[!] Captcha solve failed")
                self.save_debug_files("captcha_failure")
                return False

            submit_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "submitBtn"))
            )

            logger.info("[*] Clicking submit button...")

            time.sleep(2)

            submit_button.click()

            logger.info("[*] Submit clicked")

            time.sleep(5)

            # Check for alerts (login errors)
            try:
                alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                alert_text = alert.text
                logger.error(f"[!] LOGIN ALERT FOUND: {alert_text}")
                alert.accept()
                self.save_debug_files("login_alert")
                return False
            except TimeoutException:
                logger.info("[*] No alert detected")
            except Exception as e:
                logger.error(f"[!] Alert check failed: {e}")

            logger.info("[*] Waiting for dashboard...")

            WebDriverWait(self.driver, 25).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )

            logger.info("[+] LOGIN SUCCESSFUL!")

            return True

        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            logger.error(traceback.format_exc())
            logger.error(f"[!] Current URL: {self.driver.current_url}")
            self.save_debug_files("login_exception")
            return False

    # =========================================================
    # EXTRACTION
    # =========================================================

    def extract_current_day_units(self):
        """
        *** CHANGE 1 vs v3.7 ***

        OLD problem: var chart = Highcharts.charts[0]
          - Highcharts.charts[] can have null slots (destroyed charts)
          - charts[0] could be null, OR could be the previous-month chart
          - When null: JS returns null → Python returns 0.0 silently
          - When previous-month chart: returns wrong month's data

        FIX: Walk the array, pick first non-null entry = always current month.
             Fallback to last non-zero bar stays in the SAME chart object.
             Returns a result object so logs show exactly which chart/bar was used.
        """
        try:
            ist_now      = self.get_ist_now()
            day_of_month = ist_now.day

            logger.info(f"[*] IST day of month: {day_of_month}")

            script = """
                var dayIndex = arguments[0] - 1;  /* IST day is 1-based */

                /* ── Step 1: find first non-null chart = current month ── */
                var chart      = null;
                var chartIndex = -1;
                for (var i = 0; i < Highcharts.charts.length; i++) {
                    if (Highcharts.charts[i] != null) {
                        chart      = Highcharts.charts[i];
                        chartIndex = i;
                        break;
                    }
                }

                if (!chart || !chart.series || chart.series.length === 0) {
                    return {value: null, source: 'no_chart', chartIndex: chartIndex};
                }

                var data = chart.series[0].data;

                /* ── Step 2: use IST day index (primary) ── */
                if (dayIndex >= 0 && dayIndex < data.length &&
                        data[dayIndex] && data[dayIndex].y !== null) {
                    return {
                        value: data[dayIndex].y,
                        source: 'by_ist_day',
                        chartIndex: chartIndex,
                        barIndex: dayIndex
                    };
                }

                /* ── Step 3: fallback - last non-zero bar in SAME chart ── */
                for (var j = data.length - 1; j >= 0; j--) {
                    if (data[j] && data[j].y !== null && data[j].y > 0) {
                        return {
                            value: data[j].y,
                            source: 'fallback_last_bar',
                            chartIndex: chartIndex,
                            barIndex: j
                        };
                    }
                }

                return {value: null, source: 'no_data', chartIndex: chartIndex};
            """

            result = self.driver.execute_script(script, day_of_month)

            if result is None:
                logger.warning("[!] Highcharts JS returned None")
                return 0.0

            chart_idx = result.get('chartIndex', -1)
            source    = result.get('source', '')
            bar_idx   = result.get('barIndex', -1)
            value     = result.get('value')

            logger.info(
                f"[*] Chart result → chartIndex={chart_idx}, "
                f"barIndex={bar_idx}, source={source}, value={value}"
            )

            # Warn if we landed on chart index > 0 (unexpected - should be 0)
            if chart_idx > 0:
                logger.warning(
                    f"[!] WARNING: picked chartIndex={chart_idx} "
                    f"(expected 0). Check if charts order changed!"
                )

            if value is not None and float(value) >= 0:
                logger.info(f"[+] Current day units: {value} kWh")
                return float(value)

            logger.warning("[!] No usable chart value — returning 0.0")
            return 0.0

        except Exception as e:
            logger.error(f"[!] Extraction error: {e}")
            logger.error(traceback.format_exc())
            return 0.0

    def extract_last_reading(self):

        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            match = re.search(
                r'Last Reading As on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
                soup.get_text()
            )
            return match.group(1) if match else "N/A"
        except Exception:
            return "N/A"

    def extract_balance(self):

        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            match = re.search(
                r'Grid Bal:\s*Rs\.\s*([\d,]+\.?\d*)',
                soup.get_text()
            )
            return match.group(1) if match else "N/A"
        except Exception:
            return "N/A"

    def extract_source(self):

        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            h1 = soup.find('h1', class_='clearfix')
            if h1:
                match = re.search(
                    r'Source\s*:\s*(\w+)',
                    h1.get_text(),
                    re.IGNORECASE
                )
                if match:
                    return match.group(1)
            return "Unknown"
        except Exception:
            return "Unknown"

    # =========================================================
    # CALCULATIONS
    # =========================================================

    def calculate_hourly_consumption(self, current_units, last_hour_units):

        if last_hour_units is None or last_hour_units == 0:
            return 0.0

        return max(0.0, current_units - last_hour_units)

    def get_last_hour_units(self):
        """
        *** CHANGE 2 vs v3.7 ***

        OLD problem: returns all_rows[-1][2] blindly
          - At IST 00:00 (midnight), Today sheet still has yesterday's rows
            (archive runs AFTER this call)
          - all_rows[-1] = yesterday's 23:xx row → last_hour_units = wrong value
          - hourly_consumption = today's 00:xx units - yesterday's 23:xx units
            = large negative → clamped to 0. Or if yesterday was higher, garbage.

        FIX: Filter rows by today's IST date string before picking the last one.
             If no row exists for today yet → return 0.0 (correct: day just started).
        """
        try:
            ist_now        = self.get_ist_now()
            ist_today_str  = ist_now.strftime('%Y-%m-%d')  # e.g. "2026-05-30"

            all_rows = self.worksheets['today'].get_all_values()

            if len(all_rows) <= 1:
                logger.info("[*] Today sheet empty — first run, last_hour_units = 0.0")
                return 0.0

            # Walk backwards; pick last row whose timestamp starts with today's date
            for row in reversed(all_rows[1:]):
                if row and row[0].startswith(ist_today_str):
                    val = float(row[2]) if row[2] else 0.0
                    logger.info(f"[*] Last hour units ({row[0]}): {val} kWh")
                    return val

            # No row for today yet (e.g. just after midnight before first write)
            logger.info("[*] No row for IST today yet — last_hour_units = 0.0")
            return 0.0

        except Exception as e:
            logger.error(f"[!] Last hour fetch error: {e}")
            return 0.0

    def calculate_benchmark(self, hour_of_day):

        try:
            this_month_ws = self.worksheets['this_month']
            consumptions  = []
            ist_now       = self.get_ist_now()
            current_date  = ist_now.date()

            for days_back in range(1, 4):
                check_date = current_date - timedelta(days=days_back)

                for row in this_month_ws.get_all_values()[1:]:
                    try:
                        row_datetime = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                        if (row_datetime.date() == check_date and
                                row_datetime.hour == hour_of_day):
                            consumption = float(row[3])
                            if consumption > 0:
                                consumptions.append(consumption)
                    except Exception:
                        pass

            if consumptions:
                return round(sum(consumptions) / len(consumptions), 2)

            return None

        except Exception as e:
            logger.error(f"[!] Benchmark error: {e}")
            return None

    # =========================================================
    # SHEET APPEND  (unchanged from v3.7)
    # =========================================================

    def add_row_to_today_sheet(
        self, timestamp, hour, current_units, hourly_consumption,
        last_hour_units, benchmark, last_reading, balance, source
    ):
        try:
            row = [
                timestamp,
                hour,
                current_units,
                hourly_consumption,
                last_hour_units,
                benchmark if benchmark else "N/A",
                "YES" if benchmark and hourly_consumption > benchmark else "NO",
                last_reading,
                balance,
                source
            ]

            self.worksheets['today'].append_row(row)
            logger.info("[+] Row added to Today sheet")
            return True

        except Exception as e:
            logger.error(f"[!] Append error: {e}")
            logger.error(traceback.format_exc())
            return False

    # =========================================================
    # ARCHIVE  (unchanged from v3.7)
    # =========================================================

    def archive_old_data(self):

        try:
            ist_now    = self.get_ist_now()
            today_date = ist_now.date()

            today_ws      = self.worksheets['today']
            this_month_ws = self.worksheets['this_month']

            all_rows = today_ws.get_all_values()

            if not all_rows:
                return

            rows_to_move = []
            rows_to_keep = [all_rows[0]]

            for row in all_rows[1:]:
                try:
                    row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date()
                    if row_date < today_date:
                        rows_to_move.append(row)
                    else:
                        rows_to_keep.append(row)
                except Exception:
                    rows_to_keep.append(row)

            if rows_to_move:
                logger.info(f"[*] Archiving {len(rows_to_move)} old rows")
                for row in rows_to_move:
                    this_month_ws.append_row(row)
                today_ws.clear()
                today_ws.append_rows(rows_to_keep)
                logger.info("[+] Archive completed")

        except Exception as e:
            logger.error(f"[!] Archive error: {e}")
            logger.error(traceback.format_exc())

    # =========================================================
    # MAIN RUN  (unchanged from v3.7)
    # =========================================================

    def run_once(self):

        try:
            logger.info("=" * 80)
            logger.info("UPPCL TRACKER v3.9 START")
            logger.info("=" * 80)

            ist_now = self.get_ist_now()
            logger.info(f"[*] IST Time: {ist_now}")

            self.setup_chrome_driver()

            login_success = self.login()

            if not login_success:
                logger.error("[!] Login failed")
                return False

            current_units       = self.extract_current_day_units()
            last_hour_units     = self.get_last_hour_units()
            hourly_consumption  = self.calculate_hourly_consumption(
                current_units, last_hour_units)
            benchmark           = self.calculate_benchmark(ist_now.hour)
            last_reading        = self.extract_last_reading()
            balance             = self.extract_balance()
            source              = self.extract_source()

            success = self.add_row_to_today_sheet(
                timestamp          = ist_now.strftime('%Y-%m-%d %H:%M:%S'),
                hour               = ist_now.hour,
                current_units      = current_units,
                hourly_consumption = hourly_consumption,
                last_hour_units    = last_hour_units,
                benchmark          = benchmark,
                last_reading       = last_reading,
                balance            = balance,
                source             = source
            )

            if success:
                self.archive_old_data()
                logger.info("[+] Tracker completed successfully")

            return success

        except Exception as e:
            logger.error(f"[!] Tracker error: {e}")
            logger.error(traceback.format_exc())
            return False

        finally:
            try:
                if self.driver:
                    self.driver.quit()
                    logger.info("[+] Driver closed")
            except Exception:
                pass
            logger.info("=" * 80)


# =========================================================
# FLASK ROUTES  (unchanged from v3.7)
# =========================================================

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

        return jsonify({'status': 'error'}), 500

    except Exception as e:
        logger.error(f"[!] Fatal Error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500


# =========================================================
# MAIN  (unchanged from v3.7)
# =========================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)