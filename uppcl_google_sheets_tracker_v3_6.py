#!/usr/bin/env python3
"""
UPPCL Tracker v4.0 - Based on working v3.9

ROOT-CAUSE FIX for "LOGIN ALERT FOUND: Invalid Captcha Token"
that ONLY occurs between 00:00 and 05:30 IST on Cloud Run.

WHY IT HAPPENED
---------------
Cloud Run containers run in UTC. Chrome inherits that, so the login
page's JavaScript generates its captcha *token* using a UTC-based date.
The Xenius/UPPCL server validates that token against IST (UTC+5:30).

  - IST 05:30-23:59  ==  UTC 00:00-18:29  -> same calendar date -> token OK
  - IST 00:00-05:29  ==  UTC 18:30-23:59 (PREVIOUS day) -> browser date is
    D-1 while server date is D -> token date mismatch -> "Invalid Captcha Token"

That 5.5h window is exactly "UTC is still yesterday".

THE FIX (CHANGE A - new in v4.0)
--------------------------------
Force the browser to Asia/Kolkata BEFORE it loads the page, two ways:
  1. Set TZ=Asia/Kolkata at process start so the Chrome subprocess
     inherits IST for new Date().
  2. CDP Emulation.setTimezoneOverride as an authoritative per-session
     override applied right after the driver starts (before any get()).
Plus a verify-timezone log so you can confirm IST in Cloud Run logs.

NOTE: os.environ['TZ'] does NOT affect datetime.now(IST) calls in this
script (those are pytz tz-aware and independent of system TZ), so there
is no regression to the IST logic.

ALSO RETAINED / TIGHTENED
-------------------------
CHANGE 1 (extract_current_day_units): walk Highcharts.charts[] to the
  first non-null chart (current month). TIGHTENED so that when today's
  bar genuinely does not exist yet (portal day not rolled), it returns
  0.0 with an explicit source instead of silently leaking yesterday's
  full-day bar via the old fallback.

CHANGE 2 (get_last_hour_units): filter Today-sheet rows by today's IST
  date before picking the last one; returns 0.0 on a fresh day.
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

# =========================================================
# CHANGE A (part 1): force process timezone to IST at import,
# BEFORE Chrome is ever launched, so the Chrome subprocess
# inherits TZ=Asia/Kolkata for its JavaScript new Date().
# =========================================================
os.environ['TZ'] = 'Asia/Kolkata'
try:
    time.tzset()  # Unix only (Cloud Run is Linux) - no-op safe-guarded on Windows
except AttributeError:
    pass

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
    # GOOGLE SHEETS  (unchanged from v3.9)
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
    # CHROME DRIVER
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

            # =========================================================
            # CHANGE A (part 2): authoritative per-session timezone
            # override via CDP. Applied BEFORE any page is loaded so the
            # login page's JS sees IST when it builds the captcha token.
            # =========================================================
            try:
                self.driver.execute_cdp_cmd(
                    "Emulation.setTimezoneOverride",
                    {"timezoneId": "Asia/Kolkata"}
                )
                logger.info("[+] CDP timezone override set -> Asia/Kolkata")
            except Exception as tz_err:
                # Non-fatal: TZ env (part 1) still applies as a backstop.
                logger.warning(f"[!] CDP timezone override failed: {tz_err}")

            self._verify_browser_timezone()

            logger.info("[+] Chrome WebDriver ready")

        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            logger.error(traceback.format_exc())
            raise

    def _verify_browser_timezone(self):
        """
        CHANGE A (part 3): log what timezone / clock the browser actually
        reports, so you can confirm in Cloud Run logs that the fix took.
        Expect: tz=Asia/Kolkata and a date string with GMT+0530.
        """
        try:
            self.driver.get("about:blank")
            tz = self.driver.execute_script(
                "return Intl.DateTimeFormat().resolvedOptions().timeZone;"
            )
            now_str = self.driver.execute_script("return new Date().toString();")
            logger.info(f"[*] Browser timezone reported: {tz}")
            logger.info(f"[*] Browser new Date(): {now_str}")
        except Exception as e:
            logger.warning(f"[!] Timezone verify failed (non-fatal): {e}")

    # =========================================================
    # CAPTCHA  (unchanged logic from v3.9)
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
    # DEBUG  (unchanged from v3.9)
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
    # LOGIN  (unchanged from v3.9)
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
        CHANGE 1 (tightened in v4.0):

        Walk Highcharts.charts[] to the first non-null chart (current month).
        Then:
          - if today's bar (by IST day index) has a value -> use it
          - if the slot exists but is empty -> 0.0 (fresh day, source today_bar_empty)
          - if the IST day index is beyond data.length -> today's bar not created
            yet by the portal (UTC-day lag in 00:00-05:30 IST) -> 0.0
            (source today_bar_missing_utc_lag)

        This deliberately removes the old "fallback to last non-zero bar"
        behaviour that silently leaked YESTERDAY's full-day total during the
        early-morning window. A missing today-bar means zero consumed so far
        today, not yesterday's total.
        """
        try:
            ist_now      = self.get_ist_now()
            day_of_month = ist_now.day

            logger.info(f"[*] IST day of month: {day_of_month}")

            script = """
                var dayIndex = arguments[0] - 1;  /* IST day is 1-based */

                /* Step 1: find first non-null chart = current month */
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

                /* Step 2: today's bar by IST day index */
                if (dayIndex >= 0 && dayIndex < data.length) {
                    if (data[dayIndex] && data[dayIndex].y !== null) {
                        return {
                            value: data[dayIndex].y,
                            source: 'by_ist_day',
                            chartIndex: chartIndex,
                            barIndex: dayIndex,
                            dataLength: data.length
                        };
                    }
                    /* slot exists but empty -> fresh day, no consumption yet */
                    return {
                        value: 0,
                        source: 'today_bar_empty',
                        chartIndex: chartIndex,
                        barIndex: dayIndex,
                        dataLength: data.length
                    };
                }

                /* Step 3: IST day index beyond data -> portal day not rolled
                   (UTC-midnight lag during 00:00-05:30 IST). NOT yesterday. */
                return {
                    value: 0,
                    source: 'today_bar_missing_utc_lag',
                    chartIndex: chartIndex,
                    barIndex: dayIndex,
                    dataLength: data.length
                };
            """

            result = self.driver.execute_script(script, day_of_month)

            if result is None:
                logger.warning("[!] Highcharts JS returned None")
                return 0.0

            chart_idx  = result.get('chartIndex', -1)
            source     = result.get('source', '')
            bar_idx    = result.get('barIndex', -1)
            value      = result.get('value')
            data_len   = result.get('dataLength', -1)

            logger.info(
                f"[*] Chart result -> chartIndex={chart_idx}, "
                f"barIndex={bar_idx}, dataLength={data_len}, "
                f"source={source}, value={value}"
            )

            # Warn if we landed on chart index > 0 (unexpected - should be 0)
            if chart_idx > 0:
                logger.warning(
                    f"[!] WARNING: picked chartIndex={chart_idx} "
                    f"(expected 0). Check if charts order changed!"
                )

            if source == 'today_bar_missing_utc_lag':
                logger.info(
                    "[*] Today's bar not present yet (early-morning UTC lag). "
                    "Reporting 0.0 current-day units."
                )

            if value is not None and float(value) >= 0:
                logger.info(f"[+] Current day units: {value} kWh")
                return float(value)

            logger.warning("[!] No usable chart value - returning 0.0")
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
        CHANGE 2 (unchanged from v3.9):

        Filter Today-sheet rows by today's IST date string before picking the
        last matching row. If no row exists for today yet -> 0.0 (day start).
        """
        try:
            ist_now        = self.get_ist_now()
            ist_today_str  = ist_now.strftime('%Y-%m-%d')

            all_rows = self.worksheets['today'].get_all_values()

            if len(all_rows) <= 1:
                logger.info("[*] Today sheet empty - first run, last_hour_units = 0.0")
                return 0.0

            for row in reversed(all_rows[1:]):
                if row and row[0].startswith(ist_today_str):
                    val = float(row[2]) if row[2] else 0.0
                    logger.info(f"[*] Last hour units ({row[0]}): {val} kWh")
                    return val

            logger.info("[*] No row for IST today yet - last_hour_units = 0.0")
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
    # SHEET APPEND  (unchanged from v3.9)
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
    # ARCHIVE  (unchanged from v3.9)
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
    # MAIN RUN  (unchanged from v3.9)
    # =========================================================

    def run_once(self):

        try:
            logger.info("=" * 80)
            logger.info("UPPCL TRACKER v4.0 START")
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
# FLASK ROUTES  (unchanged from v3.9)
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
# MAIN  (unchanged from v3.9)
# =========================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)