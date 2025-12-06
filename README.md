# OrgOs - Perception Alignment System

A backend API system for collecting and analyzing perception alignment across teams.

## Overview

This system helps organizations identify perception gaps between team members by:
1. Collecting perceptions about tasks and people through structured questions
2. Comparing individual perceptions with others' self-perceptions
3. Computing misalignment scores to highlight areas where alignment is needed

## Components

1. **Backend API & Data Model** ✅ (FastAPI + PostgreSQL) - **COMPLETED**
2. **LLM Question-Generation Module** ✅ (OpenAI GPT-4) - **COMPLETED**
3. **Misalignment / Similarity Engine** ✅ (OpenAI Embeddings) - **COMPLETED**
4. **Android Client App** ✅ (Kotlin + Retrofit) - **COMPLETED**

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for PostgreSQL)
- pip

### Installation

1. Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
```

2. Start PostgreSQL using Docker:
```bash
docker-compose up -d
```

3. Create `.env` file with your OpenAI API key:
```bash
cat > .env << EOF
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/orgos
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_MODEL=gpt-4
EOF
```

Get your API key from: https://platform.openai.com/api-keys

See [ENV_SETUP.md](ENV_SETUP.md) for detailed configuration instructions.

4. Run the application:
```bash
uvicorn app.main:app --reload
```

Or use the convenience script:
```bash
chmod +x run.sh
./run.sh
```

5. Access the API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Documentation

- **[START_HERE.md](START_HERE.md)** - Quick start guide ⭐ Start here!
- **[API_TESTING_GUIDE.md](API_TESTING_GUIDE.md)** - API testing examples and curl commands
- **[LLM_QUESTIONS_GUIDE.md](LLM_QUESTIONS_GUIDE.md)** - LLM question generation documentation
- **[SIMILARITY_ENGINE_GUIDE.md](SIMILARITY_ENGINE_GUIDE.md)** - Similarity & misalignment detection
- **[ENV_SETUP.md](ENV_SETUP.md)** - Environment configuration guide
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference
- **[CURRENT_STATUS.md](CURRENT_STATUS.md)** - Overall project status

### Key Endpoints

**User Management:**
- `POST /users` - Create a new user
- `GET /users` - List all users
- `GET /alignments` - Get user's alignment list
- `POST /alignments` - Create/delete alignment edges

**Tasks & Attributes:**
- `GET /tasks` - List tasks (filtered by ownership/alignment)
- `POST /tasks` - Create a new task
- `GET /task-attributes` - Get task attribute definitions
- `GET /user-attributes` - Get user attribute definitions

**Questions & Answers:**
- `GET /questions/next` - Get next set of questions for user
- `POST /answers` - Submit answer to a question

**Misalignment Detection:**
- `GET /misalignments` - Get perception misalignments

**Debug Endpoints:**
- `GET /debug/attributes` - View all attributes grouped by type
- `GET /debug/questions/raw` - View raw question generation
- `POST /debug/similarity` - Test similarity computation
- `GET /debug/misalignments/raw` - View all misalignment pairs

## Architecture

```
app/
├── main.py                 # FastAPI application entry point
├── config.py              # Configuration management
├── database.py            # Database connection and session
├── models.py              # SQLAlchemy ORM models
├── schemas.py             # Pydantic request/response schemas
├── auth.py                # Authentication dependency
├── seed.py                # Database seeding (initial ontology)
├── routers/               # API endpoint handlers
│   ├── users.py          # User and alignment endpoints
│   ├── tasks.py          # Task and attribute endpoints
│   ├── questions.py      # Question and answer endpoints
│   ├── misalignments.py  # Misalignment detection
│   └── debug.py          # Debug/testing endpoints
└── services/              # Business logic layer
    ├── llm_questions.py  # Question generation (placeholder)
    └── similarity.py     # Similarity computation (placeholder)
```

## Database Schema

### Core Entities

- **User**: Team members who provide perceptions
- **AlignmentEdge**: Defines who aligns with whom
- **Task**: Work items that perceptions are collected about
- **AttributeDefinition**: Defines what attributes to collect (ontology)
- **AttributeAnswer**: User's answer about a specific attribute
- **QuestionLog**: Tracks all questions asked (for traceability)

### Initial Ontology

The system comes pre-seeded with task attributes:
- `priority` (enum): Critical, High, Medium, Low
- `status` (enum): Not started, In progress, Blocked, Done
- `value_type` (enum): Customer revenue, Risk reduction, etc.
- `perceived_owner` (string): Who's responsible
- `is_blocked` (bool): Is it blocked?
- `blocking_reason` (string): What's blocking it
- `impact_size` (int 1-5): Expected impact
- `direction_confidence` (int 1-5): Confidence this is right
- `main_goal` (string): Free-text goal description

And user attributes:
- `role_title`, `primary_team`, `main_domain` (strings)
- `decision_scope` (enum): Individual, Team, Cross-team, Org-wide
- `perceived_load` (enum): Underloaded, Balanced, Overloaded

## Authentication

All API endpoints (except `POST /users` and `GET /users`) require authentication via the `X-User-Id` header:

```bash
curl http://localhost:8000/tasks \
  -H "X-User-Id: <your-user-uuid>"
```

Create a user first with `POST /users`, save the returned ID, and use it in subsequent requests.

## Development

### Running Tests
```bash
# TODO: Add tests
pytest
```

### Database Migrations
The application automatically creates tables on startup. For production, consider using Alembic migrations.

### Logging
The application uses Python's standard logging. Set log level in `app/main.py`.

## System Status

All components complete! 🎉

1. ✅ **Prompt 1**: Backend API & Data Model - **COMPLETED**
2. ✅ **Prompt 2**: LLM-based question generation - **COMPLETED**
3. ✅ **Prompt 3**: Similarity engine using embeddings - **COMPLETED**
4. ✅ **Prompt 4**: Android client app - **COMPLETED**

The complete OrgOs Perception Alignment System is ready for deployment!

## Testing the System

Test different components:

```bash
# Test LLM question generation
python -m app.services.llm_questions

# Test similarity engine
python test_similarity.py

# Test full API integration
python test_api.py
```

## License

[Add your license here]

