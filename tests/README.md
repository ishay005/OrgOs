# OrgOs Test Suite

Comprehensive automated test suite for OrgOs covering backend logic, Robin AI, MCP tools, UI flows, and adversarial scenarios.

## Quick Start

```bash
# Run all standard tests (excludes UI and real OpenAI tests)
pytest tests

# Run with verbose output
pytest tests -v

# Run specific test category
pytest tests/unit              # Unit tests only
pytest tests/integration       # Integration tests only
pytest tests/scenarios         # Scenario tests only
pytest tests/properties        # Invariant/fuzz tests only
```

## Test Categories

### Unit Tests (`tests/unit/`)
Fast, isolated tests for individual functions and services.

| File | Description |
|------|-------------|
| `test_task_state_machine.py` | Task state transitions (DRAFT→ACTIVE→DONE→ARCHIVED) |
| `test_dependency_state_machine.py` | Dependency lifecycle (propose→accept/reject) |
| `test_attribute_consensus.py` | Consensus calculation (NO_DATA, SINGLE_SOURCE, ALIGNED, MISALIGNED) |
| `test_questions_engine.py` | Question generation and prioritization |
| `test_robin_mode_routing.py` | Robin mode selection and transitions |

### Integration Tests (`tests/integration/`)
Multi-component tests using test database and mocked OpenAI.

| File | Description |
|------|-------------|
| `test_task_lifecycle.py` | Full task lifecycle via API |
| `test_dependency_lifecycle.py` | Dependency creation, approval, removal via API |
| `test_merge_lifecycle.py` | Task merge with alias creation and data migration |
| `test_alignment_detection_flow.py` | Misalignment detection and resolution |
| `test_robin_daily_flow.py` | Daily sync mode phases |
| `test_robin_questions_flow.py` | Questions mode conversation |
| `test_mcp_context_tools.py` | MCP/Cortex tool responses |

### Scenario Tests (`tests/scenarios/`)
Multi-step stories testing complex workflows.

| File | Description |
|------|-------------|
| `test_small_org_alignment_scenarios.py` | Cross-team alignment, manager bulk operations |
| `test_data_drift_and_staleness.py` | Stale data detection and refresh |
| `test_adversarial_user_behavior.py` | Edge cases, garbage input, rapid changes |

### Property Tests (`tests/properties/`)
Invariant verification and fuzz testing.

| File | Description |
|------|-------------|
| `test_invariants_and_fuzz.py` | Global invariants, random operation sequences |

### UI Tests (`tests/ui/`)
End-to-end Playwright tests (requires `RUN_UI_TESTS=1`).

| File | Description |
|------|-------------|
| `test_daily_mode_ui.py` | Daily sync UI rendering and interaction |
| `test_questions_mode_ui.py` | Chat interface and responses |
| `test_task_merge_ui.py` | Merge flow UI |
| `test_dependency_flow_ui.py` | Dependency approval UI |

### Optional OpenAI Tests (`tests/integration_optional/`)
Real OpenAI API tests (requires `RUN_OPENAI_INTEGRATION_TESTS=1`).

| File | Description |
|------|-------------|
| `test_openai_integration_opt_in.py` | Real API connectivity and response format |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENV` | Application environment | `test` |
| `TEST_DATABASE_URL` | Test database connection | `postgresql://postgres:postgres@localhost:5432/orgos_test` |
| `RUN_UI_TESTS` | Enable UI tests | `0` (disabled) |
| `RUN_OPENAI_INTEGRATION_TESTS` | Enable real OpenAI tests | `0` (disabled) |

## Test Database Setup

The test suite uses a separate database to avoid contamination:

```bash
# Create test database
createdb orgos_test

# Or use Docker
docker-compose up -d postgres
docker exec -it orgos-postgres psql -U postgres -c "CREATE DATABASE orgos_test;"
```

## Running Specific Tests

```bash
# Run a single test file
pytest tests/unit/test_task_state_machine.py

# Run a single test
pytest tests/unit/test_task_state_machine.py::TestTaskCreationState::test_task_created_by_owner_is_active

# Run tests matching a pattern
pytest -k "test_merge"

# Run with coverage
pytest --cov=app --cov-report=html

# Run in parallel (requires pytest-xdist)
pytest -n auto
```

## Running UI Tests

```bash
# Install Playwright
pip install playwright
playwright install chromium

# Run UI tests
RUN_UI_TESTS=1 pytest tests/ui -v
```

## Running Real OpenAI Tests

⚠️ **Warning**: These tests incur API costs!

```bash
# Run OpenAI integration tests
RUN_OPENAI_INTEGRATION_TESTS=1 pytest tests/integration_optional -v
```

## Test Isolation

All tests use:
- **Transaction rollback**: Each test runs in a transaction that is rolled back after completion
- **Fake OpenAI client**: All OpenAI calls are mocked by default
- **Test database**: Separate database from development/production

## Debugging Tests

```bash
# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Enter debugger on failure
pytest --pdb

# Show detailed traceback
pytest --tb=long
```

## CI/CD Integration

```yaml
# Example GitHub Actions workflow
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: orgos_test
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio
      
      - run: pytest tests -v
        env:
          TEST_DATABASE_URL: postgresql://postgres:postgres@localhost:5432/orgos_test
```

## Test Structure Best Practices

1. **One assertion per test when possible** - Makes failures easier to diagnose
2. **Use fixtures for common setup** - Defined in `conftest.py`
3. **Test both happy path and edge cases** - Cover error conditions
4. **Name tests descriptively** - `test_<what>_<when>_<expected>`

## Adding New Tests

1. Create test file in appropriate directory (`unit/`, `integration/`, etc.)
2. Add module docstring explaining:
   - What system part is tested
   - Unit size (function, service, multi-component)
   - Main failure modes
3. Use fixtures from `conftest.py` for database and users
4. Follow existing naming conventions

