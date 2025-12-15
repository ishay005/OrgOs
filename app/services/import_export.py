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
    User, Task, TaskDependency, TaskRelevantUser, PromptTemplate, AttributeAnswer,
    DailySyncSession, ChatThread, ChatMessage, QuestionLog, SimilarityScore,
    MessageDebugData, AttributeDefinition, EntityType, AttributeType,
    TaskState, TaskAlias, TaskMergeProposal, TaskDependencyV2, DependencyStatus,
    AlternativeDependencyProposal, PendingDecision
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
    
    # Get all relevant users per task
    relevant_users = db.query(TaskRelevantUser).all()
    task_relevant = {}
    for r in relevant_users:
        task_title = task_id_to_title.get(r.task_id, '')
        user_name = user_id_to_name.get(r.user_id, '')
        if task_title and user_name:
            if task_title not in task_relevant:
                task_relevant[task_title] = []
            task_relevant[task_title].append(user_name)
    
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
    # Also include state machine fields
    tasks_data = []
    for t in tasks:
        owner_id = t.owner_user_id
        creator_name = user_id_to_name.get(t.created_by_user_id, '') if hasattr(t, 'created_by_user_id') and t.created_by_user_id else ''
        task_state = t.state.value if hasattr(t, 'state') and t.state else 'ACTIVE'
        
        task_row = {
            'title': t.title,
            'description': t.description or '',
            'owner': user_id_to_name.get(owner_id, ''),
            'created_by': creator_name,
            'state': task_state,
            'parent': task_id_to_title.get(t.parent_id, '') if t.parent_id else '',
            'dependencies': ', '.join(task_deps.get(t.title, [])),
            'relevant_users': ', '.join(task_relevant.get(t.title, [])),
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
    
    # ============ NEW STATE MACHINE TABLES ============
    
    # Export Task Aliases
    try:
        from app.models import TaskAlias
        aliases = db.query(TaskAlias).all()
        alias_data = []
        for alias in aliases:
            canonical_task = db.query(Task).filter(Task.id == alias.canonical_task_id).first()
            creator = db.query(User).filter(User.id == alias.alias_created_by_user_id).first()
            alias_data.append({
                'Canonical Task': canonical_task.title if canonical_task else '',
                'Alias Title': alias.alias_title,
                'Alias Created By': creator.name if creator else '',
                'Created At': alias.created_at.isoformat() if alias.created_at else ''
            })
        pd.DataFrame(alias_data).to_excel(writer, sheet_name='Task Aliases', index=False)
        logger.info(f"  ✅ Exported {len(alias_data)} task aliases")
    except Exception as e:
        logger.warning(f"  ⚠️ Could not export Task Aliases: {e}")
    
    # Export Task Merge Proposals
    try:
        from app.models import TaskMergeProposal
        merge_proposals = db.query(TaskMergeProposal).all()
        merge_data = []
        for mp in merge_proposals:
            from_task = db.query(Task).filter(Task.id == mp.from_task_id).first()
            to_task = db.query(Task).filter(Task.id == mp.to_task_id).first()
            proposed_by = db.query(User).filter(User.id == mp.proposed_by_user_id).first()
            rejected_by = db.query(User).filter(User.id == mp.rejected_by_user_id).first() if mp.rejected_by_user_id else None
            merge_data.append({
                'From Task': from_task.title if from_task else '',
                'To Task': to_task.title if to_task else '',
                'Proposed By': proposed_by.name if proposed_by else '',
                'Proposal Reason': mp.proposal_reason or '',
                'Status': mp.status.value if mp.status else '',
                'Rejected By': rejected_by.name if rejected_by else '',
                'Rejected Reason': mp.rejected_reason or '',
                'Created At': mp.created_at.isoformat() if mp.created_at else ''
            })
        pd.DataFrame(merge_data).to_excel(writer, sheet_name='Merge Proposals', index=False)
        logger.info(f"  ✅ Exported {len(merge_data)} merge proposals")
    except Exception as e:
        logger.warning(f"  ⚠️ Could not export Merge Proposals: {e}")
    
    # Export Task Dependencies V2
    try:
        from app.models import TaskDependencyV2
        dependencies = db.query(TaskDependencyV2).all()
        dep_data = []
        for dep in dependencies:
            downstream = db.query(Task).filter(Task.id == dep.downstream_task_id).first()
            upstream = db.query(Task).filter(Task.id == dep.upstream_task_id).first()
            created_by = db.query(User).filter(User.id == dep.created_by_user_id).first() if dep.created_by_user_id else None
            accepted_by = db.query(User).filter(User.id == dep.accepted_by_user_id).first() if dep.accepted_by_user_id else None
            rejected_by = db.query(User).filter(User.id == dep.rejected_by_user_id).first() if dep.rejected_by_user_id else None
            removed_by = db.query(User).filter(User.id == dep.removed_by_user_id).first() if dep.removed_by_user_id else None
            dep_data.append({
                'Downstream Task': downstream.title if downstream else '',
                'Upstream Task': upstream.title if upstream else '',
                'Status': dep.status.value if dep.status else '',
                'Created By': created_by.name if created_by else '',
                'Accepted By': accepted_by.name if accepted_by else '',
                'Accepted At': dep.accepted_at.isoformat() if dep.accepted_at else '',
                'Rejected By': rejected_by.name if rejected_by else '',
                'Rejected At': dep.rejected_at.isoformat() if dep.rejected_at else '',
                'Rejected Reason': dep.rejected_reason or '',
                'Removed By': removed_by.name if removed_by else '',
                'Removed At': dep.removed_at.isoformat() if dep.removed_at else ''
            })
        pd.DataFrame(dep_data).to_excel(writer, sheet_name='Dependencies V2', index=False)
        logger.info(f"  ✅ Exported {len(dep_data)} dependencies (v2)")
    except Exception as e:
        logger.warning(f"  ⚠️ Could not export Dependencies V2: {e}")
    
    # Export Alternative Dependency Proposals
    try:
        from app.models import AlternativeDependencyProposal, TaskDependencyV2
        alt_proposals = db.query(AlternativeDependencyProposal).all()
        alt_data = []
        for ap in alt_proposals:
            original_dep = db.query(TaskDependencyV2).filter(TaskDependencyV2.id == ap.original_dependency_id).first() if ap.original_dependency_id else None
            downstream = db.query(Task).filter(Task.id == ap.downstream_task_id).first()
            orig_upstream = db.query(Task).filter(Task.id == ap.original_upstream_task_id).first()
            suggested_upstream = db.query(Task).filter(Task.id == ap.suggested_upstream_task_id).first()
            proposed_by = db.query(User).filter(User.id == ap.proposed_by_user_id).first()
            rejected_by = db.query(User).filter(User.id == ap.rejected_by_user_id).first() if ap.rejected_by_user_id else None
            alt_data.append({
                'Downstream Task': downstream.title if downstream else '',
                'Original Upstream Task': orig_upstream.title if orig_upstream else '',
                'Suggested Upstream Task': suggested_upstream.title if suggested_upstream else '',
                'Proposed By': proposed_by.name if proposed_by else '',
                'Proposal Reason': ap.proposal_reason or '',
                'Status': ap.status.value if ap.status else '',
                'Rejected By': rejected_by.name if rejected_by else '',
                'Rejected Reason': ap.rejected_reason or ''
            })
        pd.DataFrame(alt_data).to_excel(writer, sheet_name='Alt Dep Proposals', index=False)
        logger.info(f"  ✅ Exported {len(alt_data)} alternative dependency proposals")
    except Exception as e:
        logger.warning(f"  ⚠️ Could not export Alternative Dependency Proposals: {e}")
    
    # Export Pending Decisions
    try:
        from app.models import PendingDecision
        decisions = db.query(PendingDecision).all()
        decision_data = []
        for d in decisions:
            user = db.query(User).filter(User.id == d.user_id).first()
            task = db.query(Task).filter(Task.id == d.task_id).first() if d.task_id else None
            decision_data.append({
                'User': user.name if user else '',
                'Decision Type': d.decision_type.value if d.decision_type else '',
                'Task': task.title if task else '',
                'Related Entity ID': str(d.related_entity_id) if d.related_entity_id else '',
                'Description': d.description or '',
                'Created At': d.created_at.isoformat() if d.created_at else '',
                'Resolved At': d.resolved_at.isoformat() if d.resolved_at else ''
            })
        pd.DataFrame(decision_data).to_excel(writer, sheet_name='Pending Decisions', index=False)
        logger.info(f"  ✅ Exported {len(decision_data)} pending decisions")
    except Exception as e:
        logger.warning(f"  ⚠️ Could not export Pending Decisions: {e}")
    
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
    task_row_1 = {'title': 'Build feature X', 'description': 'Implement the new feature', 'owner': 'Jane Doe', 'parent': '', 'dependencies': '', 'relevant_users': 'John Smith', 'is_active': True}
    task_row_2 = {'title': 'Write tests for X', 'description': '', 'owner': 'Jane Doe', 'parent': 'Build feature X', 'dependencies': 'Build feature X', 'relevant_users': 'John Smith, Jane Doe', 'is_active': True}
    
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
        'Sheet': [
            'Users', 'Tasks', 'Prompts', 'Attributes', 'Perception',
            'Task Aliases', 'Merge Proposals', 'Dependencies V2', 'Alt Dep Proposals', 'Pending Decisions'
        ],
        'Description': [
            'User accounts. manager = name of manager (or empty for top-level)',
            'Tasks with ALL attributes. dependencies + relevant_users = comma-separated names.',
            'AI prompts. mode = prompt mode name (see examples), has_pending = true/false',
            'Attribute definitions. Define what attributes tasks/users have.',
            'Perception answers. One row per user+task, all attributes as columns.',
            'Aliases for merged tasks. Maps merged task titles to canonical tasks.',
            'Task merge proposals. When users suggest merging duplicate tasks.',
            'Task dependencies with state. Status: PROPOSED, CONFIRMED, REJECTED, REMOVED.',
            'Alternative dependency proposals. Suggesting different upstream tasks.',
            'Pending user decisions. Tasks/merges/deps waiting for user action.'
        ],
        'Required Fields': [
            'name, team (others optional)',
            'title, owner (others optional, attributes are optional)',
            'mode, has_pending, prompt_text',
            'name, label, entity_type, type',
            'answered_by, target_user, task (attribute columns are optional)',
            'Canonical Task, Alias Title, Alias Created By',
            'From Task, To Task, Proposed By, Status',
            'Downstream Task, Upstream Task, Status, Created By',
            'Downstream Task, Original Upstream, Suggested Upstream, Proposed By, Status',
            'User, Decision Type, Task'
        ],
        'Notes': [
            'First create users, then managers. Managers must exist before referencing.',
            'Tasks include: title, description, owner, parent, dependencies, relevant_users (comma-sep user names), is_active, plus attribute columns',
            'Modes: morning_brief, user_question, collect_data, daily_opening_brief, daily_questions, daily_summary',
            'entity_type: task or user. type: string, enum, int, float, bool, date. allowed_values: JSON array for enum.',
            'answered_by = who gave opinion, target_user = task owner, task = task title. Each attribute is a column.',
            'When tasks are merged, original title becomes alias pointing to canonical.',
            'Status: PROPOSED (waiting), ACCEPTED (merged), REJECTED (denied).',
            'Downstream depends on Upstream. Status tracks dep lifecycle.',
            'Propose alternative upstream when current dep is wrong.',
            'Decision Types: TASK_ACCEPTANCE, MERGE_CONSENT, DEPENDENCY_ACCEPTANCE, ALTERNATIVE_DEP_ACCEPTANCE.'
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
    
    # ============ NEW STATE MACHINE TEMPLATE SHEETS ============
    
    # Task Aliases template
    task_aliases_example = pd.DataFrame([
        {'Canonical Task': 'Build feature X', 'Alias Title': 'Feature X Development', 'Alias Created By': 'Jane Doe'},
    ])
    task_aliases_example.to_excel(writer, sheet_name='Task Aliases', index=False)
    
    # Merge Proposals template
    merge_proposals_example = pd.DataFrame([
        {
            'From Task': 'Duplicate task name', 
            'To Task': 'Build feature X', 
            'Proposed By': 'John Smith', 
            'Proposal Reason': 'These tasks are duplicates', 
            'Status': 'PROPOSED'
        },
    ])
    merge_proposals_example.to_excel(writer, sheet_name='Merge Proposals', index=False)
    
    # Dependencies V2 template
    dependencies_v2_example = pd.DataFrame([
        {
            'Downstream Task': 'Write tests for X', 
            'Upstream Task': 'Build feature X', 
            'Status': 'CONFIRMED', 
            'Created By': 'Jane Doe'
        },
        {
            'Downstream Task': 'Deploy feature X', 
            'Upstream Task': 'Write tests for X', 
            'Status': 'PROPOSED', 
            'Created By': 'John Smith'
        },
    ])
    dependencies_v2_example.to_excel(writer, sheet_name='Dependencies V2', index=False)
    
    # Alternative Dependency Proposals template
    alt_dep_proposals_example = pd.DataFrame([
        {
            'Downstream Task': 'Deploy feature X',
            'Original Upstream Task': 'Write tests for X',
            'Suggested Upstream Task': 'Build feature X',
            'Proposed By': 'Jane Doe',
            'Proposal Reason': 'Tests can be done in parallel',
            'Status': 'PROPOSED'
        },
    ])
    alt_dep_proposals_example.to_excel(writer, sheet_name='Alt Dep Proposals', index=False)
    
    # Pending Decisions template
    pending_decisions_example = pd.DataFrame([
        {
            'User': 'Jane Doe',
            'Decision Type': 'TASK_ACCEPTANCE',
            'Task': 'Build feature X',
            'Description': 'Accept this task assigned to you?'
        },
    ])
    pending_decisions_example.to_excel(writer, sheet_name='Pending Decisions', index=False)
    
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
            db.query(TaskDependency).delete()
            db.query(TaskRelevantUser).delete()  # Delete relevant user associations
            db.query(AttributeAnswer).delete()
            
            # Delete new state machine tables
            try:
                from app.models import PendingDecision, AlternativeDependencyProposal, TaskDependencyV2, TaskMergeProposal, TaskAlias
                db.query(PendingDecision).delete()
                db.query(AlternativeDependencyProposal).delete()
                db.query(TaskDependencyV2).delete()
                db.query(TaskMergeProposal).delete()
                db.query(TaskAlias).delete()
            except Exception as e:
                logger.warning(f"  ⚠️  Could not delete state machine tables: {e}")
            
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
            
            # Set relevant users (comma-separated in 'relevant_users' column)
            relevant_str = str(row.get('relevant_users', '')) if pd.notna(row.get('relevant_users')) else ''
            if relevant_str.strip():
                relevant_names = [r.strip() for r in relevant_str.split(',') if r.strip()]
                for relevant_name in relevant_names:
                    relevant_user = name_to_user.get(relevant_name)
                    if relevant_user:
                        new_relevant = TaskRelevantUser(
                            id=uuid4(),
                            task_id=task.id,
                            user_id=relevant_user.id,
                            added_by_user_id=owner.id if owner else None
                        )
                        db.add(new_relevant)
                        if 'relevant_users_imported' not in stats:
                            stats['relevant_users_imported'] = 0
                        stats['relevant_users_imported'] += 1
                    else:
                        logger.warning(f"  ⚠️  Relevant user '{relevant_name}' not found for task '{title}'")
            
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
        # Import Dependencies V2 (State Machine Dependencies)
        # =====================================================================
        if 'Dependencies V2' in sheet_names:
            logger.info("🔗 Importing dependencies v2...")
            try:
                from app.models import TaskDependencyV2, DependencyStatus
                deps_df = sheets['Dependencies V2']
                stats['dependencies_v2_imported'] = 0
                
                for _, row in deps_df.iterrows():
                    downstream_title = str(row.get('Downstream Task', '')).strip() if pd.notna(row.get('Downstream Task')) else ''
                    upstream_title = str(row.get('Upstream Task', '')).strip() if pd.notna(row.get('Upstream Task')) else ''
                    status_str = str(row.get('Status', 'CONFIRMED')).strip().upper() if pd.notna(row.get('Status')) else 'CONFIRMED'
                    created_by_name = str(row.get('Created By', '')).strip() if pd.notna(row.get('Created By')) else ''
                    
                    if not downstream_title or not upstream_title:
                        continue
                    
                    downstream = title_to_task.get(downstream_title)
                    upstream = title_to_task.get(upstream_title)
                    created_by = name_to_user.get(created_by_name) if created_by_name else None
                    
                    if not downstream or not upstream:
                        logger.warning(f"  ⚠️  Tasks not found for dependency {downstream_title} -> {upstream_title}")
                        continue
                    
                    # Map status string to enum
                    status_map = {
                        'PROPOSED': DependencyStatus.PROPOSED,
                        'CONFIRMED': DependencyStatus.CONFIRMED,
                        'REJECTED': DependencyStatus.REJECTED,
                        'REMOVED': DependencyStatus.REMOVED
                    }
                    status = status_map.get(status_str, DependencyStatus.CONFIRMED)
                    
                    # Check if dep already exists
                    existing = db.query(TaskDependencyV2).filter(
                        TaskDependencyV2.downstream_task_id == downstream.id,
                        TaskDependencyV2.upstream_task_id == upstream.id
                    ).first()
                    
                    if not existing:
                        new_dep = TaskDependencyV2(
                            id=uuid4(),
                            downstream_task_id=downstream.id,
                            upstream_task_id=upstream.id,
                            status=status,
                            created_by_user_id=created_by.id if created_by else None
                        )
                        db.add(new_dep)
                        stats['dependencies_v2_imported'] += 1
                
                db.commit()
                logger.info(f"  ✅ Imported {stats['dependencies_v2_imported']} dependencies v2")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not import Dependencies V2: {e}")
        
        # =====================================================================
        # Import Task Aliases
        # =====================================================================
        if 'Task Aliases' in sheet_names:
            logger.info("📎 Importing task aliases...")
            try:
                from app.models import TaskAlias
                aliases_df = sheets['Task Aliases']
                stats['aliases_imported'] = 0
                
                for _, row in aliases_df.iterrows():
                    canonical_title = str(row.get('Canonical Task', '')).strip() if pd.notna(row.get('Canonical Task')) else ''
                    alias_title = str(row.get('Alias Title', '')).strip() if pd.notna(row.get('Alias Title')) else ''
                    created_by_name = str(row.get('Alias Created By', '')).strip() if pd.notna(row.get('Alias Created By')) else ''
                    
                    if not canonical_title or not alias_title:
                        continue
                    
                    canonical_task = title_to_task.get(canonical_title)
                    created_by = name_to_user.get(created_by_name) if created_by_name else None
                    
                    if not canonical_task:
                        logger.warning(f"  ⚠️  Canonical task '{canonical_title}' not found for alias '{alias_title}'")
                        continue
                    
                    new_alias = TaskAlias(
                        id=uuid4(),
                        canonical_task_id=canonical_task.id,
                        alias_title=alias_title,
                        alias_created_by_user_id=created_by.id if created_by else None
                    )
                    db.add(new_alias)
                    stats['aliases_imported'] += 1
                
                db.commit()
                logger.info(f"  ✅ Imported {stats['aliases_imported']} task aliases")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not import Task Aliases: {e}")
        
        # =====================================================================
        # Import Merge Proposals
        # =====================================================================
        if 'Merge Proposals' in sheet_names:
            logger.info("🔀 Importing merge proposals...")
            try:
                from app.models import TaskMergeProposal, MergeProposalStatus
                merges_df = sheets['Merge Proposals']
                stats['merge_proposals_imported'] = 0
                
                for _, row in merges_df.iterrows():
                    from_title = str(row.get('From Task', '')).strip() if pd.notna(row.get('From Task')) else ''
                    to_title = str(row.get('To Task', '')).strip() if pd.notna(row.get('To Task')) else ''
                    proposed_by_name = str(row.get('Proposed By', '')).strip() if pd.notna(row.get('Proposed By')) else ''
                    status_str = str(row.get('Status', 'PROPOSED')).strip().upper() if pd.notna(row.get('Status')) else 'PROPOSED'
                    
                    if not from_title or not to_title:
                        continue
                    
                    from_task = title_to_task.get(from_title)
                    to_task = title_to_task.get(to_title)
                    proposed_by = name_to_user.get(proposed_by_name) if proposed_by_name else None
                    
                    if not from_task or not to_task:
                        logger.warning(f"  ⚠️  Tasks not found for merge {from_title} -> {to_title}")
                        continue
                    
                    status_map = {
                        'PROPOSED': MergeProposalStatus.PROPOSED,
                        'ACCEPTED': MergeProposalStatus.ACCEPTED,
                        'REJECTED': MergeProposalStatus.REJECTED
                    }
                    status = status_map.get(status_str, MergeProposalStatus.PROPOSED)
                    
                    new_merge = TaskMergeProposal(
                        id=uuid4(),
                        from_task_id=from_task.id,
                        to_task_id=to_task.id,
                        proposed_by_user_id=proposed_by.id if proposed_by else None,
                        proposal_reason=str(row.get('Proposal Reason', '')) if pd.notna(row.get('Proposal Reason')) else None,
                        status=status
                    )
                    db.add(new_merge)
                    stats['merge_proposals_imported'] += 1
                
                db.commit()
                logger.info(f"  ✅ Imported {stats['merge_proposals_imported']} merge proposals")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not import Merge Proposals: {e}")
        
        # =====================================================================
        # Import Alternative Dependency Proposals
        # =====================================================================
        if 'Alt Dep Proposals' in sheet_names:
            logger.info("↔️ Importing alternative dependency proposals...")
            try:
                from app.models import AlternativeDependencyProposal, AlternativeDepStatus
                alt_df = sheets['Alt Dep Proposals']
                stats['alt_dep_proposals_imported'] = 0
                
                for _, row in alt_df.iterrows():
                    downstream_title = str(row.get('Downstream Task', '')).strip() if pd.notna(row.get('Downstream Task')) else ''
                    orig_upstream_title = str(row.get('Original Upstream Task', '')).strip() if pd.notna(row.get('Original Upstream Task')) else ''
                    suggested_upstream_title = str(row.get('Suggested Upstream Task', '')).strip() if pd.notna(row.get('Suggested Upstream Task')) else ''
                    proposed_by_name = str(row.get('Proposed By', '')).strip() if pd.notna(row.get('Proposed By')) else ''
                    status_str = str(row.get('Status', 'PROPOSED')).strip().upper() if pd.notna(row.get('Status')) else 'PROPOSED'
                    
                    if not downstream_title or not suggested_upstream_title:
                        continue
                    
                    downstream = title_to_task.get(downstream_title)
                    orig_upstream = title_to_task.get(orig_upstream_title) if orig_upstream_title else None
                    suggested_upstream = title_to_task.get(suggested_upstream_title)
                    proposed_by = name_to_user.get(proposed_by_name) if proposed_by_name else None
                    
                    if not downstream or not suggested_upstream:
                        logger.warning(f"  ⚠️  Tasks not found for alt dep proposal")
                        continue
                    
                    status_map = {
                        'PROPOSED': AlternativeDepStatus.PROPOSED,
                        'ACCEPTED': AlternativeDepStatus.ACCEPTED,
                        'REJECTED': AlternativeDepStatus.REJECTED
                    }
                    status = status_map.get(status_str, AlternativeDepStatus.PROPOSED)
                    
                    new_alt = AlternativeDependencyProposal(
                        id=uuid4(),
                        downstream_task_id=downstream.id,
                        original_upstream_task_id=orig_upstream.id if orig_upstream else None,
                        suggested_upstream_task_id=suggested_upstream.id,
                        proposed_by_user_id=proposed_by.id if proposed_by else None,
                        proposal_reason=str(row.get('Proposal Reason', '')) if pd.notna(row.get('Proposal Reason')) else None,
                        status=status
                    )
                    db.add(new_alt)
                    stats['alt_dep_proposals_imported'] += 1
                
                db.commit()
                logger.info(f"  ✅ Imported {stats['alt_dep_proposals_imported']} alternative dependency proposals")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not import Alt Dep Proposals: {e}")
        
        # =====================================================================
        # Import Pending Decisions
        # =====================================================================
        if 'Pending Decisions' in sheet_names:
            logger.info("🔔 Importing pending decisions...")
            try:
                from app.models import PendingDecision, PendingDecisionType
                decisions_df = sheets['Pending Decisions']
                stats['pending_decisions_imported'] = 0
                
                for _, row in decisions_df.iterrows():
                    user_name = str(row.get('User', '')).strip() if pd.notna(row.get('User')) else ''
                    decision_type_str = str(row.get('Decision Type', '')).strip().upper() if pd.notna(row.get('Decision Type')) else ''
                    task_title = str(row.get('Task', '')).strip() if pd.notna(row.get('Task')) else ''
                    description = str(row.get('Description', '')) if pd.notna(row.get('Description')) else ''
                    
                    if not user_name or not decision_type_str:
                        continue
                    
                    user = name_to_user.get(user_name)
                    task = title_to_task.get(task_title) if task_title else None
                    
                    if not user:
                        logger.warning(f"  ⚠️  User '{user_name}' not found for pending decision")
                        continue
                    
                    type_map = {
                        'TASK_ACCEPTANCE': PendingDecisionType.TASK_ACCEPTANCE,
                        'MERGE_CONSENT': PendingDecisionType.MERGE_CONSENT,
                        'DEPENDENCY_ACCEPTANCE': PendingDecisionType.DEPENDENCY_ACCEPTANCE,
                        'ALTERNATIVE_DEP_ACCEPTANCE': PendingDecisionType.ALTERNATIVE_DEP_ACCEPTANCE
                    }
                    decision_type = type_map.get(decision_type_str)
                    if not decision_type:
                        logger.warning(f"  ⚠️  Unknown decision type '{decision_type_str}'")
                        continue
                    
                    new_decision = PendingDecision(
                        id=uuid4(),
                        user_id=user.id,
                        decision_type=decision_type,
                        entity_type="task" if task else "unknown",
                        entity_id=task.id if task else uuid4(),
                        description=description
                    )
                    db.add(new_decision)
                    stats['pending_decisions_imported'] += 1
                
                db.commit()
                logger.info(f"  ✅ Imported {stats['pending_decisions_imported']} pending decisions")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not import Pending Decisions: {e}")
        
        # =====================================================================
        # Populate Relevant Users for Tasks
        # =====================================================================
        logger.info("👥 Populating relevant users for tasks...")
        try:
            from populate_relevant_users import populate_all_tasks
            relevant_count = populate_all_tasks(db, clear_existing=False)
            stats['relevant_users_created'] = relevant_count
            logger.info(f"  ✅ Created {relevant_count} relevant user associations")
        except Exception as e:
            logger.warning(f"  ⚠️  Could not populate relevant users: {e}")
            stats['relevant_users_created'] = 0
        
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
