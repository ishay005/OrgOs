# 🗑️ How to Clear Data from Railway Database

## ⚠️ **WARNING**
All methods below will **DELETE ALL USER DATA**. Attribute definitions (Priority, Status, Resources, etc.) are preserved.

---

## 🚀 **Method 1: Railway CLI** (Recommended - Fast & Easy)

### One-Time Setup:
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to your project (run in project directory)
cd /Users/ishaylevi/work/OrgOs
railway link
```

### Clear Data:
```bash
railway run python3 clear_all_data.py --confirm
```

✅ **Done!** Data cleared in ~2 seconds.

---

## 🖥️ **Method 2: Railway Web Console - Shell**

1. Go to https://railway.app
2. Click your project
3. Click your **app service** (the one running your FastAPI app)
4. Click **"Shell"** tab (terminal icon)
5. Type:
   ```bash
   python3 clear_all_data.py --confirm
   ```
6. Press Enter

✅ **Done!** Data cleared.

---

## 🗄️ **Method 3: Railway Web Console - SQL**

1. Go to https://railway.app
2. Click your project
3. Click your **PostgreSQL service** (database icon)
4. Click **"Data"** tab
5. Click **"Query"** button
6. Paste this SQL:

```sql
-- Clear all user data (preserves schema)
TRUNCATE TABLE similarity_scores CASCADE;
TRUNCATE TABLE attribute_answers CASCADE;
TRUNCATE TABLE question_logs CASCADE;
TRUNCATE TABLE chat_messages CASCADE;
TRUNCATE TABLE chat_threads CASCADE;
TRUNCATE TABLE tasks CASCADE;
TRUNCATE TABLE alignment_edges CASCADE;
TRUNCATE TABLE users CASCADE;
```

7. Click **"Run Query"**

✅ **Done!** Data cleared.

---

## 🔄 **Method 4: Environment Variable Trigger** (For scheduled resets)

Use this if you want Railway to clear data on next deployment:

### Step 1: Set Variable
1. Go to Railway → Your app service → **Variables**
2. Click **"New Variable"**
3. Set:
   - Variable: `RUN_CLEAR_DATA`
   - Value: `true`

### Step 2: Deploy
```bash
git push origin main
```

Railway will:
1. Deploy your app
2. **Clear all data** (because `RUN_CLEAR_DATA=true`)
3. Start fresh

### Step 3: Remove Variable (Important!)
After deployment completes:
1. Go back to **Variables**
2. **Delete** `RUN_CLEAR_DATA` variable
3. Otherwise it will clear on every deployment!

---

## 🏠 **Clear Local Database**

If you want to clear your local test database:

```bash
cd /Users/ishaylevi/work/OrgOs
source venv/bin/activate
python3 clear_all_data.py --confirm
```

Then repopulate with test data:
```bash
python3 populate_full_data.py
python3 populate_similarity_scores.py
```

Or just restart everything:
```bash
./start_local.sh
```

---

## 📊 **What Gets Deleted**

| Data Type | Deleted? | Reason |
|-----------|----------|--------|
| Users | ✅ Yes | All user accounts |
| Tasks | ✅ Yes | All tasks |
| Answers | ✅ Yes | All perception data |
| Chat History | ✅ Yes | All Robin conversations |
| Similarity Scores | ✅ Yes | All cached calculations |
| **Attribute Definitions** | ❌ **NO** | Schema preserved (Priority, Status, Resources, etc.) |

---

## 🔧 **After Clearing Data**

The database will be **empty but functional**:
- ✅ Users can register
- ✅ Users can create tasks
- ✅ Robin will work
- ✅ All features functional

Just like a fresh deployment!

---

## 🆘 **Troubleshooting**

### "ModuleNotFoundError" when running on Railway
**Fix:** Make sure you're running from your **app service**, not PostgreSQL service.

### "Permission denied"
**Fix:** The script needs `--confirm` flag for safety:
```bash
python3 clear_all_data.py --confirm
```

### Want to test locally first?
```bash
# Test on local database
cd /Users/ishaylevi/work/OrgOs
source venv/bin/activate
python3 clear_all_data.py --confirm

# Then repopulate
./start_local.sh
```

---

## 📚 **Quick Reference**

| Method | Speed | Difficulty | When to Use |
|--------|-------|------------|-------------|
| Railway CLI | ⚡ Fast | 🟢 Easy | Regular use |
| Web Shell | ⚡ Fast | 🟢 Easy | No CLI setup |
| SQL Query | ⚡ Fast | 🟡 Medium | Direct DB access |
| Env Variable | 🐌 Slow | 🔴 Complex | Automated resets |

**Recommended:** Railway CLI (Method 1)

