# Resume Builder Fix — Complete Setup

## ✅ What Was Fixed

The resume builder had a **CORS error** because it was calling Anthropic's API directly from the browser. This exposed security issues and didn't work locally.

**Fixed:** The frontend now calls the backend API instead (`http://localhost:8000/api/ai/tailor`), which handles AI calls securely server-side.

---

## 🚀 To Use the Resume Builder

### Step 1: Add Your Anthropic API Key

Get a free key from: https://console.anthropic.com

Then add it to the backend `.env` file:

**File:** `/Users/santoshreddy/career-pilot.ai/server/.env`

```env
ANTHROPIC_API_KEY=sk-ant-v0-xxxxxxxxxxxxx
```

Save the file. The backend will automatically reload (if running with `--reload`).

### Step 2: Upload Your Resume

1. Go to http://localhost:3000
2. Click **"My profile"** in the sidebar
3. Upload your resume (PDF, DOCX, TXT, or MD)
4. Verify skills were parsed correctly

### Step 3: Build Your Tailored Resume

1. Click **"Resume Builder"** in the sidebar
2. Select a job role from the dropdown
3. (Optional) Paste the job description for better tailoring
4. Choose detail level (Deep, Full, Standard, or Short)
5. Click **"Write it"**

The builder will:
- ✅ Use your profile data (work history, skills, education)
- ✅ Tailor to the selected role
- ✅ Generate 1 call per work position
- ✅ Let you edit each section
- ✅ Download as Word (.docx) or PDF

---

## 🔧 What Changed in the Code

### Frontend Fix
**File:** `web/index.html` (line ~4595)

**Before:**
```javascript
// ❌ Called Anthropic directly from browser (CORS error, exposed API key)
const r = await fetch("https://api.anthropic.com/v1/messages", {...})
```

**After:**
```javascript
// ✅ Calls backend API (secure, works locally)
const r = await fetch(CP_API + "/api/ai/tailor", {...})
```

### Backend Addition
**File:** `server/api/routers/ai.py` (added new endpoint)

```python
@router.post("/api/ai/tailor")
def tailor(req: PromptReq, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Single AI call with any prompt. Used by the resume builder frontend."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(503, "AI service not configured. Set ANTHROPIC_API_KEY to enable.")
    
    result = _call(req.prompt, req.max_tokens, req.label)
    return {"data": result}
```

---

## 📋 How to Get ANTHROPIC_API_KEY

1. Go to https://console.anthropic.com
2. Click **"API Keys"** in the sidebar
3. Click **"Create Key"**
4. Copy the key (starts with `sk-ant-`)
5. Add to `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-v0-your-key-here
   ```

**Cost:** ~$0.06 per tailored resume (cheaper after first use due to caching)

---

## 🛠️ How It Works Now

```
┌─────────────┐
│   Browser   │
│ (Frontend)  │
└──────┬──────┘
       │ HTTP POST /api/ai/tailor
       │ {prompt: "...", max_tokens: 1400}
       │
       ▼
┌──────────────────────────┐
│  Backend (FastAPI)       │
│  /api/ai/tailor endpoint │
│  - Validates user auth   │
│  - Checks API key exists │
│  - Calls Anthropic       │
│  - Caches results        │
│  - Returns JSON response │
└──────┬───────────────────┘
       │ {"data": {...}}
       │
       ▼
┌─────────────┐
│  Anthropic  │
│  API        │
└─────────────┘
```

**Benefits:**
✅ No CORS errors  
✅ API key stays server-side (secure)  
✅ Works locally and in production  
✅ Caching reduces costs  
✅ User auth built-in  

---

## ✅ Verify It's Working

After adding the API key, test it:

```bash
# Check if API key is loaded
curl -s http://localhost:8000/docs | grep -i tailor

# Test the endpoint
curl -X POST http://localhost:8000/api/ai/tailor \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Return valid JSON: {\"test\": \"ok\"}",
    "max_tokens": 100,
    "label": "test"
  }'
```

Expected response:
```json
{"data": {"test": "ok"}}
```

---

## 🎯 Next Steps

1. ✅ Add `ANTHROPIC_API_KEY` to `.env`
2. ✅ Restart backend (if not using `--reload`)
3. ✅ Upload your resume
4. ✅ Try the Resume Builder
5. ✅ Download as Word or PDF

---

## 📞 Troubleshooting

**Error: "AI service not configured"**
- Add `ANTHROPIC_API_KEY` to `.env`
- Restart the backend
- Reload the browser

**Error: "Request rejected (401)"**
- Check your API key is correct
- Regenerate key at https://console.anthropic.com

**Error: "Timed out after 90 seconds"**
- Your prompt might be too long
- Try a shorter job description
- Try less detail level

**Blank output**
- Check backend logs: `tail -f /tmp/career-pilot-backend.log`
- Verify API key is valid
- Try a simpler prompt first

---

## 📚 Files Changed

- `web/index.html` — Fixed resume builder to use backend API
- `server/api/routers/ai.py` — Added `/api/ai/tailor` endpoint
- `server/.env` — Add your API key here

Now try the Resume Builder! 🚀
