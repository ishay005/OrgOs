#!/usr/bin/env python3
"""
Populate comprehensive test data with:
- At least 3 tasks per user
- Parent/child relationships
- Dependencies
- Controlled misalignment percentage
"""
import sys
import random
from app.database import SessionLocal
from app.models import (
    User, Task, AlignmentEdge, AttributeDefinition,
    AttributeAnswer, TaskDependency, EntityType
)

# Misalignment configuration
MISALIGNMENT_RATE = 0.3  # 30% of attributes will be misaligned

def clear_all_data(db):
    """Clear all data from database"""
    print("🗑️  Clearing all data...")
    from app.models import SimilarityScore, QuestionLog
    
    # Delete in correct order (respecting foreign keys)
    db.query(SimilarityScore).delete()  # Delete similarity scores first!
    db.query(AttributeAnswer).delete()
    db.query(QuestionLog).delete()  # Delete question logs
    db.query(TaskDependency).delete()
    db.query(Task).delete()
    db.query(AlignmentEdge).delete()
    db.query(User).delete()  # Delete users too for clean start
    # Don't delete attribute definitions
    db.commit()
    print("✅ Data cleared")


def create_org_structure(db):
    """Create organizational hierarchy"""
    print("\n👥 Creating organizational structure...")
    
    # Create VP of Engineering
    vp = User(name="Sarah Feldman", email="sarah@company.com", manager_id=None)
    db.add(vp)
    db.flush()
    
    # Create Team Leads reporting to VP
    dana = User(name="Dana Cohen", email="dana@company.com", manager_id=vp.id)
    amir = User(name="Amir Levi", email="amir@company.com", manager_id=vp.id)
    db.add_all([dana, amir])
    db.flush()
    
    # Platform Team (reports to Dana)
    yael = User(name="Yael Shapira", email="yael@company.com", manager_id=dana.id)
    omer = User(name="Omer Ben-David", email="omer@company.com", manager_id=dana.id)
    noa = User(name="Noa Mizrahi", email="noa@company.com", manager_id=dana.id)
    
    # Product Team (reports to Amir)
    eitan = User(name="Eitan Goldberg", email="eitan@company.com", manager_id=amir.id)
    michal = User(name="Michal Avraham", email="michal@company.com", manager_id=amir.id)
    roi = User(name="Roi Weiss", email="roi@company.com", manager_id=amir.id)
    
    db.add_all([yael, omer, noa, eitan, michal, roi])
    db.commit()
    
    users = {
        "vp": vp, "dana": dana, "amir": amir,
        "yael": yael, "omer": omer, "noa": noa,
        "eitan": eitan, "michal": michal, "roi": roi
    }
    
    print(f"✅ Created {len(users)} users")
    return users


def create_alignment_edges(db, users):
    """Create alignment edges (who aligns with whom)"""
    print("\n🔗 Creating alignment edges...")
    
    # VP aligns with everyone
    for key in ["dana", "amir", "yael", "omer", "noa", "eitan", "michal", "roi"]:
        db.add(AlignmentEdge(source_user_id=users["vp"].id, target_user_id=users[key].id))
    
    # Team leads align with their teams and each other
    for lead_key in ["dana", "amir"]:
        for other_key in users.keys():
            if other_key not in ["vp", lead_key]:
                db.add(AlignmentEdge(source_user_id=users[lead_key].id, target_user_id=users[other_key].id))
    
    # ICs align with their manager and teammates
    platform_team = ["yael", "omer", "noa"]
    for member in platform_team:
        db.add(AlignmentEdge(source_user_id=users[member].id, target_user_id=users["dana"].id))
        for teammate in platform_team:
            if teammate != member:
                db.add(AlignmentEdge(source_user_id=users[member].id, target_user_id=users[teammate].id))
    
    product_team = ["eitan", "michal", "roi"]
    for member in product_team:
        db.add(AlignmentEdge(source_user_id=users[member].id, target_user_id=users["amir"].id))
        for teammate in product_team:
            if teammate != member:
                db.add(AlignmentEdge(source_user_id=users[member].id, target_user_id=users[teammate].id))
    
    db.commit()
    print("✅ Alignment edges created")


def create_tasks_with_relationships(db, users):
    """Create tasks with parent/child and dependency relationships"""
    print("\n📋 Creating tasks with relationships...")
    
    tasks_list = []
    
    # VP Tasks (3 tasks)
    vp_tasks = [
        Task(title="Q1 Engineering Strategy", description="Define roadmap", owner_user_id=users["vp"].id),
        Task(title="Scale engineering hiring", description="Hire 10 engineers", owner_user_id=users["vp"].id),
        Task(title="Platform modernization initiative", description="Upgrade core infrastructure", owner_user_id=users["vp"].id),
    ]
    for t in vp_tasks:
        db.add(t)
    db.flush()
    tasks_list.extend(vp_tasks)
    
    # Dana (Platform Team Lead) - 3 tasks
    dana_tasks = [
        Task(title="Migrate auth service", description="Move to microservices", owner_user_id=users["dana"].id, parent_id=vp_tasks[2].id),
        Task(title="Database upgrade project", description="Upgrade to PostgreSQL 15", owner_user_id=users["dana"].id),
        Task(title="API performance optimization", description="Reduce latency", owner_user_id=users["dana"].id),
    ]
    for t in dana_tasks:
        db.add(t)
    db.flush()
    tasks_list.extend(dana_tasks)
    
    # Amir (Product Team Lead) - 3 tasks
    amir_tasks = [
        Task(title="New onboarding flow", description="Redesign user onboarding", owner_user_id=users["amir"].id),
        Task(title="Mobile app refresh", description="Update mobile UI", owner_user_id=users["amir"].id),
        Task(title="Analytics dashboard v2", description="Build new analytics", owner_user_id=users["amir"].id),
    ]
    for t in amir_tasks:
        db.add(t)
    db.flush()
    tasks_list.extend(amir_tasks)
    
    # Platform Team ICs - 3 tasks each
    yael_tasks = [
        Task(title="Design OAuth 2.0 flow", description="Create auth spec", owner_user_id=users["yael"].id, parent_id=dana_tasks[0].id),
        Task(title="API gateway design", description="Design API gateway", owner_user_id=users["yael"].id),
        Task(title="Monitoring dashboard", description="Build observability", owner_user_id=users["yael"].id),
    ]
    
    omer_tasks = [
        Task(title="Implement OAuth provider", description="Build OAuth server", owner_user_id=users["omer"].id, parent_id=dana_tasks[0].id),
        Task(title="Rate limiting service", description="Add rate limits", owner_user_id=users["omer"].id),
        Task(title="Caching layer optimization", description="Optimize Redis", owner_user_id=users["omer"].id),
    ]
    
    noa_tasks = [
        Task(title="Database migration script", description="Migrate to PG15", owner_user_id=users["noa"].id, parent_id=dana_tasks[1].id),
        Task(title="Backup automation", description="Automate backups", owner_user_id=users["noa"].id),
        Task(title="Query optimization", description="Optimize slow queries", owner_user_id=users["noa"].id),
    ]
    
    for t in yael_tasks + omer_tasks + noa_tasks:
        db.add(t)
    db.flush()
    tasks_list.extend(yael_tasks + omer_tasks + noa_tasks)
    
    # Product Team ICs - 3 tasks each
    eitan_tasks = [
        Task(title="Onboarding wizard UI", description="Build wizard", owner_user_id=users["eitan"].id, parent_id=amir_tasks[0].id),
        Task(title="User profile redesign", description="New profile page", owner_user_id=users["eitan"].id),
        Task(title="Dark mode support", description="Add dark theme", owner_user_id=users["eitan"].id),
    ]
    
    michal_tasks = [
        Task(title="Analytics charts library", description="Build chart components", owner_user_id=users["michal"].id, parent_id=amir_tasks[2].id),
        Task(title="Export functionality", description="Add CSV/PDF export", owner_user_id=users["michal"].id),
        Task(title="Real-time updates", description="WebSocket integration", owner_user_id=users["michal"].id),
    ]
    
    roi_tasks = [
        Task(title="Mobile onboarding screens", description="iOS/Android screens", owner_user_id=users["roi"].id, parent_id=amir_tasks[0].id),
        Task(title="Push notifications", description="Implement notifications", owner_user_id=users["roi"].id),
        Task(title="Offline mode", description="Add offline support", owner_user_id=users["roi"].id),
    ]
    
    for t in eitan_tasks + michal_tasks + roi_tasks:
        db.add(t)
    db.flush()
    tasks_list.extend(eitan_tasks + michal_tasks + roi_tasks)
    
    # Add some dependencies
    db.add(TaskDependency(task_id=omer_tasks[0].id, depends_on_task_id=yael_tasks[0].id))  # OAuth impl depends on design
    db.add(TaskDependency(task_id=eitan_tasks[0].id, depends_on_task_id=yael_tasks[0].id))  # Onboarding depends on auth
    db.add(TaskDependency(task_id=michal_tasks[0].id, depends_on_task_id=noa_tasks[2].id))  # Analytics depends on query optimization
    
    db.commit()
    
    print(f"✅ Created {len(tasks_list)} tasks total")
    print(f"   • VP: 3 tasks")
    print(f"   • Team Leads: 3 each (6 total)")
    print(f"   • ICs: 3 each (18 total)")
    
    return {"all": tasks_list, "yael": yael_tasks, "omer": omer_tasks, "noa": noa_tasks,
            "eitan": eitan_tasks, "michal": michal_tasks, "roi": roi_tasks,
            "dana": dana_tasks, "amir": amir_tasks, "vp": vp_tasks}


def create_attribute_answers(db, users, tasks):
    """Create attribute answers with controlled misalignment"""
    print("\n✍️  Creating attribute answers...")
    
    # Get all task attributes
    attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    attr_by_name = {attr.name: attr for attr in attributes}
    
    # Answer choices
    choices = {
        "priority": ["Critical", "High", "Medium", "Low"],
        "status": ["Not started", "In progress", "Blocked", "Done"],
        "value_type": ["Customer revenue", "Risk reduction", "Efficiency", "Learning"],
        "is_blocked": ["false", "true"],
        "impact_size": ["1", "2", "3", "4", "5"],
        "direction_confidence": ["1", "2", "3", "4", "5"],
    }
    
    answer_count = 0
    
    # For each task
    for task in tasks["all"]:
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        manager = db.query(User).filter(User.id == owner.manager_id).first() if owner.manager_id else None
        
        # Owner answers about their own task
        owner_answers = {}
        for attr in attributes:
            value = generate_answer_value(attr, choices, task, owner)
            answer = AttributeAnswer(
                answered_by_user_id=owner.id,
                target_user_id=owner.id,
                task_id=task.id,
                attribute_id=attr.id,
                value=value,
                refused=False
            )
            db.add(answer)
            owner_answers[attr.name] = value
            answer_count += 1
        
        # Manager answers about employee's task (with controlled misalignment)
        if manager:
            for attr in attributes:
                # Decide if this should be misaligned
                should_misalign = random.random() < MISALIGNMENT_RATE
                
                if should_misalign:
                    # Generate different value
                    value = generate_different_value(attr, choices, owner_answers[attr.name], task, manager)
                else:
                    # Use same value as owner
                    value = owner_answers[attr.name]
                
                answer = AttributeAnswer(
                    answered_by_user_id=manager.id,
                    target_user_id=owner.id,
                    task_id=task.id,
                    attribute_id=attr.id,
                    value=value,
                    refused=False
                )
                db.add(answer)
                answer_count += 1
    
    db.commit()
    print(f"✅ Created {answer_count} attribute answers")
    print(f"   • With ~{int(MISALIGNMENT_RATE * 100)}% misalignment rate")


def generate_answer_value(attr, choices, task, user):
    """Generate an answer value for an attribute"""
    if attr.name in choices:
        return random.choice(choices[attr.name])
    elif attr.name == "main_goal":
        goals = [
            f"Build {task.title} to improve system quality",
            f"Deliver {task.title} for better user experience",
            f"Complete {task.title} to reduce technical debt",
            f"Implement {task.title} for scalability",
        ]
        return random.choice(goals)
    elif attr.name == "perceived_owner":
        return user.name
    elif attr.name == "blocking_reason":
        reasons = ["None", "Waiting on review", "Dependency not ready", "Resource constraint"]
        return random.choice(reasons)
    elif attr.name == "perceived_dependencies":
        # Use actual task titles for dependencies
        return ""  # Empty for simplicity
    else:
        return "Test value"


def generate_different_value(attr, choices, original_value, task, user):
    """Generate a DIFFERENT value (for misalignment)"""
    if attr.name in choices:
        # Pick a different value from choices
        options = [v for v in choices[attr.name] if v != original_value]
        return random.choice(options) if options else original_value
    elif attr.name == "main_goal":
        # Generate slightly different goal
        alternatives = [
            f"Complete {task.title} for team efficiency",
            f"Deliver {task.title} to meet deadlines",
            f"Execute {task.title} for business value",
        ]
        return random.choice(alternatives)
    elif attr.name == "perceived_owner":
        # Different person
        return user.name if user.name != original_value else "Team"
    elif attr.name == "blocking_reason":
        reasons = ["Technical blocker", "Waiting for approval", "Dependencies not met"]
        return random.choice(reasons)
    else:
        return f"Different: {original_value}"


def main():
    """Main population function"""
    print("\n" + "="*70)
    print("🚀 POPULATING COMPREHENSIVE TEST DATA")
    print("="*70)
    
    db = SessionLocal()
    
    try:
        # Step 1: Clear existing data
        clear_all_data(db)
        
        # Step 2: Create org structure
        users = create_org_structure(db)
        
        # Step 3: Create alignment edges
        create_alignment_edges(db, users)
        
        # Step 4: Create tasks with relationships
        tasks = create_tasks_with_relationships(db, users)
        
        # Step 5: Create attribute answers
        create_attribute_answers(db, users, tasks)
        
        # Summary
        print("\n" + "="*70)
        print("✅ DATA POPULATION COMPLETE!")
        print("="*70)
        print(f"\n📊 Summary:")
        print(f"   • {len(users)} users")
        print(f"   • {len(tasks['all'])} tasks (3 per user)")
        print(f"   • Parent/child relationships")
        print(f"   • Task dependencies")
        print(f"   • ~{int(MISALIGNMENT_RATE * 100)}% misalignment rate")
        print(f"\n🎯 Next Step:")
        print(f"   Run: python3 populate_similarity_scores.py")
        print(f"   To calculate similarity scores for all answers")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()

