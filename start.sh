#!/bin/bash
set -e

echo "🚀 Starting OrgOs deployment..."

# Initialize database
echo "📊 Initializing database..."
python3 init_db.py

# Seed attribute definitions
echo "🌱 Seeding attribute definitions..."
python3 app/seed.py

# Populate sample data (optional - only for demo)
if [ "$POPULATE_SAMPLE_DATA" = "true" ]; then
    echo "📝 Populating sample data..."
    python3 populate_full_data.py || echo "⚠️  Sample data population failed (not critical)"
    
    echo "🔢 Calculating similarity scores..."
    python3 populate_similarity_scores.py || echo "⚠️  Similarity score calculation failed (not critical)"
fi

# Start the application
echo "✅ Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

