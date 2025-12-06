#!/bin/bash

# Start PostgreSQL using docker-compose
echo "Starting PostgreSQL..."
docker-compose up -d

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 5

# Run the FastAPI application
echo "Starting FastAPI application..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

