#!/bin/bash
set -e

echo "🚀 Starting OrgOs deployment..."

# Initialize database
echo "📊 Initializing database..."
python3 init_db.py

# Seed attribute definitions
echo "🌱 Seeding attribute definitions..."
python3 app/seed.py

# Clear all data (optional - for resetting production)
if [ "$RUN_CLEAR_DATA" = "true" ]; then
    echo "🗑️  Clearing all user data..."
    python3 clear_all_data.py --confirm || echo "⚠️  Data clear failed"
fi

# Populate sample data (optional - only for demo)
if [ "$POPULATE_SAMPLE_DATA" = "true" ]; then
    echo "📝 Populating sample data..."
    python3 populate_full_data.py || echo "⚠️  Sample data population failed (not critical)"
    
    echo "🔢 Calculating similarity scores..."
    python3 populate_similarity_scores.py || echo "⚠️  Similarity score calculation failed (not critical)"
fi

# Start the application
echo "✅ Starting FastAPI server..."

# Railway-optimized uvicorn settings:
# - workers=1: Single worker (Railway free tier has limited CPU/memory)
# - timeout-keep-alive=75: Keep connections alive longer (reduces overhead)
# - limit-concurrency=50: Limit concurrent requests to prevent overload
# - backlog=100: Queue up to 100 connections during spikes
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8080} \
    --workers 1 \
    --timeout-keep-alive 75 \
    --limit-concurrency 50 \
    --backlog 100 \
    --log-level info

