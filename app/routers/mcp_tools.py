"""
MCP Tools API endpoints for debugging and testing.

Allows direct invocation of Cortex MCP tools from the UI.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Optional
from uuid import UUID

from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.services.cortex_tools import CORTEX_TOOLS, execute_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp-tools", tags=["mcp_tools"])


class ExecuteToolRequest(BaseModel):
    """Request body for executing an MCP tool"""
    tool_name: str
    args: dict = {}


class ToolDefinition(BaseModel):
    """Tool definition for the UI"""
    name: str
    description: str
    parameters: dict


@router.get("/list", response_model=list[ToolDefinition])
async def list_tools():
    """
    List all available MCP tools with their definitions.
    """
    tools = []
    for tool in CORTEX_TOOLS:
        if tool.get("type") == "function":
            func = tool.get("function", {})
            tools.append(ToolDefinition(
                name=func.get("name", ""),
                description=func.get("description", ""),
                parameters=func.get("parameters", {})
            ))
    return tools


@router.post("/execute")
async def execute_mcp_tool(
    request: ExecuteToolRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Execute an MCP tool and return the result.
    
    This is for debugging/testing purposes.
    """
    logger.info(f"Executing MCP tool: {request.tool_name} with args: {request.args}")
    
    # Validate tool exists
    tool_names = [t.get("function", {}).get("name") for t in CORTEX_TOOLS if t.get("type") == "function"]
    if request.tool_name not in tool_names:
        raise HTTPException(status_code=404, detail=f"Tool not found: {request.tool_name}")
    
    try:
        # Execute the tool
        result = execute_tool(
            db=db,
            user_id=current_user.id,
            tool_name=request.tool_name,
            tool_args=request.args,
            daily_session=None
        )
        
        return {
            "success": True,
            "tool_name": request.tool_name,
            "args": request.args,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error executing tool {request.tool_name}: {e}", exc_info=True)
        return {
            "success": False,
            "tool_name": request.tool_name,
            "args": request.args,
            "error": str(e)
        }

