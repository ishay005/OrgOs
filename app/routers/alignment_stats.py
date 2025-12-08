"""
Alignment statistics endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import User, Task, AttributeAnswer, AttributeDefinition
from typing import Dict
from uuid import UUID

router = APIRouter(prefix="/alignment-stats", tags=["alignment-stats"])


@router.get("/users")
async def get_user_alignment_stats(db: Session = Depends(get_db)) -> Dict[str, float]:
    """
    Get alignment percentage for each user based on ALL tasks connected to them.
    For managers/team leads: includes alignment with their employees on employees' tasks.
    Returns: { "user_id": alignment_percentage (0-100) }
    
    For each user, calculate:
    - Find all tasks they've answered about (any task where they provided answers)
    - For each of their answers, compare with other users' answers about the same task/attribute
    - If user is a manager: ALSO compare their answers about employees' tasks with employees' self-answers
    - Calculate percentage of aligned vs total comparisons
    """
    users = db.query(User).all()
    stats = {}
    
    for user in users:
        # Get all answers provided by this user
        user_answers = db.query(AttributeAnswer).filter(
            AttributeAnswer.answered_by_user_id == user.id,
            AttributeAnswer.refused == False
        ).all()
        
        if not user_answers:
            stats[str(user.id)] = 100.0  # No data
            continue
        
        total_comparisons = 0
        aligned_comparisons = 0
        
        # For each answer by this user, compare with others' answers
        for user_answer in user_answers:
            # Find all other users who answered the same attribute for the same task
            other_answers = db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == user_answer.task_id,
                AttributeAnswer.attribute_id == user_answer.attribute_id,
                AttributeAnswer.answered_by_user_id != user.id,  # Different user
                AttributeAnswer.refused == False
            ).all()
            
            # Compare with each other user's answer
            for other_answer in other_answers:
                total_comparisons += 1
                # Check if answers match
                if user_answer.value.strip().lower() == other_answer.value.strip().lower():
                    aligned_comparisons += 1
        
        # If user is a manager/team lead, ALSO include alignment with employees on THEIR tasks
        if hasattr(user, 'employees') and user.employees:
            for employee in user.employees:
                # Get all tasks owned by this employee
                employee_tasks = db.query(Task).filter(Task.owner_user_id == employee.id).all()
                
                for task in employee_tasks:
                    # Get all attributes
                    attributes = db.query(AttributeDefinition).filter(
                        AttributeDefinition.entity_type == "task"
                    ).all()
                    
                    for attr in attributes:
                        # Employee's self-answer
                        employee_answer = db.query(AttributeAnswer).filter(
                            AttributeAnswer.answered_by_user_id == employee.id,
                            AttributeAnswer.target_user_id == employee.id,
                            AttributeAnswer.task_id == task.id,
                            AttributeAnswer.attribute_id == attr.id,
                            AttributeAnswer.refused == False
                        ).first()
                        
                        # Manager's answer about this employee's task
                        manager_answer = db.query(AttributeAnswer).filter(
                            AttributeAnswer.answered_by_user_id == user.id,
                            AttributeAnswer.target_user_id == employee.id,
                            AttributeAnswer.task_id == task.id,
                            AttributeAnswer.attribute_id == attr.id,
                            AttributeAnswer.refused == False
                        ).first()
                        
                        if employee_answer and manager_answer:
                            total_comparisons += 1
                            if employee_answer.value.strip().lower() == manager_answer.value.strip().lower():
                                aligned_comparisons += 1
        
        if total_comparisons > 0:
            alignment_pct = (aligned_comparisons / total_comparisons) * 100
            stats[str(user.id)] = round(alignment_pct, 1)
        else:
            # No comparisons available (no one else answered the same tasks)
            stats[str(user.id)] = 100.0  # Neutral/no data
    
    return stats


@router.get("/tasks")
async def get_task_alignment_stats(db: Session = Depends(get_db)) -> Dict[str, float]:
    """
    Get alignment percentage for each task.
    Returns: { "task_id": alignment_percentage (0-100) }
    
    For each task, calculate:
    - How many answers about this task are aligned between different users
    - Return as percentage
    """
    tasks = db.query(Task).all()
    stats = {}
    
    for task in tasks:
        # Get task owner
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        if not owner or not owner.manager_id:
            stats[str(task.id)] = 100.0
            continue
        
        # Get all attribute definitions
        attributes = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == "task"
        ).all()
        
        total_comparisons = 0
        aligned_comparisons = 0
        
        for attr in attributes:
            # Owner's answer
            owner_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == owner.id,
                AttributeAnswer.target_user_id == owner.id,
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attr.id,
                AttributeAnswer.refused == False
            ).first()
            
            # Manager's answer
            manager_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == owner.manager_id,
                AttributeAnswer.target_user_id == owner.id,
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attr.id,
                AttributeAnswer.refused == False
            ).first()
            
            if owner_answer and manager_answer:
                total_comparisons += 1
                if owner_answer.value.strip().lower() == manager_answer.value.strip().lower():
                    aligned_comparisons += 1
        
        if total_comparisons > 0:
            alignment_pct = (aligned_comparisons / total_comparisons) * 100
            stats[str(task.id)] = round(alignment_pct, 1)
        else:
            stats[str(task.id)] = 100.0  # Neutral/no data
    
    return stats

