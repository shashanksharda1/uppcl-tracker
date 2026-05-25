#!/usr/bin/env python3
"""
Chart Inspection Tool
Examine the actual chart structure on the UPPCL page
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json

def inspect_chart(driver):
    """Inspect the chart and print all SVG details"""
    
    print("\n" + "="*70)
    print("CHART INSPECTION")
    print("="*70)
    
    try:
        # Get page source
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')
        
        # Find all SVGs
        print("\n[1] Looking for ALL SVG elements...")
        svgs = soup.find_all('svg')
        print(f"[+] Found {len(svgs)} SVG elements total")
        
        if svgs:
            for i, svg in enumerate(svgs[:5]):  # Show first 5
                print(f"\n    SVG #{i+1}:")
                print(f"    - Class: {svg.get('class')}")
                print(f"    - ID: {svg.get('id')}")
                print(f"    - Data attrs: {svg.get('data-*')}")
                
                # Count circles
                circles = svg.find_all('circle')
                print(f"    - Circles: {len(circles)}")
                
                # Count paths
                paths = svg.find_all('path')
                print(f"    - Paths: {len(paths)}")
        
        # Look for ApexCharts specifically
        print("\n[2] Looking for ApexCharts SVG...")
        apex_svg = soup.find('svg', {'class': 'apexcharts-svg'})
        if apex_svg:
            print("[+] Found apexcharts-svg!")
            circles = apex_svg.find_all('circle')
            print(f"    - Circles: {len(circles)}")
            
            # Print circle attributes
            if circles:
                print(f"    - First circle: {circles[0].get('class')}, r={circles[0].get('r')}")
        else:
            print("[-] No apexcharts-svg found")
        
        # Look for any chart container
        print("\n[3] Looking for chart containers...")
        chart_containers = soup.find_all(class_='apexcharts')
        print(f"[+] Found {len(chart_containers)} apexcharts containers")
        
        # Look for tooltips
        print("\n[4] Looking for tooltip elements...")
        tooltips = soup.find_all(class_='apexcharts-tooltip')
        print(f"[+] Found {len(tooltips)} tooltip elements")
        
        if tooltips:
            print(f"    First tooltip content: {tooltips[0].get_text()[:100]}")
        
        # Look for data labels
        print("\n[5] Looking for data labels...")
        labels = soup.find_all(class_='apexcharts-datalabels')
        print(f"[+] Found {len(labels)} data label elements")
        
        # Try to find any visible numbers on chart
        print("\n[6] Looking for numbers in chart area...")
        chart_area = soup.find('div', class_='card')
        if chart_area:
            text = chart_area.get_text()
            import re
            numbers = re.findall(r'\d+\.?\d*', text)
            print(f"[+] Numbers found in chart area: {numbers[:10]}")
        
        # Save detailed HTML for manual inspection
        print("\n[7] Saving chart HTML to file...")
        chart_html = str(apex_svg if apex_svg else svgs[0] if svgs else "No chart found")
        with open('/tmp/chart_structure.html', 'w') as f:
            f.write(chart_html)
        print("[+] Saved to /tmp/chart_structure.html")
        
    except Exception as e:
        print(f"[!] Error: {e}")

def inspect_with_selenium(driver):
    """Use Selenium to inspect live elements"""
    
    print("\n" + "="*70)
    print("SELENIUM INSPECTION")
    print("="*70)
    
    try:
        # Check for SVG with various selectors
        selectors = [
            ('//svg[@class="apexcharts-svg"]', 'SVG with exact class'),
            ('//svg[contains(@class, "apexcharts")]', 'SVG with apexcharts in class'),
            ('//svg', 'Any SVG'),
            ('//circle', 'Any circle'),
            ('//div[@class="apexcharts-tooltip"]', 'Tooltip div'),
        ]
        
        for selector, desc in selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                print(f"\n[+] {desc}: {len(elements)} found")
                
                if elements and len(elements) <= 3:
                    for i, elem in enumerate(elements):
                        try:
                            print(f"    Element {i+1}: class='{elem.get_attribute('class')}', visible={elem.is_displayed()}")
                        except:
                            pass
            except Exception as e:
                print(f"[-] {desc}: {e}")
        
        # Try to execute JavaScript
        print("\n[*] Checking ApexCharts via JavaScript...")
        try:
            result = driver.execute_script("""
            return {
                hasApex: typeof ApexCharts !== 'undefined',
                instances: window.ApexCharts ? window.ApexCharts.instances.length : 0,
                svgCount: document.querySelectorAll('svg').length,
                circleCount: document.querySelectorAll('circle').length
            };
            """)
            print(f"[+] ApexCharts info: {result}")
        except Exception as e:
            print(f"[-] JS error: {e}")
        
    except Exception as e:
        print(f"[!] Error: {e}")

def main():
    """Main"""
    print("\n🔍 UPPCL Chart Inspector\n")
    
    # Setup driver
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    
    try:
        # Navigate to UPPCL (assuming already logged in, or will prompt)
        print("[*] Opening UPPCL page...")
        driver.get("https://uppclmp.myxenius.com/AppAMR")
        print("[*] Waiting for page to load... (you have 15 seconds to log in if needed)")
        
        time.sleep(15)  # Wait for page + manual login if needed
        
        # Run inspections
        inspect_with_selenium(driver)
        inspect_chart(driver)
        
        print("\n" + "="*70)
        print("INSPECTION COMPLETE")
        print("="*70)
        print("\nCheck /tmp/chart_structure.html for HTML details")
        print("The above info will help identify why chart extraction fails")
        print("\nLooking for:")
        print("  - How many circles are on the chart")
        print("  - What class/attributes they have")
        print("  - If tooltips exist and what they contain")
        print("  - If ApexCharts is even loaded")
        
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()

if __name__ == "__main__":
    main()
