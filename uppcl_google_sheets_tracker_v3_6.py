#!/usr/bin/env python3
"""
UPPCL Tracker - LOGIN FAILURE DEBUG
Capture exact reason why login fails at midnight
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

    def check_page_source(self, label):
        """Debug: check page source for issues"""
        try:
            source = self.driver.page_source
            logger.info(f"[DEBUG] {label} - Page source length: {len(source)}")
            
            # Check for error messages
            if "error" in source.lower():
                logger.warning(f"[DEBUG] {label} - Found 'error' in page")
            if "invalid" in source.lower():
                logger.warning(f"[DEBUG] {label} - Found 'invalid' in page")
            if "failed" in source.lower():
                logger.warning(f"[DEBUG] {label} - Found 'failed' in page")
                
        except Exception as e:
            logger.warning(f"[DEBUG] Could not check page source: {e}")

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
            logger.info("\n" + "="*80)
            logger.info("LOGIN ATTEMPT")
            logger.info("="*80)
            
            logger.info("[*] Navigating to login page...")
            self.driver.get("https://uppclmp.myxenius.com/login.html")
            logger.info(f"[DEBUG] Page loaded, title: {self.driver.title}")
            self.check_page_source("AFTER_PAGE_LOAD")
            
            logger.info("[*] Waiting for username field...")
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "name"))
            )
            username_field.send_keys(self.username)
            logger.info(f"[DEBUG] Username sent")

            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(self.password)
            logger.info(f"[DEBUG] Password sent")

            self.solve_captcha()
            time.sleep(1)
            
            # Check for pre-submit alerts
            try:
                alert = WebDriverWait(self.driver, 1).until(EC.alert_is_present())
                logger.warning(f"[!] Pre-submit alert: {alert.text}")
                alert.dismiss()
                time.sleep(1)
            except:
                logger.info("[*] No pre-submit alert")

            logger.info("[*] Clicking submit...")
            submit_button = self.driver.find_element(By.ID, "submitBtn")
            submit_button.click()
            logger.info("[DEBUG] Submit button clicked")
            
            time.sleep(2)
            
            # Check page after submit
            self.check_page_source("AFTER_SUBMIT")
            logger.info(f"[DEBUG] Current URL after submit: {self.driver.current_url}")
            
            # Check for post-submit alerts
            try:
                alert = WebDriverWait(self.driver, 2).until(EC.alert_is_present())
                alert_text = alert.text
                logger.error(f"[!] ❌ POST-SUBMIT ALERT: '{alert_text}'")
                alert.dismiss()
                time.sleep(2)
                return False
            except:
                logger.info("[*] No post-submit alert")

            # Wait for chart with extended timeout
            logger.info("[*] Waiting for chart (15 sec timeout)...")
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.ID, "chartContainerHourly"))
                )
                logger.info("[+] ✓✓✓ LOGIN SUCCESSFUL!")
                return True
            except Exception as e:
                logger.error(f"[!] Chart not found after 15 sec: {e}")
                logger.error(f"[DEBUG] Current URL: {self.driver.current_url}")
                self.check_page_source("CHART_NOT_FOUND")
                
                # Try to find any content
                try:
                    page_title = self.driver.find_element(By.TAG_NAME, "h1").text
                    logger.error(f"[DEBUG] Page heading: {page_title}")
                except:
                    pass
                
                return False

        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.check_page_source("LOGIN_EXCEPTION")
            return False

    def extract_current_day_units(self):
        """Simple extraction"""
        try:
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            day_of_month = ist_now.day
            
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

    def run_once(self):
        try:
            logger.info("\n\n")
            logger.info("╔" + "="*78 + "╗")
            logger.info("║" + " "*25 + "UPPCL TRACKER RUN" + " "*37 + "║")
            logger.info("╚" + "="*78 + "╝")
            
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            logger.info(f"[*] IST Time: {ist_now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            self.setup_chrome_driver()

            if not self.login():
                logger.error("[!] ❌ LOGIN FAILED - STOPPING HERE FOR DEBUGGING")
                return False

            time.sleep(2)
            
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            timestamp = ist_now.strftime('%Y-%m-%d %H:%M:%S')
            hour = ist_now.hour

            logger.info(f"[*] Extracting data...")
            current_units = self.extract_current_day_units()
            last_reading = self.extract_last_reading()
            balance = self.extract_balance()
            source = self.extract_source()

            logger.info(f"\n[+] Extracted: {current_units} kWh, {last_reading}, {balance}")
            return True

        except Exception as e:
            logger.error(f"[!] Error: {e}")
            return False

        finally:
            if self.driver:
                self.driver.quit()
            logger.info("="*80)


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