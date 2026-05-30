#!/usr/bin/env python3
"""
UPPCL Tracker v3.9 - Fixed:

BUG 1 (Chart picks wrong month):
  - extract_current_day_units() used datetime.now().day → UTC day
  - At IST 00:00-05:30, UTC is still PREVIOUS day
  - So day_of_month was WRONG → chart returned null → 0.0
  - FIX: Always use IST day for chart index

BUG 2 (Fails 12am-5:30am IST):
  - ALL datetime.now() calls return UTC on GitHub Actions
  - _setup_worksheets() → wrong sheet name (yesterday's date)
  - archive_old_data()  → wrong date comparison
  - calculate_benchmark() → wrong date range
  - FIX: Use IST datetime everywhere via get_ist_now()

BUG 3 (Previous month chart):
  - At month boundary: UTC still in old month, IST in new month
  - dayIndex=30 on a chart with only 1 bar → null → 0.0
  - FIX: IST day used for index + fallback to last non-zero bar

ROOT CAUSE SUMMARY:
  datetime.now() = UTC on GitHub Actions cloud runner
  datetime.now() = IST on your local Mac (system timezone = IST)
  This is why it works locally but fails on cloud during 00:00-05:30 IST
"""

import os
import sys
import logging
import time
import re
import subprocess
from datetime import datetime, timedelta, timezone

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

# ─── IST Timezone ──────────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Always return current time in IST regardless of system timezone"""
    return datetime.now(tz=timezone.utc).astimezone(IST)

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('uppcl_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class UPPCLEnhancedTracker:

    def __init__(self, username, password, sheet_name, service_account_path):
        self.username = username
        self.password = password
        self.sheet_name = sheet_name
        self.service_account_path = service_account_path
        self.gs = None
        self.spreadsheet = None
        self.worksheets = {}
        self.driver = None

    # ─── Google Sheets ─────────────────────────────────────────────────────────

    def init_google_sheets(self):
        logger.info("[*] Initializing Google Sheets...")
        try:
            credentials = Credentials.from_service_account_file(
                self.service_account_path,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            credentials.refresh(Request())
            logger.info("[+] Credentials created")

            self.gs = gspread.authorize(credentials)
            self.spreadsheet = self.gs.open(self.sheet_name)
            logger.info(f"[+] Opened: {self.sheet_name}")

            self._setup_worksheets()
            logger.info("[+] Google Sheets ready!")

        except Exception as e:
            logger.error(f"[!] Google Sheets init error: {e}")
            raise

    def _setup_worksheets(self):
        """
        Create/get worksheets using IST date.
        FIX: was using datetime.now() (UTC on cloud) → wrong date during 00:00-05:30 IST
        """
        ist = get_ist_now()                                     # ← always IST
        today_str      = ist.strftime('%Y-%m-%d')
        this_month_str = ist.strftime('%B %Y')
        last_month_ist = ist - timedelta(days=ist.day)          # 1 day before 1st = last month
        last_month_str = last_month_ist.strftime('%B %Y')

        sheet_names = {
            'today':      f"Today ({today_str})",
            'this_month': f"This Month ({this_month_str})",
            'last_month': f"Last Month ({last_month_str})"
        }

        logger.info(f"[*] IST date: {today_str} | Sheets: {list(sheet_names.values())}")

        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        for key, name in sheet_names.items():
            if name not in existing:
                ws = self.spreadsheet.add_worksheet(title=name, rows=1000, cols=12)
                self._add_headers(ws)
                logger.info(f"[+] Created: {name}")
            else:
                ws = self.spreadsheet.worksheet(name)
                logger.info(f"[+] Using: {name}")
            self.worksheets[key] = ws

    def _add_headers(self, ws):
        headers = [
            'Timestamp (IST)',
            'Hour (IST)',
            'Current Day Units (kWh)',
            'Hourly Consumption (kWh)',
            'Last Hour Units (kWh)',
            'Benchmark 3-day avg (kWh)',
            'Above Benchmark?',
            'Last Reading Time',
            'Account Balance (₹)',
            'Source'
        ]
        ws.append_row(headers)

    # ─── Chrome WebDriver ───────────────────────────────────────────────────────

    def setup_chrome_driver(self):
        logger.info("[*] Setting up Chrome WebDriver...")
        try:
            opts = Options()
            opts.add_argument('--headless')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            if os.getenv('USE_SYSTEM_CHROME') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true':
                logger.info("[*] GitHub Actions: auto-detecting Chrome/ChromeDriver")

                # Find chromedriver
                r = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
                if r.returncode != 0:
                    raise Exception("chromedriver not found in PATH")
                chromedriver = r.stdout.strip()
                logger.info(f"[*] chromedriver: {chromedriver}")

                # Find Chrome binary
                chrome_r = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
                if chrome_r.returncode == 0:
                    opts.binary_location = chrome_r.stdout.strip()
                    logger.info(f"[*] Chrome: {opts.binary_location}")
                else:
                    for p in ['/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/snap/bin/chromium']:
                        if os.path.exists(p):
                            opts.binary_location = p
                            logger.info(f"[*] Chrome: {p}")
                            break

                self.driver = webdriver.Chrome(service=Service(chromedriver), options=opts)
                logger.info("[+] Chrome ready (GitHub Actions)")
            else:
                from webdriver_manager.chrome import ChromeDriverManager
                self.driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager().install()), options=opts)
                logger.info("[+] Chrome ready (local)")

        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            raise

    # ─── Login ─────────────────────────────────────────────────────────────────

    def solve_captcha(self):
        try:
            captcha_div = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "captchaText"))
            )
            answer = captcha_div.get_attribute('data-answer')
            logger.info(f"[+] Captcha: {answer}")
            inp = self.driver.find_element(By.ID, "captchaInput")
            inp.clear()
            inp.send_keys(answer)
            return True
        except Exception as e:
            logger.error(f"[!] Captcha error: {e}")
            return False

    def login(self):
        try:
            logger.info("[*] Logging in...")
            self.driver.get("https://uppclmp.myxenius.com/login.html")

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "name"))
            ).send_keys(self.username)

            self.driver.find_element(By.ID, "password").send_keys(self.password)
            self.solve_captcha()
            self.driver.find_element(By.ID, "submitBtn").click()

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )
            logger.info("[+] Login successful!")
            return True
        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            return False

    # ─── Data Extraction ───────────────────────────────────────────────────────

    def extract_current_day_units(self, ist_day_of_month):
        """
        Extract today's cumulative units from Highcharts.

        Two charts exist on the page:
          Highcharts.charts[?] — current month  ← ALWAYS use this (first non-null)
          Highcharts.charts[?] — previous month ← NEVER touch this

        Highcharts.charts[] can contain null slots (destroyed charts
        leave null gaps), so we walk the array and grab the FIRST
        non-null entry — which is always the current month chart.

        Primary  : IST day-of-month as bar index
        Fallback : last non-zero bar in the SAME first chart only
        """
        try:
            script = """
                // Step 1: find first non-null chart (= current month chart)
                var chart = null;
                var chartIndex = -1;
                for (var i = 0; i < Highcharts.charts.length; i++) {
                    if (Highcharts.charts[i] !== null &&
                        Highcharts.charts[i] !== undefined) {
                        chart      = Highcharts.charts[i];
                        chartIndex = i;
                        break;
                    }
                }

                if (!chart || !chart.series || chart.series.length === 0) {
                    return {value: null, source: 'no_chart', chartIndex: chartIndex};
                }

                var data = chart.series[0].data;
                var idx  = arguments[0] - 1;   // IST day_of_month is 1-based

                // Step 2: try IST day index directly
                if (idx >= 0 && idx < data.length &&
                    data[idx] && data[idx].y !== null) {
                    return {value: data[idx].y, source: 'by_day_index',
                            chartIndex: chartIndex, barIndex: idx};
                }

                // Step 3: fallback — last non-zero bar in SAME chart only
                for (var j = data.length - 1; j >= 0; j--) {
                    if (data[j] && data[j].y !== null && data[j].y > 0) {
                        return {value: data[j].y, source: 'fallback_last_bar',
                                chartIndex: chartIndex, barIndex: j};
                    }
                }

                return {value: null, source: 'no_data', chartIndex: chartIndex};
            """

            result = self.driver.execute_script(script, ist_day_of_month)

            if result is None:
                logger.warning("[!] Highcharts JS returned None — chart not loaded?")
                return 0.0

            chart_idx = result.get('chartIndex', -1)
            source    = result.get('source', '')
            bar_idx   = result.get('barIndex', -1)
            value     = result.get('value')

            logger.info(
                f"[*] Chart: chartIndex={chart_idx}, barIndex={bar_idx}, "
                f"source={source}, value={value}"
            )

            if value is not None and float(value) >= 0:
                logger.info(f"[+] Current day units: {value} kWh")
                return float(value)

            logger.warning("[!] No usable chart value — returning 0.0")
            return 0.0

        except Exception as e:
            logger.error(f"[!] Units extraction error: {e}")
            return 0.0

    def extract_source(self):
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            h1 = soup.find('h1', class_='clearfix')
            if h1:
                m = re.search(r'Source\s*:\s*(\w+)', h1.get_text(), re.IGNORECASE)
                if m:
                    logger.info(f"[+] Source: {m.group(1)}")
                    return m.group(1)
            return "Unknown"
        except Exception as e:
            logger.error(f"[!] Source error: {e}")
            return "Unknown"

    def extract_last_reading(self):
        try:
            text = BeautifulSoup(self.driver.page_source, 'html.parser').get_text()
            m = re.search(r'Last Reading As on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', text)
            if m:
                logger.info(f"[+] Last reading: {m.group(1)}")
                return m.group(1)
            return "N/A"
        except Exception as e:
            logger.error(f"[!] Last reading error: {e}")
            return "N/A"

    def extract_balance(self):
        try:
            text = BeautifulSoup(self.driver.page_source, 'html.parser').get_text()
            m = re.search(r'Updated Balance\s*:\s*Grid Bal:\s*Rs\.\s*([\d,]+\.?\d*)', text)
            if m:
                logger.info(f"[+] Balance: ₹{m.group(1)}")
                return m.group(1)
            return "N/A"
        except Exception as e:
            logger.error(f"[!] Balance error: {e}")
            return "N/A"

    # ─── Hourly Consumption ────────────────────────────────────────────────────

    def get_last_hour_units(self, ist_today_str):
        """
        Get units value from last row in Today's sheet.
        FIX: Filter rows by IST date string to avoid picking up
        yesterday's last row during 00:00 window.
        """
        try:
            ws = self.worksheets['today']
            all_rows = ws.get_all_values()

            if len(all_rows) <= 1:
                logger.info("[*] No previous records in Today sheet — first run of the day")
                return 0.0

            # Walk backwards through data rows, find last row for IST today
            for row in reversed(all_rows[1:]):
                if not row or not row[0]:
                    continue
                if row[0].startswith(ist_today_str):      # same IST date
                    val = float(row[2]) if row[2] else 0.0
                    logger.info(f"[*] Last hour units ({row[0]}): {val} kWh")
                    return val

            # No row for today yet → first entry of the day, start from 0
            logger.info("[*] No row for IST today yet — treating as day start (0.0)")
            return 0.0

        except Exception as e:
            logger.error(f"[!] get_last_hour_units error: {e}")
            return 0.0

    def calculate_hourly_consumption(self, current_units, last_hour_units, ist_hour):
        """
        Hourly consumption = current - last.
        Special case: hour 0 (midnight IST) resets to 0.
        """
        if ist_hour == 0:
            logger.info("[*] Midnight reset — hourly consumption = 0.0")
            return 0.0

        if last_hour_units == 0.0:
            logger.info("[*] No last-hour reference — consumption shown as 0.0")
            return 0.0

        consumption = current_units - last_hour_units
        if consumption < 0:
            logger.warning(f"[!] Negative consumption ({consumption}) — clamped to 0.0")
            return 0.0

        logger.info(f"[+] Hourly consumption: {consumption:.3f} kWh")
        return round(consumption, 3)

    # ─── Benchmark ─────────────────────────────────────────────────────────────

    def calculate_benchmark(self, ist_hour, ist_today):
        """
        Average of same hour consumption for last 3 IST days.
        FIX: was using datetime.now().date() → UTC date → wrong on cloud.
        Now uses ist_today (datetime.date in IST).
        """
        try:
            ws = self.worksheets['this_month']
            all_rows = ws.get_all_values()
            consumptions = []

            for days_back in range(1, 4):
                check_date = ist_today - timedelta(days=days_back)
                check_str  = check_date.strftime('%Y-%m-%d')

                for row in all_rows[1:]:
                    if not row or not row[0]:
                        continue
                    if not row[0].startswith(check_str):
                        continue
                    try:
                        row_hour = int(row[1])              # Hour column (IST)
                        if row_hour == ist_hour:
                            val = float(row[3]) if row[3] and row[3] != 'N/A' else 0.0
                            if val > 0:
                                consumptions.append(val)
                    except Exception:
                        continue

            if consumptions:
                avg = round(sum(consumptions) / len(consumptions), 3)
                logger.info(f"[+] Benchmark hour {ist_hour}: {avg} kWh ({len(consumptions)} days)")
                return avg

            logger.info(f"[*] No benchmark data yet for hour {ist_hour}")
            return None

        except Exception as e:
            logger.error(f"[!] Benchmark error: {e}")
            return None

    # ─── Write to Sheets ───────────────────────────────────────────────────────

    def add_row_to_today_sheet(self, ist_now, current_units, hourly_consumption,
                               last_hour_units, benchmark, last_reading, balance, source):
        try:
            above = "YES" if (benchmark and hourly_consumption > benchmark) else "NO"

            row = [
                ist_now.strftime('%Y-%m-%d %H:%M:%S'),   # IST timestamp
                ist_now.hour,                              # IST hour
                current_units,
                hourly_consumption,
                last_hour_units,
                benchmark if benchmark is not None else "N/A",
                above,
                last_reading,
                balance,
                source
            ]

            self.worksheets['today'].append_row(row)
            logger.info(f"[+] Row written ✅  {row[0]} | {current_units} kWh | +{hourly_consumption} kWh | Benchmark {benchmark}")

            if above == "YES":
                logger.info("[⚠️] Consumption ABOVE benchmark!")

            return True

        except Exception as e:
            logger.error(f"[!] append_row error: {e}")
            return False

    # ─── Archive (end-of-day cleanup) ──────────────────────────────────────────

    def archive_old_data(self, ist_today_str):
        """
        Move any rows from Today sheet that belong to a PREVIOUS IST date
        into This Month sheet.
        FIX: was using datetime.now().date() → UTC date.
        Now uses ist_today_str directly.
        """
        try:
            ws = self.worksheets['today']
            all_rows = ws.get_all_values()

            if len(all_rows) <= 1:
                return

            to_move = []
            to_keep = [all_rows[0]]     # header

            for row in all_rows[1:]:
                if not row or not row[0]:
                    to_keep.append(row)
                    continue
                if row[0].startswith(ist_today_str):
                    to_keep.append(row)
                else:
                    to_move.append(row)

            if to_move:
                logger.info(f"[*] Archiving {len(to_move)} old rows to This Month...")
                for row in to_move:
                    self.worksheets['this_month'].append_row(row)

                ws.clear()
                ws.append_rows(to_keep)
                logger.info("[+] Today sheet cleaned up")

        except Exception as e:
            logger.error(f"[!] Archive error: {e}")

    # ─── Main Run ──────────────────────────────────────────────────────────────

    def run_once(self):
        try:
            # ── Compute IST "now" once, use everywhere ──────────────────────
            ist_now        = get_ist_now()
            ist_today      = ist_now.date()
            ist_today_str  = ist_today.strftime('%Y-%m-%d')
            ist_hour       = ist_now.hour
            ist_day_of_month = ist_now.day

            logger.info(
                f"[*] IST now  : {ist_now.strftime('%Y-%m-%d %H:%M:%S %Z')}  "
                f"(day={ist_day_of_month}, hour={ist_hour})"
            )

            # ── Drive + scrape ──────────────────────────────────────────────
            self.setup_chrome_driver()

            if not self.login():
                logger.error("[!] Login failed — aborting")
                return False

            time.sleep(3)       # let chart render

            current_units    = self.extract_current_day_units(ist_day_of_month)
            last_hour_units  = self.get_last_hour_units(ist_today_str)
            hourly_consumption = self.calculate_hourly_consumption(
                current_units, last_hour_units, ist_hour)
            benchmark        = self.calculate_benchmark(ist_hour, ist_today)
            last_reading     = self.extract_last_reading()
            balance          = self.extract_balance()
            source           = self.extract_source()

            # ── Write ───────────────────────────────────────────────────────
            ok = self.add_row_to_today_sheet(
                ist_now, current_units, hourly_consumption,
                last_hour_units, benchmark, last_reading, balance, source
            )

            if ok:
                self.archive_old_data(ist_today_str)
                logger.info("[+] Capture complete ✅")

            return ok

        except Exception as e:
            logger.error(f"[!] run_once error: {e}")
            return False

        finally:
            if self.driver:
                self.driver.quit()


# ─── Entry Point ───────────────────────────────────────────────────────────────

def main():
    import argparse

    env_username = os.getenv('UPPCL_USERNAME', '5573683932')
    env_password = os.getenv('UPPCL_PASSWORD', '5573683932')
    env_sheet    = os.getenv('GOOGLE_SHEETS_NAME', 'UPPCL Consumption Tracker')

    p = argparse.ArgumentParser(description='UPPCL Tracker v3.9')
    p.add_argument('--username',        default=env_username)
    p.add_argument('--password',        default=env_password)
    p.add_argument('--sheet',           default=env_sheet)
    p.add_argument('--service-account', default='service_account.json')
    p.add_argument('--once',            action='store_true')
    args = p.parse_args()

    logger.info("=" * 60)
    logger.info("[*] UPPCL Tracker v3.9 — IST-safe, all bugs fixed")
    logger.info(f"[*] Current IST time: {get_ist_now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("=" * 60)

    tracker = UPPCLEnhancedTracker(
        args.username, args.password, args.sheet, args.service_account)

    tracker.init_google_sheets()

    if args.once:
        tracker.run_once()


if __name__ == '__main__':
    main()