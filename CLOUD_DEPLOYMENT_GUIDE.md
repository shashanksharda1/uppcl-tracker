# ☁️ UPPCL Tracker - Cloud Deployment Guide

## Overview

Your tracker can run **without your laptop** using cloud platforms. Data logs to **Google Sheets** accessible from anywhere.

---

## 📊 Comparison of Free Cloud Platforms

| Platform | Free | Setup | 24/7 | Browser | Best For |
|----------|------|-------|------|---------|----------|
| **Google Colab** | ✅ Yes | 10 min | ❌ 12h max | ✅ Needed | Testing/Learning |
| **Railway** | ✅ $5/mo | 15 min | ✅ Yes | ❌ No | Production |
| **Render** | ✅ Yes | 15 min | ✅ Yes | ❌ No | Production |
| **PythonAnywhere** | ✅ Yes | 20 min | ✅ Yes | ❌ No | Learning |
| **Heroku** | ❌ Paid | - | - | - | Not recommended |

---

## 🎯 Recommendation by Use Case

### **Just Testing / Learning**
→ Use **Google Colab**
- Keep Colab tab open
- Watch it run in real-time
- See logs as they happen
- Free forever
- 12-hour sessions usually enough for testing

### **Production / Running 24/7**
→ Use **Railway** (Recommended)
- Free $5/month tier
- True 24/7 operation
- Professional setup
- Easy deployment
- Can restart anytime

### **Budget Conscious**
→ Use **Render**
- Completely free tier
- 24/7 operation
- Good uptime
- Just slower cold starts

### **Learning Python/Deployment**
→ Use **PythonAnywhere**
- Educational focus
- Good documentation
- Ideal for beginners
- Small free tier

---

## 🚀 Quick Start (Choose One)

### Option 1: Google Colab (Easiest, 12 hours)

**Setup Time**: 10 minutes  
**Cost**: Free  
**Duration**: 12 hours max per session  

Steps:
1. Create Google Colab notebook
2. Upload `uppcl_google_sheets_tracker.py` to Drive
3. Copy-paste code to run
4. Keep browser tab open

See: `COLAB_DEPLOYMENT.md`

```bash
# In Colab cell:
python uppcl_google_sheets_tracker.py --once
```

**Good for**: Testing, learning, demos

---

### Option 2: Railway (Recommended, 24/7)

**Setup Time**: 15 minutes  
**Cost**: Free (within $5/month tier)  
**Duration**: 24/7 forever  

Steps:
1. Create GitHub repository
2. Push your code
3. Connect Railway
4. Add environment variable
5. Auto-deploys!

See: `RAILWAY_DEPLOYMENT.md`

```bash
# GitHub:
git push origin main
# Railway auto-deploys!
```

**Good for**: Production, real monitoring, reliability

---

### Option 3: Render (Free, 24/7)

**Setup Time**: 15 minutes  
**Cost**: Completely free  
**Duration**: 24/7 forever  

Steps:
1. Create GitHub repository
2. Connect Render to GitHub
3. Create new service
4. Select "Python"
5. Deploy!

See: `RENDER_DEPLOYMENT.md`

```bash
# Render auto-deploys on GitHub push
```

**Good for**: Budget-conscious, reliable 24/7

---

### Option 4: PythonAnywhere (Learning, 24/7)

**Setup Time**: 20 minutes  
**Cost**: Free tier (limited)  
**Duration**: 24/7 forever  

Steps:
1. Create PythonAnywhere account
2. Upload files via web interface
3. Set up scheduled task
4. Run!

See: `PYTHONANYWHERE_DEPLOYMENT.md`

```bash
# In PythonAnywhere scheduler:
python uppcl_google_sheets_tracker.py --once
# Run hourly
```

**Good for**: Learning, hobby projects

---

## 📋 Prerequisites (All Options)

✅ **Google Sheets Setup** (see `GOOGLE_SHEETS_SETUP.md`)
- Google Cloud Project created
- Google Sheets API enabled
- Service account created
- `service_account.json` downloaded
- Google Sheet created and shared

✅ **Project Files**
- `uppcl_google_sheets_tracker.py`
- `requirements.txt`
- `Procfile` (for Railway/Render)
- `runtime.txt` (for Railway/Render)

---

## 🔑 Key Difference: Local vs Cloud

### **Local (Laptop)**
```
Your Laptop
    ↓ (runs continuously)
    → Logs in to UPPCL
    → Captures data
    → Saves to Excel
```
**Problem**: Laptop must be on 24/7

### **Cloud (No Laptop)**
```
Your Laptop → GitHub (push code)
                ↓
            Railway/Render
                ↓ (runs 24/7 in cloud)
                → Logs in to UPPCL
                → Captures data
                → Saves to Google Sheets
                ↓
            Google Sheets (access from anywhere)
```
**Solution**: No laptop needed!

---

## 📊 Data Flow Diagram

```
Every Hour:
    [Cloud Server Running Python Script]
           ↓
    [Login to UPPCL]
           ↓
    [Extract 3 Metrics]
           ↓
    [Save to Google Sheets]
           ↓
    [You can view from phone/tablet/laptop]
```

---

## 🎯 Deployment Decision Tree

```
Do you want to test first?
    ├─ YES → Use Google Colab
    │        (10 min setup, test for 12 hours)
    │
    └─ NO → Want 24/7 running?
             ├─ YES, want best quality → Railway (Recommended)
             ├─ YES, want completely free → Render
             ├─ YES, want to learn deployment → PythonAnywhere
             │
             └─ NO → Keep using local laptop
```

---

## 🚀 Step-by-Step (Railway Recommended)

### 1. Google Sheets Setup (10 min)
```
See: GOOGLE_SHEETS_SETUP.md

✅ Create Google Cloud Project
✅ Enable Google Sheets API
✅ Create service account
✅ Download service_account.json
✅ Create Google Sheet
✅ Share with service account email
✅ Test with: python uppcl_google_sheets_tracker.py --once
```

### 2. GitHub Setup (5 min)
```
✅ Create GitHub account
✅ Create new repository: uppcl-tracker
✅ Upload files:
   - uppcl_google_sheets_tracker.py
   - requirements.txt
   - Procfile
   - runtime.txt
```

### 3. Railway Setup (5 min)
```
✅ Create Railway account (connect GitHub)
✅ Select your repository
✅ Click "Deploy"
✅ Add SERVICE_ACCOUNT_JSON variable
✅ Wait for auto-deployment
✅ Check logs
✅ Verify Google Sheet getting new rows
```

### Done! ✅
Your tracker now runs 24/7 in cloud!

---

## 💰 Cost Comparison

| Platform | Monthly Cost | Limits |
|----------|-------------|--------|
| Google Colab | $0 | 12 hour sessions |
| Railway | $0-1 | $5/mo free tier |
| Render | $0 | Slower free tier |
| PythonAnywhere | $0-5 | Limited free tier |
| Google Sheets | $0 | Unlimited rows |

**Total monthly**: $0-1 (basically free!)

---

## 📱 Access From Anywhere

Once deployed:

### Check Data
1. Open Google Sheets
2. "UPPCL Consumption Tracker"
3. See rows added hourly
4. Works on phone too!

### Monitor Status
- **Railway**: Dashboard shows logs
- **Render**: Dashboard shows logs
- **Colab**: Notebook shows output
- **PythonAnywhere**: Task history

### Manage App
- **Change interval**: Update code, push to GitHub, auto-redeploys
- **Restart**: One click on platform dashboard
- **Stop**: Stop app anytime
- **Logs**: View in real-time

---

## 🔧 Common Maintenance

### Check if Running
1. Go to platform dashboard
2. See green "running" status
3. OR check Google Sheet - new rows appearing?

### Check Logs
```
# Railway: dashboard → Logs tab
# Render: dashboard → Logs
# Colab: Scroll in notebook
# PythonAnywhere: Task history
```

### Restart if Stuck
1. Platform dashboard
2. Click "Restart" button
3. App restarts in seconds
4. No data loss (it's in Google Sheets)

### Update Code
1. Edit in GitHub
2. Commit and push
3. Platform auto-redeploys
4. Done!

---

## ⚠️ Security Notes

### Keep `service_account.json` Safe
- ✅ Store in environment variables (not GitHub)
- ✅ Never commit to repository
- ✅ Never share publicly
- ✅ Treat like password

### Rotate Keys Periodically
1. Create new service account key
2. Update environment variable
3. Delete old key
4. Done

### Monitor Usage
1. Check platform dashboard
2. Verify app is using expected resources
3. Set billing alerts (if applicable)

---

## 🆘 Troubleshooting

### "App keeps crashing"
1. Check logs on platform
2. Look for error messages
3. Common: Missing dependency
4. Fix: Update `requirements.txt`, redeploy

### "No new rows in Google Sheet"
1. Check platform logs
2. Verify `SERVICE_ACCOUNT_JSON` is set
3. Verify Google Sheet is shared
4. Check internet connectivity

### "Chrome driver error"
1. Platform should pre-install Chromium
2. If error: Add to `requirements.txt`: `chromium`
3. Redeploy

### "Random restarts"
1. Check for memory issues in logs
2. Can increase resources (if paid tier)
3. Or switch to a more performant platform

---

## 📚 Full Documentation

For detailed setup of each platform:

1. **Google Sheets Integration**  
   → See: `GOOGLE_SHEETS_SETUP.md`

2. **Google Colab Deployment**  
   → See: `COLAB_DEPLOYMENT.md`

3. **Railway Deployment**  
   → See: `RAILWAY_DEPLOYMENT.md`

4. **Render Deployment**  
   → See: `RENDER_DEPLOYMENT.md`

5. **PythonAnywhere Deployment**  
   → See: `PYTHONANYWHERE_DEPLOYMENT.md`

---

## 🎯 My Recommendation

**For most users**: **Railway**
- ✅ 24/7 operation guaranteed
- ✅ Easy deploy from GitHub
- ✅ Reliable logging
- ✅ Within free tier
- ✅ Production-ready

**For testing first**: **Google Colab**
- ✅ Instant testing
- ✅ No deployment needed
- ✅ Great for learning
- ✅ Then graduate to Railway

**For zero cost**: **Render**
- ✅ Completely free tier
- ✅ 24/7 operation
- ✅ Slower but works
- ✅ Good backup option

---

## ✅ Deployment Checklist

- [ ] Google Sheets setup complete
- [ ] `service_account.json` ready
- [ ] Python files prepared
- [ ] `requirements.txt` updated
- [ ] GitHub repository created
- [ ] Cloud platform account created
- [ ] Code deployed
- [ ] One-time test successful
- [ ] Google Sheet receiving data
- [ ] Logs being generated
- [ ] 24/7 operation confirmed

---

## 🎉 You Now Have

✅ Cloud-based electricity tracker  
✅ No laptop needed for 24/7 operation  
✅ Data in Google Sheets (accessible anywhere)  
✅ Professional deployment  
✅ Automatic hourly captures  
✅ Real-time monitoring  
✅ Free or nearly-free  

**That's enterprise-grade infrastructure!** 🚀

---

## 🚀 Next Action

1. **Choose a platform**: Colab (test) or Railway (production)
2. **Follow the guide** for that platform
3. **Deploy** in 15 minutes
4. **Monitor** your data in Google Sheets
5. **Done!** No more running laptop needed

---

**Questions?**  
- Google Sheets → See `GOOGLE_SHEETS_SETUP.md`
- Colab → See `COLAB_DEPLOYMENT.md`
- Railway → See `RAILWAY_DEPLOYMENT.md`
- Render → See `RENDER_DEPLOYMENT.md`
- PythonAnywhere → See `PYTHONANYWHERE_DEPLOYMENT.md`

**Your 24/7 cloud tracker awaits!** ☁️✨
