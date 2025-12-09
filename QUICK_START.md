# 🚀 Quick Start Guide

## Local Development (with test data)

```bash
./start_local.sh
```

That's it! Opens at **http://localhost:8000**

Includes test users:
- Alice (Developer)
- Bob (Developer)  
- Dana Cohen (Team Lead)
- Sarah Feldman (Team Lead)
- Amir Levy (Engineering Manager)
- Roi Weiss (Product Manager)

---

## Production Deployment (Railway)

### First Time Setup:

1. **Create Railway project** from GitHub repo
2. **Add PostgreSQL database** (sets `DATABASE_URL` automatically)
3. **Add environment variable:**
   - `OPENAI_API_KEY` = `your_key_here`
4. **DO NOT set** `POPULATE_SAMPLE_DATA` ✅

### Update Deployment:

```bash
git push origin main
```

Railway auto-deploys. User data is preserved.

---

## Key Difference

| Environment | Test Data | User Data |
|-------------|-----------|-----------|
| **Local** | ✅ Auto-populated | For testing |
| **Railway** | ❌ Empty database | Real users create |

---

## Environment Variables

### Railway (Production):
```bash
DATABASE_URL         # ✅ Auto-set by Railway
OPENAI_API_KEY       # ✅ Set manually
PORT                 # ✅ Auto-set by Railway
POPULATE_SAMPLE_DATA # ❌ DO NOT SET
```

### Local (.env):
```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/orgos
OPENAI_API_KEY=sk-...your-key...
POPULATE_SAMPLE_DATA=true
```

---

## Commands

```bash
# Local development
./start_local.sh              # Start with test data

# Database management
docker-compose up -d          # Start PostgreSQL
docker-compose down           # Stop PostgreSQL
python3 init_db.py           # Initialize DB
python3 app/seed.py          # Seed attributes
python3 populate_full_data.py # Populate test data (local only)

# Run manually
uvicorn app.main:app --reload --port 8000
```

---

## Access

- **Local:** http://localhost:8000
- **Railway:** Your Railway-provided URL (e.g., `https://orgos-production-xxxx.up.railway.app`)

---

## Need Help?

See full docs:
- `RAILWAY_DEPLOYMENT.md` - Detailed deployment guide
- `README.md` - Full project documentation

