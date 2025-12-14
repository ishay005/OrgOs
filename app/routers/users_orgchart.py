"""
Org chart endpoint
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Task
from app.schemas import OrgChartNode, OrgChartResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/org-chart", response_model=OrgChartResponse)
async def get_org_chart(db: Session = Depends(get_db)):
    """
    Get the organizational chart with all users and their hierarchy.
    """
    users = db.query(User).all()
    
    nodes = []
    for user in users:
        # Count employees
        employee_count = len(user.employees) if hasattr(user, 'employees') else 0
        
        # Count tasks owned
        task_count = db.query(Task).filter(Task.owner_user_id == user.id).count()
        
        nodes.append(OrgChartNode(
            id=user.id,
            name=user.name,
            email=user.email,
            team=user.team,
            role=user.role,
            manager_id=user.manager_id,
            employee_count=employee_count,
            task_count=task_count
        ))
    
    return OrgChartResponse(users=nodes)

