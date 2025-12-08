#!/usr/bin/env python3
"""
Clear all data from the database while keeping the schema (AttributeDefinitions)
"""
import sys
sys.path.insert(0, '/Users/ishaylevi/work/OrgOs')

from app.database import SessionLocal
from app.models import (
    User, Task, AlignmentEdge, AttributeAnswer, 
    QuestionLog, TaskDependency
)

def clear_all_data():
    """Clear all user data from the database"""
    db = SessionLocal()
    try:
        print("🗑️  Clearing all data from database...")
        
        # Delete in order to respect foreign key constraints
        deleted_answers = db.query(AttributeAnswer).delete()
        print(f"   ✅ Deleted {deleted_answers} attribute answers")
        
        deleted_questions = db.query(QuestionLog).delete()
        print(f"   ✅ Deleted {deleted_questions} question logs")
        
        deleted_dependencies = db.query(TaskDependency).delete()
        print(f"   ✅ Deleted {deleted_dependencies} task dependencies")
        
        deleted_tasks = db.query(Task).delete()
        print(f"   ✅ Deleted {deleted_tasks} tasks")
        
        deleted_alignments = db.query(AlignmentEdge).delete()
        print(f"   ✅ Deleted {deleted_alignments} alignment edges")
        
        deleted_users = db.query(User).delete()
        print(f"   ✅ Deleted {deleted_users} users")
        
        db.commit()
        print("\n✅ Database cleared successfully!")
        print("📋 AttributeDefinitions (schema) preserved")
        print("\n🎯 Your system is now ready for fresh data!")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error clearing database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  CLEAR ALL DATA FROM DATABASE")
    print("="*70 + "\n")
    
    confirm = input("⚠️  This will delete ALL users, tasks, answers, etc.\n   Type 'yes' to confirm: ")
    
    if confirm.lower() == 'yes':
        clear_all_data()
    else:
        print("\n❌ Operation cancelled")

