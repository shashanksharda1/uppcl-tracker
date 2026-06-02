#!/usr/bin/env python3
"""
UPPCL Tracker v3.9 - Based on last working v3.7
Changes on top of v3.7:

CHANGE 1 — extract_current_day_units():
  Page has two charts:
    #chartContainerHourly → Current Month  (left section)  ← we want this
    #chartContainerDaily  → Previous Month (right section) ← never touch
  OLD: Highcharts.charts[0] — array index unreliable, can land on either chart
  NEW: $('#chartContainerHourly').highcharts() — targets by div ID, same method
       the page uses to create the chart. 100% accurate.
  FALLBACK: renderTo.id match if jQuery method fails.

CHANGE 2 — get_last_hour_units():
  OLD: returns all_rows[-1] blindly → at midnight picks yesterday's last row
  NEW: filters rows by IST today's date string first

CHANGE 3 — archive_old_data():
  OLD: only moved Today → This Month, never handled month rollover
  NEW: also moves This Month → Last Month when month changes
       (fixes data lost on month switchover)

CHANGE 4 — recalculate_benchmarks() [new method]:
  Recalculates Benchmark and Above Benchmark? columns for all rows
  in Today + This Month sheets. Called via /recalculate endpoint
  or automatically at midnight (hour 0) each day.
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

app  = Flask(__name__)
IST  = pytz.timezone('Asia/Kolkata')


class UPPCLTracker:

    def __init__(self, username, password, sheet_name):
        self.username   = username
        self.password   = password
        self.sheet_name = sheet_name
        self.gs         = None
        self.worksheets = {}
        self.driver     = None

    # =========================================================
    # TIMEZONE
    # =========================================================

    def get_ist_now(self):
        return datetime.now(IST)

    # =========================================================
    # GOOGLE SHEETS  (unchanged from v3.7)
    # =========================================================

    def init_google_sheets(self):
        logger.info("[*] Initializing Google Sheets...")
        try:
            sa_json = os.environ.get('SERVICE_ACCOUNT_JSON')
            if not sa_json:
                raise ValueError("SERVICE_ACCOUNT_JSON not set")

            credentials = Credentials.from_service_account_info(
                json.loads(sa_json),
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
            'today':      'Today',
            'this_month': 'This Month',
            'last_month': 'Last Month'
        }
        existing = {ws.title: ws for ws in spreadsheet.worksheets()}
        for key, name in sheet_names.items():
            if name not in existing:
                ws = spreadsheet.add_worksheet(title=name, rows=2000, cols=10)
                self._add_headers(ws)
            else:
                ws = existing[name]
            self.worksheets[key] = ws

    def _add_headers(self, ws):
        ws.append_row([
            'Timestamp (IST)', 'Hour (IST)', 'Current Day Units (kWh)',
            'Hourly Consumption (kWh)', 'Last Hour Units (kWh)',
            'Benchmark (3-day avg)', 'Above Benchmark?',
            'Last Reading Time', 'Account Balance (Rs)', 'Source'
        ])

    # =========================================================
    # CHROME DRIVER  (unchanged from v3.7)
    # =========================================================

    def setup_chrome_driver(self):
        logger.info("[*] Setting up Chrome WebDriver...")
        try:
            opts = Options()
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('--window-size=1920,1080')
            opts.add_argument(
                'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/125.0.0.0 Safari/537.36'
            )

            r = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
            chromedriver_bin = r.stdout.strip()

            cr = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
            if cr.returncode == 0:
                opts.binary_location = cr.stdout.strip()

            self.driver = webdriver.Chrome(service=Service(chromedriver_bin), options=opts)
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
            answer = captcha_div.get_attribute('data-answer')
            if not (answer and answer.strip()):
                answer = self.driver.execute_script(
                    "return document.getElementById('captchaText').textContent.trim();"
                )
            logger.info(f"[+] Captcha: {answer}")
            inp = self.driver.find_element(By.ID, "captchaInput")
            inp.clear()
            inp.send_keys(answer.strip())
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
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            ss  = f"/tmp/{prefix}_{ts}.png"
            htm = f"/tmp/{prefix}_{ts}.html"
            self.driver.save_screenshot(ss)
            with open(htm, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.error(f"[!] Screenshot: {ss}  HTML: {htm}")
        except Exception as e:
            logger.error(f"[!] save_debug_files: {e}")

    # =========================================================
    # LOGIN  (unchanged from v3.7)
    # =========================================================

    def login(self):
        try:
            logger.info("[*] Opening login page...")
            self.driver.get("https://uppclmp.myxenius.com/login.html")
            logger.info(f"[*] URL: {self.driver.current_url}")

            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "name"))
            ).send_keys(self.username)
            self.driver.find_element(By.ID, "password").send_keys(self.password)
            logger.info("[+] Credentials entered")

            if not self.solve_captcha():
                logger.error("[!] Captcha failed")
                self.save_debug_files("captcha_failure")
                return False

            btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "submitBtn"))
            )
            time.sleep(2)
            btn.click()
            logger.info("[*] Submit clicked")
            time.sleep(5)

            try:
                alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                logger.error(f"[!] LOGIN ALERT: {alert.text}")
                alert.accept()
                self.save_debug_files("login_alert")
                return False
            except TimeoutException:
                logger.info("[*] No alert")

            WebDriverWait(self.driver, 25).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )
            logger.info("[+] LOGIN SUCCESSFUL!")
            return True

        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            logger.error(traceback.format_exc())
            logger.error(f"[!] URL: {self.driver.current_url}")
            self.save_debug_files("login_exception")
            return False

    # =========================================================
    # EXTRACTION
    # =========================================================

    def extract_current_day_units(self):
        """
        CHANGE 1: Target chart by container div ID, NOT by array index.

        Page structure (confirmed from page source):
          <section class="left box-spce">
            <div id="chartContainerHourly">  ← CURRENT month chart
          <section class="right">
            <div id="chartContainerDaily">   ← PREVIOUS month chart

        The page initialises them as:
          $('#chartContainerHourly').highcharts({...})  ← current
          $('#chartContainerDaily').highcharts({...})   ← previous

        We retrieve the current month chart the same way:
          $('#chartContainerHourly').highcharts()

        This is impossible to get wrong — it's the same reference the
        page itself uses. Array index approach is completely abandoned.
        """
        try:
            ist_now      = self.get_ist_now()
            day_of_month = ist_now.day
            logger.info(f"[*] IST day {day_of_month} — targeting #chartContainerHourly")

            script = """
                var dayIndex = arguments[0] - 1;   /* IST day is 1-based */

                /* ── Primary: get chart bound to #chartContainerHourly ─── */
                /* Same method the page uses to create the chart            */
                var chart = null;
                try {
                    chart = $('#chartContainerHourly').highcharts();
                } catch(e) {}

                /* ── Fallback: find by renderTo.id (no jQuery needed) ──── */
                if (!chart) {
                    for (var i = 0; i < Highcharts.charts.length; i++) {
                        var c = Highcharts.charts[i];
                        if (c && c.renderTo && c.renderTo.id === 'chartContainerHourly') {
                            chart = c;
                            break;
                        }
                    }
                }

                if (!chart || !chart.series || chart.series.length === 0) {
                    return {value: null, source: 'no_chart'};
                }

                var data = chart.series[0].data;

                /* ── Step 1: use IST day index ───────────────────────── */
                if (dayIndex >= 0 && dayIndex < data.length &&
                        data[dayIndex] && data[dayIndex].y !== null) {
                    return {value: data[dayIndex].y,
                            source: 'by_ist_day', barIndex: dayIndex};
                }

                /* ── Step 2: fallback — last non-zero bar, SAME chart ── */
                for (var j = data.length - 1; j >= 0; j--) {
                    if (data[j] && data[j].y !== null && data[j].y > 0) {
                        return {value: data[j].y,
                                source: 'fallback_last_bar', barIndex: j};
                    }
                }

                return {value: null, source: 'no_data'};
            """

            result = self.driver.execute_script(script, day_of_month)

            if not result:
                logger.warning("[!] Chart script returned None")
                return 0.0

            source  = result.get('source', '')
            bar_idx = result.get('barIndex', -1)
            value   = result.get('value')

            logger.info(f"[*] Chart → source={source}, barIndex={bar_idx}, value={value}")

            if value is not None and float(value) >= 0:
                logger.info(f"[+] Current day units: {value} kWh")
                return float(value)

            logger.warning("[!] No usable value — returning 0.0")
            return 0.0

        except Exception as e:
            logger.error(f"[!] Extraction error: {e}")
            logger.error(traceback.format_exc())
            return 0.0

    def extract_last_reading(self):
        try:
            text  = BeautifulSoup(self.driver.page_source, 'html.parser').get_text()
            match = re.search(
                r'Last Reading As on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', text)
            return match.group(1) if match else "N/A"
        except Exception:
            return "N/A"

    def extract_balance(self):
        try:
            text  = BeautifulSoup(self.driver.page_source, 'html.parser').get_text()
            match = re.search(r'Grid Bal:\s*Rs\.\s*([\d,]+\.?\d*)', text)
            return match.group(1) if match else "N/A"
        except Exception:
            return "N/A"

    def extract_source(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            h1   = soup.find('h1', class_='clearfix')
            if h1:
                m = re.search(r'Source\s*:\s*(\w+)', h1.get_text(), re.IGNORECASE)
                if m:
                    return m.group(1)
            return "Unknown"
        except Exception:
            return "Unknown"

    # =========================================================
    # CALCULATIONS
    # =========================================================

    def calculate_hourly_consumption(self, current_units, last_hour_units):
        if not last_hour_units:
            return 0.0
        return max(0.0, round(current_units - last_hour_units, 3))

    def get_last_hour_units(self):
        """
        CHANGE 2: Filter by today's IST date before picking last row.
        Prevents midnight boundary bug where yesterday's 23:xx row
        was returned as last_hour_units for today's 00:xx entry.
        """
        try:
            ist_now       = self.get_ist_now()
            ist_today_str = ist_now.strftime('%Y-%m-%d')

            all_rows = self.worksheets['today'].get_all_values()

            if len(all_rows) <= 1:
                logger.info("[*] Today sheet empty — last_hour_units = 0.0")
                return 0.0

            for row in reversed(all_rows[1:]):
                if row and row[0].startswith(ist_today_str):
                    val = float(row[2]) if row[2] else 0.0
                    logger.info(f"[*] Last hour units ({row[0]}): {val} kWh")
                    return val

            logger.info("[*] No row for IST today yet — last_hour_units = 0.0")
            return 0.0

        except Exception as e:
            logger.error(f"[!] get_last_hour_units error: {e}")
            return 0.0

    def calculate_benchmark(self, hour_of_day, reference_date=None):
        """Calculate 3-day average for a given hour and date."""
        try:
            ist_now      = self.get_ist_now()
            current_date = reference_date if reference_date else ist_now.date()
            consumptions = []

            # Search both this_month and last_month for the 3 prior days
            for ws_key in ['this_month', 'last_month']:
                rows = self.worksheets[ws_key].get_all_values()
                for days_back in range(1, 4):
                    check_date = current_date - timedelta(days=days_back)
                    for row in rows[1:]:
                        try:
                            rd = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                            if rd.date() == check_date and rd.hour == hour_of_day:
                                cons = float(row[3])
                                if cons > 0:
                                    consumptions.append(cons)
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

    def add_row_to_today_sheet(self, timestamp, hour, current_units,
                               hourly_consumption, last_hour_units,
                               benchmark, last_reading, balance, source):
        try:
            row = [
                timestamp, hour, current_units, hourly_consumption,
                last_hour_units,
                benchmark if benchmark is not None else "N/A",
                "YES" if benchmark and hourly_consumption > benchmark else "NO",
                last_reading, balance, source
            ]
            self.worksheets['today'].append_row(row)
            logger.info("[+] Row added to Today sheet")
            return True
        except Exception as e:
            logger.error(f"[!] Append error: {e}")
            logger.error(traceback.format_exc())
            return False

    # =========================================================
    # ARCHIVE
    # =========================================================

    def archive_old_data(self):
        """
        CHANGE 3: Two-stage archive on month rollover.

        Stage 1 (runs every day):
          Today → This Month  (rows whose date < IST today)

        Stage 2 (runs on month change):
          This Month → Last Month  (rows whose month ≠ current IST month)
          This was MISSING before, causing data loss on month switchover.
        """
        ist_now       = self.get_ist_now()
        today_date    = ist_now.date()
        current_month = ist_now.strftime('%Y-%m')   # e.g. "2026-06"

        # ── Stage 1: Today → This Month ──────────────────────────────
        try:
            today_ws      = self.worksheets['today']
            this_month_ws = self.worksheets['this_month']
            all_rows      = today_ws.get_all_values()

            if all_rows:
                to_move = []
                to_keep = [all_rows[0]]

                for row in all_rows[1:]:
                    try:
                        rd = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date()
                        if rd < today_date:
                            to_move.append(row)
                        else:
                            to_keep.append(row)
                    except Exception:
                        to_keep.append(row)

                if to_move:
                    logger.info(f"[*] Stage 1: moving {len(to_move)} rows → This Month")
                    for row in to_move:
                        this_month_ws.append_row(row)
                    today_ws.clear()
                    today_ws.append_rows(to_keep)
                    logger.info("[+] Stage 1 archive done")

        except Exception as e:
            logger.error(f"[!] Stage 1 archive error: {e}")
            logger.error(traceback.format_exc())

        # ── Stage 2: This Month → Last Month (month rollover) ────────
        try:
            this_month_ws = self.worksheets['this_month']
            last_month_ws = self.worksheets['last_month']
            all_rows      = this_month_ws.get_all_values()

            if all_rows:
                to_move = []
                to_keep = [all_rows[0]]

                for row in all_rows[1:]:
                    try:
                        row_month = row[0][:7]   # "2026-05" from "2026-05-31 23:32:15"
                        if row_month != current_month:
                            to_move.append(row)
                        else:
                            to_keep.append(row)
                    except Exception:
                        to_keep.append(row)

                if to_move:
                    logger.info(
                        f"[*] Stage 2: moving {len(to_move)} rows "
                        f"(prev month) → Last Month"
                    )
                    for row in to_move:
                        last_month_ws.append_row(row)
                    this_month_ws.clear()
                    this_month_ws.append_rows(to_keep)
                    logger.info("[+] Stage 2 month-rollover archive done")

        except Exception as e:
            logger.error(f"[!] Stage 2 archive error: {e}")
            logger.error(traceback.format_exc())

    # =========================================================
    # RECALCULATE BENCHMARKS  (CHANGE 4 — new method)
    # =========================================================

    def recalculate_benchmarks(self):
        """
        CHANGE 4: Recalculate Benchmark (col F) and Above Benchmark? (col G)
        for every data row in Today and This Month sheets.

        Reads all historical data from This Month + Last Month into a
        lookup dict first, then updates only rows where values changed.
        Uses batch_update to minimise API calls.

        Called:
          - Via /recalculate endpoint (manual reconciliation)
          - Automatically at hour 0 (midnight IST) each day
        """
        logger.info("[*] Starting benchmark recalculation...")

        # Build lookup: (date, hour) → [consumption_values]
        lookup = {}

        for ws_key in ['last_month', 'this_month']:
            try:
                rows = self.worksheets[ws_key].get_all_values()
                for row in rows[1:]:
                    try:
                        dt   = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                        key  = (dt.date(), dt.hour)
                        cons = float(row[3]) if row[3] and row[3] not in ('N/A', '') else 0.0
                        if cons > 0:
                            lookup.setdefault(key, []).append(cons)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"[!] Lookup build error ({ws_key}): {e}")

        total_updated = 0

        # Recalculate for Today and This Month
        for ws_key in ['today', 'this_month']:
            try:
                ws       = self.worksheets[ws_key]
                all_rows = ws.get_all_values()

                if len(all_rows) <= 1:
                    continue

                batch = []

                for i, row in enumerate(all_rows[1:], start=2):  # row 2 onwards (1-indexed)
                    try:
                        dt           = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                        row_date     = dt.date()
                        row_hour     = dt.hour
                        hourly_cons  = float(row[3]) if row[3] and row[3] not in ('N/A', '') else 0.0

                        # Average of same hour over 3 prior days
                        consumptions = []
                        for days_back in range(1, 4):
                            key = (row_date - timedelta(days=days_back), row_hour)
                            consumptions.extend(lookup.get(key, []))

                        if consumptions:
                            new_bench = round(sum(consumptions) / len(consumptions), 2)
                            new_above = "YES" if hourly_cons > new_bench else "NO"
                        else:
                            new_bench = "N/A"
                            new_above = "NO"

                        # Only queue update if value actually changed
                        old_bench = row[5] if len(row) > 5 else ''
                        old_above = row[6] if len(row) > 6 else ''

                        if str(old_bench) != str(new_bench) or old_above != new_above:
                            batch.append({
                                'range':  f'F{i}:G{i}',
                                'values': [[new_bench, new_above]]
                            })

                    except Exception:
                        pass

                if batch:
                    ws.batch_update(batch)
                    total_updated += len(batch)
                    logger.info(f"[+] {ws_key}: updated {len(batch)} rows")
                else:
                    logger.info(f"[*] {ws_key}: all values already correct")

            except Exception as e:
                logger.error(f"[!] Recalculate error ({ws_key}): {e}")
                logger.error(traceback.format_exc())

        logger.info(f"[+] Recalculation done — {total_updated} cells updated")
        return total_updated

    # =========================================================
    # MAIN RUN
    # =========================================================

    def run_once(self):
        try:
            logger.info("=" * 80)
            logger.info("UPPCL TRACKER v3.9 START")
            logger.info("=" * 80)

            ist_now = self.get_ist_now()
            logger.info(f"[*] IST Time: {ist_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

            self.setup_chrome_driver()

            if not self.login():
                logger.error("[!] Login failed")
                return False

            current_units      = self.extract_current_day_units()
            last_hour_units    = self.get_last_hour_units()
            hourly_consumption = self.calculate_hourly_consumption(current_units, last_hour_units)
            benchmark          = self.calculate_benchmark(ist_now.hour)
            last_reading       = self.extract_last_reading()
            balance            = self.extract_balance()
            source             = self.extract_source()

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

                # Recalculate benchmarks at midnight every day
                if ist_now.hour == 0:
                    logger.info("[*] Midnight — running benchmark recalculation")
                    self.recalculate_benchmarks()

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
# FLASK ROUTES
# =========================================================

def _make_tracker():
    return UPPCLTracker(
        os.getenv('UPPCL_USERNAME'),
        os.getenv('UPPCL_PASSWORD'),
        os.getenv('GOOGLE_SHEETS_NAME', 'UPPCL Consumption Tracker')
    )


@app.route('/', methods=['GET', 'POST'])
def trigger():
    logger.info("[*] HTTP trigger received")
    try:
        tracker = _make_tracker()
        tracker.init_google_sheets()
        success = tracker.run_once()
        return jsonify({'status': 'success' if success else 'error'}), 200 if success else 500
    except Exception as e:
        logger.error(f"[!] Fatal: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/recalculate', methods=['GET', 'POST'])
def recalculate():
    """
    Manual endpoint to recalculate Benchmark and Above Benchmark?
    for all rows in Today + This Month sheets.

    Use when: historical rows have wrong/missing benchmark values,
    e.g. after first 3 days of a month when data has accumulated.
    """
    logger.info("[*] /recalculate triggered")
    try:
        tracker = _make_tracker()
        tracker.init_google_sheets()
        updated = tracker.recalculate_benchmarks()
        return jsonify({'status': 'success', 'rows_updated': updated}), 200
    except Exception as e:
        logger.error(f"[!] Recalculate error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500


# =========================================================
# MAIN
# =========================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)