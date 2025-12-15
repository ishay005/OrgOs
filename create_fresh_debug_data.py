#!/usr/bin/env python3
"""
Create fresh debug data from scratch
- 2 users
- 5 tasks each with parent-child relationships
- All 9 attributes filled for both perspectives
- Direct database insertion to ensure data is there
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.models import User, Task, AttributeDefinition, AttributeAnswer, EntityType, TaskRelevantUser
from sqlalchemy import text
import random
from datetime import datetime
import uuid

# Answer values for each attribute
ANSWER_VALUES = {
    "priority": ["Critical", "High", "Medium", "Low"],
    "status": ["Not started", "In progress", "Blocked", "Done"],
    "value_type": ["Customer revenue", "Risk reduction", "Efficiency", "Learning", "Internal hygiene"],
    "perceived_owner": ["Bob Smith", "Alice Chen", "Team", "Product"],
    "is_blocked": ["false", "true"],
    "blocking_reason": ["None", "Waiting on review", "External dependencies", "Technical issues"],
    "impact_size": ["1", "2", "3", "4", "5"],
    "direction_confidence": ["1", "2", "3", "4", "5"],
    "main_goal": [
        "Improve system security and authentication",
        "Increase development velocity",
        "Reduce technical debt",
        "Enhance user experience",
        "Enable better analytics"
    ]
}

def clear_data(db):
    """Clear existing data"""
    print("🗑️  Clearing existing data...")
    
    # Delete in order of dependencies
    db.execute(text("DELETE FROM attribute_answers"))
    db.execute(text("DELETE FROM question_logs"))
    db.execute(text("DELETE FROM task_dependencies"))
    # alignment_edges table was deprecated and dropped
    db.execute(text("DELETE FROM tasks"))
    db.execute(text("DELETE FROM users"))
    db.commit()
    
    print("   ✅ All data cleared")

def create_debug_data():
    print("\n" + "="*70)
    print("🎲 CREATING FRESH DEBUG DATA")
    print("="*70)
    
    db = SessionLocal()
    
    try:
        # Initialize database
        init_db()
        
        # Clear existing data
        clear_data(db)
        
        # Create users
        print("\n1️⃣  Creating users...")
        bob = User(
            id=uuid.uuid4(),
            name="Bob Smith",
            email="bob@example.com",
            timezone="America/New_York"
        )
        alice = User(
            id=uuid.uuid4(),
            name="Alice Chen",
            email="alice@example.com",
            timezone="America/Los_Angeles"
        )
        db.add(bob)
        db.add(alice)
        db.commit()
        print(f"   ✅ Bob: {bob.id}")
        print(f"   ✅ Alice: {alice.id}")
        
        # Note: Alignments are now handled via TaskRelevantUser
        # They will be created after tasks via populate_relevant_users
        print("\n2️⃣  Skipping legacy alignments (using TaskRelevantUser instead)...")
        
        # Create Bob's tasks with relationships
        print("\n3️⃣  Creating Bob's tasks...")
        
        # Parent task 1
        auth_system = Task(
            id=uuid.uuid4(),
            title="Build Authentication System",
            description="Complete OAuth2 implementation",
            owner_user_id=bob.id
        )
        db.add(auth_system)
        db.flush()
        
        # Children of auth system
        oauth_task = Task(
            id=uuid.uuid4(),
            title="Implement OAuth2 provider",
            description="Google and GitHub OAuth",
            owner_user_id=bob.id,
            parent_id=auth_system.id  # Set parent
        )
        
        jwt_task = Task(
            id=uuid.uuid4(),
            title="JWT token management",
            description="Token generation and validation",
            owner_user_id=bob.id,
            parent_id=auth_system.id  # Set parent
        )
        db.add(oauth_task)
        db.add(jwt_task)
        
        # Parent task 2
        cicd = Task(
            id=uuid.uuid4(),
            title="Setup CI/CD Pipeline",
            description="Automated deployment",
            owner_user_id=bob.id
        )
        db.add(cicd)
        db.flush()
        
        # Child of CI/CD
        github_actions = Task(
            id=uuid.uuid4(),
            title="Configure GitHub Actions",
            description="Setup automated testing",
            owner_user_id=bob.id,
            parent_id=cicd.id  # Set parent
        )
        db.add(github_actions)
        
        db.commit()
        bob_tasks = [auth_system, oauth_task, jwt_task, cicd, github_actions]
        print(f"   ✅ Created {len(bob_tasks)} tasks for Bob")
        
        # Create Alice's tasks
        print("\n4️⃣  Creating Alice's tasks...")
        
        # Parent task
        dashboard = Task(
            id=uuid.uuid4(),
            title="Design Analytics Dashboard",
            description="User analytics UI",
            owner_user_id=alice.id
        )
        db.add(dashboard)
        db.flush()
        
        # Children
        charts = Task(
            id=uuid.uuid4(),
            title="Implement data charts",
            description="Charts and graphs",
            owner_user_id=alice.id,
            parent_id=dashboard.id  # Set parent
        )
        
        filters = Task(
            id=uuid.uuid4(),
            title="Add filter controls",
            description="Date range and filters",
            owner_user_id=alice.id,
            parent_id=dashboard.id  # Set parent
        )
        
        # Independent tasks
        mobile = Task(
            id=uuid.uuid4(),
            title="Mobile App Redesign",
            description="Complete UI/UX overhaul",
            owner_user_id=alice.id
        )
        
        api_docs = Task(
            id=uuid.uuid4(),
            title="API Documentation",
            description="REST API docs",
            owner_user_id=alice.id
        )
        
        db.add_all([charts, filters, mobile, api_docs])
        db.commit()
        alice_tasks = [dashboard, charts, filters, mobile, api_docs]
        print(f"   ✅ Created {len(alice_tasks)} tasks for Alice")
        
        # Add dependencies
        print("\n5️⃣  Adding dependencies...")
        from app.models import TaskDependency
        
        # API docs depends on auth system
        dep1 = TaskDependency(
            task_id=api_docs.id,
            depends_on_task_id=auth_system.id
        )
        db.add(dep1)
        db.commit()
        print("   ✅ API Documentation → depends on → Auth System")
        
        # Get all tasks
        all_tasks = bob_tasks + alice_tasks
        
        # Get all attributes
        print("\n6️⃣  Getting attributes...")
        attributes = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == EntityType.TASK
        ).all()
        print(f"   ✅ Found {len(attributes)} attributes")
        
        # Fill ALL attributes for ALL tasks from BOTH perspectives
        print("\n7️⃣  Filling attribute answers...")
        
        answer_count = 0
        for user, user_name in [(bob, "Bob"), (alice, "Alice")]:
            print(f"\n   Filling for {user_name}...")
            
            for task in all_tasks:
                for attr in attributes:
                    # Get random value
                    attr_name = attr.name
                    
                    if attr_name in ANSWER_VALUES:
                        value = random.choice(ANSWER_VALUES[attr_name])
                    elif attr.type.value == 'enum' and attr.allowed_values:
                        value = random.choice(attr.allowed_values)
                    elif attr.type.value == 'bool':
                        value = random.choice(["true", "false"])
                    elif attr.type.value in ['int', 'float']:
                        value = str(random.randint(1, 5))
                    else:
                        value = f"Value for {attr_name}"
                    
                    # Create answer
                    answer = AttributeAnswer(
                        id=uuid.uuid4(),
                        answered_by_user_id=user.id,
                        target_user_id=task.owner_user_id,
                        task_id=task.id,
                        attribute_id=attr.id,
                        value=value,
                        refused=False,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(answer)
                    answer_count += 1
            
            db.commit()
            print(f"   ✅ Created answers for {user_name}")
        
        print(f"\n   📊 Total answers created: {answer_count}")
        
        # Verify data
        print("\n8️⃣  Verifying data...")
        total_tasks = db.query(Task).count()
        total_answers = db.query(AttributeAnswer).count()
        tasks_with_parents = db.query(Task).filter(Task.parent_id.isnot(None)).count()
        
        print(f"   ✅ Tasks: {total_tasks}")
        print(f"   ✅ Answers: {total_answers}")
        print(f"   ✅ Tasks with parents: {tasks_with_parents}")
        
        # Summary
        print("\n" + "="*70)
        print("✅ FRESH DEBUG DATA CREATED!")
        print("="*70)
        print(f"\n📊 Summary:")
        print(f"   • 2 users (Bob & Alice)")
        print(f"   • {total_tasks} tasks total")
        print(f"   • {tasks_with_parents} tasks with parent relationships")
        print(f"   • {total_answers} attribute answers")
        print(f"   • {len(attributes)} attributes × {total_tasks} tasks × 2 users")
        print(f"\n🎮 Test it:")
        print(f"   http://localhost:8000/ → Dashboard → Task Graph")
        print(f"\n✨ What to check:")
        print(f"   • Click ANY task → See BOTH Bob and Alice answers")
        print(f"   • All {len(attributes)} attributes should show")
        print(f"   • Parent-child relationships visible")
        print(f"   • Dependencies shown as red dashed lines")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_debug_data()

