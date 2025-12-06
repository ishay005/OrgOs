# Quick Reference Guide

## 🚀 Getting Started in 3 Steps

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL
docker-compose up -d

# 3. Run the API
uvicorn app.main:app --reload
```

Visit: http://localhost:8000/docs

## 📊 System Flow

```
1. Users → Create accounts (POST /users)
   ↓
2. Users → Align with teammates (POST /alignments)
   ↓
3. Users → Create tasks (POST /tasks)
   ↓
4. Users → Get questions about tasks (GET /questions/next)
   ↓
5. Users → Submit answers (POST /answers)
   ↓
6. System → Computes misalignments (GET /misalignments)
   ↓
7. Users → Review perception gaps
```

## 🔑 Authentication

All requests (except user creation) need:
```bash
-H "X-User-Id: <your-uuid>"
```

## 📝 Common Operations

### Create a User
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

### Create an Alignment
```bash
curl -X POST http://localhost:8000/alignments \
  -H "X-User-Id: <alice-id>" \
  -H "Content-Type: application/json" \
  -d '{"target_user_id": "<bob-id>", "align": true}'
```

### Create a Task
```bash
curl -X POST http://localhost:8000/tasks \
  -H "X-User-Id: <user-id>" \
  -H "Content-Type: application/json" \
  -d '{"title": "My Task", "description": "Task details"}'
```

### Get Questions
```bash
curl "http://localhost:8000/questions/next?max_questions=5" \
  -H "X-User-Id: <user-id>"
```

### Submit Answer
```bash
curl -X POST http://localhost:8000/answers \
  -H "X-User-Id: <user-id>" \
  -H "Content-Type: application/json" \
  -d '{"question_id": "<q-id>", "value": "High", "refused": false}'
```

### View Misalignments
```bash
curl http://localhost:8000/misalignments \
  -H "X-User-Id: <user-id>"
```

## 🎯 Key Concepts

### Alignment
- Users declare who they "align with" (want to compare perceptions with)
- When you align with someone, you'll get questions about their tasks
- Misalignments are computed between you and people you align with

### Attributes
- Defined in the ontology (task or user attributes)
- Examples: priority, status, main_goal, value_type
- Some are enums, some are free text, some are numeric

### Questions
- System generates questions about task attributes
- You answer about your own tasks AND tasks of people you align with
- Answers become stale after 1 day (you'll be re-asked)
- You can refuse to answer (won't be asked again)

### Misalignments
- Compares YOUR perception of someone's task
- With THEIR perception of their own task
- Returns similarity scores (0.0 = different, 1.0 = identical)

## 🔍 Debug Endpoints

### View All Attributes
```bash
curl http://localhost:8000/debug/attributes
```

### Test Similarity Algorithm
```bash
curl -X POST http://localhost:8000/debug/similarity \
  -H "Content-Type: application/json" \
  -d '{
    "attribute_type": "enum",
    "value_a": "High",
    "value_b": "Medium"
  }'
```

### View Raw Questions
```bash
curl http://localhost:8000/debug/questions/raw \
  -H "X-User-Id: <user-id>"
```

## 📦 Project Structure

```
OrgOs/
├── app/
│   ├── main.py              ← FastAPI app entry point
│   ├── models.py            ← Database models
│   ├── schemas.py           ← API request/response schemas
│   ├── auth.py              ← Authentication
│   ├── seed.py              ← Initial data seeding
│   ├── routers/             ← API endpoints
│   │   ├── users.py
│   │   ├── tasks.py
│   │   ├── questions.py
│   │   ├── misalignments.py
│   │   └── debug.py
│   └── services/            ← Business logic
│       ├── llm_questions.py  (placeholder for Prompt 2)
│       └── similarity.py     (placeholder for Prompt 3)
├── docker-compose.yml       ← PostgreSQL setup
├── requirements.txt         ← Python dependencies
├── test_api.py             ← Automated test script
└── README.md               ← Full documentation
```

## 🧪 Testing

### Automated Test
```bash
python test_api.py
```

### Interactive Docs
Open http://localhost:8000/docs

### Manual Testing
See `API_TESTING_GUIDE.md` for detailed examples

## 🐛 Troubleshooting

### "Connection refused" error
- Make sure PostgreSQL is running: `docker-compose ps`
- Start it: `docker-compose up -d`

### "Module not found" error
- Install dependencies: `pip install -r requirements.txt`

### "User not found" (401 error)
- Make sure you're using a valid user ID in X-User-Id header
- Create a user first with `POST /users`

### Database issues
- Restart PostgreSQL: `docker-compose restart`
- Check logs: `docker-compose logs postgres`

## 📚 Documentation

- **README.md** - Full system documentation
- **API_TESTING_GUIDE.md** - Complete API examples with curl
- **IMPLEMENTATION_SUMMARY.md** - What's implemented and what's next
- **http://localhost:8000/docs** - Interactive API documentation

## 🎯 Next Steps

1. ✅ Backend API - **DONE!**
2. ⏳ LLM Question Generation (Prompt 2)
3. ⏳ Similarity Engine (Prompt 3)
4. ⏳ Android Client (Prompt 4)

## 💡 Pro Tips

1. **Save User IDs** - After creating a user, save the returned ID
2. **Use Debug Endpoints** - Great for understanding how the system works
3. **Check Swagger UI** - Interactive testing at /docs
4. **View Logs** - Server logs show all requests and errors
5. **Alignment is Key** - You only see tasks from people you align with

## ⚡ One-Line Commands

```bash
# Full setup and run
pip install -r requirements.txt && docker-compose up -d && sleep 3 && uvicorn app.main:app --reload

# Run tests
python test_api.py

# Stop everything
docker-compose down

# View database
docker-compose exec postgres psql -U postgres -d orgos
```

