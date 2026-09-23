# Job Sources Expansion Guide

Your system is already pulling **4,880 jobs** from 154 ATS boards. To add comprehensive coverage of **contract roles** and **federal jobs**, configure these optional API keys.

## Current Coverage
✅ **4,880 active jobs** across 17 role families:
- 1,853 full-time roles
- 27 contract roles (target: 200)
- 3,344 type unclear
- All roles: backend, product, design, data, DevOps, managers, and more

---

## API Keys to Add

### 1. USAJOBS (Free, 2 min setup)
**What:** Federal government IT and QA jobs  
**Volume:** +40-80 jobs  
**Cost:** Free  
**Setup:**
1. Go to [developer.usajobs.gov](https://developer.usajobs.gov)
2. Sign up with your email
3. Receive `USAJOBS_KEY` in your inbox
4. Also provide your email (or it will use the one in env)

**Environment Variables:**
```bash
export USAJOBS_KEY="your_key_here"
export USAJOBS_EMAIL="your_email@example.com"
```

---

### 2. RapidAPI / JSearch (Paid, best for contracts)
**What:** Reads Google for Jobs, indexes Dice, Indeed, staffing boards  
**Volume:** +120-200 contract roles (this is THE source for contract/C2C work)  
**Cost:** ~$30/month  
**Setup:**
1. Go to [rapidapi.com](https://rapidapi.com)
2. Sign up (free account)
3. Subscribe to "JSearch" API (free tier available, ~$30/mo for production)
4. Copy your RapidAPI Key from your profile

**Environment Variables:**
```bash
export RAPIDAPI_KEY="your_rapidapi_key_here"
```

---

### 3. Adzuna (Free tier, 1000 calls/month)
**What:** Aggregates 1000s of US boards including staffing agencies  
**Volume:** +40-80 mixed roles  
**Cost:** Free (1000 calls/month)  
**Setup:**
1. Go to [adzuna.com/api/v1/applications](https://www.adzuna.com/api/v1/applications)
2. Register your application
3. Receive `app_id` and `app_key`

**Environment Variables:**
```bash
export ADZUNA_APP_ID="your_app_id_here"
export ADZUNA_APP_KEY="your_app_key_here"
```

---

## Quick Setup (macOS)

Add to your `~/.zshrc` or `~/.bash_profile`:

```bash
# Career Pilot Job Sources
export USAJOBS_KEY="..."
export USAJOBS_EMAIL="..."
export RAPIDAPI_KEY="..."
export ADZUNA_APP_ID="..."
export ADZUNA_APP_KEY="..."
```

Then reload:
```bash
source ~/.zshrc
```

---

## Run After Setup

Once you've set the environment variables, re-run ingestion:

```bash
cd /Users/santoshreddy/career-pilot.ai
python server/ingest/run.py --once
```

This will pull from all sources and show you the expanded job board with contract roles.

---

## Expected Results After Setup
- **Total jobs:** 5,500+
- **Contract roles:** 150-200+ (currently only 27)
- **Full-time roles:** 2,000+
- **All role families:** retained and expanded

---

## Why These Sources Matter

| Source | Primary Value | Staffing Agencies |
|--------|---------------|-------------------|
| ATS Boards (Greenhouse, Lever) | Direct employers, clean | No |
| USAJOBS | Federal government IT/QA | No |
| RapidAPI (JSearch) | **Contract roles on Dice** | **Yes** |
| Adzuna | Mixed board aggregation | Yes |

**Key insight:** Contract/staffing roles don't live on Greenhouse. They live on Dice and staffing aggregators. That's why the "contract is short" warning — you need the metered APIs to surface that volume.

---

## Questions?

Each API has excellent documentation:
- [USAJOBS API Docs](https://developer.usajobs.gov/)
- [RapidAPI JSearch](https://rapidapi.com/letscrape-6beBoa7v8hWkA29fP/api/jsearch)
- [Adzuna API Docs](https://www.adzuna.com/api/v1/documentation)
