"""
Populate Relevant Users for Tasks
==================================

This script calculates which users should be "relevant" (need to align) on each task.

LOGIC FOR DETERMINING RELEVANT USERS:
-------------------------------------

A user is relevant to a task if they need to have aligned perception about it.
This includes:

1. MANAGER of Task Owner
   - Managers need visibility into their employees' tasks
   - They provide direction and need to be aligned on priorities/status

2. EMPLOYEES of Task Owner (if owner is a manager)
   - Direct reports may be affected by or contributing to the task
   - They need to understand what their manager is working on

3. OWNERS of DEPENDENT TASKS (task dependencies)
   - If Task A depends on Task B, owner of A is relevant to B
   - They need to be aligned on when B will be done, its priority, etc.

4. OWNERS of TASKS THAT DEPEND ON THIS TASK
   - If this task blocks another task, that task's owner is relevant
   - Bidirectional dependency awareness

MANUAL REGISTRATION RULES:
- Anyone can register/unregister THEMSELVES to any task
- Task OWNER can register/unregister ANYONE from their task
- MANAGER can register/unregister their employees (direct or indirect) to any task

NOTE: The task OWNER is NOT stored as a relevant user (they are implicitly relevant)

WHEN IS THIS DATA UPDATED:
--------------------------
1. Initial population: Run this script
2. New task created: Auto-populate in task creation endpoint
3. Dependency added/removed: Update relevant users
4. Manager/team changes: Re-run script or trigger recalculation
5. Alignment edge added: Add to relevant users

"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uuid import uuid4
from app.database import SessionLocal
from app.models import (
    User, Task, TaskDependency, TaskRelevantUser
)


def calculate_relevant_users_for_task(db, task) -> set:
    """
    Calculate which users should be relevant for a given task.
    Returns a set of user IDs (excluding the owner).
    """
    relevant_user_ids = set()
    owner_id = task.owner_user_id
    
    # Get the owner
    owner = db.query(User).filter(User.id == owner_id).first()
    if not owner:
        return relevant_user_ids
    
    # 1. MANAGER of task owner
    if owner.manager_id:
        relevant_user_ids.add(owner.manager_id)
    
    # 2. EMPLOYEES of task owner (direct reports)
    employees = db.query(User).filter(User.manager_id == owner_id).all()
    for emp in employees:
        relevant_user_ids.add(emp.id)
    
    # 3. OWNERS of tasks that THIS task depends on
    # If this task depends on task B, owner of B is relevant here
    deps = db.query(TaskDependency).filter(
        TaskDependency.task_id == task.id
    ).all()
    for dep in deps:
        dep_task = db.query(Task).filter(Task.id == dep.depends_on_task_id).first()
        if dep_task and dep_task.owner_user_id != owner_id:
            relevant_user_ids.add(dep_task.owner_user_id)
    
    # 4. OWNERS of tasks that DEPEND ON this task
    # If task B depends on this task, owner of B is relevant here
    dependent_on_this = db.query(TaskDependency).filter(
        TaskDependency.depends_on_task_id == task.id
    ).all()
    for dep in dependent_on_this:
        dep_task = db.query(Task).filter(Task.id == dep.task_id).first()
        if dep_task and dep_task.owner_user_id != owner_id:
            relevant_user_ids.add(dep_task.owner_user_id)
    
    # NOTE: AlignmentEdge concept has been REMOVED from the system.
    # Relevant users are determined by rules 1-4 above + manual registration.
    
    # Remove owner from relevant users (they're implicitly relevant)
    relevant_user_ids.discard(owner_id)
    
    return relevant_user_ids


def populate_all_tasks(db, clear_existing=False):
    """
    Populate relevant users for all tasks.
    """
    print("=" * 60)
    print("POPULATING RELEVANT USERS FOR ALL TASKS")
    print("=" * 60)
    
    if clear_existing:
        print("\n🗑️  Clearing existing relevant user associations...")
        db.query(TaskRelevantUser).delete()
        db.commit()
        print("   Done.")
    
    tasks = db.query(Task).filter(Task.is_active == True).all()
    print(f"\n📋 Processing {len(tasks)} active tasks...")
    
    total_added = 0
    
    for task in tasks:
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        owner_name = owner.name if owner else "Unknown"
        
        # Calculate relevant users
        relevant_ids = calculate_relevant_users_for_task(db, task)
        
        added_count = 0
        for user_id in relevant_ids:
            # Check if already exists
            existing = db.query(TaskRelevantUser).filter(
                TaskRelevantUser.task_id == task.id,
                TaskRelevantUser.user_id == user_id
            ).first()
            
            if not existing:
                rel = TaskRelevantUser(
                    id=uuid4(),
                    task_id=task.id,
                    user_id=user_id,
                    added_by_user_id=None  # Auto-generated
                )
                db.add(rel)
                added_count += 1
                total_added += 1
        
        if added_count > 0:
            user_names = []
            for uid in relevant_ids:
                u = db.query(User).filter(User.id == uid).first()
                if u:
                    user_names.append(u.name)
            print(f"   ✅ {task.title} (owner: {owner_name})")
            print(f"      → Added {added_count} relevant users: {', '.join(user_names)}")
    
    db.commit()
    
    print(f"\n{'=' * 60}")
    print(f"✅ DONE! Added {total_added} relevant user associations.")
    print(f"{'=' * 60}")
    
    return total_added


def update_relevant_users_for_task(db, task_id):
    """
    Update relevant users for a single task.
    Called when a task is created or modified.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return 0
    
    # Calculate new relevant users
    new_relevant_ids = calculate_relevant_users_for_task(db, task)
    
    # Get existing relevant users
    existing = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.task_id == task_id
    ).all()
    existing_ids = {r.user_id for r in existing}
    
    # Add new ones
    added = 0
    for user_id in new_relevant_ids:
        if user_id not in existing_ids:
            rel = TaskRelevantUser(
                id=uuid4(),
                task_id=task_id,
                user_id=user_id,
                added_by_user_id=None
            )
            db.add(rel)
            added += 1
    
    # Note: We don't remove existing ones (user may have added manually)
    
    db.commit()
    return added


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("RELEVANT USERS CALCULATION LOGIC")
    print("=" * 60)
    print("""
A user is marked as "relevant" to a task if they need aligned perception.

WHO IS RELEVANT (auto-calculated):
  1. Manager of task owner     → oversight & direction
  2. Employees of task owner   → collaboration & awareness  
  3. Dependency owners         → blocked by / blocking

MANUAL REGISTRATION:
  - Anyone can register/unregister THEMSELVES
  - Task owner can register/unregister ANYONE
  - Manager can register/unregister their employees

This script will calculate and populate this data for all existing tasks.
    """)
    
    # Ask for confirmation
    if "--yes" in sys.argv:
        confirm = "y"
    else:
        try:
            confirm = input("Continue? (y/n): ").strip().lower()
        except EOFError:
            confirm = "y"  # Non-interactive mode
    
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)
    
    clear = False
    if len(sys.argv) > 1 and "--clear" in sys.argv:
        clear = True
        print("\n⚠️  Will clear existing relevant user data first.")
    
    db = SessionLocal()
    try:
        populate_all_tasks(db, clear_existing=clear)
    finally:
        db.close()

