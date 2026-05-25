#!/usr/bin/env python3
"""
UPPCL Tracker v3.8 - Enhanced with:
- Hourly tracking at minute 2 of each hour
- Auto-computed hourly consumption (current hour - last hour)
- Benchmark comparison (last 3 days same hour average)
- Multi-sheet organization (Today, This Month, Last Month)
- Conditional formatting alerts for high consumption
"""

import os
import sys
import logging
import time
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

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

# Setup logging
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
    """Enhanced UPPCL tracker with hourly consumption and benchmarking"""
    
    def __init__(self, username, password, sheet_name, service_account_path):
        self.username = username
        self.password = password
        self.sheet_name = sheet_name
        self.service_account_path = service_account_path
        self.gs = None
        self.worksheets = {}  # Store references: 'today', 'this_month', 'last_month'
        self.driver = None
        
    def init_google_sheets(self):
        """Initialize Google Sheets with multiple sheet tabs"""
        logger.info("[*] Initializing Google Sheets...")
        
        try:
            # Load credentials with both required scopes
            credentials = Credentials.from_service_account_file(
                self.service_account_path,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            
            credentials.refresh(Request())
            logger.info("[+] Credentials created with correct scopes")
            
            # Authorize and open spreadsheet
            self.gs = gspread.authorize(credentials)
            spreadsheet = self.gs.open(self.sheet_name)
            logger.info(f"[+] Opened spreadsheet: {self.sheet_name}")
            
            # Initialize or get worksheets
            self._setup_worksheets(spreadsheet)
            
            logger.info("[+] Google Sheets ready!")
            
        except Exception as e:
            logger.error(f"[!] Google Sheets error: {e}")
            raise
    
    def _setup_worksheets(self, spreadsheet):
        """Setup or get today, this month, and last month worksheets"""
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
                    # Create new sheet
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
        """Add headers to a worksheet"""
        headers = [
            'Timestamp',
            'Hour',
            'Current Day Units (kWh)',
            'Hourly Consumption (kWh)',
            'Last Hour Units (kWh)',
            'Benchmark (3-day avg)',
            'Above Benchmark?',
            'Last Reading Time',
            'Account Balance (₹)',
            'Source'
        ]
        worksheet.append_row(headers)
        logger.info("[+] Headers added to worksheet")
    
    def setup_chrome_driver(self):
        """Setup Chrome WebDriver - auto-detects paths"""
        logger.info("[*] Setting up Chrome WebDriver...")
        
        try:
            # Chrome options for headless operation
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # Check if running on GitHub Actions
            if os.getenv('USE_SYSTEM_CHROME') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true':
                logger.info("[*] GitHub Actions environment detected")
                
                # Find ChromeDriver
                result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception("ChromeDriver not found in PATH")
                
                chromedriver_bin = result.stdout.strip()
                logger.info(f"[*] Found chromedriver at: {chromedriver_bin}")
                
                # Find Chrome
                chrome_result = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
                if chrome_result.returncode == 0:
                    chrome_bin = chrome_result.stdout.strip()
                    chrome_options.binary_location = chrome_bin
                    logger.info(f"[*] Found Chrome at: {chrome_bin}")
                else:
                    chrome_paths = [
                        '/usr/bin/google-chrome',
                        '/usr/bin/chromium-browser',
                        '/snap/bin/chromium'
                    ]
                    for path in chrome_paths:
                        if os.path.exists(path):
                            chrome_options.binary_location = path
                            logger.info(f"[*] Found Chrome at: {path}")
                            break
                
                service = Service(chromedriver_bin)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("[+] Chrome WebDriver initialized (GitHub Actions)")
            else:
                # Local development
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("[+] Chrome WebDriver initialized (local)")
            
        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            raise
    
    def solve_captcha(self):
        """Solve login captcha"""
        try:
            logger.info("[*] Solving captcha...")
            
            captcha_div = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "captchaText"))
            )
            
            captcha_text = captcha_div.get_attribute('data-answer')
            logger.info(f"[+] Captcha answer extracted: {captcha_text}")
            
            captcha_input = self.driver.find_element(By.ID, "captchaInput")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            
            logger.info("[+] Captcha solved")
            return True
            
        except Exception as e:
            logger.error(f"[!] Captcha error: {e}")
            return False
    
    def login(self):
        """Login to UPPCL portal"""
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
            
            submit_button = self.driver.find_element(By.ID, "submitBtn")
            submit_button.click()
            
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )
            
            logger.info("[+] Login successful!")
            return True
            
        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            return False
    
    def extract_source(self):
        """Extract power source"""
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
            logger.error(f"[!] Source extraction error: {e}")
            return "Unknown"
    
    def extract_current_day_units(self):
        """Extract current day cumulative units from Highcharts"""
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
                logger.info(f"[+] Current day units: {units} kWh")
                return float(units)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"[!] Units extraction error: {e}")
            return 0.0
    
    def extract_last_reading(self):
        """Extract last reading time"""
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
            logger.error(f"[!] Last reading extraction error: {e}")
            return "N/A"
    
    def extract_balance(self):
        """Extract account balance"""
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            text = soup.get_text()
            
            match = re.search(r'Updated Balance\s*:\s*Grid Bal:\s*Rs\.\s*([\d,]+\.?\d*)', text)
            if match:
                balance = match.group(1)
                logger.info(f"[+] Balance: ₹{balance}")
                return balance
            
            return "N/A"
            
        except Exception as e:
            logger.error(f"[!] Balance extraction error: {e}")
            return "N/A"
    
    def calculate_hourly_consumption(self, current_units, last_hour_units):
        """Calculate consumption in current hour"""
        if last_hour_units is None or last_hour_units == 0:
            return 0.0
        
        consumption = current_units - last_hour_units
        # If negative (likely midnight reset), set to 0
        if consumption < 0:
            return 0.0
        
        logger.info(f"[+] Hourly consumption: {consumption} kWh")
        return consumption
    
    def get_last_hour_units(self):
        """Get units from last hour's record"""
        try:
            today_ws = self.worksheets['today']
            all_rows = today_ws.get_all_values()
            
            if len(all_rows) > 1:  # More than just headers
                last_row = all_rows[-1]
                last_units = float(last_row[2]) if last_row[2] else 0.0
                logger.info(f"[*] Last hour units: {last_units} kWh")
                return last_units
            
            logger.info("[*] No previous hour record found")
            return 0.0
            
        except Exception as e:
            logger.error(f"[!] Error getting last hour units: {e}")
            return 0.0
    
    def calculate_benchmark(self, hour_of_day):
        """Calculate 3-day average benchmark for this hour"""
        try:
            today_ws = self.worksheets['today']
            this_month_ws = self.worksheets['this_month']
            
            consumptions = []
            current_date = datetime.now().date()
            
            # Get last 3 days consumption for this hour
            for days_back in range(1, 4):
                check_date = current_date - timedelta(days=days_back)
                
                try:
                    # Search in this month sheet
                    all_rows = this_month_ws.get_all_values()
                    
                    for row in all_rows[1:]:  # Skip headers
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
                logger.info(f"[+] Benchmark for hour {hour_of_day}: {benchmark:.2f} kWh (from {len(consumptions)} days)")
                return round(benchmark, 2)
            else:
                logger.info(f"[*] No benchmark data for hour {hour_of_day}")
                return None
            
        except Exception as e:
            logger.error(f"[!] Benchmark calculation error: {e}")
            return None
    
    def add_row_to_today_sheet(self, timestamp, hour, current_units, hourly_consumption, 
                               last_hour_units, benchmark, last_reading, balance, source):
        """Add row to today's sheet"""
        try:
            # Determine if above benchmark
            above_benchmark = "YES" if benchmark and hourly_consumption > benchmark else "NO"
            
            row = [
                timestamp,
                hour,
                current_units,
                hourly_consumption,
                last_hour_units,
                benchmark if benchmark else "N/A",
                above_benchmark,
                last_reading,
                balance,
                source
            ]
            
            today_ws = self.worksheets['today']
            today_ws.append_row(row)
            logger.info("[+] Row added to Today's sheet! ✅")
            
            # Add conditional formatting if above benchmark
            if above_benchmark == "YES":
                self._apply_alert_formatting(today_ws)
            
            return True
            
        except Exception as e:
            logger.error(f"[!] Google Sheets append error: {e}")
            return False
    
    def _apply_alert_formatting(self, worksheet):
        """Apply conditional formatting to highlight high consumption rows"""
        try:
            # Note: Conditional formatting through gspread API requires more complex setup
            # For now, we'll just log it. In production, you'd use spreadsheet.batch_update()
            logger.info("[*] Alert: High consumption detected (above benchmark)")
            
        except Exception as e:
            logger.error(f"[!] Formatting error: {e}")
    
    def archive_old_data(self):
        """Move yesterday's data from today to this month sheet"""
        try:
            today_ws = self.worksheets['today']
            today = datetime.now().date()
            
            all_rows = today_ws.get_all_values()
            
            if len(all_rows) > 1:
                rows_to_move = []
                rows_to_keep = [all_rows[0]]  # Keep headers
                
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
                    # Add to this month sheet
                    this_month_ws = self.worksheets['this_month']
                    for row in rows_to_move:
                        this_month_ws.append_row(row)
                    
                    logger.info(f"[+] Archived {len(rows_to_move)} old records to This Month sheet")
                    
                    # Clear today sheet and re-add headers
                    if len(rows_to_keep) > 1:
                        today_ws.clear()
                        today_ws.append_rows(rows_to_keep)
                        logger.info("[+] Cleaned up Today sheet")
            
        except Exception as e:
            logger.error(f"[!] Archive error: {e}")
    
    def run_once(self):
        """Run tracker once"""
        try:
            logger.info("[*] Running hourly capture...")
            
            self.setup_chrome_driver()
            
            if not self.login():
                logger.error("[!] Login failed")
                return False
            
            time.sleep(2)
            
            # Extract all metrics
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            hour = datetime.now().hour
            current_units = self.extract_current_day_units()
            last_hour_units = self.get_last_hour_units()
            hourly_consumption = self.calculate_hourly_consumption(current_units, last_hour_units)
            benchmark = self.calculate_benchmark(hour)
            last_reading = self.extract_last_reading()
            balance = self.extract_balance()
            source = self.extract_source()
            
            # Add to today's sheet
            success = self.add_row_to_today_sheet(
                timestamp, hour, current_units, hourly_consumption,
                last_hour_units, benchmark, last_reading, balance, source
            )
            
            if success:
                # Archive old data from today sheet to this month
                self.archive_old_data()
                logger.info("[+] Hourly capture completed successfully!")
            
            return success
            
        except Exception as e:
            logger.error(f"[!] Error during capture: {e}")
            return False
            
        finally:
            if self.driver:
                self.driver.quit()

def main():
    """Main entry point"""
    import argparse
    
    # Get from environment variables
    env_username = os.getenv('UPPCL_USERNAME', '5573683932')
    env_password = os.getenv('UPPCL_PASSWORD', '5573683932')
    env_sheet = os.getenv('GOOGLE_SHEETS_NAME', 'UPPCL Consumption Tracker')
    
    sa_path = 'service_account.json'
    
    parser = argparse.ArgumentParser(description='UPPCL Tracker v3.8')
    parser.add_argument('--username', default=env_username)
    parser.add_argument('--password', default=env_password)
    parser.add_argument('--sheet', default=env_sheet)
    parser.add_argument('--service-account', default=sa_path)
    parser.add_argument('--once', action='store_true')
    
    args = parser.parse_args()
    
    logger.info("[*] UPPCL Tracker v3.8 - Enhanced with Hourly Benchmarking")
    
    tracker = UPPCLEnhancedTracker(
        args.username,
        args.password,
        args.sheet,
        args.service_account
    )
    
    # Initialize Google Sheets
    tracker.init_google_sheets()
    
    if args.once:
        tracker.run_once()

if __name__ == '__main__':
    main()