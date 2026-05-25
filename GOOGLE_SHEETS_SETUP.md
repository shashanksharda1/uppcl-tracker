# 🔗 Google Sheets Integration Setup Guide

## Overview

Instead of saving to Excel, your tracker will:
- ✅ Log data directly to **Google Sheets**
- ✅ Access it from anywhere (phone, laptop, tablet)
- ✅ Auto-refresh in real-time
- ✅ Share with family/friends easily
- ✅ Create charts and dashboards

---

## Step 1: Create Google Cloud Project

### 1.1 Go to Google Cloud Console
1. Visit: https://console.cloud.google.com/
2. Sign in with your Google account

### 1.2 Create New Project
1. Click project dropdown at top
2. Click "NEW PROJECT"
3. Name it: "UPPCL Tracker"
4. Click CREATE

### 1.3 Enable Google Sheets API
1. Search for: "Google Sheets API"
2. Click on it
3. Click "ENABLE"

---

## Step 2: Create Service Account

### 2.1 Go to Service Accounts
1. In Google Cloud Console, go to: **APIs & Services** → **Credentials**
2. Click "CREATE CREDENTIALS" → "Service Account"

### 2.2 Fill Service Account Details
- **Service account name**: `uppcl-tracker`
- **Service account ID**: Auto-filled
- Click "CREATE AND CONTINUE"

### 2.3 Grant Permissions
- **Role**: "Editor" (or search "Editor")
- Click "CONTINUE"

### 2.4 Create JSON Key
1. Click "CREATE KEY"
2. Select "JSON"
3. Click "CREATE"
4. File `[project-name]-[id].json` downloads automatically

**IMPORTANT**: Rename this file to `service_account.json`

---

## Step 3: Share Google Sheet with Service Account

### 3.1 Get Service Account Email
1. Open the downloaded `service_account.json` with notepad
2. Find the line: `"client_email": "something@...iam.gserviceaccount.com"`
3. Copy that email address

### 3.2 Create Google Sheet
1. Go to: https://sheets.google.com/
2. Click "+" (New Sheet)
3. Name it: "UPPCL Consumption Tracker"
4. Click "Share"
5. Paste the service account email
6. Click "Share"

---

## Step 4: Setup Python Environment

### 4.1 Install Google Sheets Package
```bash
pip install gspread google-auth-oauthlib google-auth-httplib2
```

### 4.2 Place `service_account.json`
Put the JSON file in the same folder as your Python script

```
your_folder/
├── uppcl_google_sheets_tracker.py
├── service_account.json              ← Place here!
├── requirements.txt
└── uppcl_tracker.log
```

---

## Step 5: Update Script (If Different Credentials)

If you used different username/password:

```bash
python uppcl_google_sheets_tracker.py --username YOUR_USER --password YOUR_PASS --once
```

---

## Step 6: Test

### Run Once
```bash
python uppcl_google_sheets_tracker.py --once
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
    Reading: 2026-05-25 02:17:50
    Balance: ₹4,575.08
[*] Saving to Google Sheets...
[+] Row added to Google Sheets!
[+] Sheet: UPPCL Consumption Tracker
```

### Check Google Sheet
1. Go to: https://sheets.google.com/
2. Open: "UPPCL Consumption Tracker"
3. Should see one row with today's data

---

## Step 7: Run Continuous

```bash
python uppcl_google_sheets_tracker.py --interval 60
```

Your tracker will now:
- Log in every 60 minutes
- Capture all 3 metrics
- Add row to Google Sheet
- Run indefinitely

---

## 📊 Your Google Sheet Structure

```
Timestamp           | Current Day Units (kWh) | Last Reading Time        | Account Balance (₹)
2026-05-25 09:00:00 | 3.0                     | 2026-05-25 02:17:50     | ₹4,575.08
2026-05-25 10:00:00 | 3.5                     | 2026-05-25 03:15:00     | ₹4,575.08
2026-05-25 11:00:00 | 4.2                     | 2026-05-25 04:30:00     | ₹4,575.08
```

---

## ✨ Google Sheets Features You Can Use

### Create Chart
1. Select data columns
2. Insert → Chart
3. Choose type (Line, Bar, etc.)

### Conditional Formatting
1. Select column
2. Format → Conditional formatting
3. Highlight when balance < 500

### Formulas
```
# Daily average
=AVERAGE(B:B)

# Total consumption
=SUM(B:B)

# Max consumption hour
=MAX(B:B)
```

### Sharing
- Click "Share" → Enter emails
- Grant view/edit access
- Works on all devices

---

## 🔄 Google Sheet is Now Live!

You can now:
- ✅ View from phone (Google Sheets app)
- ✅ Share with family/friends
- ✅ Create dashboards
- ✅ Export to other tools
- ✅ Set alerts/notifications
- ✅ Access 24/7 from anywhere

---

## 🔐 Security Notes

### `service_account.json` is Sensitive!
- It gives full access to your Google Sheets
- **Don't share it publicly**
- **Don't commit to GitHub**
- Keep it in your project folder only

### Add to `.gitignore` (if using GitHub)
```bash
echo "service_account.json" >> .gitignore
```

---

## ❓ Troubleshooting

### "File not found: service_account.json"
- Check file is in same folder as script
- Check filename spelling exactly

### "Authentication failed"
- Verify service account email is correct
- Check Google Sheet is shared with that email
- Check Google Sheets API is enabled

### "No data showing in sheet"
- Check Google Sheet name matches script
- Verify service account has write access
- Check logs for errors

---

## 📱 Access Your Data Anywhere

### Google Sheets App
- Download from App Store / Play Store
- Open "UPPCL Consumption Tracker"
- Works offline too!

### Desktop
- Go to https://sheets.google.com/
- Data updates automatically

### Share with Others
- Click "Share" in Google Sheets
- Enter their email
- They can view in real-time

---

## 🎉 Next: Deploy to Cloud

Now that Google Sheets is working, you can:
1. Deploy to **Google Colab** (see `COLAB_DEPLOYMENT.md`)
2. Deploy to **Railway** (see `RAILWAY_DEPLOYMENT.md`)
3. Deploy to **Render** (see `RENDER_DEPLOYMENT.md`)
4. Deploy to **PythonAnywhere** (see `PYTHONANYWHERE_DEPLOYMENT.md`)

All free platforms - no laptop needed!

---

## Commands Reference

```bash
# Test once
python uppcl_google_sheets_tracker.py --once

# Run hourly
python uppcl_google_sheets_tracker.py --interval 60

# Run every 30 minutes
python uppcl_google_sheets_tracker.py --interval 30

# Run every 2 hours
python uppcl_google_sheets_tracker.py --interval 120

# Custom sheet name
python uppcl_google_sheets_tracker.py --sheet "My Tracker" --once
```

---

**Your Google Sheets tracker is ready! 📊✨**
