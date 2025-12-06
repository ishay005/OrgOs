# Task Relationships Guide

## Overview

The OrgOs system now supports rich task relationships that model organizational work structures:

1. **Parent-Child Hierarchy**: Tasks can have parent tasks and child subtasks
2. **Dependencies**: Tasks can depend on other tasks
3. **Visual Graph**: See all task relationships in an interactive graph view

## Features

### 1. Parent-Child Relationships

#### Creating a Task with a Parent

```json
POST /tasks
{
  "title": "Implement login page",
  "description": "Build the login UI",
  "parent_id": "uuid-of-parent-task"
}
```

**Validation**:
- Parent task MUST exist or you'll get a 400 error
- Prevents orphaned tasks with invalid parents

#### Auto-Creating Child Tasks

```json
POST /tasks
{
  "title": "Authentication System",
  "children": [
    "OAuth2 Integration",
    "Session Management", 
    "Password Reset Flow"
  ]
}
```

**Behavior**:
- If a child task with that title exists → links it as a child
- If it doesn't exist → creates new task with that title
- All children owned by the same user
- Parent-child link automatically established

### 2. Task Dependencies

```json
POST /tasks
{
  "title": "Deploy to Production",
  "dependencies": [
    "uuid-of-task-1",
    "uuid-of-task-2"
  ]
}
```

**Validation**:
- All dependency task IDs must exist
- Creates entries in `task_dependencies` junction table

### 3. Task Graph Visualization

#### API Endpoint

```bash
GET /tasks/graph
```

Returns all tasks with their relationship data:

```json
[
  {
    "id": "uuid",
    "title": "Authentication System",
    "description": "...",
    "owner_name": "Bob Smith",
    "parent_id": null,
    "children_ids": ["uuid1", "uuid2"],
    "dependency_ids": []
  }
]
```

#### Web UI - Task Graph Page

Navigate to: **Dashboard → 🔗 Task Graph**

**Features**:
- **Visual Layout**: Hierarchical graph with parent tasks at top, children below
- **Color Coding**:
  - Blue border: Task has a parent
  - Orange border: Task has children
  - Red left border: Task has dependencies
- **Connection Lines**:
  - Solid blue: Parent-child (vertical)
  - Solid orange: Alternative child indication
  - Dashed red: Dependencies (horizontal)
- **Interactive Filters**:
  - Filter by owner
  - Toggle parent/child/dependency connections
  - Refresh button
- **Legend**: Visual guide to relationship types

### 4. Database Schema

#### Tasks Table

```sql
CREATE TABLE tasks (
  id UUID PRIMARY KEY,
  title VARCHAR NOT NULL,
  description TEXT,
  owner_user_id UUID NOT NULL REFERENCES users(id),
  parent_id UUID REFERENCES tasks(id),  -- NEW
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_tasks_parent_id ON tasks(parent_id);
```

#### Task Dependencies Table

```sql
CREATE TABLE task_dependencies (
  id UUID PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  depends_on_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  created_at TIMESTAMP,
  UNIQUE(task_id, depends_on_task_id)
);

CREATE INDEX idx_task_dependencies_task_id ON task_dependencies(task_id);
CREATE INDEX idx_task_dependencies_depends_on ON task_dependencies(depends_on_task_id);
```

## Usage Examples

### Example 1: Project with Subtasks

```python
# Create parent project
project = create_task({
    "title": "Mobile App Redesign",
    "description": "Complete UI/UX overhaul"
})

# Create subtasks automatically
create_task({
    "title": "Mobile App Redesign",
    "children": [
        "Design new screens",
        "Implement navigation",
        "Add animations",
        "User testing"
    ]
})
```

### Example 2: Task with Dependencies

```python
# Create prerequisite tasks
auth = create_task({"title": "Build Auth API"})
db = create_task({"title": "Setup Database"})

# Create dependent task
create_task({
    "title": "Deploy Backend",
    "dependencies": [auth["id"], db["id"]]
})
```

### Example 3: Complex Hierarchy

```python
# Epic
epic = create_task({"title": "E-commerce Platform"})

# Features as children of epic
checkout = create_task({
    "title": "Checkout Flow",
    "parent_id": epic["id"],
    "children": ["Cart Page", "Payment Page", "Confirmation"]
})

product_catalog = create_task({
    "title": "Product Catalog", 
    "parent_id": epic["id"],
    "children": ["Search", "Filters", "Product Detail"]
})
```

## Web UI Workflow

### Creating Related Tasks

1. Go to **Dashboard → My Tasks**
2. Click **+ New Task**
3. In the modal:
   - **Title**: Enter task name
   - **Description**: Optional details
   - **Parent Task**: Select from dropdown (or None)
   - **Child Tasks**: Enter comma-separated titles
   - **Dependencies**: Multi-select from available tasks

### Viewing the Task Graph

1. Go to **Dashboard → 🔗 Task Graph**
2. Use filters:
   - **Owner**: Show only tasks by specific person
   - **Checkboxes**: Toggle relationship types
3. Hover over tasks to see descriptions
4. Visual layout shows hierarchy automatically

### Filtering the Graph

- **By Owner**: Dropdown to show one person's tasks
- **Show Parents**: Toggle upward parent links
- **Show Children**: Toggle downward child links  
- **Show Dependencies**: Toggle horizontal dependency arrows

## Testing

Run the test script to verify everything works:

```bash
cd /Users/ishaylevi/work/OrgOs
source venv/bin/activate
python test_task_relationships.py
```

This tests:
- ✅ Parent-child creation
- ✅ Auto-child task generation
- ✅ Dependency validation
- ✅ Parent existence validation
- ✅ Graph API endpoint

## Graph Layout Algorithm

The graph uses a hierarchical layout:

1. **Level Assignment**: BFS from root tasks (no parent)
2. **Vertical Placement**: Each level placed below previous
3. **Horizontal Centering**: Tasks centered within level
4. **Connection Drawing**: 
   - SVG lines for connections
   - Arrows pointing to dependencies
5. **Collision Avoidance**: Horizontal spacing between tasks

## API Response Examples

### Regular Task List

```bash
GET /tasks?include_self=true&include_aligned=true
```

```json
[
  {
    "id": "uuid",
    "title": "Task Title",
    "description": "...",
    "owner_user_id": "uuid",
    "owner_name": "Bob Smith",
    "parent_id": "uuid-or-null",
    "is_active": true,
    "created_at": "2024-01-01T10:00:00"
  }
]
```

### Task Graph

```bash
GET /tasks/graph
```

```json
[
  {
    "id": "uuid",
    "title": "Authentication System",
    "description": "Build auth",
    "owner_name": "Bob Smith",
    "parent_id": null,
    "children_ids": ["child-uuid-1", "child-uuid-2"],
    "dependency_ids": []
  }
]
```

## Best Practices

1. **Use Parents for Hierarchy**: Organize work into epics/features/tasks
2. **Use Dependencies for Sequencing**: Model "must complete X before Y"
3. **Auto-Create Children**: Quick way to break down work
4. **Keep Graph Manageable**: Too many tasks = cluttered visualization
5. **Filter Strategically**: Use owner filter for focused views

## Future Enhancements

Potential additions:
- Circular dependency detection
- Critical path highlighting
- Progress rollup (parent shows % of children done)
- Drag-and-drop graph editing
- Gantt chart view
- Cycle time analytics

## Troubleshooting

### Parent Validation Error

```
Error 400: Parent task {id} does not exist
```

**Solution**: Ensure parent task is created first, use correct UUID

### Duplicate Children

If you list the same child twice, only one link is created (idempotent by title).

### Graph Not Loading

1. Check browser console for errors
2. Verify `/tasks/graph` returns data
3. Check filters aren't excluding all tasks
4. Refresh page

### No Connections Visible

1. Ensure checkbox filters are enabled
2. Check that tasks actually have relationships
3. Verify tasks are not filtered out by owner

## Migration Applied

The system automatically applied this migration:

```sql
-- migrations/add_task_relationships.sql
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES tasks(id);

CREATE TABLE IF NOT EXISTS task_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, depends_on_task_id)
);
```

## Summary

You now have a complete task relationship system:
- ✅ Parent-child hierarchies
- ✅ Auto-creation of child tasks
- ✅ Task dependencies
- ✅ Validation (parent must exist)
- ✅ Graph visualization with filtering
- ✅ Full CRUD API support
- ✅ Beautiful web UI

Navigate to **http://localhost:8000/** and explore the Task Graph page!

