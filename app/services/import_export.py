"""
Import/Export service for system data (users, tasks, prompts)
Uses names instead of IDs for human readability
Supports: Excel (.xlsx) and Apple Numbers (.numbers) files
Alignments and Answers are calculated after import, not stored in file
"""

import pandas as pd
from openpyxl import Workbook
from io import BytesIO
from typing import Dict, Optional
from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session
import logging
import json
import tempfile
import os

from app.models import (
    User, Task, TaskDependency, PromptTemplate, AttributeAnswer, AlignmentEdge,
    DailySyncSession, ChatThread, ChatMessage, QuestionLog, SimilarityScore,
    MessageDebugData, AttributeDefinition, EntityType, AttributeType
)

# Try to import numbers-parser for Apple Numbers support
try:
    from numbers_parser import Document as NumbersDocument
    NUMBERS_SUPPORT = True
except ImportError:
    NUMBERS_SUPPORT = False
    logger.warning("numbers-parser not installed - Apple Numbers files not supported")

logger = logging.getLogger(__name__)


def convert_numbers_to_dataframes(file_content: bytes) -> Dict[str, pd.DataFrame]:
    """
    Convert an Apple Numbers file to a dictionary of pandas DataFrames.
    Each sheet becomes a key in the dictionary.
    """
    if not NUMBERS_SUPPORT:
        raise ValueError("Apple Numbers support not installed. Install with: pip install numbers-parser")
    
    # Write to temp file (numbers-parser needs a file path)
    with tempfile.NamedTemporaryFile(suffix='.numbers', delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    
    try:
        doc = NumbersDocument(tmp_path)
        sheets = {}
        
        for sheet in doc.sheets:
            for table in sheet.tables:
                # Use sheet name as key (or table name if multiple tables per sheet)
                sheet_name = sheet.name
                if len(sheet.tables) > 1:
                    sheet_name = f"{sheet.name}_{table.name}"
                
                # Convert table to list of dicts
                if table.num_rows > 0:
                    # Get headers from first row
                    headers = []
                    for col_idx in range(table.num_cols):
                        cell_value = table.cell(0, col_idx).value
                        headers.append(str(cell_value) if cell_value is not None else f"Column{col_idx}")
                    
                    # Get data rows - skip empty rows
                    rows = []
                    for row_idx in range(1, table.num_rows):
                        row_data = {}
                        has_data = False
                        for col_idx, header in enumerate(headers):
                            cell_value = table.cell(row_idx, col_idx).value
                            row_data[header] = cell_value
                            # Check if this row has any actual data
                            if cell_value is not None and str(cell_value).strip():
                                has_data = True
                        
                        # Only add rows that have at least some data
                        if has_data:
                            rows.append(row_data)
                    
                    if rows:
                        sheets[sheet_name] = pd.DataFrame(rows)
                    else:
                        sheets[sheet_name] = pd.DataFrame(columns=headers)
        
        return sheets
    
    finally:
        # Clean up temp file
        os.unlink(tmp_path)


# ==============================================================================
# EXPORT Functions
# ==============================================================================

def export_all_data_to_excel(db: Session) -> BytesIO:
    """
    Export all system data to Excel file with multiple sheets.
    Uses NAMES instead of IDs for human readability.
    COMBINED FORMAT: Tasks include all attributes, Perception has all attributes as columns
    """
    logger.info("📊 Starting data export to Excel...")
    
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    
    # Build lookup maps
    users = db.query(User).all()
    user_id_to_name = {u.id: u.name for u in users}
    
    tasks = db.query(Task).all()
    task_id_to_title = {t.id: t.title for t in tasks}
    
    # Get all task attributes
    task_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    attr_names = [a.name for a in task_attributes]
    attr_id_to_name = {a.id: a.name for a in task_attributes}
    
    # Get all answers indexed by (task_id, user_id, attr_name)
    all_answers = db.query(AttributeAnswer).all()
    answer_lookup = {}
    for a in all_answers:
        if a.task_id:
            key = (a.task_id, a.answered_by_user_id, attr_id_to_name.get(a.attribute_id, ''))
            answer_lookup[key] = a.value
    
    # Get all dependencies
    dependencies = db.query(TaskDependency).all()
    task_deps = {}
    for d in dependencies:
        task_title = task_id_to_title.get(d.task_id, '')
        dep_title = task_id_to_title.get(d.depends_on_task_id, '')
        if task_title not in task_deps:
            task_deps[task_title] = []
        task_deps[task_title].append(dep_title)
    
    # Export Users (using names)
    users_data = [{
        'name': u.name,
        'email': u.email or '',
        'team': u.team or '',
        'timezone': u.timezone,
        'manager': user_id_to_name.get(u.manager_id, '') if u.manager_id else ''
    } for u in users]
    pd.DataFrame(users_data).to_excel(writer, sheet_name='Users', index=False)
    logger.info(f"  ✅ Exported {len(users_data)} users")
    
    # Export Tasks (COMBINED - with all attributes and dependencies)
    tasks_data = []
    for t in tasks:
        owner_id = t.owner_user_id
        task_row = {
            'title': t.title,
            'description': t.description or '',
            'owner': user_id_to_name.get(owner_id, ''),
            'parent': task_id_to_title.get(t.parent_id, '') if t.parent_id else '',
            'dependencies': ', '.join(task_deps.get(t.title, [])),
            'is_active': t.is_active
        }
        # Add all attribute values (owner's view)
        for attr_name in attr_names:
            key = (t.id, owner_id, attr_name)
            task_row[attr_name] = answer_lookup.get(key, '')
        tasks_data.append(task_row)
    
    pd.DataFrame(tasks_data).to_excel(writer, sheet_name='Tasks', index=False)
    logger.info(f"  ✅ Exported {len(tasks_data)} tasks with all attributes")
    
    # Export Prompts
    prompts = db.query(PromptTemplate).filter(PromptTemplate.is_active == True).all()
    prompts_data = [{
        'mode': p.mode,
        'has_pending': p.has_pending,
        'prompt_text': p.prompt_text,
        'context_config': json.dumps(p.context_config) if p.context_config else '{}',
        'created_by': p.created_by or '',
        'notes': p.notes or ''
    } for p in prompts]
    pd.DataFrame(prompts_data).to_excel(writer, sheet_name='Prompts', index=False)
    logger.info(f"  ✅ Exported {len(prompts_data)} active prompts")
    
    # Export Attribute Definitions
    attributes_data = [{
        'name': a.name,
        'label': a.label,
        'entity_type': a.entity_type.value,
        'type': a.type.value,
        'description': a.description or '',
        'allowed_values': json.dumps(a.allowed_values) if a.allowed_values else '',
        'is_required': a.is_required
    } for a in task_attributes]
    pd.DataFrame(attributes_data).to_excel(writer, sheet_name='Attributes', index=False)
    logger.info(f"  ✅ Exported {len(attributes_data)} attribute definitions")
    
    # Export Perception Data (COMBINED - one row per user+task, all attributes as columns)
    # Group answers by (answered_by, target_user, task)
    perception_groups = {}
    for a in all_answers:
        if a.task_id:
            key = (a.answered_by_user_id, a.target_user_id, a.task_id)
            if key not in perception_groups:
                perception_groups[key] = {}
            attr_name = attr_id_to_name.get(a.attribute_id, '')
            if attr_name:
                perception_groups[key][attr_name] = a.value
    
    perception_data = []
    for (answered_by_id, target_user_id, task_id), attrs in perception_groups.items():
        row = {
            'answered_by': user_id_to_name.get(answered_by_id, ''),
            'target_user': user_id_to_name.get(target_user_id, ''),
            'task': task_id_to_title.get(task_id, '')
        }
        # Add all attribute columns
        for attr_name in attr_names:
            row[attr_name] = attrs.get(attr_name, '')
        perception_data.append(row)
    
    pd.DataFrame(perception_data).to_excel(writer, sheet_name='Perception', index=False)
    logger.info(f"  ✅ Exported {len(perception_data)} perception rows (all attributes)")
    
    writer.close()
    output.seek(0)
    
    logger.info("✅ Export complete!")
    return output


def export_template_to_excel(db: Session) -> BytesIO:
    """
    Export an empty template showing the required format for import.
    Uses names, not IDs!
    COMBINED FORMAT: Tasks include all attributes, Perception has all attributes as columns
    Dynamically pulls attributes from the database schema.
    """
    logger.info("📋 Creating import template...")
    
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    
    # Get actual attributes from database
    task_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    task_attr_names = [a.name for a in task_attributes]
    
    user_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.USER
    ).all()
    user_attr_names = [a.name for a in user_attributes]
    
    # Users template with examples
    users_example = pd.DataFrame([
        {'name': 'John Smith', 'email': 'john@company.com', 'team': 'Engineering', 'timezone': 'UTC', 'manager': ''},
        {'name': 'Jane Doe', 'email': 'jane@company.com', 'team': 'Engineering', 'timezone': 'UTC', 'manager': 'John Smith'},
    ])
    users_example.to_excel(writer, sheet_name='Users', index=False)
    
    # Tasks template (COMBINED - with dependencies and all actual attributes)
    task_row_1 = {'title': 'Build feature X', 'description': 'Implement the new feature', 'owner': 'Jane Doe', 'parent': '', 'dependencies': '', 'is_active': True}
    task_row_2 = {'title': 'Write tests for X', 'description': '', 'owner': 'Jane Doe', 'parent': 'Build feature X', 'dependencies': 'Build feature X', 'is_active': True}
    
    # Add all task attributes as columns
    for attr in task_attributes:
        if attr.type == AttributeType.ENUM and attr.allowed_values:
            # Use first allowed value as example
            task_row_1[attr.name] = attr.allowed_values[0] if attr.allowed_values else ''
            task_row_2[attr.name] = attr.allowed_values[1] if len(attr.allowed_values) > 1 else ''
        elif attr.type == AttributeType.INT:
            task_row_1[attr.name] = 5
            task_row_2[attr.name] = 3
        elif attr.type == AttributeType.BOOL:
            task_row_1[attr.name] = True
            task_row_2[attr.name] = False
        else:
            task_row_1[attr.name] = ''
            task_row_2[attr.name] = ''
    
    tasks_example = pd.DataFrame([task_row_1, task_row_2])
    tasks_example.to_excel(writer, sheet_name='Tasks', index=False)
    
    # Default context_config with all variables
    default_context_config = json.dumps({
        "history_size": 2,                    # Number of recent messages to include
        "include_personal_tasks": True,       # Tasks owned by user
        "include_manager_tasks": False,       # Tasks owned by user's manager
        "include_employee_tasks": False,      # Tasks owned by user's employees
        "include_aligned_tasks": False,       # Tasks owned by aligned users
        "include_all_org_tasks": False,       # All tasks in organization
        "include_user_info": True,            # Always included
        "include_manager": True,              # Always included
        "include_employees": False,           # List of user's employees
        "include_aligned_users": False,       # List of aligned users
        "include_all_users": False,           # All users in organization
        "include_pending": True               # Include pending questions
    })
    
    # Prompts template with actual mode names and full context_config
    prompts_example = pd.DataFrame([
        {'mode': 'morning_brief', 'has_pending': False, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
        {'mode': 'morning_brief', 'has_pending': True, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
        {'mode': 'user_question', 'has_pending': False, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
        {'mode': 'user_question', 'has_pending': True, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
        {'mode': 'collect_data', 'has_pending': True, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
        {'mode': 'daily_opening_brief', 'has_pending': False, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
        {'mode': 'daily_questions', 'has_pending': True, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
        {'mode': 'daily_summary', 'has_pending': False, 'prompt_text': 'Your prompt text here...', 'context_config': default_context_config, 'created_by': '', 'notes': ''},
    ])
    prompts_example.to_excel(writer, sheet_name='Prompts', index=False)
    
    # Attributes template - use actual attributes from database
    all_attributes = task_attributes + user_attributes
    attributes_data = []
    for attr in all_attributes:
        attributes_data.append({
            'name': attr.name,
            'label': attr.label,
            'entity_type': attr.entity_type.value,
            'type': attr.type.value,
            'description': attr.description or '',
            'allowed_values': json.dumps(attr.allowed_values) if attr.allowed_values else '',
            'is_required': attr.is_required
        })
    
    if attributes_data:
        attributes_example = pd.DataFrame(attributes_data)
    else:
        # Fallback if no attributes exist
        attributes_example = pd.DataFrame([
            {'name': 'priority', 'label': 'Priority', 'entity_type': 'task', 'type': 'enum', 'description': 'Task priority level', 'allowed_values': '["Critical", "High", "Medium", "Low"]', 'is_required': False},
            {'name': 'status', 'label': 'Status', 'entity_type': 'task', 'type': 'enum', 'description': 'Current task status', 'allowed_values': '["Not started", "In progress", "Done", "Blocked"]', 'is_required': False},
        ])
    attributes_example.to_excel(writer, sheet_name='Attributes', index=False)
    
    # Perception template (COMBINED - all task attributes as columns)
    perception_row_1 = {'answered_by': 'Jane Doe', 'target_user': 'Jane Doe', 'task': 'Build feature X'}
    perception_row_2 = {'answered_by': 'John Smith', 'target_user': 'Jane Doe', 'task': 'Build feature X'}
    
    # Add all task attributes as columns
    for attr in task_attributes:
        if attr.type == AttributeType.ENUM and attr.allowed_values:
            perception_row_1[attr.name] = attr.allowed_values[0] if attr.allowed_values else ''
            perception_row_2[attr.name] = attr.allowed_values[1] if len(attr.allowed_values) > 1 else ''
        elif attr.type == AttributeType.INT:
            perception_row_1[attr.name] = 5
            perception_row_2[attr.name] = 3
        elif attr.type == AttributeType.BOOL:
            perception_row_1[attr.name] = True
            perception_row_2[attr.name] = False
        else:
            perception_row_1[attr.name] = ''
            perception_row_2[attr.name] = ''
    
    perception_example = pd.DataFrame([perception_row_1, perception_row_2])
    perception_example.to_excel(writer, sheet_name='Perception', index=False)
    
    # Add instructions sheet
    instructions = pd.DataFrame({
        'Sheet': ['Users', 'Tasks', 'Prompts', 'Attributes', 'Perception'],
        'Description': [
            'User accounts. manager = name of manager (or empty for top-level)',
            'Tasks with ALL attributes. dependencies = comma-separated task titles. Attributes as columns.',
            'AI prompts. mode = prompt mode name (see examples), has_pending = true/false',
            'Attribute definitions. Define what attributes tasks/users have.',
            'Perception answers. One row per user+task, all attributes as columns.'
        ],
        'Required Fields': [
            'name, team (others optional)',
            'title, owner (others optional, attributes are optional)',
            'mode, has_pending, prompt_text',
            'name, label, entity_type, type',
            'answered_by, target_user, task (attribute columns are optional)'
        ],
        'Notes': [
            'First create users, then managers. Managers must exist before referencing.',
            'Tasks include: title, description, owner, parent, dependencies (comma-sep), is_active, plus ALL attribute columns',
            'Modes: morning_brief, user_question, collect_data, daily_opening_brief, daily_questions, daily_summary',
            'entity_type: task or user. type: string, enum, int, float, bool, date. allowed_values: JSON array for enum.',
            'answered_by = who gave opinion, target_user = task owner, task = task title. Each attribute is a column.'
        ]
    })
    instructions.to_excel(writer, sheet_name='_Instructions', index=False)
    
    # Add context_config reference sheet
    context_config_help = pd.DataFrame({
        'Variable': [
            'history_size',
            'include_personal_tasks',
            'include_manager_tasks',
            'include_employee_tasks',
            'include_aligned_tasks',
            'include_all_org_tasks',
            'include_user_info',
            'include_manager',
            'include_employees',
            'include_aligned_users',
            'include_all_users',
            'include_pending'
        ],
        'Type': ['number', 'boolean', 'boolean', 'boolean', 'boolean', 'boolean', 'boolean', 'boolean', 'boolean', 'boolean', 'boolean', 'boolean'],
        'Default': [2, True, False, False, False, False, True, True, False, False, False, True],
        'Description': [
            'Number of recent chat messages to include in context',
            'Include tasks owned by the current user',
            'Include tasks owned by the user\'s manager',
            'Include tasks owned by the user\'s direct reports',
            'Include tasks owned by users the current user is aligned with',
            'Include ALL tasks in the organization',
            'Include current user info (always on)',
            'Include manager info (always on)',
            'Include list of user\'s direct reports',
            'Include list of aligned users',
            'Include list of all users in organization',
            'Include pending questions in the context'
        ]
    })
    context_config_help.to_excel(writer, sheet_name='_Context_Config', index=False)
    
    writer.close()
    output.seek(0)
    
    logger.info("✅ Template created!")
    return output


# ==============================================================================
# VALIDATION Functions
# ==============================================================================

def parse_import_file(file: BytesIO, filename: str = "") -> Dict[str, pd.DataFrame]:
    """
    Parse import file (Excel or Numbers) into dictionary of DataFrames.
    Returns dict with sheet names as keys and DataFrames as values.
    """
    file_content = file.read()
    file.seek(0)
    
    # Detect file type
    is_numbers = filename.lower().endswith('.numbers') if filename else False
    
    # Also check magic bytes for Numbers files (ZIP format)
    if not is_numbers and file_content[:4] == b'PK\x03\x04':
        # Could be Numbers (which is a ZIP) - try to detect
        try:
            import zipfile
            with zipfile.ZipFile(BytesIO(file_content)) as zf:
                if any('Index/Tables' in name or 'Document.iwa' in name for name in zf.namelist()):
                    is_numbers = True
        except:
            pass
    
    if is_numbers:
        logger.info("📱 Detected Apple Numbers file")
        return convert_numbers_to_dataframes(file_content)
    else:
        logger.info("📊 Detected Excel file")
        excel_file = pd.ExcelFile(BytesIO(file_content))
        sheets = {}
        for sheet_name in excel_file.sheet_names:
            sheets[sheet_name] = pd.read_excel(BytesIO(file_content), sheet_name=sheet_name)
        return sheets


def validate_import_file(file: BytesIO, filename: str = "") -> Dict[str, any]:
    """
    Validate the import file format (Excel or Numbers) before importing.
    """
    logger.info("🔍 Validating import file...")
    
    try:
        # Parse file into DataFrames
        sheets = parse_import_file(file, filename)
        sheet_names = list(sheets.keys())
        
        errors = []
        warnings = []
        
        # Required sheets
        if 'Users' not in sheet_names:
            errors.append("Missing required sheet: 'Users'")
        
        if 'Tasks' not in sheet_names:
            errors.append("Missing required sheet: 'Tasks'")
        
        if errors:
            return {'valid': False, 'errors': errors, 'warnings': warnings, 'sheets': sheets}
        
        # Validate Users sheet
        users_df = sheets['Users']
        if 'name' not in users_df.columns:
            errors.append("Users sheet missing required column: 'name'")
        
        # Validate Tasks sheet
        tasks_df = sheets['Tasks']
        required_task_cols = ['title', 'owner']
        for col in required_task_cols:
            if col not in tasks_df.columns:
                errors.append(f"Tasks sheet missing required column: '{col}'")
        
        # Validate optional sheets if present
        if 'Prompts' in sheet_names:
            prompts_df = sheets['Prompts']
            required_prompt_cols = ['mode', 'has_pending', 'prompt_text']
            for col in required_prompt_cols:
                if col not in prompts_df.columns:
                    errors.append(f"Prompts sheet missing required column: '{col}'")
        
        if errors:
            return {'valid': False, 'errors': errors, 'warnings': warnings, 'sheets': sheets}
        
        # Check for data
        if len(users_df) == 0:
            warnings.append("Users sheet is empty")
        if len(tasks_df) == 0:
            warnings.append("Tasks sheet is empty")
        
        logger.info(f"✅ Validation complete: {len(errors)} errors, {len(warnings)} warnings")
        return {'valid': True, 'errors': [], 'warnings': warnings, 'sheets': sheets}
        
    except Exception as e:
        logger.error(f"❌ Validation error: {e}")
        import traceback
        traceback.print_exc()
        return {'valid': False, 'errors': [f"File format error: {str(e)}"], 'warnings': [], 'sheets': {}}


# ==============================================================================
# IMPORT Functions
# ==============================================================================

def import_data_from_excel(db: Session, file: BytesIO, replace_mode: bool = False, filename: str = "") -> Dict[str, any]:
    """
    Import data from Excel or Numbers file.
    Uses NAMES for lookups, not IDs.
    Alignments and Answers are NOT imported - they are calculated automatically.
    Supports: .xlsx (Excel) and .numbers (Apple Numbers) files.
    """
    logger.info(f"📥 Starting data import (replace_mode={replace_mode}, file={filename})...")
    
    # Validate first (this also parses the file)
    file.seek(0)
    validation = validate_import_file(file, filename)
    
    if not validation['valid']:
        logger.error(f"❌ Validation failed: {validation['errors']}")
        return {
            'success': False,
            'errors': validation['errors'],
            'message': 'File validation failed. Please fix the errors and try again.'
        }
    
    try:
        # Use pre-parsed sheets from validation
        sheets = validation['sheets']
        sheet_names = list(sheets.keys())
        
        stats = {
            'users_imported': 0,
            'users_skipped': 0,
            'tasks_imported': 0,
            'tasks_skipped': 0,
            'dependencies_imported': 0,
            'prompts_imported': 0,
            'attributes_imported': 0,
            'attributes_skipped': 0,
            'perception_imported': 0,
            'perception_skipped': 0
        }
        
        # In replace mode, delete existing users and tasks (but NOT prompts)
        if replace_mode:
            logger.info("🗑️  REPLACE MODE: Deleting existing users and tasks...")
            
            # Delete in correct order to respect foreign keys
            db.query(SimilarityScore).delete()
            db.query(MessageDebugData).delete()  # Must be before ChatMessage
            db.query(DailySyncSession).delete()
            db.query(ChatMessage).delete()
            db.query(ChatThread).delete()
            db.query(QuestionLog).delete()
            db.query(AlignmentEdge).delete()
            db.query(TaskDependency).delete()
            db.query(AttributeAnswer).delete()
            db.query(Task).delete()
            db.query(User).delete()
            db.commit()
            logger.info("  ✅ Existing data deleted")
        
        # =====================================================================
        # PASS 1: Import Users (without manager relationships)
        # =====================================================================
        logger.info("👥 Importing users (pass 1 - creating users)...")
        users_df = sheets['Users']
        
        name_to_user = {}
        
        for _, row in users_df.iterrows():
            # Handle None values properly
            raw_name = row.get('name')
            if raw_name is None or pd.isna(raw_name):
                continue
            name = str(raw_name).strip()
            # Skip empty names or "None" string
            if not name or name.lower() == 'none':
                continue
            
            # Check if user exists (by name)
            if not replace_mode:
                existing = db.query(User).filter(User.name == name).first()
                if existing:
                    name_to_user[name] = existing
                    stats['users_skipped'] += 1
                    logger.info(f"  ⏭️  User '{name}' already exists, skipping")
                    continue
            
            new_user = User(
                id=uuid4(),
                name=name,
                email=str(row.get('email', '')) if pd.notna(row.get('email')) else None,
                team=str(row.get('team', '')) if pd.notna(row.get('team')) else None,
                timezone=str(row.get('timezone', 'UTC')) if pd.notna(row.get('timezone')) else 'UTC',
                manager_id=None  # Set in pass 2
            )
            db.add(new_user)
            db.flush()
            
            name_to_user[name] = new_user
            stats['users_imported'] += 1
        
        db.commit()
        logger.info(f"  ✅ Created {stats['users_imported']} users")
        
        # =====================================================================
        # PASS 2: Update Manager Relationships
        # =====================================================================
        logger.info("👥 Importing users (pass 2 - setting managers)...")
        # users_df already loaded from sheets
        
        for _, row in users_df.iterrows():
            name = str(row['name']).strip()
            manager_name = str(row.get('manager', '')) if pd.notna(row.get('manager')) else ''
            
            if manager_name and manager_name.strip():
                manager_name = manager_name.strip()
                user = name_to_user.get(name)
                manager = name_to_user.get(manager_name)
                
                if user and manager:
                    user.manager_id = manager.id
                elif manager_name:
                    logger.warning(f"  ⚠️  Manager '{manager_name}' not found for user '{name}'")
        
        db.commit()
        logger.info("  ✅ Manager relationships set")
        
        # =====================================================================
        # PASS 3: Import Tasks (without parent relationships)
        # =====================================================================
        logger.info("📋 Importing tasks (pass 1 - creating tasks)...")
        tasks_df = sheets['Tasks']
        
        title_to_task = {}
        
        for _, row in tasks_df.iterrows():
            title = str(row['title']).strip()
            owner_name = str(row['owner']).strip() if pd.notna(row.get('owner')) else ''
            
            if not title or not owner_name:
                continue
            
            # Find owner
            owner = name_to_user.get(owner_name)
            if not owner:
                logger.warning(f"  ⚠️  Owner '{owner_name}' not found for task '{title}', skipping")
                stats['tasks_skipped'] += 1
                continue
            
            # Check if task exists (by title)
            if not replace_mode:
                existing = db.query(Task).filter(Task.title == title).first()
                if existing:
                    title_to_task[title] = existing
                    stats['tasks_skipped'] += 1
                    logger.info(f"  ⏭️  Task '{title}' already exists, skipping")
                    continue
            
            new_task = Task(
                id=uuid4(),
                title=title,
                description=str(row.get('description', '')) if pd.notna(row.get('description')) else None,
                owner_user_id=owner.id,
                parent_id=None,  # Set in pass 2
                is_active=bool(row.get('is_active', True)) if pd.notna(row.get('is_active')) else True
            )
            db.add(new_task)
            db.flush()
            
            title_to_task[title] = new_task
            stats['tasks_imported'] += 1
        
        db.commit()
        logger.info(f"  ✅ Created {stats['tasks_imported']} tasks")
        
        # =====================================================================
        # PASS 4: Update Task Parent Relationships and Dependencies (from Tasks sheet)
        # =====================================================================
        logger.info("📋 Importing tasks (pass 2 - setting parents and dependencies)...")
        # tasks_df already loaded from sheets
        
        # Get attribute definitions for creating owner answers
        all_attrs = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == EntityType.TASK
        ).all()
        attr_name_to_id = {a.name: a.id for a in all_attrs}
        attr_names = list(attr_name_to_id.keys())
        
        for _, row in tasks_df.iterrows():
            title = str(row['title']).strip()
            task = title_to_task.get(title)
            if not task:
                continue
            
            owner = name_to_user.get(str(row['owner']).strip())
            
            # Set parent
            parent_title = str(row.get('parent', '')) if pd.notna(row.get('parent')) else ''
            if parent_title and parent_title.strip():
                parent_title = parent_title.strip()
                parent = title_to_task.get(parent_title)
                if parent:
                    task.parent_id = parent.id
                else:
                    logger.warning(f"  ⚠️  Parent task '{parent_title}' not found for task '{title}'")
            
            # Set dependencies (comma-separated in 'dependencies' column)
            deps_str = str(row.get('dependencies', '')) if pd.notna(row.get('dependencies')) else ''
            if deps_str.strip():
                dep_titles = [d.strip() for d in deps_str.split(',') if d.strip()]
                for dep_title in dep_titles:
                    dep_task = title_to_task.get(dep_title)
                    if dep_task:
                        new_dep = TaskDependency(
                            id=uuid4(),
                            task_id=task.id,
                            depends_on_task_id=dep_task.id
                        )
                        db.add(new_dep)
                        stats['dependencies_imported'] += 1
                    else:
                        logger.warning(f"  ⚠️  Dependency '{dep_title}' not found for task '{title}'")
            
            # Create owner's attribute answers from task columns
            if owner:
                for attr_name in attr_names:
                    if attr_name in row and pd.notna(row.get(attr_name)):
                        value = str(row[attr_name]).strip()
                        if value:
                            attr_id = attr_name_to_id.get(attr_name)
                            if attr_id:
                                new_answer = AttributeAnswer(
                                    id=uuid4(),
                                    answered_by_user_id=owner.id,
                                    target_user_id=owner.id,
                                    task_id=task.id,
                                    attribute_id=attr_id,
                                    value=value,
                                    refused=False
                                )
                                db.add(new_answer)
                                stats['perception_imported'] += 1
        
        db.commit()
        logger.info("  ✅ Parent relationships, dependencies, and owner answers set")
        
        # =====================================================================
        # Import Prompts (add as new versions)
        # =====================================================================
        if 'Prompts' in sheet_names:
            logger.info("📝 Importing prompts...")
            prompts_df = sheets['Prompts']
            
            for _, row in prompts_df.iterrows():
                mode = str(row['mode']).strip()
                has_pending = bool(row.get('has_pending', False))
                prompt_text = str(row.get('prompt_text', ''))
                
                if not mode or not prompt_text:
                    continue
                
                # Get next version number for this mode
                max_version = db.query(PromptTemplate).filter(
                    PromptTemplate.mode == mode,
                    PromptTemplate.has_pending == has_pending
                ).count()
                next_version = max_version + 1
                
                # Deactivate previous prompts for this mode
                db.query(PromptTemplate).filter(
                    PromptTemplate.mode == mode,
                    PromptTemplate.has_pending == has_pending
                ).update({'is_active': False})
                
                # Parse context_config
                context_config = {}
                if pd.notna(row.get('context_config')):
                    try:
                        context_config = json.loads(str(row['context_config']))
                    except:
                        context_config = {}
                
                new_prompt = PromptTemplate(
                    id=uuid4(),
                    mode=mode,
                    has_pending=has_pending,
                    prompt_text=prompt_text,
                    context_config=context_config,
                    version=next_version,
                    is_active=True,
                    created_by=str(row.get('created_by', 'Import')) if pd.notna(row.get('created_by')) else 'Import',
                    notes=str(row.get('notes', '')) if pd.notna(row.get('notes')) else f'Imported on {datetime.utcnow().isoformat()}'
                )
                db.add(new_prompt)
                stats['prompts_imported'] += 1
            
            db.commit()
            logger.info(f"  ✅ Imported {stats['prompts_imported']} prompts")
        
        # =====================================================================
        # Import Attribute Definitions
        # =====================================================================
        if 'Attributes' in sheet_names:
            logger.info("📊 Importing attribute definitions...")
            attrs_df = sheets['Attributes']
            stats['attributes_imported'] = 0
            stats['attributes_skipped'] = 0
            
            for _, row in attrs_df.iterrows():
                name = str(row['name']).strip() if pd.notna(row.get('name')) else ''
                if not name:
                    continue
                
                entity_type_str = str(row.get('entity_type', 'task')).strip().lower()
                entity_type = EntityType.TASK if entity_type_str == 'task' else EntityType.USER
                
                # Check if attribute already exists
                existing = db.query(AttributeDefinition).filter(
                    AttributeDefinition.name == name,
                    AttributeDefinition.entity_type == entity_type
                ).first()
                
                if existing:
                    logger.info(f"  ⏭️  Attribute '{name}' already exists, skipping")
                    stats['attributes_skipped'] += 1
                    continue
                
                # Parse type
                type_str = str(row.get('type', 'string')).strip().lower()
                attr_type_map = {
                    'string': AttributeType.STRING,
                    'enum': AttributeType.ENUM,
                    'int': AttributeType.INT,
                    'float': AttributeType.FLOAT,
                    'bool': AttributeType.BOOL,
                    'date': AttributeType.DATE
                }
                attr_type = attr_type_map.get(type_str, AttributeType.STRING)
                
                # Parse allowed_values
                allowed_values = None
                if pd.notna(row.get('allowed_values')) and row.get('allowed_values'):
                    try:
                        allowed_values = json.loads(str(row['allowed_values']))
                    except:
                        allowed_values = None
                
                new_attr = AttributeDefinition(
                    entity_type=entity_type,
                    name=name,
                    label=str(row.get('label', name)) if pd.notna(row.get('label')) else name,
                    type=attr_type,
                    description=str(row.get('description', '')) if pd.notna(row.get('description')) else None,
                    allowed_values=allowed_values,
                    is_required=bool(row.get('is_required', False)) if pd.notna(row.get('is_required')) else False
                )
                db.add(new_attr)
                stats['attributes_imported'] += 1
            
            db.commit()
            logger.info(f"  ✅ Imported {stats['attributes_imported']} attributes ({stats['attributes_skipped']} skipped)")
        
        # =====================================================================
        # Import Perception Data (COMBINED - all attributes as columns)
        # =====================================================================
        if 'Perception' in sheet_names:
            logger.info("💭 Importing perception data (combined format)...")
            perception_df = sheets['Perception']
            
            # Build attribute name to ID map
            all_attrs = db.query(AttributeDefinition).filter(
                AttributeDefinition.entity_type == EntityType.TASK
            ).all()
            attr_name_to_id = {a.name: a.id for a in all_attrs}
            attr_names = list(attr_name_to_id.keys())
            
            for _, row in perception_df.iterrows():
                answered_by_name = str(row.get('answered_by', '')).strip() if pd.notna(row.get('answered_by')) else ''
                target_user_name = str(row.get('target_user', '')).strip() if pd.notna(row.get('target_user')) else ''
                task_title = str(row.get('task', '')).strip() if pd.notna(row.get('task')) else ''
                
                if not answered_by_name or not target_user_name or not task_title:
                    stats['perception_skipped'] += 1
                    continue
                
                # Lookup IDs
                answered_by = name_to_user.get(answered_by_name)
                target_user = name_to_user.get(target_user_name)
                task = title_to_task.get(task_title)
                
                if not answered_by:
                    logger.warning(f"  ⚠️  answered_by user '{answered_by_name}' not found, skipping row")
                    stats['perception_skipped'] += 1
                    continue
                if not target_user:
                    logger.warning(f"  ⚠️  target_user '{target_user_name}' not found, skipping row")
                    stats['perception_skipped'] += 1
                    continue
                if not task:
                    logger.warning(f"  ⚠️  task '{task_title}' not found, skipping row")
                    stats['perception_skipped'] += 1
                    continue
                
                # Process each attribute column
                for attr_name in attr_names:
                    if attr_name in row and pd.notna(row.get(attr_name)):
                        value = str(row[attr_name]).strip()
                        if value:
                            attr_id = attr_name_to_id.get(attr_name)
                            if attr_id:
                                new_answer = AttributeAnswer(
                                    id=uuid4(),
                                    answered_by_user_id=answered_by.id,
                                    target_user_id=target_user.id,
                                    task_id=task.id,
                                    attribute_id=attr_id,
                                    value=value,
                                    refused=False
                                )
                                db.add(new_answer)
                                stats['perception_imported'] += 1
            
            db.commit()
            logger.info(f"  ✅ Imported {stats['perception_imported']} perception answers ({stats['perception_skipped']} rows skipped)")
        
        # =====================================================================
        # Create Alignment Edges (based on org structure + task dependencies)
        # =====================================================================
        logger.info("🔗 Creating alignment edges...")
        stats['alignment_edges_created'] = 0
        
        # Track created edges to avoid duplicates
        created_edges = set()
        
        def add_edge(source_id, target_id):
            """Add an alignment edge if it doesn't exist"""
            key = (str(source_id), str(target_id))
            if key not in created_edges and source_id != target_id:
                db.add(AlignmentEdge(source_user_id=source_id, target_user_id=target_id))
                created_edges.add(key)
                return 1
            return 0
        
        # Get all users
        all_users = list(name_to_user.values())
        all_tasks = list(title_to_task.values())
        
        for user in all_users:
            # 1. Manager alignment (bidirectional)
            if user.manager_id:
                manager = db.query(User).filter(User.id == user.manager_id).first()
                if manager:
                    stats['alignment_edges_created'] += add_edge(user.id, manager.id)
                    stats['alignment_edges_created'] += add_edge(manager.id, user.id)
            
            # 2. Employees alignment (direct reports)
            employees = [u for u in all_users if u.manager_id == user.id]
            for employee in employees:
                stats['alignment_edges_created'] += add_edge(user.id, employee.id)
                stats['alignment_edges_created'] += add_edge(employee.id, user.id)
            
            # 3. Teammates alignment (same manager)
            if user.manager_id:
                teammates = [u for u in all_users if u.manager_id == user.manager_id and u.id != user.id]
                for teammate in teammates:
                    stats['alignment_edges_created'] += add_edge(user.id, teammate.id)
        
        # 4. Task dependency connections
        # Get all task dependencies
        all_dependencies = db.query(TaskDependency).all()
        
        for dep in all_dependencies:
            task = db.query(Task).filter(Task.id == dep.task_id).first()
            depends_on_task = db.query(Task).filter(Task.id == dep.depends_on_task_id).first()
            
            if task and depends_on_task and task.owner_user_id and depends_on_task.owner_user_id:
                if task.owner_user_id != depends_on_task.owner_user_id:
                    # Create bidirectional alignment between task owners
                    stats['alignment_edges_created'] += add_edge(task.owner_user_id, depends_on_task.owner_user_id)
                    stats['alignment_edges_created'] += add_edge(depends_on_task.owner_user_id, task.owner_user_id)
        
        db.commit()
        logger.info(f"  ✅ Created {stats['alignment_edges_created']} alignment edges")
        
        # =====================================================================
        # Recalculate Similarity Scores
        # =====================================================================
        logger.info("📊 Recalculating similarity scores...")
        try:
            from app.services.similarity_cache import recalculate_all_similarity_scores
            scores_created = recalculate_all_similarity_scores(db)
            stats['similarity_scores_calculated'] = scores_created
            logger.info(f"  ✅ Calculated {scores_created} similarity scores")
        except Exception as e:
            logger.warning(f"  ⚠️  Similarity calculation skipped: {e}")
            stats['similarity_scores_calculated'] = 0
        
        logger.info(f"✅ Import complete! Stats: {stats}")
        return {
            'success': True,
            'stats': stats,
            'warnings': validation['warnings'],
            'message': 'Data imported successfully!'
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'errors': [f"Import failed: {str(e)}"],
            'message': 'Import failed. Database was not modified.'
        }
