#!/usr/bin/env python3
"""Launch the case viewer in a browser with a specific case pre-loaded."""

import argparse
import http.server
import json
import os
import socketserver
import threading
import webbrowser
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.io_utils import read_json, read_text


PORT = 8765

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Case {case_id} - TaskGraph Viewer</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; }}
        
        .header {{ background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%); padding: 20px; border-bottom: 1px solid #333; }}
        .header h1 {{ font-size: 1.5rem; color: #00d9ff; margin-bottom: 10px; }}
        
        .meta-bar {{ display: flex; gap: 30px; flex-wrap: wrap; }}
        .meta-item {{ display: flex; gap: 8px; font-size: 0.9rem; }}
        .meta-label {{ color: #666; }}
        .meta-value {{ color: #00d9ff; font-weight: 600; }}
        
        .main {{ padding: 20px; }}
        
        .prompt-panel {{ background: #16213e; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .prompt-panel h2 {{ color: #ffd43b; margin-bottom: 15px; font-size: 1.1rem; }}
        .prompt-content {{ white-space: pre-wrap; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.9rem; line-height: 1.6; color: #ffd43b; background: #1a1a2e; padding: 15px; border-radius: 8px; }}
        
        .diff-panel {{ background: #2a2a4a; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .diff-panel h2 {{ color: #00d9ff; margin-bottom: 15px; font-size: 1.1rem; }}
        .diff-item {{ display: flex; align-items: center; gap: 10px; padding: 8px 0; font-size: 0.9rem; border-bottom: 1px solid #333; }}
        .diff-item:last-child {{ border-bottom: none; }}
        .diff-icon {{ width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; }}
        .diff-icon.add {{ background: #51cf66; color: #000; }}
        .diff-icon.remove {{ background: #ff6b6b; color: #fff; }}
        .diff-icon.modify {{ background: #ffd43b; color: #000; }}
        
        .panels {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 1200px) {{ .panels {{ grid-template-columns: 1fr; }} }}
        
        .panel {{ background: #16213e; border-radius: 12px; overflow: hidden; }}
        .panel-header {{ padding: 15px 20px; background: #1a1a2e; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }}
        .panel-header h2 {{ font-size: 1.1rem; }}
        .panel-header.partial h2 {{ color: #ff6b6b; }}
        .panel-header.target h2 {{ color: #51cf66; }}
        .stats {{ font-size: 0.8rem; color: #888; }}
        .panel-content {{ padding: 15px; max-height: 70vh; overflow-y: auto; }}
        
        .section {{ margin-bottom: 20px; }}
        .section-title {{ font-size: 0.85rem; color: #666; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }}
        
        .task-card {{ background: #1a1a2e; border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 3px solid #00d9ff; }}
        .task-card.added {{ border-left-color: #51cf66; background: rgba(81, 207, 102, 0.1); }}
        .task-card.removed {{ border-left-color: #ff6b6b; background: rgba(255, 107, 107, 0.1); }}
        .task-card.modified {{ border-left-color: #ffd43b; background: rgba(255, 212, 59, 0.1); }}
        
        .task-title {{ font-weight: 600; color: #fff; margin-bottom: 8px; font-size: 0.95rem; }}
        .task-id {{ color: #666; font-size: 0.75rem; margin-left: 8px; }}
        
        .task-fields {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; font-size: 0.8rem; }}
        .field {{ display: flex; gap: 5px; align-items: center; }}
        .field-name {{ color: #666; }}
        .field-value {{ color: #aaa; }}
        .field-value.changed {{ color: #ffd43b; font-weight: 600; }}
        
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
        .badge-Critical {{ background: #ff6b6b; color: #fff; }}
        .badge-High {{ background: #ffa94d; color: #000; }}
        .badge-Medium {{ background: #ffd43b; color: #000; }}
        .badge-Low {{ background: #69db7c; color: #000; }}
        
        .deps-section {{ margin-top: 15px; }}
        .dep-item {{ background: #1a1a2e; padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
        .dep-arrow {{ color: #00d9ff; }}
        .dep-status {{ margin-left: auto; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
        .dep-CONFIRMED {{ background: #51cf66; color: #000; }}
        .dep-PROPOSED {{ background: #ffd43b; color: #000; }}
        .dep-REJECTED {{ background: #ff6b6b; color: #fff; }}
        .dep-REMOVED {{ background: #666; color: #fff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Case {case_id}</h1>
        <div class="meta-bar">
            <div class="meta-item"><span class="meta-label">Bucket:</span><span class="meta-value">{bucket}</span></div>
            <div class="meta-item"><span class="meta-label">Format:</span><span class="meta-value">{prompt_format}</span></div>
            <div class="meta-item"><span class="meta-label">Target:</span><span class="meta-value">{target_id}</span></div>
        </div>
    </div>
    
    <div class="main">
        <div class="prompt-panel">
            <h2>📝 Prompt (Instructions for LLM)</h2>
            <div class="prompt-content">{prompt}</div>
        </div>
        
        <div class="diff-panel">
            <h2>📊 Required Changes</h2>
            {diff_html}
        </div>
        
        <div class="panels">
            <div class="panel">
                <div class="panel-header partial">
                    <h2>📄 Partial (Starting State)</h2>
                    <div class="stats">{partial_task_count} tasks, {partial_dep_count} deps</div>
                </div>
                <div class="panel-content">{partial_html}</div>
            </div>
            
            <div class="panel">
                <div class="panel-header target">
                    <h2>🎯 Target (Expected Result)</h2>
                    <div class="stats">{target_task_count} tasks, {target_dep_count} deps</div>
                </div>
                <div class="panel-content">{target_html}</div>
            </div>
        </div>
    </div>
</body>
</html>
'''


def escape_html(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def compute_diff(partial, target):
    """Compute differences between partial and target."""
    diff = {
        'added': [],
        'removed': [],
        'modified': []
    }
    
    partial_tasks = partial.get('tasks', {})
    target_tasks = target.get('tasks', {})
    
    partial_by_title = {t.get('title'): (tid, t) for tid, t in partial_tasks.items() if t.get('title')}
    target_by_title = {t.get('title'): (tid, t) for tid, t in target_tasks.items() if t.get('title')}
    
    for title in target_by_title:
        if title not in partial_by_title:
            diff['added'].append(title)
        else:
            _, pt = partial_by_title[title]
            _, tt = target_by_title[title]
            changes = []
            for field in ['priority', 'status', 'state', 'impact_size', 'owner', 'parent']:
                if pt.get(field) != tt.get(field):
                    changes.append(f"{field}: {pt.get(field)} → {tt.get(field)}")
            if changes:
                diff['modified'].append((title, changes))
    
    for title in partial_by_title:
        if title not in target_by_title:
            diff['removed'].append(title)
    
    return diff


def render_diff_html(diff):
    items = []
    for title in diff['added']:
        items.append(f'<div class="diff-item"><span class="diff-icon add">+</span> Add task: "{escape_html(title)}"</div>')
    for title in diff['removed']:
        items.append(f'<div class="diff-item"><span class="diff-icon remove">−</span> Remove task: "{escape_html(title)}"</div>')
    for title, changes in diff['modified']:
        changes_str = ', '.join(changes)
        items.append(f'<div class="diff-item"><span class="diff-icon modify">~</span> Modify "{escape_html(title)}": {escape_html(changes_str)}</div>')
    
    if not items:
        return '<div class="diff-item" style="color: #666;">No structural changes detected</div>'
    return '\n'.join(items)


def render_state_html(state, diff, state_type):
    """Render a state as HTML."""
    html_parts = []
    
    tasks = state.get('tasks', {})
    deps = state.get('dependencies', [])
    
    # Build lookup
    partial_titles = set()
    target_titles = set()
    modified_titles = set()
    
    if state_type == 'partial':
        target_titles = set(diff['added'])
        partial_titles = set(diff['removed'])
    else:
        target_titles = set(diff['added'])
        partial_titles = set(diff['removed'])
    
    modified_titles = {m[0] for m in diff['modified']}
    
    # Tasks
    html_parts.append('<div class="section"><div class="section-title">📋 Tasks</div>')
    
    for tid, task in sorted(tasks.items()):
        title = task.get('title', 'Untitled')
        
        card_class = ''
        if state_type == 'target' and title in diff['added']:
            card_class = 'added'
        elif state_type == 'partial' and title in diff['removed']:
            card_class = 'removed'
        elif title in modified_titles:
            card_class = 'modified'
        
        fields_html = []
        for field, badge_class in [('priority', True), ('status', False), ('state', False), ('impact_size', False), ('owner', False)]:
            if task.get(field):
                val = task[field]
                if field == 'priority':
                    fields_html.append(f'<div class="field"><span class="field-name">{field}:</span><span class="badge badge-{val}">{val}</span></div>')
                elif field == 'impact_size':
                    fields_html.append(f'<div class="field"><span class="field-name">impact:</span><span class="field-value">{val}/5</span></div>')
                else:
                    fields_html.append(f'<div class="field"><span class="field-name">{field}:</span><span class="field-value">{val}</span></div>')
        
        if task.get('parent'):
            fields_html.append(f'<div class="field"><span class="field-name">parent:</span><span class="field-value">{task["parent"]}</span></div>')
        
        html_parts.append(f'''
            <div class="task-card {card_class}">
                <div class="task-title">{escape_html(title)}<span class="task-id">{tid}</span></div>
                <div class="task-fields">{''.join(fields_html)}</div>
            </div>
        ''')
    
    html_parts.append('</div>')
    
    # Dependencies
    if deps:
        html_parts.append('<div class="section deps-section"><div class="section-title">🔗 Dependencies</div>')
        for dep in deps:
            task_title = tasks.get(dep['task'], {}).get('title', dep['task'])
            depends_title = tasks.get(dep['depends_on'], {}).get('title', dep['depends_on'])
            status = dep.get('status', 'UNKNOWN')
            html_parts.append(f'''
                <div class="dep-item">
                    <span>{escape_html(task_title)}</span>
                    <span class="dep-arrow">→</span>
                    <span>{escape_html(depends_title)}</span>
                    <span class="dep-status dep-{status}">{status}</span>
                </div>
            ''')
        html_parts.append('</div>')
    
    return '\n'.join(html_parts)


def generate_html(case_dir):
    """Generate HTML for a case."""
    partial = read_json(os.path.join(case_dir, 'partial.json'))
    target = read_json(os.path.join(case_dir, 'target.json'))
    prompt = read_text(os.path.join(case_dir, 'prompt.txt'))
    meta = read_json(os.path.join(case_dir, 'meta.json'))
    
    diff = compute_diff(partial, target)
    
    return HTML_TEMPLATE.format(
        case_id=meta.get('case_id', os.path.basename(case_dir)),
        bucket=meta.get('bucket', 'N/A'),
        prompt_format=meta.get('prompt_format', 'N/A'),
        target_id=meta.get('target_id', 'N/A'),
        prompt=escape_html(prompt),
        diff_html=render_diff_html(diff),
        partial_task_count=len(partial.get('tasks', {})),
        partial_dep_count=len(partial.get('dependencies', [])),
        target_task_count=len(target.get('tasks', {})),
        target_dep_count=len(target.get('dependencies', [])),
        partial_html=render_state_html(partial, diff, 'partial'),
        target_html=render_state_html(target, diff, 'target')
    )


def main():
    parser = argparse.ArgumentParser(description='View a test case in the browser')
    parser.add_argument('--case_dir', type=str, required=True, help='Path to case directory')
    parser.add_argument('--output', type=str, default=None, help='Output HTML file (optional)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    
    args = parser.parse_args()
    
    html = generate_html(args.case_dir)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(html)
        print(f'Saved to: {args.output}')
        if not args.no_browser:
            webbrowser.open(f'file://{os.path.abspath(args.output)}')
    else:
        # Create temp file and open
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            temp_path = f.name
        print(f'Generated: {temp_path}')
        if not args.no_browser:
            webbrowser.open(f'file://{temp_path}')


if __name__ == '__main__':
    main()

