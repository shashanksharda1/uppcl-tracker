# 🚂 Deploy to Railway (FREE, Easiest Permanent)

## Why Railway?

✅ **Completely Free** - $5/month free tier (includes 1 app)  
✅ **24/7 Running** - No timeouts like Colab  
✅ **Easy Deploy** - Connect GitHub, click deploy  
✅ **Perfect for Python** - Direct support  
✅ **Built-in Logging** - View logs anytime  

**Best Option for Production!**

---

## 📋 What You Need

1. **GitHub Account** (free)
2. **Railway Account** (free)
3. Your UPPCL project files
4. `service_account.json` (kept safe)

---

## Step 1: Create GitHub Repository

### 1.1 Go to GitHub
1. Visit: https://github.com/
2. Sign up (if needed)

### 1.2 Create New Repository
1. Click **+** → New repository
2. Name: `uppcl-tracker`
3. Description: "UPPCL electricity consumption tracker"
4. Select: Public
5. Click "Create repository"

### 1.3 Upload Your Files
Option A (Web Upload):
1. Click "Upload files"
2. Drag files into the box
3. Add commit message: "Initial commit"
4. Commit

Files to upload:
```
uppcl_google_sheets_tracker.py
requirements.txt
Procfile                          (create - see below)
runtime.txt                       (create - see below)
```

---

## Step 2: Create Required Files

### 2.1 Create `Procfile`

In GitHub, click "Add file" → "Create new file"

Name: `Procfile`

Content:
```
worker: python uppcl_google_sheets_tracker.py --interval 60
```

Commit.

### 2.2 Create `runtime.txt`

Name: `runtime.txt`

Content:
```
python-3.11.0
```

Commit.

### 2.3 Update `requirements.txt`

Make sure it has:
```
selenium==4.15.2
webdriver-manager==4.0.1
beautifulsoup4==4.12.2
gspread==5.12.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
pandas==2.1.3
```

---

## Step 3: Create Railway Account

### 3.1 Go to Railway
1. Visit: https://railway.app/
2. Click "Start Project"
3. Sign up with GitHub (easiest)

### 3.2 Connect GitHub
1. Authorize Railway to access GitHub
2. Select repository: `uppcl-tracker`
3. Click "Deploy"

Railway will:
- Detect Python project
- Install dependencies
- Start your app
- Show logs

---

## Step 4: Add Environment Variables

Your app needs `service_account.json` content as environment variable.

### 4.1 Get Content of service_account.json

On your computer:
1. Open `service_account.json` with text editor
2. Copy ALL content (entire JSON)

### 4.2 Add to Railway

1. In Railway dashboard, go to your project
2. Click "Variables" tab
3. Click "New Variable"
4. Name: `SERVICE_ACCOUNT_JSON`
5. Value: Paste the entire JSON content
6. Save

### 4.3 Modify Script

Update `uppcl_google_sheets_tracker.py`:

Replace this line:
```python
def init_google_sheets(self):
    ...
    if not os.path.exists(self.service_account_json):
```

With:
```python
def init_google_sheets(self):
    ...
    # Get from environment variable in production
    import json
    
    if os.getenv('SERVICE_ACCOUNT_JSON'):
        # Create temp file from env var
        service_account_data = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
        with open('/tmp/service_account.json', 'w') as f:
            json.dump(service_account_data, f)
        self.service_account_json = '/tmp/service_account.json'
    elif not os.path.exists(self.service_account_json):
```

---

## Step 5: Deploy!

### 5.1 Railway Automatic Deploy

Once you:
1. ✅ Created GitHub repo
2. ✅ Added `Procfile`
3. ✅ Added `runtime.txt`
4. ✅ Updated `requirements.txt`
5. ✅ Added `SERVICE_ACCOUNT_JSON` variable

Railway automatically deploys! Just wait...

---

## Step 6: Monitor

### View Logs
1. Go to Railway dashboard
2. Click your project
3. Click "Logs"
4. See real-time execution!

Expected logs:
```
[*] Initializing Google Sheets...
[+] Opened existing spreadsheet: UPPCL Consumption Tracker
[*] Navigating to login page...
[+] Login successful!
[*] Extracting current day units...
[+] Data captured:
[*] Saving to Google Sheets...
[+] Row added to Google Sheets!
```

### View Google Sheet
1. Open Google Sheets
2. "UPPCL Consumption Tracker"
3. See rows being added every hour!

---

## 📊 Railway Dashboard

Shows:
- ✅ App status (running, stopped, restarting)
- ✅ Logs in real-time
- ✅ CPU/Memory usage
- ✅ Deployment history

---

## 💰 Pricing

Railway free tier includes:
- **$5/month free credit**
- **1 project with multiple apps**
- **Enough for always-on Python app**

This tracker uses <$1/month!

---

## 🔄 Deploy Updates

When you make changes:

1. Edit files in GitHub
2. Commit changes
3. Railway auto-detects
4. Automatically redeploys
5. Checks logs to verify

No manual intervention needed!

---

## ⚙️ Restart Service

If something goes wrong:

1. Go to Railway dashboard
2. Click project
3. Click "..." menu
4. Click "Restart"

It will restart in seconds.

---

## 🚨 Troubleshooting

### "Deployment failed"
Check logs:
1. Click "Logs" tab
2. Look for error messages
3. Common: Missing dependency in `requirements.txt`

### "Build taking too long"
Railway needs to install dependencies. Usually takes 3-5 minutes.

### "SERVICE_ACCOUNT_JSON not found"
1. Go to "Variables" tab
2. Verify variable is set
3. Redeploy app

### "Chrome driver failed"
Railway pre-installs Chromium. Usually works out of box.
If error:
1. Add to `requirements.txt`: `google-chrome-stable`
2. Redeploy

---

## 🎯 Next: Advanced Features

### Monitor Remote Logs
```bash
# Install Railway CLI
npm install -g @railway/cli

# View logs
railway logs

# Restart
railway restart
```

### Scale Resources
1. Go to Railway dashboard
2. Click project
3. Increase CPU/Memory if needed
4. Runs within free tier!

### Set Alerts
1. Click project
2. Settings → Notifications
3. Email alerts if app crashes

---

## 📱 Access From Anywhere

Your app runs on Railway servers:
- ✅ View Google Sheet from phone
- ✅ Check Railway logs from phone
- ✅ No computer needs to be on
- ✅ Works 24/7

---

## 🎉 You Now Have

- ✅ GitHub repository with your code
- ✅ Railway running your app 24/7
- ✅ Google Sheets logging data hourly
- ✅ Free forever (within free tier)
- ✅ Automatic monitoring and logging

---

## Comparison: Colab vs Railway

| Feature | Colab | Railway |
|---------|-------|---------|
| **24/7 Running** | ❌ (12hr max) | ✅ |
| **No Browser Needed** | ❌ | ✅ |
| **Free** | ✅ | ✅ |
| **Setup Time** | 10 min | 15 min |
| **Reliability** | Good | Better |
| **Best For** | Testing | Production |

---

## 🚀 Next Steps

1. ✅ Create GitHub repository
2. ✅ Upload project files
3. ✅ Create Railway account
4. ✅ Add environment variables
5. ✅ Wait for auto-deploy
6. ✅ Check Google Sheet for new data!

---

## 💡 Pro Tips

### Commit Changes Often
```bash
git add .
git commit -m "Update tracking interval"
git push origin main
```
Railway auto-deploys on push!

### Keep Secrets Safe
Never commit `service_account.json` to GitHub!
Always use environment variables (like we did).

### Monitor Costs
1. Go to Railway dashboard
2. Click "Usage"
3. See remaining free credit
4. Usually $0-1/month for this app

---

## ✅ Checklist

- [ ] GitHub account created
- [ ] Repository created and files uploaded
- [ ] `Procfile` created with worker command
- [ ] `runtime.txt` created with Python version
- [ ] Railway account created and connected
- [ ] SERVICE_ACCOUNT_JSON environment variable added
- [ ] App deployed and running
- [ ] Logs showing successful captures
- [ ] Google Sheet receiving new rows

---

## 🎊 Congratulations!

Your UPPCL tracker is now:
- ✅ Running 24/7 on Railway
- ✅ Logging to Google Sheets
- ✅ Completely free
- ✅ No laptop needed
- ✅ Accessible from anywhere

**That's production-grade deployment!** 🚀✨

---

**Need help?** Check Railway docs: https://docs.railway.app/
