#!/usr/bin/env python3
"""
Populate OrgOs database with realistic sample data for development and debugging.

This script creates:
- 2 teams with team leads and members
- Alignment networks
- Tasks with parent/child relationships and dependencies
- Attribute answers for all tasks
- Misalignment examples for testing
"""
import requests
import time
from typing import Dict, List, Optional
import random

# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "http://localhost:8000"
CLEAR_DB_FIRST = True  # Set to True to clear existing data

# ============================================================================
# Helper Functions
# ============================================================================

def api_request(method: str, endpoint: str, data: dict = None, user_id: str = None) -> dict:
    """Make an API request with optional authentication"""
    url = f"{BASE_URL}{endpoint}"
    headers = {}
    if user_id:
        headers["X-User-Id"] = user_id
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, json=data, headers=headers)
    elif method == "PUT":
        response = requests.put(url, json=data, headers=headers)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    if response.status_code not in [200, 201]:
        print(f"❌ Error: {method} {endpoint} returned {response.status_code}")
        print(f"   Response: {response.text}")
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
    else:
        print(f"⚠️  Warning: Could not clear database: {result.stderr}")


# ============================================================================
# Data Generation Functions
# ============================================================================

def create_users() -> Dict[str, dict]:
    """Create users for both teams"""
    print("\n👥 Creating users...")
    
    users = {}
    
    # Team 1: Platform Team
    print("  Creating Platform Team...")
    dana = api_request("POST", "/users", {
        "name": "Dana Cohen",
        "email": "dana@company.com",
        "timezone": "Asia/Jerusalem"
    })
    users["dana"] = dana
    print(f"    ✅ Dana Cohen (Team Lead) - ID: {dana['id']}")
    
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
        print(f"    ✅ {name} - ID: {user['id']}")
    
    # Team 2: Product Team
    print("  Creating Product Team...")
    amir = api_request("POST", "/users", {
        "name": "Amir Levi",
        "email": "amir@company.com",
        "timezone": "Asia/Jerusalem"
    })
    users["amir"] = amir
    print(f"    ✅ Amir Levi (Team Lead) - ID: {amir['id']}")
    
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
        print(f"    ✅ {name} - ID: {user['id']}")
    
    print(f"✅ Created {len(users) - 2} users total")
    return users


def create_alignments(users: Dict[str, dict]):
    """Create alignment network"""
    print("\n🤝 Creating alignment network...")
    
    # Platform team alignments
    dana_id = users["dana"]["id"]
    for member in users["platform_team"]:
        # Dana aligns with all team members
        api_request("POST", "/alignments", {
            "target_user_id": member["id"],
            "align": True
        }, user_id=dana_id)
        
        # Each member aligns with Dana
        api_request("POST", "/alignments", {
            "target_user_id": dana_id,
            "align": True
        }, user_id=member["id"])
    
    print(f"  ✅ Platform Team: Dana ↔ 5 members")
    
    # Product team alignments
    amir_id = users["amir"]["id"]
    for member in users["product_team"]:
        # Amir aligns with all team members
        api_request("POST", "/alignments", {
            "target_user_id": member["id"],
            "align": True
        }, user_id=amir_id)
        
        # Each member aligns with Amir
        api_request("POST", "/alignments", {
            "target_user_id": amir_id,
            "align": True
        }, user_id=member["id"])
    
    print(f"  ✅ Product Team: Amir ↔ 5 members")
    
    # Cross-team: Dana ↔ Amir
    api_request("POST", "/alignments", {
        "target_user_id": amir_id,
        "align": True
    }, user_id=dana_id)
    
    api_request("POST", "/alignments", {
        "target_user_id": dana_id,
        "align": True
    }, user_id=amir_id)
    
    print(f"  ✅ Cross-team: Dana ↔ Amir")
    
    # A couple more cross-team alignments
    api_request("POST", "/alignments", {
        "target_user_id": users["yael"]["id"],
        "align": True
    }, user_id=users["tamar"]["id"])
    
    api_request("POST", "/alignments", {
        "target_user_id": users["roi"]["id"],
        "align": True
    }, user_id=users["omer"]["id"])
    
    print(f"  ✅ Cross-team: Yael ↔ Tamar, Omer ↔ Roi")


def create_tasks(users: Dict[str, dict]) -> Dict[str, dict]:
    """Create tasks with hierarchy and dependencies"""
    print("\n📝 Creating tasks...")
    
    tasks = {}
    
    # ========================================================================
    # Platform Team Tasks
    # ========================================================================
    print("  Creating Platform Team tasks...")
    
    # Epic 1: Auth System Migration
    auth_epic = api_request("POST", "/tasks", {
        "title": "Migrate auth service to new stack",
        "description": "Move authentication system from legacy monolith to new microservices architecture with OAuth 2.0"
    }, user_id=users["dana"]["id"])
    tasks["auth_epic"] = auth_epic
    print(f"    ✅ Epic: {auth_epic['title']}")
    
    # Children of auth epic
    auth_design = api_request("POST", "/tasks", {
        "title": "Design new authentication flow",
        "description": "Create technical spec for OAuth 2.0 implementation",
        "parent_id": auth_epic["id"]
    }, user_id=users["yael"]["id"])
    tasks["auth_design"] = auth_design
    print(f"      ✅ Child: {auth_design['title']}")
    
    auth_impl = api_request("POST", "/tasks", {
        "title": "Implement OAuth 2.0 provider",
        "description": "Build OAuth server with token management",
        "parent_id": auth_epic["id"],
        "dependencies": [auth_design["id"]]
    }, user_id=users["omer"]["id"])
    tasks["auth_impl"] = auth_impl
    print(f"      ✅ Child: {auth_impl['title']}")
    
    auth_migration = api_request("POST", "/tasks", {
        "title": "Migrate existing users to new auth",
        "description": "Data migration script for user accounts",
        "parent_id": auth_epic["id"],
        "dependencies": [auth_impl["id"]]
    }, user_id=users["noa"]["id"])
    tasks["auth_migration"] = auth_migration
    print(f"      ✅ Child: {auth_migration['title']}")
    
    # Epic 2: Logging Infrastructure
    logging_epic = api_request("POST", "/tasks", {
        "title": "Refactor logging pipeline",
        "description": "Upgrade to structured logging with better observability"
    }, user_id=users["dana"]["id"])
    tasks["logging_epic"] = logging_epic
    print(f"    ✅ Epic: {logging_epic['title']}")
    
    # Children of logging epic
    logging_analysis = api_request("POST", "/tasks", {
        "title": "Analyze current logging patterns",
        "description": "Audit existing logs and identify improvements",
        "parent_id": logging_epic["id"]
    }, user_id=users["eitan"]["id"])
    tasks["logging_analysis"] = logging_analysis
    print(f"      ✅ Child: {logging_analysis['title']}")
    
    logging_impl = api_request("POST", "/tasks", {
        "title": "Implement structured logging library",
        "description": "Create wrapper for JSON-based structured logs",
        "parent_id": logging_epic["id"],
        "dependencies": [logging_analysis["id"]]
    }, user_id=users["michal"]["id"])
    tasks["logging_impl"] = logging_impl
    print(f"      ✅ Child: {logging_impl['title']}")
    
    # ========================================================================
    # Product Team Tasks
    # ========================================================================
    print("  Creating Product Team tasks...")
    
    # Epic 3: User Onboarding
    onboarding_epic = api_request("POST", "/tasks", {
        "title": "Implement new onboarding flow",
        "description": "Redesign user onboarding with interactive tutorial"
    }, user_id=users["amir"]["id"])
    tasks["onboarding_epic"] = onboarding_epic
    print(f"    ✅ Epic: {onboarding_epic['title']}")
    
    # Children of onboarding epic
    onboarding_design = api_request("POST", "/tasks", {
        "title": "Design onboarding UX",
        "description": "Create wireframes and user flows for new onboarding",
        "parent_id": onboarding_epic["id"]
    }, user_id=users["tamar"]["id"])
    tasks["onboarding_design"] = onboarding_design
    print(f"      ✅ Child: {onboarding_design['title']}")
    
    onboarding_frontend = api_request("POST", "/tasks", {
        "title": "Build onboarding UI components",
        "description": "Implement React components for interactive tutorial",
        "parent_id": onboarding_epic["id"],
        "dependencies": [onboarding_design["id"], auth_impl["id"]]  # Cross-team dependency!
    }, user_id=users["roi"]["id"])
    tasks["onboarding_frontend"] = onboarding_frontend
    print(f"      ✅ Child: {onboarding_frontend['title']} (depends on Platform auth)")
    
    onboarding_analytics = api_request("POST", "/tasks", {
        "title": "Add onboarding analytics",
        "description": "Track user progress through onboarding steps",
        "parent_id": onboarding_epic["id"],
        "dependencies": [onboarding_frontend["id"], logging_impl["id"]]  # Cross-team dependency!
    }, user_id=users["shira"]["id"])
    tasks["onboarding_analytics"] = onboarding_analytics
    print(f"      ✅ Child: {onboarding_analytics['title']} (depends on Platform logging)")
    
    # Epic 4: Dashboard Improvements
    dashboard_epic = api_request("POST", "/tasks", {
        "title": "Redesign main dashboard",
        "description": "Modern dashboard with real-time metrics"
    }, user_id=users["amir"]["id"])
    tasks["dashboard_epic"] = dashboard_epic
    print(f"    ✅ Epic: {dashboard_epic['title']}")
    
    # Children of dashboard epic
    dashboard_api = api_request("POST", "/tasks", {
        "title": "Build dashboard API endpoints",
        "description": "Create REST APIs for dashboard metrics",
        "parent_id": dashboard_epic["id"]
    }, user_id=users["asaf"]["id"])
    tasks["dashboard_api"] = dashboard_api
    print(f"      ✅ Child: {dashboard_api['title']}")
    
    dashboard_ui = api_request("POST", "/tasks", {
        "title": "Implement dashboard UI",
        "description": "Build responsive dashboard with charts and widgets",
        "parent_id": dashboard_epic["id"],
        "dependencies": [dashboard_api["id"]]
    }, user_id=users["liora"]["id"])
    tasks["dashboard_ui"] = dashboard_ui
    print(f"      ✅ Child: {dashboard_ui['title']}")
    
    print(f"✅ Created {len(tasks)} tasks total")
    return tasks


def get_attribute_id(attribute_name: str) -> Optional[str]:
    """Get attribute ID by name"""
    attrs = api_request("GET", "/task-attributes")
    if not attrs:
        return None
    for attr in attrs:
        if attr["name"] == attribute_name:
            return attr["id"]
    return None


def create_attribute_answers(users: Dict[str, dict], tasks: Dict[str, dict]):
    """Create attribute answers for all tasks"""
    print("\n💭 Creating attribute answers...")
    
    # Get attribute IDs
    status_attr_id = get_attribute_id("status")
    owner_attr_id = get_attribute_id("perceived_owner")
    goal_attr_id = get_attribute_id("main_goal")
    
    if not all([status_attr_id, owner_attr_id, goal_attr_id]):
        print("❌ Could not find required attributes")
        return
    
    # Define task configs: (task_key, owner_key, status, goal_description)
    task_configs = [
        ("auth_epic", "dana", "In progress", 
         "Move our authentication system to a modern microservices architecture to improve security and scalability."),
        ("auth_design", "yael", "Done", 
         "Create comprehensive technical documentation for OAuth 2.0 implementation including security considerations."),
        ("auth_impl", "omer", "In progress", 
         "Build a robust OAuth 2.0 provider that handles token generation, validation, and refresh workflows."),
        ("auth_migration", "noa", "Not started", 
         "Safely migrate all existing user accounts to the new authentication system without data loss."),
        
        ("logging_epic", "dana", "In progress", 
         "Upgrade our logging infrastructure to use structured logging for better debugging and monitoring."),
        ("logging_analysis", "eitan", "Done", 
         "Review current logging practices and identify gaps in observability across our services."),
        ("logging_impl", "michal", "In progress", 
         "Create a reusable logging library that outputs JSON-formatted structured logs with proper context."),
        
        ("onboarding_epic", "amir", "In progress", 
         "Redesign the user onboarding experience to reduce time-to-value and increase activation rates."),
        ("onboarding_design", "tamar", "Done", 
         "Design an intuitive onboarding flow with interactive elements that guide users through key features."),
        ("onboarding_frontend", "roi", "Blocked", 
         "Implement the frontend components for the new onboarding flow using React and TypeScript."),
        ("onboarding_analytics", "shira", "Not started", 
         "Instrument the onboarding flow with analytics to track user progress and identify drop-off points."),
        
        ("dashboard_epic", "amir", "In progress", 
         "Create a modern, real-time dashboard that gives users actionable insights into their metrics."),
        ("dashboard_api", "asaf", "In progress", 
         "Build backend APIs that aggregate and serve dashboard data efficiently with proper caching."),
        ("dashboard_ui", "liora", "Not started", 
         "Develop a beautiful, responsive dashboard UI with interactive charts and customizable widgets."),
    ]
    
    answer_count = 0
    for task_key, owner_key, status, goal in task_configs:
        task = tasks.get(task_key)
        owner = users.get(owner_key)
        
        if not task or not owner:
            continue
        
        # Owner's self-answers
        # Status
        api_request("POST", "/answers", {
            "question_id": f"debug-{task['id']}-status",
            "value": status,
            "refused": False
        }, user_id=owner["id"])
        
        # Perceived owner
        api_request("POST", "/answers", {
            "question_id": f"debug-{task['id']}-owner",
            "value": owner["name"],
            "refused": False
        }, user_id=owner["id"])
        
        # Main goal
        api_request("POST", "/answers", {
            "question_id": f"debug-{task['id']}-goal",
            "value": goal,
            "refused": False
        }, user_id=owner["id"])
        
        answer_count += 3
        print(f"  ✅ {task['title'][:40]}... ({status})")
    
    print(f"✅ Created {answer_count} attribute answers")


def create_misalignment_examples(users: Dict[str, dict], tasks: Dict[str, dict]):
    """Create conflicting perceptions for misalignment testing"""
    print("\n⚠️  Creating misalignment examples...")
    
    status_attr_id = get_attribute_id("status")
    owner_attr_id = get_attribute_id("perceived_owner")
    goal_attr_id = get_attribute_id("main_goal")
    
    # Example 1: auth_impl - Omer thinks it's "In progress", Dana thinks it's "Blocked"
    task = tasks["auth_impl"]
    dana = users["dana"]
    
    api_request("POST", "/answers", {
        "question_id": f"debug-misalign-{task['id']}-status",
        "value": "Blocked",
        "refused": False
    }, user_id=dana["id"])
    
    api_request("POST", "/answers", {
        "question_id": f"debug-misalign-{task['id']}-goal",
        "value": "Implement OAuth provider with basic token management",  # Simpler version
        "refused": False
    }, user_id=dana["id"])
    
    print(f"  ✅ Misalignment: {task['title']}")
    print(f"     - Status: Omer says 'In progress', Dana says 'Blocked'")
    print(f"     - Goal: Different interpretations")
    
    # Example 2: onboarding_frontend - Roi thinks it's "Blocked", Amir thinks it's "In progress"
    task = tasks["onboarding_frontend"]
    amir = users["amir"]
    
    api_request("POST", "/answers", {
        "question_id": f"debug-misalign2-{task['id']}-status",
        "value": "In progress",
        "refused": False
    }, user_id=amir["id"])
    
    api_request("POST", "/answers", {
        "question_id": f"debug-misalign2-{task['id']}-goal",
        "value": "Build React components for the new user onboarding tutorial",  # Similar but different
        "refused": False
    }, user_id=amir["id"])
    
    print(f"  ✅ Misalignment: {task['title']}")
    print(f"     - Status: Roi says 'Blocked', Amir says 'In progress'")
    print(f"     - Goal: Semantically similar but not identical")
    
    # Example 3: logging_impl - Michal thinks it's "In progress", Dana thinks it's "Done"
    task = tasks["logging_impl"]
    dana = users["dana"]
    
    api_request("POST", "/answers", {
        "question_id": f"debug-misalign3-{task['id']}-status",
        "value": "Done",
        "refused": False
    }, user_id=dana["id"])
    
    print(f"  ✅ Misalignment: {task['title']}")
    print(f"     - Status: Michal says 'In progress', Dana says 'Done'")


# ============================================================================
# Main Script
# ============================================================================

def main():
    print("\n" + "="*70)
    print("  POPULATE ORGOS DATABASE WITH SAMPLE DATA")
    print("="*70)
    
    start_time = time.time()
    
    # Step 1: Clear database if requested
    if CLEAR_DB_FIRST:
        clear_database()
    
    # Step 2: Create users
    users = create_users()
    if not users:
        print("❌ Failed to create users")
        return
    
    # Step 3: Create alignments
    create_alignments(users)
    
    # Step 4: Create tasks
    tasks = create_tasks(users)
    if not tasks:
        print("❌ Failed to create tasks")
        return
    
    # Step 5: Create attribute answers
    create_attribute_answers(users, tasks)
    
    # Step 6: Create misalignment examples
    create_misalignment_examples(users, tasks)
    
    # Summary
    elapsed = time.time() - start_time
    print("\n" + "="*70)
    print("  📊 SUMMARY")
    print("="*70)
    print(f"  ✅ Users created: {len([u for k, u in users.items() if isinstance(u, dict)])}")
    print(f"  ✅ Tasks created: {len(tasks)}")
    print(f"  ✅ Parent tasks: 4 (2 per team)")
    print(f"  ✅ Child tasks: 10")
    print(f"  ✅ Cross-team dependencies: 2")
    print(f"  ✅ Alignment edges: ~24")
    print(f"  ✅ Attribute answers: ~42")
    print(f"  ✅ Misalignment examples: 3")
    print(f"  ⏱️  Completed in: {elapsed:.2f}s")
    print("\n" + "="*70)
    print("  🎉 Sample data population complete!")
    print("="*70)
    print("\n  Test it:")
    print(f"    • GET {BASE_URL}/tasks")
    print(f"    • GET {BASE_URL}/users/org-chart")
    print(f"    • GET {BASE_URL}/debug/misalignments/raw")
    print()


if __name__ == "__main__":
    main()

