#!/usr/bin/env python3
"""
UPPCL Hourly Tracker with Google Sheets - v3.5
IMPROVED: Better chart tooltip extraction with ApexCharts support
"""

import time
from datetime import datetime, timedelta
import logging
import re
import os
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

import gspread
from google.oauth2.service_account import Credentials

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
    def __init__(
        self,
        username,
        password,
        google_sheets_name='UPPCL Consumption Tracker',
        service_account_json=None
    ):
        self.username = username
        self.password = password
        self.google_sheets_name = google_sheets_name
        self.service_account_json = service_account_json or 'service_account.json'
        
        self.base_url = "https://uppclmp.myxenius.com/login.html"
        self.home_url = "https://uppclmp.myxenius.com/AppAMR"
        self.driver = None
        self.sheet = None
        
        logger.info(f"[*] UPPCL Tracker v3.5 - Improved Chart Extraction")
        self.init_google_sheets()
    
    def init_google_sheets(self):
        """Initialize Google Sheets connection"""
        try:
            logger.info("[*] Initializing Google Sheets...")
            
            if not os.path.exists(self.service_account_json):
                logger.error(f"[!] Service account file not found: {self.service_account_json}")
                return False
            
            credentials = Credentials.from_service_account_file(
                self.service_account_json,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            
            logger.info("[+] Credentials created with correct scopes")
            client = gspread.authorize(credentials)
            
            try:
                self.spreadsheet = client.open(self.google_sheets_name)
                logger.info(f"[+] Opened spreadsheet: {self.google_sheets_name}")
            except gspread.SpreadsheetNotFound:
                logger.error(f"[!] Google Sheet not found: {self.google_sheets_name}")
                return False
            
            try:
                self.sheet = self.spreadsheet.worksheet('Hourly Data')
            except gspread.WorksheetNotFound:
                logger.info("[*] Creating worksheet: Hourly Data")
                self.sheet = self.spreadsheet.add_worksheet(title='Hourly Data', rows=10000, cols=4)
                headers = ['Timestamp', 'Current Day Units (kWh)', 'Last Reading Time', 'Account Balance (₹)']
                self.sheet.append_row(headers)
                logger.info("[+] Added headers to sheet")
            
            logger.info("[+] Google Sheets ready!")
            return True
        except Exception as e:
            logger.error(f"[!] Google Sheets error: {e}")
            return False
    
    def setup_driver(self, headless=False):
        """Setup Chrome WebDriver"""
        try:
            logger.info("[*] Setting up Chrome WebDriver...")
            options = webdriver.ChromeOptions()
            
            if headless:
                options.add_argument('--headless')
            
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("[+] WebDriver initialized")
            return True
        except Exception as e:
            logger.error(f"[!] WebDriver error: {e}")
            return False
    
    def handle_alert(self):
        """Handle unexpected alerts"""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            logger.warning(f"[!] Alert: {alert_text}")
            alert.accept()
            return True
        except:
            return False
    
    def solve_math_captcha(self, expression):
        """Solve mathematical captcha"""
        try:
            match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', expression)
            if not match:
                return None
            
            num1 = int(match.group(1))
            operator = match.group(2)
            num2 = int(match.group(3))
            
            if operator == '+': answer = num1 + num2
            elif operator == '-': answer = num1 - num2
            elif operator == '*': answer = num1 * num2
            elif operator == '/': answer = int(num1 / num2)
            else: return None
            
            logger.info(f"[+] Math: {num1} {operator} {num2} = {answer}")
            return str(answer)
        except Exception as e:
            logger.warning(f"[!] Math solving error: {e}")
            return None
    
    def solve_captcha_from_page(self):
        """Read captcha from DOM"""
        try:
            logger.info("[*] Waiting for captcha element to render...")
            
            captcha_element = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//div[@id="captchaText"]'))
            )
            logger.info("[+] Captcha element loaded")
            time.sleep(1.5)
            
            answer = captcha_element.get_attribute('data-answer')
            
            if answer:
                answer = str(answer).strip()
                displayed_text = captcha_element.text
                logger.info(f"[*] Captcha display: '{displayed_text}'")
                logger.info(f"[+] Captcha answer: {answer}")
                
                if '+' in displayed_text or '-' in displayed_text or '*' in displayed_text or '/' in displayed_text:
                    logger.info("[*] Detected math captcha, solving...")
                    math_answer = self.solve_math_captcha(displayed_text)
                    if math_answer:
                        logger.info(f"[+] Math solved: {math_answer}")
                        return math_answer
                
                if answer and len(answer) >= 1:
                    return answer
            
            logger.warning("[!] Could not read captcha answer")
            return None
        except Exception as e:
            logger.error(f"[!] Error reading captcha: {e}")
            return None
    
    def find_captcha_input_field(self):
        """Find captcha input field"""
        try:
            captcha_selectors = [
                '//input[@id="captchaInput"]',
                '//input[@placeholder="Enter Captcha"]',
                '//input[@id="captcha"]',
                '//input[@name="captcha"]',
                '//input[@type="text"]',
            ]
            
            for selector in captcha_selectors:
                try:
                    field = self.driver.find_element(By.XPATH, selector)
                    if field and field.is_displayed():
                        logger.info(f"[+] Found captcha input field")
                        return field
                except:
                    continue
            
            logger.warning("[!] Could not find captcha input field")
            return None
        except Exception as e:
            logger.error(f"[!] Error: {e}")
            return None
    
    def login(self):
        """Perform login"""
        try:
            logger.info("[*] Navigating to login page...")
            self.driver.get(self.base_url)
            time.sleep(4)
            
            logger.info("[*] Entering credentials...")
            
            try:
                username_field = self.driver.find_element(By.XPATH, '//input[@id="name"]')
                username_field.clear()
                username_field.send_keys(self.username)
                logger.info(f"[+] Username entered")
            except Exception as e:
                logger.warning(f"[!] Username error: {e}")
            
            time.sleep(0.5)
            try:
                password_field = self.driver.find_element(By.XPATH, '//input[@id="password"]')
                password_field.clear()
                password_field.send_keys(self.password)
                logger.info(f"[+] Password entered")
            except Exception as e:
                logger.warning(f"[!] Password error: {e}")
            
            time.sleep(1)
            logger.info("[*] Solving captcha...")
            captcha_answer = self.solve_captcha_from_page()
            
            if captcha_answer:
                captcha_input = self.find_captcha_input_field()
                if captcha_input:
                    try:
                        captcha_input.clear()
                        captcha_input.send_keys(captcha_answer)
                        logger.info(f"[+] Captcha entered: {captcha_answer}")
                    except Exception as e:
                        logger.warning(f"[!] Could not enter captcha: {e}")
                else:
                    logger.warning("[!] Could not find captcha input field")
            else:
                logger.warning("[!] Could not solve captcha")
            
            time.sleep(1)
            logger.info("[*] Submitting login...")
            
            submit_selectors = [
                '//button[@id="submitBtn"]',
                '//button[@type="submit"]',
                '//button[contains(text(), "Submit")]',
            ]
            
            for selector in submit_selectors:
                try:
                    submit = self.driver.find_element(By.XPATH, selector)
                    if submit and submit.is_enabled():
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", submit)
                        time.sleep(0.3)
                        submit.click()
                        logger.info(f"[+] Submit button clicked")
                        break
                except:
                    continue
            
            time.sleep(3)
            
            if self.handle_alert():
                logger.warning("[!] Login failed - captcha was incorrect")
                return False
            
            time.sleep(2)
            
            if 'login' not in self.driver.current_url.lower():
                logger.info("[+] Login successful!")
                return True
            else:
                logger.error("[!] Still on login page")
                return False
        except Exception as e:
            logger.error(f"[!] Login error: {e}")
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
            except:
                pass
            return False
    
    def extract_current_day_units(self):
        """v3.5: Improved chart tooltip extraction"""
        try:
            logger.info("[*] Extracting current day units...")
            
            today = datetime.now()
            day_of_month = today.day
            
            # Wait for chart to load
            logger.info("[*] Waiting for chart...")
            svg = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//svg[@class="apexcharts-svg"]'))
            )
            time.sleep(1.5)
            
            # Find data points
            logger.info(f"[*] Finding day {day_of_month} data point...")
            circles = self.driver.find_elements(By.XPATH, '//svg[@class="apexcharts-svg"]//circle[@r]')
            
            if not circles:
                circles = self.driver.find_elements(By.XPATH, '//svg//circle')
            
            logger.info(f"[+] Found {len(circles)} data points")
            
            if not circles or len(circles) < day_of_month:
                logger.warning(f"[!] Not enough data points")
                return None
            
            # Hover over today's circle
            target_circle = circles[day_of_month - 1]
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth'});", target_circle)
            time.sleep(0.5)
            
            logger.info(f"[*] Hovering over day {day_of_month}...")
            actions = ActionChains(self.driver)
            actions.move_to_element(target_circle).perform()
            time.sleep(1.5)
            
            # Look for tooltip
            tooltip_selectors = [
                '//div[@class="apexcharts-tooltip apexcharts-active"]',
                '//div[contains(@class, "apexcharts-tooltip") and contains(@class, "active")]',
                '//div[@class="apexcharts-tooltip-custom"]',
                '//*[contains(@class, "tooltip")][@style and not(contains(@style, "display: none"))]',
                '//div[contains(text(), "Unit")]',
            ]
            
            tooltip = None
            for selector in tooltip_selectors:
                try:
                    tooltip = WebDriverWait(self.driver, 0.5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    if tooltip and tooltip.is_displayed():
                        logger.info(f"[+] Tooltip found")
                        break
                except:
                    continue
            
            if not tooltip:
                logger.warning("[!] Tooltip not found")
                return None
            
            # Extract text
            tooltip_text = tooltip.text.strip()
            logger.info(f"[*] Tooltip: '{tooltip_text}'")
            
            if not tooltip_text:
                tooltip_text = self.driver.execute_script("return arguments[0].innerHTML;", tooltip)
                logger.info(f"[*] Tooltip HTML: '{tooltip_text}'")
            
            # Parse units
            patterns = [
                r'Units?\s*:\s*(\d+\.?\d*)',
                r'Grid\s+Units?\s*:\s*(\d+\.?\d*)',
                r'(\d+\.?\d*)\s*(?:kWh|KWH)',
                r'>(\d+\.?\d*)<',
                r'(\d+\.?\d*)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, tooltip_text, re.IGNORECASE)
                if match:
                    units = float(match.group(1))
                    logger.info(f"[+] Extracted: {units} kWh")
                    return units
            
            logger.warning("[!] Could not parse units from tooltip")
            return None
        
        except Exception as e:
            logger.error(f"[!] Error: {e}")
            return None
    
    def extract_last_reading_time(self):
        """Extract last reading timestamp"""
        try:
            logger.info("[*] Extracting last reading time...")
            
            page_html = self.driver.page_source
            soup = BeautifulSoup(page_html, 'html.parser')
            page_text = soup.get_text()
            
            match = re.search(
                r'Last\s+Reading\s+As\s+on\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
                page_text,
                re.IGNORECASE
            )
            
            if match:
                timestamp = match.group(1)
                logger.info(f"[+] Last reading: {timestamp}")
                return timestamp
            
            logger.warning("[!] Last reading time not found")
            return None
        except Exception as e:
            logger.error(f"[!] Error: {e}")
            return None
    
    def extract_account_balance(self):
        """Extract account balance"""
        try:
            logger.info("[*] Extracting account balance...")
            
            page_html = self.driver.page_source
            soup = BeautifulSoup(page_html, 'html.parser')
            page_text = soup.get_text()
            
            match = re.search(
                r'Updated\s+Balance\s*:\s*Grid\s+Bal\s*:\s*Rs\.\s*([\d,]+\.?\d*)',
                page_text,
                re.IGNORECASE
            )
            
            if match:
                balance_str = match.group(1).replace(',', '')
                balance = float(balance_str)
                logger.info(f"[+] Balance: ₹{balance:.2f}")
                return balance
            
            logger.warning("[!] Balance not found")
            return None
        except Exception as e:
            logger.error(f"[!] Error: {e}")
            return None
    
    def capture_and_save(self):
        """Capture data and save"""
        try:
            logger.info("\n" + "="*70)
            logger.info(f"[CAPTURE] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("="*70)
            
            units = self.extract_current_day_units()
            last_reading = self.extract_last_reading_time()
            balance = self.extract_account_balance()
            
            row = [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                units if units is not None else 'N/A',
                last_reading if last_reading else 'N/A',
                f"₹{balance:.2f}" if balance is not None else 'N/A'
            ]
            
            if not self.sheet:
                logger.error("[!] Google Sheets not initialized")
                return False
            
            self.sheet.append_row(row)
            logger.info("[+] Row added to Google Sheets! ✅")
            
            return True
        except Exception as e:
            logger.error(f"[!] Error: {e}")
            return False
    
    def run_once(self):
        """Run single capture"""
        try:
            if not self.setup_driver(headless=False):
                return False
            
            if not self.login():
                self.driver.quit()
                return False
            
            logger.info("[*] Navigating to home page...")
            self.driver.get(self.home_url)
            time.sleep(3)
            
            result = self.capture_and_save()
            
            self.driver.quit()
            return result
        except Exception as e:
            logger.error(f"[!] Error: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            return False
    
    def run_continuous(self, interval_minutes=60):
        """Run continuously"""
        logger.info("="*70)
        logger.info("UPPCL GOOGLE SHEETS TRACKER - CONTINUOUS MODE")
        logger.info("="*70)
        logger.info(f"Interval: {interval_minutes} minutes")
        logger.info(f"Spreadsheet: {self.google_sheets_name}")
        logger.info("="*70 + "\n")
        
        cycle = 0
        try:
            while True:
                cycle += 1
                logger.info(f"\n[CYCLE {cycle}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                if self.setup_driver(headless=True):
                    if self.login():
                        self.driver.get(self.home_url)
                        time.sleep(3)
                        self.capture_and_save()
                    
                    self.driver.quit()
                
                next_run = datetime.now() + timedelta(minutes=interval_minutes)
                logger.info(f"[*] Next: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            logger.info("\n[*] Tracker stopped")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='UPPCL Tracker v3.5 - Improved Chart Extraction')
    parser.add_argument('--username', default='5573683932', help='UPPCL username')
    parser.add_argument('--password', default='5573683932', help='UPPCL password')
    parser.add_argument('--sheet', default='UPPCL Consumption Tracker', help='Google Sheet name')
    parser.add_argument('--service-account', default='service_account.json', help='Service account JSON')
    parser.add_argument('--interval', type=int, default=60, help='Interval in minutes')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    
    args = parser.parse_args()
    
    tracker = UPPCLGoogleSheetsTracker(
        args.username,
        args.password,
        args.sheet,
        args.service_account
    )
    
    if args.once:
        logger.info("[*] Running single capture...")
        tracker.run_once()
    else:
        tracker.run_continuous(args.interval)


if __name__ == "__main__":
    main()
