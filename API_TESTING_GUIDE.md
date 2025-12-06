# API Testing Guide

This guide provides example curl commands to test all the endpoints in the OrgOs API.

## Setup

1. Start the PostgreSQL database:
```bash
docker-compose up -d
```

2. Start the FastAPI application:
```bash
uvicorn app.main:app --reload
```

Or use the convenience script:
```bash
chmod +x run.sh
./run.sh
```

3. Access API documentation at: http://localhost:8000/docs

## Testing Flow

### 1. Create Users

```bash
# Create user 1 (Alice)
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice",
    "email": "alice@example.com",
    "timezone": "America/New_York",
    "notification_time": "09:00"
  }'

# Save the returned user ID as USER_1_ID

# Create user 2 (Bob)
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bob",
    "email": "bob@example.com",
    "timezone": "America/Los_Angeles"
  }'

# Save the returned user ID as USER_2_ID
```

### 2. List All Users

```bash
curl http://localhost:8000/users
```

### 3. Create Alignment (Alice aligns with Bob)

```bash
curl -X POST http://localhost:8000/alignments \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <USER_1_ID>" \
  -d '{
    "target_user_id": "<USER_2_ID>",
    "align": true
  }'
```

### 4. View Alignments

```bash
curl http://localhost:8000/alignments \
  -H "X-User-Id: <USER_1_ID>"
```

### 5. View Attribute Definitions

```bash
# Get task attributes
curl http://localhost:8000/task-attributes

# Get user attributes
curl http://localhost:8000/user-attributes

# Get all attributes (debug endpoint)
curl http://localhost:8000/debug/attributes
```

### 6. Create Tasks

```bash
# Bob creates a task
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <USER_2_ID>" \
  -d '{
    "title": "Implement user authentication",
    "description": "Add OAuth2 authentication to the API"
  }'

# Save the returned task ID as TASK_1_ID

# Bob creates another task
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <USER_2_ID>" \
  -d '{
    "title": "Setup CI/CD pipeline",
    "description": "Configure GitHub Actions for automated testing"
  }'
```

### 7. List Tasks

```bash
# Alice views tasks (her own + Bob's since she aligns with him)
curl "http://localhost:8000/tasks?include_self=true&include_aligned=true" \
  -H "X-User-Id: <USER_1_ID>"

# Bob views only his tasks
curl "http://localhost:8000/tasks?include_self=true&include_aligned=false" \
  -H "X-User-Id: <USER_2_ID>"
```

### 8. Get Questions

```bash
# Alice gets questions about Bob's tasks
curl "http://localhost:8000/questions/next?max_questions=5" \
  -H "X-User-Id: <USER_1_ID>"

# Save a question_id from the response as QUESTION_1_ID
```

### 9. Submit Answers

```bash
# Alice answers a question about task priority
curl -X POST http://localhost:8000/answers \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <USER_1_ID>" \
  -d '{
    "question_id": "<QUESTION_1_ID>",
    "value": "High",
    "refused": false
  }'

# Alice refuses to answer a question
curl -X POST http://localhost:8000/answers \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <USER_1_ID>" \
  -d '{
    "question_id": "<QUESTION_2_ID>",
    "refused": true
  }'
```

### 10. Bob Answers Questions About His Own Tasks

```bash
# Bob gets questions
curl "http://localhost:8000/questions/next?max_questions=5" \
  -H "X-User-Id: <USER_2_ID>"

# Bob answers about priority (different from Alice's perception)
curl -X POST http://localhost:8000/answers \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <USER_2_ID>" \
  -d '{
    "question_id": "<BOB_QUESTION_ID>",
    "value": "Medium",
    "refused": false
  }'
```

### 11. View Misalignments

```bash
# Alice checks misalignments with Bob
curl http://localhost:8000/misalignments \
  -H "X-User-Id: <USER_1_ID>"

# This will show differences between Alice's perception of Bob's tasks
# and Bob's own perception
```

## Debug Endpoints

### Test Similarity Algorithm

```bash
curl -X POST http://localhost:8000/debug/similarity \
  -H "Content-Type: application/json" \
  -d '{
    "attribute_type": "enum",
    "allowed_values": ["Critical", "High", "Medium", "Low"],
    "value_a": "High",
    "value_b": "Medium"
  }'

# Test string similarity
curl -X POST http://localhost:8000/debug/similarity \
  -H "Content-Type: application/json" \
  -d '{
    "attribute_type": "string",
    "value_a": "Implement secure authentication for users",
    "value_b": "Add user login security"
  }'
```

### View Raw Questions

```bash
curl http://localhost:8000/debug/questions/raw \
  -H "X-User-Id: <USER_1_ID>"
```

### View Raw Misalignments

```bash
curl http://localhost:8000/debug/misalignments/raw \
  -H "X-User-Id: <USER_1_ID>"
```

## Health Check

```bash
curl http://localhost:8000/health
```

## Complete Example Flow

Here's a complete test script you can run (replace USER_IDs with actual values):

```bash
#!/bin/bash

# Create users
ALICE=$(curl -s -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}' | jq -r '.id')

BOB=$(curl -s -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob", "email": "bob@example.com"}' | jq -r '.id')

echo "Created users: Alice=$ALICE, Bob=$BOB"

# Alice aligns with Bob
curl -s -X POST http://localhost:8000/alignments \
  -H "Content-Type: application/json" \
  -H "X-User-Id: $ALICE" \
  -d "{\"target_user_id\": \"$BOB\", \"align\": true}" > /dev/null

echo "Alice aligned with Bob"

# Bob creates a task
TASK=$(curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -H "X-User-Id: $BOB" \
  -d '{"title": "Build feature X", "description": "Important feature"}' | jq -r '.id')

echo "Bob created task: $TASK"

# Alice gets questions
echo "Alice's questions:"
curl -s "http://localhost:8000/questions/next?max_questions=3" \
  -H "X-User-Id: $ALICE" | jq .

# Save and answer a question
QUESTION=$(curl -s "http://localhost:8000/questions/next?max_questions=1" \
  -H "X-User-Id: $ALICE" | jq -r '.[0].question_id')

curl -s -X POST http://localhost:8000/answers \
  -H "Content-Type: application/json" \
  -H "X-User-Id: $ALICE" \
  -d "{\"question_id\": \"$QUESTION\", \"value\": \"High\", \"refused\": false}" > /dev/null

echo "Alice answered a question"

# Bob answers the same attribute
BOB_QUESTION=$(curl -s "http://localhost:8000/questions/next?max_questions=1" \
  -H "X-User-Id: $BOB" | jq -r '.[0].question_id')

curl -s -X POST http://localhost:8000/answers \
  -H "Content-Type: application/json" \
  -H "X-User-Id: $BOB" \
  -d "{\"question_id\": \"$BOB_QUESTION\", \"value\": \"Medium\", \"refused\": false}" > /dev/null

echo "Bob answered a question"

# Check misalignments
echo "Misalignments:"
curl -s http://localhost:8000/misalignments \
  -H "X-User-Id: $ALICE" | jq .
```

## Notes

- All authenticated endpoints require the `X-User-Id` header
- The database is automatically initialized and seeded on startup
- See http://localhost:8000/docs for interactive API documentation
- The similarity engine is a placeholder - will be enhanced in Prompt 3
- The question generation uses simple templates - will be enhanced with LLM in Prompt 2

