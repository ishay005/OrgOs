# Quick Start: Task Graph Visualization

## 🚀 Get Started in 3 Steps

### Step 1: Open the Web Interface

```bash
# Server should already be running on:
http://localhost:8000/
```

### Step 2: Create Some Related Tasks

1. **Login** (or register if first time)
2. Click **Dashboard** → **My Tasks** → **+ New Task**
3. Create a parent task:
   ```
   Title: "Build Mobile App"
   Description: "Complete mobile application"
   Parent Task: None
   Child Tasks: "Design UI, Implement API, Testing"
   Dependencies: (leave empty)
   ```
4. Click **Create**

This will create:
- 1 parent task: "Build Mobile App"  
- 3 child tasks automatically: "Design UI", "Implement API", "Testing"

### Step 3: View the Graph

1. Click **🔗 Task Graph** in the navigation
2. You'll see your tasks laid out hierarchically:
   ```
   ┌─────────────────┐
   │ Build Mobile App│  (parent - top)
   └─────────────────┘
          │
          ├─────────────────┐
          │                 │
   ┌──────────┐   ┌─────────────┐   ┌─────────┐
   │Design UI │   │Implement API│   │ Testing │  (children - below)
   └──────────┘   └─────────────┘   └─────────┘
   ```

## 🎨 Visual Elements Explained

### Task Node Colors

- **Blue Border**: Task has a parent (it's someone's child)
- **Orange Border**: Task has children (it's a parent)
- **Red Left Border**: Task has dependencies (blocks other work)

### Connection Lines

- **Solid Blue Line** (↕️): Parent ↔ Child relationship (vertical)
- **Solid Orange Line** (↕️): Child indicator (vertical)
- **Dashed Red Line** (↔️): Dependency (horizontal, left to right)

### Example Visual

```
     ┌──────────────┐
     │ Epic Task    │ ← Orange border (has children)
     └──────────────┘
           │ Blue line (parent link)
     ┌─────┴─────┐
     │           │
┌────────┐  ┌────────┐
│Feature1│  │Feature2│ ← Blue border (has parent)
└────────┘  └────────┘
     │
     │ Blue line
     │
┌────────┐
│Subtask │
└────────┘

With dependency:
┌────────┐ ╌╌╌╌╌> ┌────────┐
│Task A  │  Red   │Task B  │ ← Red left border
└────────┘ dashed └────────┘
          (B depends on A)
```

## 🔍 Using Filters

### Filter by Owner
```
Owner: [All Users ▼]  ← Select to show only one person's tasks
```

### Show/Hide Relationships
```
☑ Parents       ← Uncheck to hide parent links
☑ Children      ← Uncheck to hide child links  
☑ Dependencies  ← Uncheck to hide dependency arrows
```

### Refresh
Click **🔄 Refresh** after creating new tasks

## 📝 Creating Complex Hierarchies

### Example: E-commerce Project

1. **Create Epic** (top level):
   ```
   Title: "E-commerce Platform"
   Children: "User Management, Product Catalog, Checkout"
   ```

2. **Add Dependencies**:
   Create a deployment task that depends on others:
   ```
   Title: "Deploy to Production"
   Dependencies: [select multiple existing tasks]
   ```

3. **Result**:
   ```
   ┌─────────────────────┐
   │E-commerce Platform  │
   └─────────────────────┘
        │      │      │
        ▼      ▼      ▼
     ┌────┐ ┌────┐ ┌────┐
     │User│ │Prod│ │Chck│
     └────┘ └────┘ └────┘
        │      │      │
        └──────┴──────┘
               │
               ▼
        ┌────────────┐
        │   Deploy   │ ← Depends on all three
        └────────────┘
   ```

## 🎯 Real-World Example

After running the test script, you'll see:

```
Build Authentication System (Bob)
  │
  └─> Implement OAuth2 provider (Bob)

Database Setup (Bob)
  ├─> Configure PostgreSQL (Bob)
  ├─> Set up migrations (Bob)  
  └─> Create backup strategy (Bob)

Deploy to Production (Bob)
  ╌╌╌depends on╌╌> Build Authentication System
  ╌╌╌depends on╌╌> Database Setup
```

## 🛠️ Pro Tips

1. **Start Simple**: Create 2-3 tasks first to understand the layout
2. **Use Hierarchy**: Parent tasks = projects, children = work items
3. **Dependencies = Sequence**: Use for "must finish X before Y"
4. **Filter by You**: Set owner filter to your name for focused view
5. **Hover for Details**: Mouse over tasks to see full description

## 🐛 Troubleshooting

### Graph is Empty
- Check the owner filter (set to "All Users")
- Make sure you've created tasks
- Click 🔄 Refresh

### No Lines Visible  
- Enable all checkboxes (Parents, Children, Dependencies)
- Verify tasks actually have relationships

### Tasks Overlapping
- Graph auto-layouts, but many tasks at same level may crowd
- Use owner filter to reduce visible tasks

## 🧪 Test the System

Run this to populate with example data:

```bash
cd /Users/ishaylevi/work/OrgOs
source venv/bin/activate  
python test_task_relationships.py
```

Then open: **http://localhost:8000/** → **Dashboard** → **🔗 Task Graph**

You'll see a pre-built graph with:
- ✅ Parent-child relationships
- ✅ Auto-generated child tasks
- ✅ Task dependencies
- ✅ Multiple users' tasks

## 📚 Next Steps

1. Create your own tasks with relationships
2. Experiment with filters
3. Add team members and align with them
4. Answer questions about tasks to detect misalignments
5. Use the graph to visualize team understanding

---

**Enjoy visualizing your organization's task relationships!** 🎉

