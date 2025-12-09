#!/bin/bash
set -e

echo "🚀 Starting OrgOs locally with test data..."

# Activate virtual environment if needed
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set environment for local development
export POPULATE_SAMPLE_DATA=true
export DATABASE_URL=${DATABASE_URL:-"postgresql://postgres:postgres@localhost:5432/orgos"}

# Check if database is running
if ! docker ps | grep -q orgos-postgres; then
    echo "📦 Starting PostgreSQL with Docker Compose..."
    docker-compose up -d
    echo "⏳ Waiting for PostgreSQL to be ready..."
    sleep 3
fi

# Initialize database
echo "📊 Initializing database..."
python3 init_db.py

# Seed attribute definitions
echo "🌱 Seeding attribute definitions..."
python3 app/seed.py

# Populate sample data (for local testing)
echo "📝 Populating sample/test data..."
python3 populate_full_data.py || echo "⚠️  Sample data population failed"

echo "🔢 Calculating similarity scores..."
python3 populate_similarity_scores.py || echo "⚠️  Similarity score calculation failed"

# Start the application
echo "✅ Starting FastAPI server on http://localhost:8000..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

