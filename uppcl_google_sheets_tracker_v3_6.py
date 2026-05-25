#!/usr/bin/env python3
"""
UPPCL Tracker v3.7 - Fixed for GitHub Actions
Uses system Chrome and ChromeDriver (pre-installed on GitHub Actions)
"""

import os
import sys
import logging
import time
import re
from datetime import datetime
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
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

class UPPCLGoogleSheetsTracker:
    """UPPCL tracker with Google Sheets integration - GitHub Actions compatible"""
    
    def __init__(self, username, password, sheet_name, service_account_path):
        self.username = username
        self.password = password
        self.sheet_name = sheet_name
        self.service_account_path = service_account_path
        self.gs = None
        self.worksheet = None
        self.driver = None
        
    def init_google_sheets(self):
        """Initialize Google Sheets connection with correct scopes"""
        logger.info("[*] Initializing Google Sheets...")
        
        try:
            # Load credentials with BOTH required scopes
            credentials = Credentials.from_service_account_file(
                self.service_account_path,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            
            # Refresh credentials
            credentials.refresh(Request())
            logger.info("[+] Credentials created with correct scopes")
            
            # Authorize and open spreadsheet
            self.gs = gspread.authorize(credentials)
            self.worksheet = self.gs.open(self.sheet_name).sheet1
            logger.info(f"[+] Opened spreadsheet: {self.sheet_name}")
            logger.info("[+] Google Sheets ready!")
            
        except Exception as e:
            logger.error(f"[!] Google Sheets error: {e}")
            raise
    
    def setup_chrome_driver(self):
        """Setup Chrome WebDriver - uses system Chrome on GitHub Actions"""
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
                logger.info("[*] Using system Chrome (GitHub Actions environment)")
                chrome_options.binary_location = '/opt/hostedtoolcache/setup-chrome/chromium/1635668/x64/chrome'
                
                # Use system chromedriver (pass as service parameter, not positional)
                from selenium.webdriver.chrome.service import Service
                service = Service('/usr/local/bin/chromedriver')
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # Local development - use webdriver-manager
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            logger.info("[+] Chrome WebDriver initialized")
            
        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            raise
    
    def solve_captcha(self):
        """Solve login captcha"""
        try:
            logger.info("[*] Solving captcha...")
            
            # Find captcha element
            captcha_div = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "captchaText"))
            )
            
            captcha_text = captcha_div.get_attribute('data-answer')
            logger.info(f"[+] Captcha answer extracted: {captcha_text}")
            
            # Fill captcha input
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
            
            # Enter credentials
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "name"))
            )
            username_field.send_keys(self.username)
            
            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(self.password)
            
            # Solve and submit
            self.solve_captcha()
            
            submit_button = self.driver.find_element(By.ID, "submitBtn")
            submit_button.click()
            
            # Wait for redirect to dashboard
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "chartContainerHourly"))
            )
            
            logger.info("[+] Login successful!")
            return True
            
        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            return False
    
    def extract_source(self):
        """Extract power source from heading"""
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
            
            logger.warning("[!] Could not extract source")
            return "Unknown"
            
        except Exception as e:
            logger.error(f"[!] Source extraction error: {e}")
            return "Unknown"
    
    def extract_units(self):
        """Extract current day units from Highcharts"""
        try:
            day_of_month = datetime.now().day
            
            # JavaScript to extract from Highcharts
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
                logger.info(f"[+] Extracted from Highcharts: {units} kWh")
                return float(units)
            
            logger.warning("[!] Could not extract units from chart")
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
            
            logger.warning("[!] Could not extract last reading time")
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
            
            logger.warning("[!] Could not extract balance")
            return "N/A"
            
        except Exception as e:
            logger.error(f"[!] Balance extraction error: {e}")
            return "N/A"
    
    def add_row_to_sheets(self, timestamp, source, units, last_reading, balance):
        """Add data row to Google Sheets"""
        try:
            row = [timestamp, source, units, last_reading, balance]
            self.worksheet.append_row(row)
            logger.info("[+] Row added to Google Sheets! ✅")
            
        except Exception as e:
            logger.error(f"[!] Google Sheets append error: {e}")
    
    def run_once(self):
        """Run tracker once"""
        try:
            logger.info("[*] Running single capture...")
            
            self.setup_chrome_driver()
            
            if not self.login():
                logger.error("[!] Login failed")
                return False
            
            # Wait for chart to load
            time.sleep(2)
            
            # Extract all metrics
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            source = self.extract_source()
            units = self.extract_units()
            last_reading = self.extract_last_reading()
            balance = self.extract_balance()
            
            # Add to sheets
            self.add_row_to_sheets(timestamp, source, units, last_reading, balance)
            
            logger.info("[+] Single capture completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"[!] Error during capture: {e}")
            return False
            
        finally:
            if self.driver:
                self.driver.quit()
    
    def run_continuous(self, interval=60):
        """Run tracker continuously"""
        logger.info(f"[*] Starting continuous tracking every {interval} seconds...")
        
        try:
            while True:
                self.run_once()
                logger.info(f"[*] Next capture in {interval} seconds...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("[*] Tracker stopped by user")
        except Exception as e:
            logger.error(f"[!] Continuous run error: {e}")

def main():
    """Main entry point"""
    import argparse
    
    # Get from environment variables (GitHub Actions)
    env_username = os.getenv('UPPCL_USERNAME', '5573683932')
    env_password = os.getenv('UPPCL_PASSWORD', '5573683932')
    env_sheet = os.getenv('GOOGLE_SHEETS_NAME', 'UPPCL Consumption Tracker')
    
    sa_path = 'service_account.json'
    
    parser = argparse.ArgumentParser(description='UPPCL Tracker')
    parser.add_argument('--username', default=env_username)
    parser.add_argument('--password', default=env_password)
    parser.add_argument('--sheet', default=env_sheet)
    parser.add_argument('--service-account', default=sa_path)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--once', action='store_true')
    
    args = parser.parse_args()
    
    logger.info("[*] UPPCL Tracker v3.7 - GitHub Actions Compatible")
    
    tracker = UPPCLGoogleSheetsTracker(
        args.username,
        args.password,
        args.sheet,
        args.service_account
    )
    
    # Initialize Google Sheets first
    tracker.init_google_sheets()
    
    if args.once:
        tracker.run_once()
    else:
        tracker.run_continuous(args.interval)

if __name__ == '__main__':
    main()
