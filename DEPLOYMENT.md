# OrgOs Cloud Deployment Guide

## Option 1: Railway (Recommended - Easiest)

### Step 1: Sign up for Railway
1. Go to https://railway.app
2. Sign up with GitHub account (free tier available)

### Step 2: Install Railway CLI
```bash
# Install Railway CLI
npm install -g @railway/cli

# Or using Homebrew (Mac)
brew install railway
```

### Step 3: Login to Railway
```bash
railway login
```

### Step 4: Initialize Railway Project
```bash
cd /Users/ishaylevi/work/OrgOs
railway init
```

### Step 5: Add PostgreSQL Database
```bash
railway add --database postgresql
```

### Step 6: Set Environment Variables
```bash
# Set OpenAI API key
railway variables set OPENAI_API_KEY=your_openai_key_here

# Railway will automatically set DATABASE_URL for PostgreSQL
```

### Step 7: Deploy!
```bash
railway up
```

### Step 8: Get Your URL
```bash
railway domain
```

---

## Option 2: Render (Alternative - Also Easy)

### Step 1: Sign up for Render
1. Go to https://render.com
2. Sign up with GitHub account

### Step 2: Create PostgreSQL Database
1. Click "New +" → "PostgreSQL"
2. Choose free tier
3. Create database
4. Copy the "Internal Database URL"

### Step 3: Create Web Service
1. Click "New +" → "Web Service"
2. Connect your GitHub repository (or manual deploy)
3. Configure:
   - **Name**: orgos
   - **Environment**: Docker
   - **Region**: Choose closest to you
   - **Branch**: main (or your branch)
   - **Build Command**: (leave empty, Docker handles it)
   - **Start Command**: `./start.sh`

### Step 4: Set Environment Variables
Add these in Render dashboard:
- `OPENAI_API_KEY`: your_openai_key
- `DATABASE_URL`: paste the Internal Database URL from step 2

### Step 5: Deploy
Click "Create Web Service" and wait for deployment!

---

## Option 3: Docker Compose (Local Production)

### Run with Docker Compose
```bash
cd /Users/ishaylevi/work/OrgOs

# Create .env file
cat > .env << EOF
OPENAI_API_KEY=your_key_here
DATABASE_URL=postgresql+psycopg://orgos:password@db:5432/orgos
EOF

# Start everything
docker-compose up -d
```

---

## Post-Deployment Steps

### 1. Populate Initial Data
Once deployed, you can populate data via API or run script:

```bash
# SSH into your server or run locally pointing to production DB
python3 populate_full_data.py
python3 populate_similarity_scores.py
```

### 2. Test the Deployment
- Visit your deployment URL
- Try registering a user
- Check that all features work

### 3. Share with Team
- Send the URL to your team
- They can register and start using it!

---

## Environment Variables Required

- `OPENAI_API_KEY`: Your OpenAI API key
- `DATABASE_URL`: PostgreSQL connection string (auto-set by Railway/Render)
- `PORT`: Port to run on (auto-set by platform, default: 8000)

---

## Troubleshooting

### Database Connection Issues
- Check DATABASE_URL format
- Ensure PostgreSQL is running
- Check network access

### Migration Errors
- SSH into container: `railway run bash`
- Run manually: `alembic upgrade head`

### Missing Dependencies
- Check requirements.txt is complete
- Rebuild: `railway up --detach`

---

## Cost Estimate

### Railway (Recommended)
- **Free Tier**: $5/month credit (enough for small teams)
- **Pro**: $20/month (unlimited usage)

### Render
- **Free Tier**: Available (with some limitations)
- **Starter**: $7/month per service

### Recommended for Production
- Railway Starter: ~$20/month total (app + database)
- Render Starter: ~$14/month total

---

## Security Notes

1. **Never commit .env files** - Already in .gitignore
2. **Use environment variables** for all secrets
3. **Enable HTTPS** - Railway/Render do this automatically
4. **Rotate keys regularly** - Change OpenAI key periodically
5. **Backup database** - Set up automated backups on Railway/Render

---

## Support

- Railway Docs: https://docs.railway.app
- Render Docs: https://render.com/docs
- OrgOs Issues: (your repo URL)

