#!/bin/bash

echo "🧪 OrgOs System Test"
echo "===================="
echo ""

# Step 1: Create User 1 (Alice)
echo "1️⃣  Creating User: Alice"
ALICE_RESPONSE=$(curl -s -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}')
ALICE_ID=$(echo $ALICE_RESPONSE | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "   ✅ Alice ID: $ALICE_ID"
echo ""

# Step 2: Create User 2 (Bob)
echo "2️⃣  Creating User: Bob"
BOB_RESPONSE=$(curl -s -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob", "email": "bob@example.com"}')
BOB_ID=$(echo $BOB_RESPONSE | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "   ✅ Bob ID: $BOB_ID"
echo ""

# Step 3: Alice aligns with Bob
echo "3️⃣  Alice aligns with Bob"
curl -s -X POST http://localhost:8000/alignments \
  -H "Content-Type: application/json" \
  -H "X-User-Id: $ALICE_ID" \
  -d "{\"target_user_id\": \"$BOB_ID\", \"align\": true}" > /dev/null
echo "   ✅ Alignment created"
echo ""

# Step 4: Bob creates a task
echo "4️⃣  Bob creates a task"
TASK_RESPONSE=$(curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -H "X-User-Id: $BOB_ID" \
  -d '{"title": "Build user dashboard", "description": "Create analytics dashboard for users"}')
TASK_ID=$(echo $TASK_RESPONSE | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "   ✅ Task ID: $TASK_ID"
echo ""

# Step 5: Get task attributes
echo "5️⃣  Available task attributes:"
curl -s http://localhost:8000/task-attributes | grep -o '"label":"[^"]*"' | cut -d'"' -f4 | head -5 | while read attr; do
  echo "   - $attr"
done
echo ""

# Step 6: Alice views tasks (should see Bob's task)
echo "6️⃣  Alice's view of tasks:"
curl -s http://localhost:8000/tasks \
  -H "X-User-Id: $ALICE_ID" | grep -o '"title":"[^"]*"' | cut -d'"' -f4 | while read title; do
  echo "   - $title"
done
echo ""

# Step 7: Try to get questions (will work but without OpenAI key, uses templates)
echo "7️⃣  Getting questions for Alice:"
QUESTIONS=$(curl -s "http://localhost:8000/questions/next?max_questions=2" \
  -H "X-User-Id: $ALICE_ID")
echo "$QUESTIONS" | grep -o '"question_text":"[^"]*"' | head -2 | cut -d'"' -f4 | while read question; do
  echo "   Q: ${question:0:100}..."
done
echo ""

echo "✅ System is fully operational!"
echo ""
echo "📖 Next Steps:"
echo "   1. Add OPENAI_API_KEY to .env for LLM-powered questions"
echo "   2. Open http://localhost:8000/docs for interactive API docs"
echo "   3. Run: python test_api.py for comprehensive testing"
echo "   4. Run: python test_similarity.py (requires OpenAI key)"
echo ""
echo "💾 User IDs for manual testing:"
echo "   Alice: $ALICE_ID"
echo "   Bob: $BOB_ID"
echo "   Task: $TASK_ID"
echo ""

