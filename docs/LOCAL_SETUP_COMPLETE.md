# Career Pilot AI — Complete Setup Guide (Frontend + Backend Integrated)

**Status: ✅ Frontend and Backend are now integrated and ready to use locally**

This guide walks you through the complete setup that has been performed to get the frontend and backend working together.

---

## What Has Been Done

### 1. **Backend Setup** ✅
- Installed all Python dependencies from `requirements.txt`
- Created `.env` file with development configuration
- Initialized SQLite database with seed data (8 sample jobs, dev user, etc.)
- Started the FastAPI server on `http://localhost:8000`

### 2. **Frontend Configuration** ✅
- Updated `web/index.html` to point to the local backend API endpoint
- Frontend now connects to `http://localhost:8000` instead of running in demo mode

### 3. **Database Setup** ✅
- Created 11 tables in SQLite database
- Loaded sample data:
  - 1 dev user: `Santosh Reddy <dev@careerpilot.local>`
  - 3 positions with work history
  - 8 sample jobs with visa parsing
  - 6 courses
  - 5 connections
  - 4 referral records

---

## How to Use It

### Quick Start (Already Running)

1. **Open the Frontend**
   ```
   Open: /Users/santoshreddy/career-pilot.ai/web/index.html in your browser
   ```
   - The frontend is a single HTML file — no build process needed
   - It will automatically connect to the backend at `http://localhost:8000`

2. **Backend is Running**
   ```
   The API server is running at: http://localhost:8000
   API Docs available at: http://localhost:8000/docs (Swagger UI)
   ```

3. **Try It Out**
   - Click on job listings — they come from the database
   - Try the recruiter mode toggle in the sidebar
   - Upload a resume, try the evaluation feature
   - Try creating applications (they'll be saved to the database)

---

## Backend Server Details

### How to (Re)Start the Backend

If the server stops or you need to restart it:

```bash
cd /Users/santoshreddy/career-pilot.ai/server

# Install dependencies (if not done yet)
pip install -r requirements.txt

# Start the server
PYTHONPATH=/Users/santoshreddy/career-pilot.ai/server python -m uvicorn api.main:app --reload --port 8000
```

The server will:
- Watch for code changes and reload automatically (--reload flag)
- Run on `http://localhost:8000`
- Use SQLite database at `./server/dev.db`
- Require no external services (no Postgres/Redis needed for local dev)

### Environment Variables (`.env` file)

Located at: `/Users/santoshreddy/career-pilot.ai/server/.env`

**Current Configuration (Dev Mode):**
```env
DATABASE_URL=sqlite:///./dev.db
ENV=dev
FRONTEND_URL=http://localhost:3000
# All other services (Stripe, AI, etc.) are in demo mode
```

**To Enable Features:**
- Add `ANTHROPIC_API_KEY=sk-...` to enable AI features (tailoring, cover letters, evaluation)
- Add Stripe keys to enable payment processing
- Add Supabase URL/secret to enable real authentication

### API Endpoints

The backend provides 16 endpoints across these categories:

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `/api/jobs` | Get job listings with filters | ✅ Working |
| `/api/profile` | Get/update user profile | ✅ Working |
| `/api/applications` | Manage job applications | ✅ Working |
| `/api/tailor` | AI resume tailoring | ✅ Working (demo mode without key) |
| `/api/cover-letter` | AI cover letter generation | ✅ Working (demo mode) |
| `/api/evaluate` | $5 profile evaluation | ✅ Working (demo mode) |
| `/api/billing/checkout` | Stripe checkout session | ✅ Working |
| `/health` | Server health check | ✅ Working |

**Try the API directly:**
```bash
# View all jobs
curl http://localhost:8000/api/jobs

# View API documentation
# Open http://localhost:8000/docs in browser (Swagger UI)
```

---

## Database

### Location
```
/Users/santoshreddy/career-pilot.ai/server/dev.db
```

### Schema (11 Tables)
- `users` — job seekers and recruiters
- `positions` — work experience
- `user_skills` — top skills per user
- `jobs` — job board listings
- `applications` — applications user has made
- `ai_cache` — cached AI responses (protects margins)
- `courses` — professional development
- `connections` — user's network
- `referrals` — referral tracking
- `support_tickets` — support queue
- `feedback` — user feedback (for iteration)

### Reset/Reseed Database

To start with fresh sample data:

```bash
cd /Users/santoshreddy/career-pilot.ai/server

# Option 1: Delete and recreate
rm dev.db
python seed.py

# Option 2: Just reseed (clears old data, loads new)
python seed.py
```

---

## Frontend

### Location
```
/Users/santoshreddy/career-pilot.ai/web/index.html
```

### How It Works
- **Single HTML file** — no build tools needed
- **Static HTML/CSS/JS** — loads in any browser
- **Connects to backend** via the `API_ENDPOINT` constant
- **Local storage** for UI state and cache

### API Endpoint Configuration

The frontend's API endpoint is set in the `<script>` section:

**File:** `/Users/santoshreddy/career-pilot.ai/web/index.html`, line 2308

```javascript
const API_ENDPOINT = "http://localhost:8000";
```

**To change it:**
1. Open `web/index.html` in a text editor
2. Find line 2308: `const API_ENDPOINT = "";`
3. Replace with your backend URL: `const API_ENDPOINT = "http://your-backend-url:8000";`
4. Save and reload the browser

### Features Included

**Job Seeker Features:**
- Search & filter jobs (by title, location, visa status, salary)
- AI-powered resume tailoring
- AI cover letter generation
- Track applications
- Mock interview practice
- Profile evaluation ($5 one-time)
- Autopilot mode (prepare applications, you approve before sending)

**Recruiter Features:**
- Candidate bench management
- Fit-matched job ranking
- Submission tracking

---

## Troubleshooting

### Backend won't start

**Error: `ModuleNotFoundError: No module named 'api'`**
```bash
# Make sure PYTHONPATH is set correctly when running uvicorn:
cd /Users/santoshreddy/career-pilot.ai/server
PYTHONPATH=/Users/santoshreddy/career-pilot.ai/server python -m uvicorn api.main:app --reload --port 8000
```

**Error: `Address already in use`**
```bash
# Another process is using port 8000. Kill it:
lsof -i :8000
# Then kill the process ID shown

# Or use a different port:
PYTHONPATH=/Users/santoshreddy/career-pilot.ai/server python -m uvicorn api.main:app --reload --port 8001
```

### Frontend not connecting to backend

**Check:** Open browser console (F12 → Console tab)
- Look for error messages about API calls failing
- Verify `http://localhost:8000` is accessible
- Try directly: `curl http://localhost:8000/health`

**Solution:**
1. Verify backend is running: `http://localhost:8000/docs` should show Swagger UI
2. Verify frontend has correct endpoint: `web/index.html` line 2308
3. Check CORS is enabled (it's set to allow `*` in dev mode)

### Database issues

**Error: `No such table`**
```bash
# Reseed the database:
cd /Users/santoshreddy/career-pilot.ai/server
rm dev.db
python seed.py
```

**To inspect the database:**
```bash
# Install sqlite3 (usually comes with Python)
sqlite3 /Users/santoshreddy/career-pilot.ai/server/dev.db

# Inside sqlite3:
.tables                          # List all tables
.schema jobs                     # Show jobs table structure
SELECT COUNT(*) FROM jobs;       # Count jobs
.quit                            # Exit
```

---

## Next Steps (Optional Enhancements)

### 1. **Enable AI Features** (15 min)
Get an Anthropic API key and add it to `.env`:
```env
ANTHROPIC_API_KEY=sk-ant-xxxxx
```
This enables:
- Resume tailoring
- Cover letter generation
- Profile evaluation
- Mock interview questions

See: `docs/KEYS.md` for details

### 2. **Enable Stripe Payments** (30 min)
Create a Stripe account and run:
```bash
cd /Users/santoshreddy/career-pilot.ai/server
python setup_stripe.py
```
This auto-creates all price tiers. See: `docs/KEYS.md`

### 3. **Add More Job Data** (hours)
Grow the `ingest/companies.yaml` file with more ATS endpoints:
- Aim for 300+ companies
- Add Greenhouse, Lever, Ashby slugs
- The job ingestion pipeline will fetch from all of them

### 4. **Deploy to Production** (see `docs/GO_LIVE.md`)
- Frontend: Cloudflare Pages
- Backend: Railway, Render, or Fly.io
- Database: Supabase (Postgres)

---

## File Structure

```
career-pilot.ai/
├── web/
│   └── index.html                    # ← Frontend (open in browser)
├── server/                           # ← Backend (Python/FastAPI)
│   ├── api/
│   │   ├── main.py                   # FastAPI app
│   │   ├── settings.py               # Configuration
│   │   ├── models.py                 # Database schema
│   │   ├── auth.py                   # Authentication
│   │   └── routers/
│   │       ├── jobs.py               # Job listings
│   │       ├── profile.py            # User profile
│   │       ├── ai.py                 # AI features
│   │       ├── billing.py            # Stripe integration
│   │       └── ... (support, evaluation, interview, referrals)
│   ├── ingest/
│   │   ├── ingest.py                 # Job ingestion pipeline
│   │   ├── companies.yaml            # ATS slug list
│   │   └── ... (parsers, classifiers)
│   ├── .env                          # ← Environment variables
│   ├── dev.db                        # ← SQLite database (created by seed.py)
│   ├── seed.py                       # Initialize database
│   ├── requirements.txt              # Python dependencies
│   ├── Makefile                      # Build commands
│   └── docker-compose.yml            # (Optional) Docker setup
├── docs/
│   ├── SETUP.md                      # Full setup guide
│   ├── KEYS.md                       # API key configuration
│   ├── GO_LIVE.md                    # Deployment guide
│   └── ... (other docs)
└── extension/                        # Chrome extension (separate)
```

---

## Summary

✅ **Backend is running** at `http://localhost:8000`  
✅ **Frontend is configured** to connect to backend  
✅ **Database is seeded** with sample data  
✅ **Both are ready to use**  

**To start using it:** Open `/Users/santoshreddy/career-pilot.ai/web/index.html` in your browser. The frontend will connect to the backend automatically and pull real data from the database instead of showing demo data.

---

## Support

For detailed information, see the original docs:
- `START_HERE.md` — Quick overview
- `docs/SETUP.md` — Complete setup instructions
- `docs/KEYS.md` — API key management
- `docs/GO_LIVE.md` — Deployment guide
- `SECURITY.md` — Security checklist
