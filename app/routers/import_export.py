"""
Import/Export API endpoints
"""

from fastapi import APIRouter, Depends, UploadFile, File, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID
from io import BytesIO
from datetime import datetime
import logging

from app.database import get_db
from app.services.import_export import (
    export_all_data_to_excel,
    export_template_to_excel,
    validate_import_file,
    import_data_from_excel
)

router = APIRouter(prefix="/import-export", tags=["import-export"])
logger = logging.getLogger(__name__)


@router.get("/export")
async def export_data(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Mode 1: Export all system data to Excel file
    """
    try:
        logger.info(f"📊 Export requested by user {x_user_id}")
        
        # Generate Excel file
        excel_file = export_all_data_to_excel(db)
        
        # Return as downloadable file
        filename = f"orgos_data_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logger.error(f"❌ Export error: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/template")
async def export_template(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Mode 2: Export empty template showing required format
    Dynamically includes all attributes from the database schema.
    """
    try:
        logger.info(f"📋 Template requested by user {x_user_id}")
        
        # Generate template file with actual attributes from DB
        excel_file = export_template_to_excel(db)
        
        # Return as downloadable file
        filename = f"orgos_import_template.xlsx"
        
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logger.error(f"❌ Template export error: {e}")
        raise HTTPException(status_code=500, detail=f"Template export failed: {str(e)}")


@router.post("/import")
async def import_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Mode 3: Import data from Excel file (APPEND mode)
    Adds new data without deleting existing data.
    """
    try:
        logger.info(f"📥 Import (append) requested by user {x_user_id}, file: {file.filename}")
        
        # Read uploaded file
        contents = await file.read()
        file_obj = BytesIO(contents)
        
        # Import data (append mode) - pass filename for format detection
        result = import_data_from_excel(db, file_obj, replace_mode=False, filename=file.filename or "")
        
        if result['success']:
            return {
                "success": True,
                "message": result['message'],
                "stats": result['stats'],
                "warnings": result.get('warnings', [])
            }
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": result['message'],
                    "errors": result['errors']
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/import-replace")
async def import_replace_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Mode 4: Import data from Excel file (REPLACE mode)
    Deletes existing users/tasks, then imports from file.
    Prompts are NOT deleted - new prompts are added as latest versions.
    
    ⚠️ WARNING: This will DELETE all existing users, tasks, and their data!
    """
    try:
        logger.info(f"📥 Import (REPLACE) requested by user {x_user_id}, file: {file.filename}")
        logger.warning("⚠️  REPLACE MODE - This will delete existing data!")
        
        # Read uploaded file
        contents = await file.read()
        file_obj = BytesIO(contents)
        
        # Import data (replace mode) - pass filename for format detection
        result = import_data_from_excel(db, file_obj, replace_mode=True, filename=file.filename or "")
        
        if result['success']:
            return {
                "success": True,
                "message": result['message'],
                "stats": result['stats'],
                "warnings": result.get('warnings', [])
            }
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": result['message'],
                    "errors": result['errors']
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Import (replace) error: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/validate")
async def validate_file(
    file: UploadFile = File(...),
    x_user_id: str = Header(...)
):
    """
    Validate an Excel file before importing (without actually importing)
    """
    try:
        logger.info(f"🔍 File validation requested by user {x_user_id}")
        
        # Read uploaded file
        contents = await file.read()
        file_obj = BytesIO(contents)
        
        # Validate
        result = validate_import_file(file_obj)
        
        return {
            "valid": result['valid'],
            "errors": result['errors'],
            "warnings": result['warnings']
        }
    
    except Exception as e:
        logger.error(f"❌ Validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

