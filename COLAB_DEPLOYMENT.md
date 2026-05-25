# 🚀 Deploy to Google Colab (FREE & EASIEST)

## Why Google Colab?

✅ **Completely Free** - No credit card needed  
✅ **Easy Setup** - Just copy-paste  
✅ **12 Hour Sessions** - Plenty for 24/7 tracking  
✅ **Already Have Google Account** - Reuse for login  
✅ **Integrated with Google Sheets** - Perfect fit!  

---

## 📋 What You Need

1. **Google Account** (same one you use for Gmail)
2. **UPPCL Credentials** (username/password)
3. **service_account.json** (from Google Sheets setup)
4. **Google Sheet** created and shared with service account

---

## Step 1: Upload Files to Google Drive

### 1.1 Open Google Drive
1. Go to: https://drive.google.com/
2. Create new folder: "UPPCL_Tracker"

### 1.2 Upload Files
1. Right-click in folder → Upload files
2. Upload these files:
   - `uppcl_google_sheets_tracker.py`
   - `service_account.json` (keep secure!)
   - `requirements.txt`

---

## Step 2: Create Google Colab Notebook

### 2.1 Create New Notebook
1. In same Drive folder, right-click → More → Google Colaboratory
2. Name it: "UPPCL_Tracker_Runner"

### 2.2 Copy This Code

Paste into Colab cell and run:

```python
# Mount Google Drive
from google.colab import drive
drive.mount('/content/drive')

# Change to project folder
import os
os.chdir('/content/drive/My Drive/UPPCL_Tracker')

# List files
!ls -la
```

Expected output:
```
requirements.txt
service_account.json
uppcl_google_sheets_tracker.py
```

---

## Step 3: Install Dependencies

Paste in new cell:

```python
# Install Selenium and dependencies
!pip install -q selenium webdriver-manager gspread google-auth-oauthlib google-auth-httplib2

# Install Chrome for Selenium
!apt-get install -q chromium-chromedriver > /dev/null 2>&1

print("[+] All packages installed!")
```

Run and wait for completion.

---

## Step 4: Run One-Time Test

Paste in new cell:

```python
import subprocess
import sys

result = subprocess.run(
    [sys.executable, 'uppcl_google_sheets_tracker.py', '--once'],
    capture_output=True,
    text=True
)

print(result.stdout)
if result.stderr:
    print("ERRORS:")
    print(result.stderr)
```

Expected output:
```
[*] Initializing Google Sheets...
[+] Opened existing spreadsheet: UPPCL Consumption Tracker
[*] Navigating to login page...
[+] Login successful!
[*] Extracting current day units...
[+] Data captured:
    Units: 3.2
...
[+] Row added to Google Sheets!
```

Check Google Sheet to verify data was added!

---

## Step 5: Run Continuous (24/7)

### Option A: Simple Continuous

Paste in new cell:

```python
import subprocess
import sys

# Run continuous every 60 minutes
result = subprocess.run(
    [sys.executable, 'uppcl_google_sheets_tracker.py', '--interval', '60'],
    capture_output=True,
    text=True
)

print(result.stdout)
```

**Problem**: Colab sessions disconnect after 12 hours.

---

### Option B: Auto-Restart Loop (BETTER)

Paste in new cell and run:

```python
import subprocess
import sys
import time
from datetime import datetime

cycle = 0
while True:
    cycle += 1
    print(f"\n{'='*70}")
    print(f"[CYCLE {cycle}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('='*70)
    
    try:
        result = subprocess.run(
            [sys.executable, 'uppcl_google_sheets_tracker.py', '--once'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)  # Last 500 chars
        
        if result.stderr:
            print("Errors:", result.stderr[-200:])
    except subprocess.TimeoutExpired:
        print("[!] Process timeout - retrying next cycle")
    except Exception as e:
        print(f"[!] Error: {e}")
    
    print(f"[*] Waiting 60 minutes until next cycle...")
    time.sleep(60 * 60)  # 60 minutes
```

This will:
- Run continuously
- Capture every 60 minutes
- Auto-restart if it fails
- Add rows to Google Sheets
- Show progress in notebook

---

## Step 6: Prevent Colab Timeout

**Problem**: Colab disconnects after 12 hours of idle time.

**Solution**: Add auto-click extension or run from phone:

### Option 1: Keep Browser Open
- Keep Colab tab open in browser
- Don't close the page
- Keep computer awake (or use phone's always-on)

### Option 2: Use Colab Pro (Optional)
- $10/month gets 24-hour sessions
- But Google Sheets method is free forever!

### Option 3: Deploy to Permanent Cloud (See Next Section)
- Use Railway, Render, or PythonAnywhere
- These are specifically designed for 24/7

---

## 📊 View Your Data

While Colab is running:
1. Go to Google Sheets
2. Open "UPPCL Consumption Tracker"
3. Watch rows being added automatically!
4. Create charts, formulas, etc.

---

## 🔄 If Session Dies

Colab sessions sometimes disconnect. When that happens:

### Check What Happened
1. Open Colab notebook
2. Scroll down - you'll see where it stopped
3. Check Google Sheets - data is still there!

### Restart
1. Run the cells again
2. It resumes automatically
3. No data is lost (it's in Google Sheets)

---

## 💡 Pro Tips

### Monitor in Real-Time
```python
# View latest Google Sheets data
import gspread
from google.oauth2.service_account import Credentials

creds = Credentials.from_service_account_file('service_account.json')
client = gspread.authorize(creds)
sheet = client.open('UPPCL Consumption Tracker').sheet1

# Get last 5 rows
rows = sheet.get_all_values()
for row in rows[-5:]:
    print(row)
```

### Send Notifications
```python
# Add this to send email alerts when balance is low
import smtplib

if balance < 500:
    # Send email alert
    smtp = smtplib.SMTP('smtp.gmail.com', 587)
    smtp.login('your_email@gmail.com', 'your_app_password')
    # Send message...
```

---

## 📱 Save Colab Link

Save your Colab notebook link so you can access it anytime:

1. Click **Share** button in Colab
2. Get the link
3. Bookmark it
4. Can resume from phone, tablet, anywhere

---

## ✅ Colab Checklist

- [ ] Files uploaded to Drive
- [ ] Colab notebook created
- [ ] Dependencies installed
- [ ] Test run successful
- [ ] Data added to Google Sheet
- [ ] Continuous loop running
- [ ] Bookmark Colab link

---

## 🚨 Common Issues

### "ModuleNotFoundError: No module named 'selenium'"
```python
!pip install selenium webdriver-manager
```

### "Chrome driver not found"
```python
!apt-get install -q chromium-chromedriver
```

### "service_account.json not found"
- Make sure file is uploaded to Drive
- Run: `!ls -la` to verify it's there

### "Permission denied for Google Sheets"
- Check service account email is correct
- Check Google Sheet is shared with that email
- Check Google Sheets API is enabled

---

## 🎯 Next Steps

### Keep It Simple (Colab)
Just keep Colab running in background:
- Open your Colab notebook
- Run the continuous cell
- Leave it running
- Check Google Sheets anytime

### Go Permanent (Optional)
If you want true 24/7 without keeping browser open:
- See `RAILWAY_DEPLOYMENT.md`
- See `RENDER_DEPLOYMENT.md`
- See `PYTHONANYWHERE_DEPLOYMENT.md`

---

## 🎉 You're All Set!

Your tracker is now running in cloud (Google Colab) and logging to Google Sheets!

**Next**: Monitor your data in Google Sheets and create visualizations! 📊✨

---

**Pro Tip**: Share your Google Sheet with family to track electricity together! 👨‍👩‍👧‍👦
