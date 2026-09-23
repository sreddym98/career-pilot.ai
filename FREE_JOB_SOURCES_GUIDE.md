# FREE JOB SOURCES SETUP

## ✅ What You Get (NO PAYMENT)

- **USAJOBS**: 40-80+ federal IT/QA roles (totally free)
- **ADZUNA Free Tier**: 40-80+ mixed roles, 1000 calls/month (free)
- **Public APIs**: Remotive, RemoteOK, Arbeitnow, TheMuse (already running, free)

**Total new roles: +150-200+ from free sources alone**

---

## 📋 SETUP IN 5 MINUTES

### 1️⃣ USAJOBS (Free — 2 minutes)

**Get your API key:**
1. Open: https://developer.usajobs.gov
2. Click **"Sign Up"** 
3. Enter your email (e.g., santosh@example.com)
4. Check your email → you'll get an **Authorization-Key** (the API key)

**Then run:**
```bash
export USAJOBS_EMAIL="your_email@example.com"
export USAJOBS_KEY="your_authorization_key_from_email"
```

### 2️⃣ ADZUNA Free Tier (Free — 2 minutes)

**Get your credentials:**
1. Open: https://www.adzuna.com/api/v1/applications
2. Click **"Add Application"**
3. Enter any name (e.g., "career-pilot")
4. You'll immediately see:
   - **app_id** (copy this)
   - **app_key** (copy this)

**Then run:**
```bash
export ADZUNA_APP_ID="your_app_id"
export ADZUNA_APP_KEY="your_app_key"
```

---

## 🔧 QUICKSTART

### Option A: Temporary (Current session only)

```bash
# Set all at once
export USAJOBS_EMAIL="your_email@example.com"
export USAJOBS_KEY="your_key_here"
export ADZUNA_APP_ID="your_app_id_here"
export ADZUNA_APP_KEY="your_app_key_here"

# Run ingestion
cd /Users/santoshreddy/career-pilot.ai
python server/ingest/run.py --once
```

### Option B: Permanent (Add to shell config)

```bash
# Edit your shell config
nano ~/.zshrc
# OR
nano ~/.bash_profile
```

**Add these lines at the end:**
```bash
# Career Pilot — Free Job Sources
export USAJOBS_EMAIL="your_email@example.com"
export USAJOBS_KEY="your_key_here"
export ADZUNA_APP_ID="your_app_id_here"
export ADZUNA_APP_KEY="your_app_key_here"
```

**Save (Ctrl+O, Enter, Ctrl+X)**

**Reload:**
```bash
source ~/.zshrc
```

---

## 🚀 RUN THE INGESTION

```bash
cd /Users/santoshreddy/career-pilot.ai
python server/ingest/run.py --once
```

**Expected results:**
- +40-80 federal jobs (USAJOBS)
- +40-80 mixed roles (ADZUNA)
- Your 4,880 jobs will expand to **~5,100+ total**
- Plus 1,315 contract roles already detected ✨

---

## 💰 Why These Are Free

| Source | Why Free | Limit | Roles Added |
|--------|----------|-------|-------------|
| USAJOBS | Government API | Unlimited | 40-80 |
| ADZUNA Free | Free tier | 1000/month | 40-80 |
| Remotive | Public feed | Unlimited | ~7 |
| RemoteOK | Public feed | Unlimited | ~2 |
| Arbeitnow | Public API | Unlimited | ~2 |
| TheMuse | Public API | 15 roles | ~268 |

**Current already running for free:** +275 jobs from public sources

---

## ⚠️ PAID OPTION (Optional — Not Required)

If you want **120-200+ MORE contract roles** from Dice/staffing agencies:
- RapidAPI JSearch: ~$30/month
- Get key from: https://rapidapi.com → Search "JSearch" → Subscribe

But you DON'T need this — the FREE sources give you solid coverage!

---

## 📞 NEED HELP?

1. Can't find the USAJOBS key? → Check your spam folder
2. ADZUNA credentials not showing? → Try a different browser or clear cookies
3. Ingestion failing? → Check environment variables with `echo $USAJOBS_KEY`

**You're ready! Get those free jobs running!** 🚀
