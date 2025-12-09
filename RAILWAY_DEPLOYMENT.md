# Railway Deployment Guide

## 🚂 Environment Variables for Railway

### **Required Variables:**

1. **`DATABASE_URL`** (automatically set by Railway when you add PostgreSQL)
   - Format: `postgresql://user:password@host:port/database`
   - Set by Railway's PostgreSQL service automatically

2. **`OPENAI_API_KEY`**
   - Your OpenAI API key for Robin AI assistant
   - Get from: https://platform.openai.com/api-keys

3. **`PORT`** (automatically set by Railway)
   - Default: 8080
   - Railway sets this automatically

### **Optional Variables:**

4. **`POPULATE_SAMPLE_DATA`** 
   - **DO NOT SET THIS IN PRODUCTION/RAILWAY** ❌
   - Only set to `true` for local development/testing
   - If not set or set to `false`, no test data is populated
   - Real users will create their own data

---

## 📋 Railway Setup Checklist

### Step 1: Create Railway Project
1. Go to https://railway.app
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Select your OrgOs repository

### Step 2: Add PostgreSQL Database
1. Click "New" → "Database" → "Add PostgreSQL"
2. Railway automatically sets `DATABASE_URL` variable
3. Wait for database to provision

### Step 3: Configure Environment Variables
1. Go to your service → "Variables" tab
2. Add **`OPENAI_API_KEY`** = `your_api_key_here`
3. **DO NOT** add `POPULATE_SAMPLE_DATA` (leave it unset for production)

### Step 4: Deploy
1. Railway will automatically build and deploy
2. First deployment will:
   - Initialize database tables ✅
   - Seed attribute definitions ✅
   - **NOT** populate test data ✅ (because `POPULATE_SAMPLE_DATA` is not set)
3. Access your app at the Railway-provided URL

---

## 🏠 Local Development

### For local testing with sample data:

```bash
# Option 1: Use the local startup script (recommended)
./start_local.sh

# Option 2: Manual setup
export POPULATE_SAMPLE_DATA=true
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/orgos"
docker-compose up -d
python3 init_db.py
python3 app/seed.py
python3 populate_full_data.py
python3 populate_similarity_scores.py
uvicorn app.main:app --reload
```

The local script (`start_local.sh`) automatically:
- ✅ Starts PostgreSQL with Docker
- ✅ Initializes database
- ✅ Seeds attribute definitions
- ✅ Populates test data (Alice, Bob, Dana, etc.)
- ✅ Calculates similarity scores
- ✅ Starts server with hot reload

---

## 🔄 Update Deployment

When you make code changes:

```bash
git add .
git commit -m "Your changes"
git push origin main
```

Railway automatically redeploys. The startup script will:
- ✅ Run database migrations (idempotent, safe to re-run)
- ✅ Seed new attributes if added
- ❌ **Will NOT** reset or populate test data (preserves user data)

---

## 🗑️ Reset Railway Database (if needed)

⚠️ **WARNING: This deletes ALL data!**

1. Go to Railway → PostgreSQL service
2. Click "Data" tab
3. Connect to database
4. Run:
   ```sql
   DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;
   ```
5. Restart your application service (triggers init_db.py)

---

## ✅ Current Configuration

### Production (Railway):
- `DATABASE_URL`: ✅ Set automatically by PostgreSQL service
- `OPENAI_API_KEY`: ✅ Set manually
- `POPULATE_SAMPLE_DATA`: ❌ **NOT SET** (no test data)
- `PORT`: ✅ Set automatically by Railway

### Local Development:
- `DATABASE_URL`: Set in `.env` or `start_local.sh`
- `OPENAI_API_KEY`: Set in `.env`
- `POPULATE_SAMPLE_DATA`: ✅ **Set to `true`** (includes test data)
- `PORT`: 8000 (default for local)

---

## 🐛 Troubleshooting

### Issue: Test data appearing in production
**Fix:** Make sure `POPULATE_SAMPLE_DATA` is NOT set in Railway variables.

### Issue: Database connection errors
**Fix:** Verify `DATABASE_URL` is set correctly. Railway sets this automatically when PostgreSQL is added.

### Issue: OpenAI errors
**Fix:** Verify `OPENAI_API_KEY` is set in Railway variables.

### Issue: Need to check environment variables
**SSH into Railway container:**
```bash
railway run bash
echo $POPULATE_SAMPLE_DATA  # Should be empty
echo $DATABASE_URL          # Should be postgresql://...
echo $OPENAI_API_KEY        # Should be sk-...
```

