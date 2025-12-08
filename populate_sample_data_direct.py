#!/usr/bin/env python3
"""
Populate OrgOs database with realistic sample data - Direct DB insertion version.

This script creates:
- 2 teams with team leads and members
- Alignment networks
- Tasks with parent/child relationships and dependencies
- Attribute answers directly in DB
- Misalignment examples for testing
"""
import sys
sys.path.insert(0, '/Users/ishaylevi/work/OrgOs')

import requests
import time
from typing import Dict, List
from datetime import datetime
import uuid

from app.database import SessionLocal
from app.models import (
    User, Task, AlignmentEdge, AttributeDefinition,
    AttributeAnswer, TaskDependency
)

# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "http://localhost:8000"
CLEAR_DB_FIRST = True

# ============================================================================
# Helper Functions
# ============================================================================

def api_request(method: str, endpoint: str, data: dict = None, user_id: str = None) -> dict:
    """Make an API request"""
    url = f"{BASE_URL}{endpoint}"
    headers = {}
    if user_id:
        headers["X-User-Id"] = user_id
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, json=data, headers=headers)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    if response.status_code not in [200, 201]:
        print(f"❌ Error: {method} {endpoint} returned {response.status_code}")
        return None
    
    return response.json()


def clear_database():
    """Clear all existing data"""
    print("🗑️  Clearing existing data...")
    import subprocess
    result = subprocess.run(
        ["python3", "clear_all_data.py"],
        input="yes\n",
        text=True,
        capture_output=True,
        cwd="/Users/ishaylevi/work/OrgOs"
    )
    if result.returncode == 0:
        print("✅ Database cleared")


def create_users() -> Dict[str, dict]:
    """Create users via API"""
    print("\n👥 Creating users...")
    
    users = {}
    
    # Top Level: VP of Engineering (Team Manager)
    print("  Creating VP of Engineering...")
    sarah = api_request("POST", "/users", {
        "name": "Sarah Feldman",
        "email": "sarah@company.com",
        "timezone": "Asia/Jerusalem"
    })
    users["sarah"] = sarah
    print(f"    ✅ Sarah Feldman (VP Engineering)")
    
    # Team 1: Platform Team
    print("  Creating Platform Team...")
    dana = api_request("POST", "/users", {
        "name": "Dana Cohen",
        "email": "dana@company.com",
        "timezone": "Asia/Jerusalem",
        "manager_id": sarah["id"]
    })
    users["dana"] = dana
    print(f"    ✅ Dana Cohen (Team Lead, reports to Sarah)")
    
    platform_members = [
        ("Yael Shapira", "yael@company.com"),
        ("Omer Ben-David", "omer@company.com"),
        ("Noa Mizrahi", "noa@company.com"),
        ("Eitan Goldberg", "eitan@company.com"),
        ("Michal Avraham", "michal@company.com"),
    ]
    
    users["platform_team"] = []
    for name, email in platform_members:
        user = api_request("POST", "/users", {
            "name": name,
            "email": email,
            "timezone": "Asia/Jerusalem",
            "manager_id": dana["id"]
        })
        users["platform_team"].append(user)
        users[name.split()[0].lower()] = user
        print(f"    ✅ {name}")
    
    # Team 2: Product Team  
    print("  Creating Product Team...")
    amir = api_request("POST", "/users", {
        "name": "Amir Levi",
        "email": "amir@company.com",
        "timezone": "Asia/Jerusalem",
        "manager_id": sarah["id"]
    })
    users["amir"] = amir
    print(f"    ✅ Amir Levi (Team Lead, reports to Sarah)")
    
    product_members = [
        ("Tamar Katz", "tamar@company.com"),
        ("Roi Weiss", "roi@company.com"),
        ("Shira Friedman", "shira@company.com"),
        ("Asaf Peretz", "asaf@company.com"),
        ("Liora Stein", "liora@company.com"),
    ]
    
    users["product_team"] = []
    for name, email in product_members:
        user = api_request("POST", "/users", {
            "name": name,
            "email": email,
            "timezone": "Asia/Jerusalem",
            "manager_id": amir["id"]
        })
        users["product_team"].append(user)
        users[name.split()[0].lower()] = user
        print(f"    ✅ {name}")
    
    # Chief of Staff (reports to Sarah)
    print("  Creating additional executive...")
    maya = api_request("POST", "/users", {
        "name": "Maya Rosenberg",
        "email": "maya@company.com",
        "timezone": "Asia/Jerusalem",
        "manager_id": sarah["id"]
    })
    users["maya"] = maya
    print(f"    ✅ Maya Rosenberg (Chief of Staff, reports to Sarah)")
    
    print(f"✅ Created 14 users (1 VP, 2 team leads, 10 ICs, 1 Chief of Staff)")
    return users


def create_alignments(users: Dict[str, dict]):
    """Create alignment network via API"""
    print("\n🤝 Creating alignment network...")
    
    sarah_id = users["sarah"]["id"]
    dana_id = users["dana"]["id"]
    amir_id = users["amir"]["id"]
    maya_id = users["maya"]["id"]
    
    # Sarah (VP) aligns with direct reports (Dana, Amir, Maya)
    for user in [users["dana"], users["amir"], users["maya"]]:
        api_request("POST", "/alignments", {"target_user_id": user["id"], "align": True}, user_id=sarah_id)
        api_request("POST", "/alignments", {"target_user_id": sarah_id, "align": True}, user_id=user["id"])
    print(f"  ✅ VP level: Sarah ↔ Dana, Amir, Maya")
    
    # Platform team
    for member in users["platform_team"]:
        api_request("POST", "/alignments", {"target_user_id": member["id"], "align": True}, user_id=dana_id)
        api_request("POST", "/alignments", {"target_user_id": dana_id, "align": True}, user_id=member["id"])
    print(f"  ✅ Platform Team: Dana ↔ 5 members")
    
    # Product team
    for member in users["product_team"]:
        api_request("POST", "/alignments", {"target_user_id": member["id"], "align": True}, user_id=amir_id)
        api_request("POST", "/alignments", {"target_user_id": amir_id, "align": True}, user_id=member["id"])
    print(f"  ✅ Product Team: Amir ↔ 5 members")
    
    # Cross-team at lead level
    api_request("POST", "/alignments", {"target_user_id": amir_id, "align": True}, user_id=dana_id)
    api_request("POST", "/alignments", {"target_user_id": dana_id, "align": True}, user_id=amir_id)
    print(f"  ✅ Cross-team: Dana ↔ Amir")
    
    print(f"  ✅ Created alignment network")


def create_tasks(users: Dict[str, dict]) -> Dict[str, dict]:
    """Create tasks via API"""
    print("\n📝 Creating tasks...")
    
    tasks = {}
    
    # VP Level Tasks
    print("  Creating VP level tasks...")
    strategy_task = api_request("POST", "/tasks", {
        "title": "Q1 Engineering Strategy",
        "description": "Define technical roadmap and priorities for Q1"
    }, user_id=users["sarah"]["id"])
    tasks["strategy_task"] = strategy_task
    
    hiring_task = api_request("POST", "/tasks", {
        "title": "Scale engineering hiring",
        "description": "Hire 5 senior engineers across teams"
    }, user_id=users["sarah"]["id"])
    tasks["hiring_task"] = hiring_task
    
    # Chief of Staff Tasks
    process_task = api_request("POST", "/tasks", {
        "title": "Improve cross-team collaboration",
        "description": "Implement weekly sync process between Platform and Product"
    }, user_id=users["maya"]["id"])
    tasks["process_task"] = process_task
    
    # Platform Team
    print("  Creating Platform Team tasks...")
    auth_epic = api_request("POST", "/tasks", {"title": "Migrate auth service to new stack", "description": "Move authentication to microservices"}, user_id=users["dana"]["id"])
    tasks["auth_epic"] = auth_epic
    
    auth_design = api_request("POST", "/tasks", {"title": "Design new authentication flow", "description": "Create OAuth 2.0 spec", "parent_id": auth_epic["id"]}, user_id=users["yael"]["id"])
    tasks["auth_design"] = auth_design
    
    auth_impl = api_request("POST", "/tasks", {"title": "Implement OAuth 2.0 provider", "description": "Build OAuth server", "parent_id": auth_epic["id"], "dependencies": [auth_design["id"]]}, user_id=users["omer"]["id"])
    tasks["auth_impl"] = auth_impl
    
    auth_migration = api_request("POST", "/tasks", {"title": "Migrate existing users to new auth", "description": "Data migration script", "parent_id": auth_epic["id"], "dependencies": [auth_impl["id"]]}, user_id=users["noa"]["id"])
    tasks["auth_migration"] = auth_migration
    
    logging_epic = api_request("POST", "/tasks", {"title": "Refactor logging pipeline", "description": "Structured logging upgrade"}, user_id=users["dana"]["id"])
    tasks["logging_epic"] = logging_epic
    
    logging_analysis = api_request("POST", "/tasks", {"title": "Analyze current logging patterns", "description": "Audit existing logs", "parent_id": logging_epic["id"]}, user_id=users["eitan"]["id"])
    tasks["logging_analysis"] = logging_analysis
    
    logging_impl = api_request("POST", "/tasks", {"title": "Implement structured logging library", "description": "JSON-based logging wrapper", "parent_id": logging_epic["id"], "dependencies": [logging_analysis["id"]]}, user_id=users["michal"]["id"])
    tasks["logging_impl"] = logging_impl
    
    # Product Team
    onboarding_epic = api_request("POST", "/tasks", {"title": "Implement new onboarding flow", "description": "Interactive tutorial redesign"}, user_id=users["amir"]["id"])
    tasks["onboarding_epic"] = onboarding_epic
    
    onboarding_design = api_request("POST", "/tasks", {"title": "Design onboarding UX", "description": "Create wireframes", "parent_id": onboarding_epic["id"]}, user_id=users["tamar"]["id"])
    tasks["onboarding_design"] = onboarding_design
    
    onboarding_frontend = api_request("POST", "/tasks", {"title": "Build onboarding UI components", "description": "React components", "parent_id": onboarding_epic["id"], "dependencies": [onboarding_design["id"], auth_impl["id"]]}, user_id=users["roi"]["id"])
    tasks["onboarding_frontend"] = onboarding_frontend
    
    onboarding_analytics = api_request("POST", "/tasks", {"title": "Add onboarding analytics", "description": "Track user progress", "parent_id": onboarding_epic["id"], "dependencies": [onboarding_frontend["id"], logging_impl["id"]]}, user_id=users["shira"]["id"])
    tasks["onboarding_analytics"] = onboarding_analytics
    
    dashboard_epic = api_request("POST", "/tasks", {"title": "Redesign main dashboard", "description": "Real-time metrics dashboard"}, user_id=users["amir"]["id"])
    tasks["dashboard_epic"] = dashboard_epic
    
    dashboard_api = api_request("POST", "/tasks", {"title": "Build dashboard API endpoints", "description": "REST APIs for metrics", "parent_id": dashboard_epic["id"]}, user_id=users["asaf"]["id"])
    tasks["dashboard_api"] = dashboard_api
    
    dashboard_ui = api_request("POST", "/tasks", {"title": "Implement dashboard UI", "description": "Charts and widgets", "parent_id": dashboard_epic["id"], "dependencies": [dashboard_api["id"]]}, user_id=users["liora"]["id"])
    tasks["dashboard_ui"] = dashboard_ui
    
    print(f"✅ Created 17 tasks (3 VP level, 14 team level)")
    return tasks


def create_attribute_answers_direct(users: Dict[str, dict], tasks: Dict[str, dict]):
    """Create attribute answers directly in database - from both owner and team lead POV"""
    print("\n💭 Creating attribute answers (direct DB)...")
    print("   Creating answers from owner POV and team lead POV...")
    print("   80% aligned, 20% misaligned...")
    
    db = SessionLocal()
    try:
        import random
        random.seed(42)  # For reproducible results
        
        # Get attribute IDs
        status_attr = db.query(AttributeDefinition).filter(AttributeDefinition.name == "status").first()
        owner_attr = db.query(AttributeDefinition).filter(AttributeDefinition.name == "perceived_owner").first()
        goal_attr = db.query(AttributeDefinition).filter(AttributeDefinition.name == "main_goal").first()
        dependency_attr = db.query(AttributeDefinition).filter(AttributeDefinition.name == "perceived_dependencies").first()
        
        if not all([status_attr, owner_attr, goal_attr]):
            print("❌ Required attributes not found")
            return
        
        # Task configs: (task_key, owner_key, status, goal)
        configs = [
            # VP level tasks
            ("strategy_task", "sarah", "In progress", "Define comprehensive technical roadmap and set strategic priorities for Q1 engineering initiatives."),
            ("hiring_task", "sarah", "In progress", "Scale our engineering organization by hiring 5 senior engineers to support growth."),
            # Chief of Staff task
            ("process_task", "maya", "In progress", "Establish effective cross-team collaboration processes to improve communication and delivery."),
            # Platform team
            ("auth_epic", "dana", "In progress", "Move our authentication system to modern microservices for better security and scalability."),
            ("auth_design", "yael", "Done", "Create comprehensive OAuth 2.0 technical documentation with security best practices."),
            ("auth_impl", "omer", "In progress", "Build robust OAuth 2.0 provider handling token generation, validation, and refresh."),
            ("auth_migration", "noa", "Not started", "Safely migrate all existing user accounts to new authentication without data loss."),
            ("logging_epic", "dana", "In progress", "Upgrade logging infrastructure to structured logging for better observability."),
            ("logging_analysis", "eitan", "Done", "Review current logging practices and identify observability gaps."),
            ("logging_impl", "michal", "In progress", "Create reusable logging library outputting JSON-formatted structured logs."),
            # Product team
            ("onboarding_epic", "amir", "In progress", "Redesign user onboarding to reduce time-to-value and increase activation rates."),
            ("onboarding_design", "tamar", "Done", "Design intuitive onboarding flow with interactive elements guiding users."),
            ("onboarding_frontend", "roi", "Blocked", "Implement frontend components for new onboarding using React and TypeScript."),
            ("onboarding_analytics", "shira", "Not started", "Instrument onboarding with analytics to track progress and identify drop-offs."),
            ("dashboard_epic", "amir", "In progress", "Create modern real-time dashboard giving users actionable insights."),
            ("dashboard_api", "asaf", "In progress", "Build backend APIs aggregating and serving dashboard data efficiently."),
            ("dashboard_ui", "liora", "Not started", "Develop beautiful responsive dashboard with interactive charts and widgets."),
        ]
        
        # Alternative status/goal for misalignments
        status_alternatives = {
            "In progress": "Blocked",
            "Done": "In progress",
            "Blocked": "In progress",
            "Not started": "In progress"
        }
        
        goal_variations = {
            # VP level
            "Define comprehensive technical roadmap and set strategic priorities for Q1 engineering initiatives.": 
                "Set Q1 technical priorities and roadmap.",
            "Scale our engineering organization by hiring 5 senior engineers to support growth.": 
                "Hire senior engineers for team growth.",
            "Establish effective cross-team collaboration processes to improve communication and delivery.": 
                "Improve cross-team collaboration and communication.",
            # Platform team
            "Move our authentication system to modern microservices for better security and scalability.": 
                "Migrate authentication to microservices architecture.",
            "Create comprehensive OAuth 2.0 technical documentation with security best practices.": 
                "Document OAuth 2.0 implementation.",
            "Build robust OAuth 2.0 provider handling token generation, validation, and refresh.": 
                "Implement OAuth provider with token management.",
            "Safely migrate all existing user accounts to new authentication without data loss.": 
                "Migrate user accounts to new auth system.",
            "Upgrade logging infrastructure to structured logging for better observability.": 
                "Improve logging system with structured logs.",
            "Review current logging practices and identify observability gaps.": 
                "Analyze current logging setup.",
            "Create reusable logging library outputting JSON-formatted structured logs.": 
                "Build logging library for JSON logs.",
            # Product team
            "Redesign user onboarding to reduce time-to-value and increase activation rates.": 
                "Improve onboarding flow for users.",
            "Design intuitive onboarding flow with interactive elements guiding users.": 
                "Create onboarding UX design.",
            "Implement frontend components for new onboarding using React and TypeScript.": 
                "Build React components for onboarding.",
            "Instrument onboarding with analytics to track progress and identify drop-offs.": 
                "Add analytics to onboarding flow.",
            "Create modern real-time dashboard giving users actionable insights.": 
                "Build new dashboard with metrics.",
            "Build backend APIs aggregating and serving dashboard data efficiently.": 
                "Create dashboard backend APIs.",
            "Develop beautiful responsive dashboard with interactive charts and widgets.": 
                "Implement dashboard frontend UI.",
        }
        
        answer_count = 0
        aligned_count = 0
        misaligned_count = 0
        
        for idx, (task_key, owner_key, status, goal) in enumerate(configs):
            task = tasks.get(task_key)
            owner = users.get(owner_key)
            
            if not task or not owner:
                continue
            
            # Get actual task and user objects from DB
            db_task = db.query(Task).filter(Task.id == task["id"]).first()
            db_owner = db.query(User).filter(User.id == owner["id"]).first()
            
            if not db_task or not db_owner:
                continue
            
            # Create owner's self-answers
            status_answer = AttributeAnswer(
                answered_by_user_id=db_owner.id,
                target_user_id=db_owner.id,
                task_id=db_task.id,
                attribute_id=status_attr.id,
                value=status,
                refused=False
            )
            db.add(status_answer)
            
            owner_answer = AttributeAnswer(
                answered_by_user_id=db_owner.id,
                target_user_id=db_owner.id,
                task_id=db_task.id,
                attribute_id=owner_attr.id,
                value=owner["name"],
                refused=False
            )
            db.add(owner_answer)
            
            goal_answer = AttributeAnswer(
                answered_by_user_id=db_owner.id,
                target_user_id=db_owner.id,
                task_id=db_task.id,
                attribute_id=goal_attr.id,
                value=goal,
                refused=False
            )
            db.add(goal_answer)
            
            # Dependency answer (if task has dependencies)
            if dependency_attr and hasattr(db_task, 'dependencies') and db_task.dependencies:
                # Get dependency task titles
                dep_titles = [t.title for t in db_task.dependencies]
                dep_value = ", ".join(dep_titles) if dep_titles else "None"
                
                dep_answer = AttributeAnswer(
                    answered_by_user_id=db_owner.id,
                    target_user_id=db_owner.id,
                    task_id=db_task.id,
                    attribute_id=dependency_attr.id,
                    value=dep_value,
                    refused=False
                )
                db.add(dep_answer)
                answer_count += 1
            
            answer_count += 3
            
            # Find manager (team lead)
            manager_id = owner.get("manager_id")
            if manager_id:
                # Get manager from DB
                db_manager = db.query(User).filter(User.id == manager_id).first()
                
                if db_manager:
                    # Determine misalignment level for this task
                    # 30% fully aligned, 50% partially misaligned, 20% fully misaligned
                    rand = random.random()
                    
                    if rand < 0.30:
                        # Fully aligned (30%)
                        misalign_status = False
                        misalign_goal = False
                        misalign_dependency = False
                        aligned_count += 1
                    elif rand < 0.80:
                        # Partially misaligned (50%) - randomly misalign 1-2 attributes
                        num_to_misalign = random.randint(1, 2)
                        attrs_to_misalign = random.sample(['status', 'goal', 'dependency'], num_to_misalign)
                        misalign_status = 'status' in attrs_to_misalign
                        misalign_goal = 'goal' in attrs_to_misalign
                        misalign_dependency = 'dependency' in attrs_to_misalign
                        misaligned_count += 1
                    else:
                        # Fully misaligned (20%) - all attributes different
                        misalign_status = True
                        misalign_goal = True
                        misalign_dependency = True
                        misaligned_count += 1
                    
                    # Apply misalignments
                    manager_status = status_alternatives.get(status, status) if misalign_status else status
                    manager_goal = goal_variations.get(goal, goal) if misalign_goal else goal
                    
                    # Manager's answers about this task
                    manager_status_answer = AttributeAnswer(
                        answered_by_user_id=db_manager.id,
                        target_user_id=db_owner.id,  # About the owner
                        task_id=db_task.id,
                        attribute_id=status_attr.id,
                        value=manager_status,
                        refused=False
                    )
                    db.add(manager_status_answer)
                    
                    manager_owner_answer = AttributeAnswer(
                        answered_by_user_id=db_manager.id,
                        target_user_id=db_owner.id,
                        task_id=db_task.id,
                        attribute_id=owner_attr.id,
                        value=owner["name"],
                        refused=False
                    )
                    db.add(manager_owner_answer)
                    
                    manager_goal_answer = AttributeAnswer(
                        answered_by_user_id=db_manager.id,
                        target_user_id=db_owner.id,
                        task_id=db_task.id,
                        attribute_id=goal_attr.id,
                        value=manager_goal,
                        refused=False
                    )
                    db.add(manager_goal_answer)
                    
                    # Manager's dependency answer (if task has dependencies)
                    if dependency_attr and hasattr(db_task, 'dependencies') and db_task.dependencies:
                        # Get dependency task titles
                        dep_titles = [t.title for t in db_task.dependencies]
                        
                        # Manager might have different perception (misalignment)
                        if misalign_dependency and dep_titles:
                            # Misaligned: wrong dependency perception
                            # Get a random other task as misperceived dependency
                            all_tasks = db.query(Task).filter(Task.id != db_task.id).limit(3).all()
                            if all_tasks:
                                wrong_dep = random.choice(all_tasks)
                                manager_dep_value = wrong_dep.title
                            else:
                                manager_dep_value = ", ".join(dep_titles)
                        else:
                            # Aligned: same dependency perception
                            manager_dep_value = ", ".join(dep_titles)
                        
                        manager_dep_answer = AttributeAnswer(
                            answered_by_user_id=db_manager.id,
                            target_user_id=db_owner.id,
                            task_id=db_task.id,
                            attribute_id=dependency_attr.id,
                            value=manager_dep_value,
                            refused=False
                        )
                        db.add(manager_dep_answer)
                        answer_count += 1
                    
                    answer_count += 3
        
        db.commit()
        print(f"✅ Created {answer_count} attribute answers")
        if aligned_count + misaligned_count > 0:
            print(f"   📊 Alignment: {aligned_count} fully aligned ({aligned_count/(aligned_count+misaligned_count)*100:.0f}%), {misaligned_count} with misalignments ({misaligned_count/(aligned_count+misaligned_count)*100:.0f}%)")
            print(f"   🎯 Target: 50% fully aligned, 40% partially misaligned, 10% fully misaligned")
        
    finally:
        db.close()


def create_misalignment_examples_direct(users: Dict[str, dict], tasks: Dict[str, dict]):
    """No longer needed - misalignments are created automatically in create_attribute_answers_direct"""
    print("\n✅ Misalignments already created in attribute answers (20% of tasks)")
    pass


def main():
    print("\n" + "="*70)
    print("  POPULATE ORGOS WITH SAMPLE DATA (Direct DB)")
    print("="*70)
    
    start_time = time.time()
    
    if CLEAR_DB_FIRST:
        clear_database()
    
    users = create_users()
    if not users:
        return
    
    create_alignments(users)
    tasks = create_tasks(users)
    if not tasks:
        return
    
    create_attribute_answers_direct(users, tasks)
    create_misalignment_examples_direct(users, tasks)
    
    elapsed = time.time() - start_time
    print("\n" + "="*70)
    print("  📊 SUMMARY")
    print("="*70)
    print(f"  ✅ Users: 12 (2 teams with hierarchy)")
    print(f"  ✅ Team leads: 2 (Dana, Amir)")
    print(f"  ✅ Individual contributors: 10")
    print(f"  ✅ Tasks: 14 (4 epics, 10 children)")
    print(f"  ✅ Cross-team dependencies: 2")
    print(f"  ✅ Alignment edges: ~24")
    print(f"  ✅ Attribute answers: ~84 (owner + team lead POV)")
    print(f"  ✅ Data alignment: ~80% aligned, ~20% misaligned")
    print(f"  ⏱️  Time: {elapsed:.2f}s")
    print("\n" + "="*70)
    print("  🎉 Sample data complete!")
    print("="*70)
    print(f"\n  🧪 Test endpoints:")
    print(f"     • {BASE_URL}/users/org-chart")
    print(f"     • {BASE_URL}/tasks")
    print(f"     • {BASE_URL}/misalignments (login as team lead)")
    print()


if __name__ == "__main__":
    main()

