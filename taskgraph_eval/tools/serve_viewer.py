#!/usr/bin/env python3
"""Serve the case viewer with API endpoints for comparison and model execution."""

import argparse
import http.server
import json
import os
import socketserver
import sys
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.executor import apply_ops, ExecutorError
from taskgraph_eval.legality import validate_state
from taskgraph_eval.compare import compare_states
from taskgraph_eval.io_utils import read_json, read_text, write_json
from taskgraph_eval.openai_runner import call_openai, get_full_prompt

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TOOLS_DIR)


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, cases_dir=None, **kwargs):
        self.cases_dir = cases_dir
        super().__init__(*args, directory=TOOLS_DIR, **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/cases':
            self.send_cases_list()
        elif parsed.path == '/api/case':
            qs = parse_qs(parsed.query)
            case_id = qs.get('id', [None])[0]
            if case_id:
                self.send_case_data(case_id)
            else:
                self.send_error(400, 'Missing case id')
        elif parsed.path == '/':
            self.send_viewer_html()
        else:
            super().do_GET()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json_response({'error': 'Invalid JSON'}, 400)
            return
        
        if parsed.path == '/api/compare':
            self.handle_compare(data)
        elif parsed.path == '/api/run-model':
            self.handle_run_model(data)
        elif parsed.path == '/api/apply-ops':
            self.handle_apply_ops(data)
        elif parsed.path == '/api/run-all':
            self.handle_run_all(data)
        else:
            self.send_error(404, 'Not found')
    
    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))
    
    def send_cases_list(self):
        cases = []
        cases_path = os.path.join(PROJECT_DIR, self.cases_dir or 'cases')
        if os.path.exists(cases_path):
            for name in sorted(os.listdir(cases_path)):
                case_path = os.path.join(cases_path, name)
                if os.path.isdir(case_path):
                    meta_path = os.path.join(case_path, 'meta.json')
                    if os.path.exists(meta_path):
                        meta = read_json(meta_path)
                        case_info = {
                            'id': name,
                            'bucket': meta.get('bucket'),
                            'format': meta.get('prompt_format'),
                            'target_id': meta.get('target_id'),
                            'status': None  # not run yet
                        }
                        # Check if produced.json exists and compare
                        produced_path = os.path.join(case_path, 'produced.json')
                        target_path = os.path.join(case_path, 'target.json')
                        if os.path.exists(produced_path) and os.path.exists(target_path):
                            try:
                                produced = read_json(produced_path)
                                target = read_json(target_path)
                                comparison = compare_states(target, produced)
                                legality_errors = validate_state(produced)
                                case_info['status'] = 'passed' if comparison.match and len(legality_errors) == 0 else 'failed'
                            except Exception:
                                case_info['status'] = 'error'
                        cases.append(case_info)
        self.send_json_response({'cases': cases})
    
    def send_case_data(self, case_id):
        case_path = os.path.join(PROJECT_DIR, self.cases_dir or 'cases', case_id)
        if not os.path.exists(case_path):
            self.send_json_response({'error': 'Case not found'}, 404)
            return
        
        try:
            partial = read_json(os.path.join(case_path, 'partial.json'))
            prompt_text = read_text(os.path.join(case_path, 'prompt.txt'))
            
            # Build full prompt using shared module
            full_prompt = get_full_prompt(prompt_text, partial)
            
            data = {
                'partial': partial,
                'target': read_json(os.path.join(case_path, 'target.json')),
                'prompt': prompt_text,
                'full_prompt': full_prompt,
                'meta': read_json(os.path.join(case_path, 'meta.json'))
            }
            
            # Check if model_ops exists
            ops_path = os.path.join(case_path, 'model_ops.json')
            if os.path.exists(ops_path):
                data['model_ops'] = read_json(ops_path)
            
            # Check if produced exists
            produced_path = os.path.join(case_path, 'produced.json')
            if os.path.exists(produced_path):
                data['produced'] = read_json(produced_path)
            
            self.send_json_response(data)
        except Exception as e:
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_compare(self, data):
        """Compare two states and return differences."""
        try:
            expected = data.get('expected')
            actual = data.get('actual')
            
            if not expected or not actual:
                self.send_json_response({'error': 'Missing expected or actual state'}, 400)
                return
            
            result = compare_states(expected, actual)
            self.send_json_response(result.to_dict())
        except Exception as e:
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_apply_ops(self, data):
        """Apply operations to a partial state."""
        try:
            partial = data.get('partial')
            ops = data.get('ops')
            
            if not partial or not ops:
                self.send_json_response({'error': 'Missing partial or ops'}, 400)
                return
            
            produced = apply_ops(partial, ops)
            errors = validate_state(produced)
            
            self.send_json_response({
                'produced': produced,
                'valid': len(errors) == 0,
                'errors': errors
            })
        except ExecutorError as e:
            self.send_json_response({'error': f'Executor error: {e}'}, 400)
        except Exception as e:
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_run_model(self, data):
        """Run the model on a case."""
        try:
            case_id = data.get('case_id')
            model_name = data.get('model', 'gpt-5-mini')
            
            if not case_id:
                self.send_json_response({'error': 'Missing case_id'}, 400)
                return
            
            if not os.environ.get('OPENAI_API_KEY'):
                self.send_json_response({'error': 'OPENAI_API_KEY not set'}, 400)
                return
            
            case_path = os.path.join(PROJECT_DIR, self.cases_dir or 'cases', case_id)
            partial = read_json(os.path.join(case_path, 'partial.json'))
            target = read_json(os.path.join(case_path, 'target.json'))
            prompt = read_text(os.path.join(case_path, 'prompt.txt'))
            
            # Call OpenAI using shared module
            ops = call_openai(
                prompt_text=prompt,
                partial_json=partial,
                model=model_name,
                max_output_tokens=4000
            )
            
            # Save ops
            ops_path = os.path.join(case_path, 'model_ops.json')
            write_json(ops_path, ops)
            
            # Apply and validate
            try:
                produced = apply_ops(partial, ops)
                write_json(os.path.join(case_path, 'produced.json'), produced)
                
                legality_errors = validate_state(produced)
                comparison = compare_states(target, produced)
                
                result = {
                    'ops': ops,
                    'produced': produced,
                    'valid': len(legality_errors) == 0,
                    'legality_errors': legality_errors,
                    'comparison': comparison.to_dict(),
                    'passed': comparison.match
                }
            except ExecutorError as e:
                result = {
                    'ops': ops,
                    'error': f'Executor error: {e}',
                    'passed': False
                }
            
            self.send_json_response(result)
            
        except Exception as e:
            import traceback
            self.send_json_response({
                'error': str(e),
                'traceback': traceback.format_exc()
            }, 500)
    
    def handle_run_all(self, data):
        """Run model on all cases in parallel."""
        import concurrent.futures
        
        try:
            model_name = data.get('model', 'gpt-5-mini')
            failed_only = data.get('failed_only', False)
            
            if not os.environ.get('OPENAI_API_KEY'):
                self.send_json_response({'error': 'OPENAI_API_KEY not set'}, 400)
                return
            
            # Get all case IDs, optionally filter to failed/pending only
            cases_path = os.path.join(PROJECT_DIR, self.cases_dir or 'cases')
            case_ids = []
            if os.path.exists(cases_path):
                for name in sorted(os.listdir(cases_path)):
                    case_path = os.path.join(cases_path, name)
                    if os.path.isdir(case_path) and os.path.exists(os.path.join(case_path, 'meta.json')):
                        if failed_only:
                            # Check if case passed - skip if it did
                            produced_path = os.path.join(case_path, 'produced.json')
                            target_path = os.path.join(case_path, 'target.json')
                            if os.path.exists(produced_path) and os.path.exists(target_path):
                                try:
                                    produced = read_json(produced_path)
                                    target = read_json(target_path)
                                    comparison = compare_states(target, produced)
                                    legality_errors = validate_state(produced)
                                    if comparison.match and len(legality_errors) == 0:
                                        continue  # Skip passed tests
                                except Exception:
                                    pass  # Include if error checking
                        case_ids.append(name)
            
            results = []
            
            def run_single_case(case_id):
                try:
                    case_path = os.path.join(PROJECT_DIR, self.cases_dir or 'cases', case_id)
                    partial = read_json(os.path.join(case_path, 'partial.json'))
                    target = read_json(os.path.join(case_path, 'target.json'))
                    prompt = read_text(os.path.join(case_path, 'prompt.txt'))
                    meta = read_json(os.path.join(case_path, 'meta.json'))
                    
                    ops = call_openai(
                        prompt_text=prompt,
                        partial_json=partial,
                        model=model_name,
                        max_output_tokens=4000
                    )
                    
                    write_json(os.path.join(case_path, 'model_ops.json'), ops)
                    
                    produced = apply_ops(partial, ops)
                    write_json(os.path.join(case_path, 'produced.json'), produced)
                    
                    legality_errors = validate_state(produced)
                    comparison = compare_states(target, produced)
                    
                    return {
                        'case_id': case_id,
                        'bucket': meta.get('bucket'),
                        'passed': comparison.match and len(legality_errors) == 0,
                        'errors': comparison.errors[:5] if not comparison.match else [],
                        'legality_errors': legality_errors[:3]
                    }
                except Exception as e:
                    return {
                        'case_id': case_id,
                        'passed': False,
                        'error': str(e)
                    }
            
            # Run in parallel with ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(run_single_case, case_ids))
            
            passed = sum(1 for r in results if r.get('passed'))
            failed = len(results) - passed
            
            self.send_json_response({
                'total': len(results),
                'passed': passed,
                'failed': failed,
                'results': results
            })
            
        except Exception as e:
            import traceback
            self.send_json_response({
                'error': str(e),
                'traceback': traceback.format_exc()
            }, 500)
    
    def send_viewer_html(self):
        """Send the enhanced viewer HTML."""
        html = self.get_viewer_html()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def get_viewer_html(self):
        return VIEWER_HTML


VIEWER_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TaskGraph Case Viewer</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #0f0f1a; color: #eee; min-height: 100vh; }
        
        .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 15px 20px; border-bottom: 1px solid #333; display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
        .header h1 { font-size: 1.3rem; color: #00d9ff; }
        
        .case-selector { display: flex; align-items: center; gap: 10px; }
        .case-selector select { background: #2a2a4a; border: 1px solid #444; color: #fff; padding: 8px 12px; border-radius: 6px; min-width: 200px; }
        
        .btn { background: #00d9ff; color: #000; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.2s; }
        .btn-warning { background: #fcc419; }
        .btn-warning:hover { background: #fab005; }
        .btn:hover { background: #00b8d9; transform: translateY(-1px); }
        .btn:disabled { background: #444; color: #888; cursor: not-allowed; transform: none; }
        .btn-success { background: #51cf66; }
        .btn-warning { background: #ffd43b; color: #000; }
        .btn-danger { background: #ff6b6b; }
        
        .tabs { display: flex; gap: 5px; margin-left: auto; }
        .tab { background: #2a2a4a; color: #aaa; border: none; padding: 8px 16px; border-radius: 6px 6px 0 0; cursor: pointer; }
        .tab.active { background: #16213e; color: #00d9ff; }
        
        .main { display: flex; height: calc(100vh - 60px); }
        
        .sidebar { width: 250px; background: #16213e; border-right: 1px solid #333; overflow-y: auto; flex-shrink: 0; }
        .sidebar h3 { padding: 15px; color: #888; font-size: 0.8rem; text-transform: uppercase; border-bottom: 1px solid #333; }
        .case-list { list-style: none; }
        .case-item { padding: 10px 15px; cursor: pointer; border-bottom: 1px solid #222; display: flex; justify-content: space-between; align-items: center; }
        .case-item:hover { background: #1a1a2e; }
        .case-item.active { background: #2a2a4a; border-left: 3px solid #00d9ff; }
        .case-item.failed { background: rgba(255, 107, 107, 0.15); border-left: 3px solid #ff6b6b; }
        .case-item.failed .id { color: #ff6b6b; }
        .case-item.passed { border-left: 3px solid #51cf66; }
        .case-item.passed .id { color: #51cf66; }
        .case-item .id { font-weight: 600; color: #fff; }
        .case-item .bucket { font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; }
        .bucket-ADD { background: #51cf66; color: #000; }
        .bucket-EDIT { background: #ffd43b; color: #000; }
        .bucket-DELETE { background: #ff6b6b; color: #fff; }
        .bucket-MIXED { background: #845ef7; color: #fff; }
        
        .content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
        
        .toolbar { background: #1a1a2e; padding: 10px 20px; border-bottom: 1px solid #333; display: flex; gap: 10px; align-items: center; }
        .toolbar .info { margin-left: auto; font-size: 0.85rem; color: #888; }
        .status-badge { padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
        .status-pass { background: #51cf66; color: #000; }
        .status-fail { background: #ff6b6b; color: #fff; }
        .status-pending { background: #ffd43b; color: #000; }
        
        .view-container { flex: 1; overflow: hidden; display: flex; }
        
        /* Compare View */
        .compare-view { display: none; flex: 1; flex-direction: column; overflow: hidden; }
        .compare-view.active { display: flex; }
        
        .diff-header { background: #16213e; padding: 15px 20px; border-bottom: 1px solid #333; }
        .diff-header h2 { color: #00d9ff; font-size: 1.1rem; margin-bottom: 10px; }
        .diff-stats { display: flex; gap: 20px; font-size: 0.9rem; }
        .diff-stat { display: flex; align-items: center; gap: 6px; }
        .diff-stat .icon { width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: bold; }
        .diff-stat .icon.add { background: #51cf66; color: #000; }
        .diff-stat .icon.remove { background: #ff6b6b; color: #fff; }
        .diff-stat .icon.modify { background: #ffd43b; color: #000; }
        
        .diff-content { flex: 1; overflow-y: auto; padding: 20px; }
        .diff-section { margin-bottom: 25px; }
        .diff-section h3 { color: #888; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 10px; }
        .diff-item { background: #16213e; border-radius: 8px; padding: 12px 15px; margin-bottom: 8px; display: flex; align-items: flex-start; gap: 12px; }
        .diff-item .icon { flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .diff-item .details { flex: 1; }
        .diff-item .title { font-weight: 600; color: #fff; margin-bottom: 4px; }
        .diff-item .changes { font-size: 0.85rem; color: #aaa; }
        .diff-item .change { margin-top: 4px; }
        .diff-item .field-name { color: #00d9ff; }
        .diff-item .old-value { color: #ff6b6b; text-decoration: line-through; }
        .diff-item .new-value { color: #51cf66; }
        
        /* Side by Side View */
        .side-view { display: none; flex: 1; }
        .side-view.active { display: flex; }
        
        .panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .panel:first-child { border-right: 1px solid #333; }
        .panel-header { padding: 12px 20px; background: #16213e; border-bottom: 1px solid #333; }
        .panel-header.partial h2 { color: #ff6b6b; }
        .panel-header.target h2 { color: #51cf66; }
        .panel-header.produced h2 { color: #845ef7; }
        .panel-header h2 { font-size: 1rem; }
        .panel-content { flex: 1; overflow-y: auto; padding: 15px; background: #0f0f1a; }
        
        /* Prompt View */
        .prompt-view { display: none; flex: 1; flex-direction: column; overflow: hidden; }
        .prompt-view.active { display: flex; }
        .prompt-content { flex: 1; overflow-y: auto; padding: 20px; }
        .prompt-box { background: #16213e; border-radius: 12px; padding: 20px; font-family: 'Consolas', monospace; white-space: pre-wrap; line-height: 1.6; color: #ffd43b; }
        
        /* Model Output View */
        .model-view { display: none; flex: 1; flex-direction: column; overflow: hidden; }
        .model-view.active { display: flex; }
        .model-content { flex: 1; overflow-y: auto; padding: 20px; }
        .ops-list { background: #16213e; border-radius: 12px; padding: 15px; }
        .op-item { background: #1a1a2e; border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #00d9ff; }
        .op-type { font-weight: 600; color: #00d9ff; margin-bottom: 6px; }
        .op-details { font-size: 0.85rem; color: #aaa; font-family: monospace; }
        
        /* Task cards */
        .task-card { background: #16213e; border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 3px solid #00d9ff; }
        .task-card.added { border-left-color: #51cf66; background: rgba(81, 207, 102, 0.1); }
        .task-card.removed { border-left-color: #ff6b6b; background: rgba(255, 107, 107, 0.1); }
        .task-card.modified { border-left-color: #ffd43b; background: rgba(255, 212, 59, 0.1); }
        .task-title { font-weight: 600; color: #fff; margin-bottom: 6px; }
        .task-id { color: #666; font-size: 0.75rem; margin-left: 6px; }
        .task-fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 6px; font-size: 0.8rem; }
        .field { display: flex; gap: 4px; }
        .field-name { color: #666; }
        .field-value { color: #aaa; }
        
        .loading { text-align: center; padding: 40px; color: #666; }
        .error { background: rgba(255, 107, 107, 0.2); border: 1px solid #ff6b6b; border-radius: 8px; padding: 15px; margin: 20px; color: #ff6b6b; }
        
        .empty-state { text-align: center; padding: 60px 20px; color: #666; }
        .empty-state h2 { margin-bottom: 10px; color: #888; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 TaskGraph Viewer</h1>
        <div class="case-selector">
            <select id="caseSelect" onchange="loadCase(this.value)">
                <option value="">Select a case...</option>
            </select>
            <button class="btn" onclick="loadCasesList()">↻ Refresh</button>
        </div>
        <div class="tabs">
            <button class="tab active" onclick="showView('compare')">📊 Required Changes</button>
            <button class="tab" onclick="showView('side')">📄 Partial vs Target</button>
            <button class="tab" onclick="showView('prompt')">📝 Prompt</button>
            <button class="tab" onclick="showView('model')">🤖 Model Ops</button>
            <button class="tab" onclick="showView('results')">✅ Produced vs Target</button>
        </div>
    </div>
    
    <div class="main">
        <div class="sidebar">
            <h3>Test Cases</h3>
            <ul class="case-list" id="caseList"></ul>
        </div>
        
        <div class="content">
            <div class="toolbar">
                <button class="btn btn-success" id="runModelBtn" onclick="runModel()" disabled>▶ Run Model</button>
                <button class="btn" id="compareBtn" onclick="compareStates()" disabled>⚖ Compare</button>
                <button class="btn btn-warning" id="runAllBtn" onclick="runAllTests(false)">🚀 Run All</button>
                <button class="btn" id="runFailedBtn" onclick="runAllTests(true)" style="background:#ff6b6b;color:#fff;">🔄 Run Failed/Pending</button>
                <div class="info">
                    <span id="statusBadge"></span>
                    <span id="runAllStatus"></span>
                </div>
            </div>
            
            <div class="view-container">
                <!-- Compare View -->
                <div class="compare-view active" id="compareView">
                    <div class="diff-header">
                        <h2>Differences: Partial → Target</h2>
                        <div class="diff-stats" id="diffStats"></div>
                    </div>
                    <div class="diff-content" id="diffContent">
                        <div class="empty-state">
                            <h2>Select a case to view differences</h2>
                        </div>
                    </div>
                </div>
                
                <!-- Side by Side View -->
                <div class="side-view" id="sideView">
                    <div class="panel">
                        <div class="panel-header partial"><h2>📄 Partial (Starting)</h2></div>
                        <div class="panel-content" id="partialContent"></div>
                    </div>
                    <div class="panel">
                        <div class="panel-header target"><h2>🎯 Target (Expected)</h2></div>
                        <div class="panel-content" id="targetContent"></div>
                    </div>
                </div>
                
                <!-- Prompt View -->
                <div class="prompt-view" id="promptView">
                    <div class="prompt-content">
                        <div class="prompt-box" id="promptBox">Select a case to view the prompt</div>
                    </div>
                </div>
                
                <!-- Model Output View -->
                <div class="model-view" id="modelView">
                    <div class="model-content" id="modelContent">
                        <div class="empty-state">
                            <h2>No model output yet</h2>
                            <p>Click "Run Model" to execute and see results</p>
                        </div>
                    </div>
                </div>
                
                <!-- Results View (Produced vs Target) -->
                <div class="compare-view" id="resultsView">
                    <div class="diff-header">
                        <h2>Comparison: Produced vs Target</h2>
                        <div class="diff-stats" id="resultsDiffStats"></div>
                    </div>
                    <div class="diff-content" id="resultsDiffContent">
                        <div class="empty-state">
                            <h2>No model output yet</h2>
                            <p>Click "Run Model" to generate produced state and compare</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentCase = null;
        let caseData = null;
        
        async function loadCasesList() {
            try {
                const res = await fetch('/api/cases');
                const data = await res.json();
                
                const select = document.getElementById('caseSelect');
                const list = document.getElementById('caseList');
                
                select.innerHTML = '<option value="">Select a case...</option>';
                list.innerHTML = '';
                
                for (const c of data.cases) {
                    const statusClass = c.status ? c.status : '';
                    const statusIcon = c.status === 'passed' ? '✓' : (c.status === 'failed' ? '✗' : '');
                    select.innerHTML += `<option value="${c.id}">${c.id} (${c.bucket}) ${statusIcon}</option>`;
                    list.innerHTML += `
                        <li class="case-item ${statusClass}" data-case-id="${c.id}" onclick="loadCase('${c.id}')">
                            <span class="id">${statusIcon} ${c.id}</span>
                            <span class="bucket bucket-${c.bucket}">${c.bucket}</span>
                        </li>
                    `;
                }
            } catch (e) {
                console.error('Failed to load cases:', e);
            }
        }
        
        async function loadCase(caseId) {
            if (!caseId) return;
            
            currentCase = caseId;
            document.getElementById('caseSelect').value = caseId;
            
            // Update sidebar selection
            document.querySelectorAll('.case-item').forEach(el => {
                el.classList.toggle('active', el.textContent.includes(caseId));
            });
            
            try {
                const res = await fetch(`/api/case?id=${caseId}`);
                caseData = await res.json();
                
                document.getElementById('runModelBtn').disabled = false;
                document.getElementById('compareBtn').disabled = false;
                
                renderDiff();
                renderSideView();
                renderPrompt();
                renderModelOutput();
                renderResults();
                updateStatus();
            } catch (e) {
                console.error('Failed to load case:', e);
            }
        }
        
        function renderDiff() {
            if (!caseData) return;
            
            const partial = caseData.partial;
            const target = caseData.target;
            
            const diff = computeDiff(partial, target);
            
            const statsHtml = `
                <div class="diff-stat"><span class="icon add">+</span> ${diff.added.length} added</div>
                <div class="diff-stat"><span class="icon remove">−</span> ${diff.removed.length} removed</div>
                <div class="diff-stat"><span class="icon modify">~</span> ${diff.modified.length} modified</div>
            `;
            document.getElementById('diffStats').innerHTML = statsHtml;
            
            let contentHtml = '';
            
            if (diff.added.length > 0) {
                contentHtml += '<div class="diff-section"><h3>Tasks to Add</h3>';
                for (const item of diff.added) {
                    contentHtml += `
                        <div class="diff-item">
                            <div class="icon add">+</div>
                            <div class="details">
                                <div class="title"><span class="task-id">${item.id || '?'}</span> ${escapeHtml(item.title)}</div>
                                <div class="changes">${formatFields(item.fields, getIdToTitleMap(caseData.target))}</div>
                            </div>
                        </div>
                    `;
                }
                contentHtml += '</div>';
            }
            
            if (diff.removed.length > 0) {
                contentHtml += '<div class="diff-section"><h3>Tasks to Remove</h3>';
                for (const item of diff.removed) {
                    contentHtml += `
                        <div class="diff-item">
                            <div class="icon remove">−</div>
                            <div class="details">
                                <div class="title"><span class="task-id">${item.id}</span> ${escapeHtml(item.title)}</div>
                            </div>
                        </div>
                    `;
                }
                contentHtml += '</div>';
            }
            
            if (diff.modified.length > 0) {
                contentHtml += '<div class="diff-section"><h3>Tasks to Modify</h3>';
                for (const item of diff.modified) {
                    let changesHtml = '';
                    for (const change of item.changes) {
                        changesHtml += `
                            <div class="change">
                                <span class="field-name">${change.field}:</span>
                                <span class="old-value">${change.from ?? 'null'}</span> →
                                <span class="new-value">${change.to ?? 'null'}</span>
                            </div>
                        `;
                    }
                    contentHtml += `
                        <div class="diff-item">
                            <div class="icon modify">~</div>
                            <div class="details">
                                <div class="title"><span class="task-id">${item.id}</span> ${escapeHtml(item.title)}</div>
                                <div class="changes">${changesHtml}</div>
                            </div>
                        </div>
                    `;
                }
                contentHtml += '</div>';
            }
            
            if (!contentHtml) {
                contentHtml = '<div class="empty-state"><h2>No differences detected</h2></div>';
            }
            
            document.getElementById('diffContent').innerHTML = contentHtml;
        }
        
        function getIdToTitleMap(state) {
            const map = {};
            const tasks = Array.isArray(state.tasks) ? state.tasks : Object.values(state.tasks || {});
            for (const task of tasks) {
                if (task.id && task.title) map[task.id] = task.title;
            }
            return map;
        }
        
        function computeDiff(partial, target) {
            const diff = { added: [], removed: [], modified: [] };
            
            const partialByTitle = {};
            const targetByTitle = {};
            
            // Handle tasks as array (new format)
            const partialTasks = Array.isArray(partial.tasks) ? partial.tasks : Object.values(partial.tasks || {});
            const targetTasks = Array.isArray(target.tasks) ? target.tasks : Object.values(target.tasks || {});
            
            for (const task of partialTasks) {
                if (task.title) partialByTitle[task.title] = task;
            }
            for (const task of targetTasks) {
                if (task.title) targetByTitle[task.title] = task;
            }
            
            // Build id->title maps for resolving parent/dependency references
            const partialIdToTitle = {};
            const targetIdToTitle = {};
            for (const task of partialTasks) {
                if (task.id && task.title) partialIdToTitle[task.id] = task.title;
            }
            for (const task of targetTasks) {
                if (task.id && task.title) targetIdToTitle[task.id] = task.title;
            }
            
            for (const [title, task] of Object.entries(targetByTitle)) {
                if (!partialByTitle[title]) {
                    diff.added.push({ id: task.id, title, fields: task });
                } else {
                    const pt = partialByTitle[title];
                    const changes = [];
                    
                    // Compare regular fields
                    for (const field of ['priority', 'status', 'state', 'impact_size', 'owner', 'created_by', 'perceived_owner', 'main_goal', 'resources']) {
                        if (pt[field] !== task[field]) {
                            changes.push({ field, from: pt[field], to: task[field] });
                        }
                    }
                    
                    // Compare parent (by title)
                    const ptParentTitle = pt.parent ? partialIdToTitle[pt.parent] : null;
                    const taskParentTitle = task.parent ? targetIdToTitle[task.parent] : null;
                    if (ptParentTitle !== taskParentTitle) {
                        changes.push({ field: 'parent', from: ptParentTitle, to: taskParentTitle });
                    }
                    
                    // Compare depends_on (by titles)
                    const ptDeps = (pt.depends_on || []).map(id => partialIdToTitle[id] || id).sort();
                    const taskDeps = (task.depends_on || []).map(id => targetIdToTitle[id] || id).sort();
                    if (JSON.stringify(ptDeps) !== JSON.stringify(taskDeps)) {
                        changes.push({ field: 'depends_on', from: ptDeps.join(', ') || 'none', to: taskDeps.join(', ') || 'none' });
                    }
                    
                    if (changes.length > 0) {
                        diff.modified.push({ id: pt.id, targetId: task.id, title, changes });
                    }
                }
            }
            
            for (const title of Object.keys(partialByTitle)) {
                if (!targetByTitle[title]) {
                    const pt = partialByTitle[title];
                    diff.removed.push({ id: pt.id, title });
                }
            }
            
            return diff;
        }
        
        function renderSideView() {
            if (!caseData) return;
            document.getElementById('partialContent').innerHTML = renderState(caseData.partial);
            document.getElementById('targetContent').innerHTML = renderState(caseData.target);
        }
        
        function renderState(state) {
            let html = '';
            // Handle tasks as array (new format)
            const tasks = Array.isArray(state.tasks) ? state.tasks : Object.values(state.tasks || {});
            const idToTitle = {};
            for (const task of tasks) {
                if (task.id && task.title) idToTitle[task.id] = task.title;
            }
            
            // Sort by id
            const sortedTasks = [...tasks].sort((a, b) => (a.id || '').localeCompare(b.id || ''));
            
            for (const task of sortedTasks) {
                html += `
                    <div class="task-card">
                        <div class="task-title">${escapeHtml(task.title || 'Untitled')}<span class="task-id">${task.id || '?'}</span></div>
                        <div class="task-fields">${formatFields(task, idToTitle)}</div>
                    </div>
                `;
            }
            
            return html || '<div class="empty-state">No tasks</div>';
        }
        
        function formatFields(task, idToTitle = {}) {
            const fields = [];
            if (task.priority) fields.push(`<div class="field"><span class="field-name">priority:</span><span class="field-value">${task.priority}</span></div>`);
            if (task.status) fields.push(`<div class="field"><span class="field-name">status:</span><span class="field-value">${task.status}</span></div>`);
            if (task.state) fields.push(`<div class="field"><span class="field-name">state:</span><span class="field-value">${task.state}</span></div>`);
            if (task.impact_size) fields.push(`<div class="field"><span class="field-name">impact:</span><span class="field-value">${task.impact_size}/5</span></div>`);
            if (task.owner) fields.push(`<div class="field"><span class="field-name">owner:</span><span class="field-value">${task.owner}</span></div>`);
            // Add parent field
            if (task.parent) {
                const parentTitle = idToTitle[task.parent] || task.parent;
                fields.push(`<div class="field"><span class="field-name">parent:</span><span class="field-value">${escapeHtml(parentTitle)}</span></div>`);
            }
            // Add depends_on field
            if (task.depends_on && task.depends_on.length > 0) {
                const depTitles = task.depends_on.map(id => idToTitle[id] || id).join(', ');
                fields.push(`<div class="field"><span class="field-name">depends_on:</span><span class="field-value">${escapeHtml(depTitles)}</span></div>`);
            }
            return fields.join('');
        }
        
        function renderPrompt() {
            if (!caseData) return;
            // Show full prompt with context
            document.getElementById('promptBox').textContent = caseData.full_prompt || caseData.prompt;
        }
        
        function renderModelOutput() {
            if (!caseData) return;
            
            const content = document.getElementById('modelContent');
            
            if (!caseData.model_ops) {
                content.innerHTML = `
                    <div class="empty-state">
                        <h2>No model output yet</h2>
                        <p>Click "Run Model" to execute and see results</p>
                    </div>
                `;
                return;
            }
            
            const ops = Array.isArray(caseData.model_ops) ? caseData.model_ops : caseData.model_ops.ops || [];
            
            let html = '<div class="ops-list"><h3 style="color: #00d9ff; margin-bottom: 15px;">Operations (' + ops.length + ')</h3>';
            
            for (const op of ops) {
                html += `
                    <div class="op-item">
                        <div class="op-type">${op.op}</div>
                        <div class="op-details">${JSON.stringify(op, null, 2)}</div>
                    </div>
                `;
            }
            
            html += '</div>';
            
            content.innerHTML = html;
        }
        
        function renderResults() {
            if (!caseData) return;
            
            const statsEl = document.getElementById('resultsDiffStats');
            const contentEl = document.getElementById('resultsDiffContent');
            
            if (!caseData.produced) {
                statsEl.innerHTML = '';
                contentEl.innerHTML = `
                    <div class="empty-state">
                        <h2>No produced state yet</h2>
                        <p>Click "Run Model" to generate produced state and compare</p>
                    </div>
                `;
                return;
            }
            
            // Compare PRODUCED to TARGET (what's wrong with produced)
            const diff = computeProducedVsTargetDiff(caseData.produced, caseData.target);
            
            const totalIssues = diff.missing.length + diff.extra.length + diff.wrong.length;
            
            if (totalIssues === 0) {
                statsEl.innerHTML = '<span style="color: #51cf66; font-weight: bold;">✓ PERFECT MATCH!</span>';
                contentEl.innerHTML = `
                    <div class="empty-state" style="color: #51cf66;">
                        <h2>✓ Perfect Match!</h2>
                        <p>Produced state exactly matches target</p>
                    </div>
                `;
                return;
            }
            
            statsEl.innerHTML = `
                <div class="diff-stat"><span class="icon remove">−</span> ${diff.missing.length} missing</div>
                <div class="diff-stat"><span class="icon add">+</span> ${diff.extra.length} extra</div>
                <div class="diff-stat"><span class="icon modify">~</span> ${diff.wrong.length} wrong values</div>
            `;
            
            let contentHtml = '';
            
            // Missing tasks (in target but not in produced)
            if (diff.missing.length > 0) {
                contentHtml += '<div class="diff-section"><h3>❌ Missing Tasks (should have created)</h3>';
                for (const item of diff.missing) {
                    contentHtml += `
                        <div class="diff-item">
                            <div class="icon remove">−</div>
                            <div class="details">
                                <div class="title"><span class="task-id">${item.id}</span> ${escapeHtml(item.title)}</div>
                                <div class="changes">This task exists in target but was not created</div>
                            </div>
                        </div>
                    `;
                }
                contentHtml += '</div>';
            }
            
            // Extra tasks (in produced but not in target)
            if (diff.extra.length > 0) {
                contentHtml += '<div class="diff-section"><h3>➕ Extra Tasks (should have deleted)</h3>';
                for (const item of diff.extra) {
                    contentHtml += `
                        <div class="diff-item">
                            <div class="icon add">+</div>
                            <div class="details">
                                <div class="title"><span class="task-id">${item.id}</span> ${escapeHtml(item.title)}</div>
                                <div class="changes">This task should not exist in produced state</div>
                            </div>
                        </div>
                    `;
                }
                contentHtml += '</div>';
            }
            
            // Wrong field values
            if (diff.wrong.length > 0) {
                contentHtml += '<div class="diff-section"><h3>⚠️ Wrong Field Values</h3>';
                for (const item of diff.wrong) {
                    let changesHtml = '';
                    for (const change of item.changes) {
                        changesHtml += `
                            <div class="change">
                                <span class="field-name">${change.field}:</span>
                                produced=<span class="old-value">${change.produced ?? 'null'}</span>,
                                expected=<span class="new-value">${change.expected ?? 'null'}</span>
                            </div>
                        `;
                    }
                    contentHtml += `
                        <div class="diff-item">
                            <div class="icon modify">~</div>
                            <div class="details">
                                <div class="title"><span class="task-id">${item.id}</span> ${escapeHtml(item.title)}</div>
                                <div class="changes">${changesHtml}</div>
                            </div>
                        </div>
                    `;
                }
                contentHtml += '</div>';
            }
            
            contentEl.innerHTML = contentHtml;
        }
        
        function computeProducedVsTargetDiff(produced, target) {
            const diff = { missing: [], extra: [], wrong: [] };
            
            const producedByTitle = {};
            const targetByTitle = {};
            
            // Handle tasks as array (new format)
            const producedTasks = Array.isArray(produced.tasks) ? produced.tasks : Object.values(produced.tasks || {});
            const targetTasks = Array.isArray(target.tasks) ? target.tasks : Object.values(target.tasks || {});
            
            // Build id->title maps
            const prodIdToTitle = {};
            const targetIdToTitle = {};
            for (const task of producedTasks) {
                if (task.id && task.title) prodIdToTitle[task.id] = task.title;
            }
            for (const task of targetTasks) {
                if (task.id && task.title) targetIdToTitle[task.id] = task.title;
            }
            
            for (const task of producedTasks) {
                if (task.title) producedByTitle[task.title] = task;
            }
            for (const task of targetTasks) {
                if (task.title) targetByTitle[task.title] = task;
            }
            
            // Find missing (in target but not in produced)
            for (const title of Object.keys(targetByTitle)) {
                const targetTask = targetByTitle[title];
                if (!producedByTitle[title]) {
                    diff.missing.push({ id: targetTask.id, title });
                }
            }
            
            // Find extra (in produced but not in target)
            for (const title of Object.keys(producedByTitle)) {
                const producedTask = producedByTitle[title];
                if (!targetByTitle[title]) {
                    diff.extra.push({ id: producedTask.id, title });
                }
            }
            
            // Find wrong values (both have it but fields differ)
            for (const [title, targetTask] of Object.entries(targetByTitle)) {
                const producedTask = producedByTitle[title];
                if (!producedTask) continue;
                
                const changes = [];
                for (const field of ['priority', 'status', 'state', 'impact_size', 'owner', 'created_by']) {
                    if (producedTask[field] !== targetTask[field]) {
                        changes.push({ 
                            field, 
                            produced: producedTask[field], 
                            expected: targetTask[field] 
                        });
                    }
                }
                
                // Compare parent (by title)
                const prodParentTitle = producedTask.parent ? prodIdToTitle[producedTask.parent] : null;
                const targetParentTitle = targetTask.parent ? targetIdToTitle[targetTask.parent] : null;
                if (prodParentTitle !== targetParentTitle) {
                    changes.push({ 
                        field: 'parent', 
                        produced: producedTask.parent ? `${producedTask.parent} (${prodParentTitle || '?'})` : 'none',
                        expected: targetTask.parent ? `${targetTask.parent} (${targetParentTitle || '?'})` : 'none'
                    });
                }
                
                // Compare depends_on (by titles)
                const prodDeps = (producedTask.depends_on || []).map(id => prodIdToTitle[id] || id).sort();
                const targetDeps = (targetTask.depends_on || []).map(id => targetIdToTitle[id] || id).sort();
                if (JSON.stringify(prodDeps) !== JSON.stringify(targetDeps)) {
                    changes.push({ 
                        field: 'depends_on', 
                        produced: prodDeps.join(', ') || 'none',
                        expected: targetDeps.join(', ') || 'none'
                    });
                }
                
                if (changes.length > 0) {
                    diff.wrong.push({ id: producedTask.id, title, targetId: targetTask.id, changes });
                }
            }
            
            return diff;
        }
        
        function updateStatus() {
            const badge = document.getElementById('statusBadge');
            
            if (!caseData) {
                badge.innerHTML = '';
                return;
            }
            
            if (caseData.model_ops && caseData.produced) {
                // Has been run, check if passed
                const comparison = computeDiff(caseData.produced, caseData.target);
                const passed = comparison.added.length === 0 && comparison.removed.length === 0 && comparison.modified.length === 0;
                
                if (passed) {
                    badge.innerHTML = '<span class="status-badge status-pass">✓ PASSED</span>';
                } else {
                    badge.innerHTML = '<span class="status-badge status-fail">✗ FAILED</span>';
                }
            } else {
                badge.innerHTML = '<span class="status-badge status-pending">○ Not Run</span>';
            }
        }
        
        async function runModel() {
            if (!currentCase) return;
            
            const btn = document.getElementById('runModelBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Running...';
            
            try {
                const res = await fetch('/api/run-model', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ case_id: currentCase, model: 'gpt-5-mini' })
                });
                
                const result = await res.json();
                
                if (result.error) {
                    alert('Error: ' + result.error);
                } else {
                    caseData.model_ops = result.ops;
                    if (result.produced) {
                        caseData.produced = result.produced;
                    }
                    
                    renderModelOutput();
                    renderResults();
                    updateStatus();
                    switchToView('results');  // Switch to results to see produced vs target
                }
            } catch (e) {
                alert('Failed to run model: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '▶ Run Model';
            }
        }
        
        async function compareStates() {
            if (!caseData) return;
            switchToView('compare');
        }
        
        async function runAllTests(failedOnly = false) {
            const btn = failedOnly ? document.getElementById('runFailedBtn') : document.getElementById('runAllBtn');
            const statusEl = document.getElementById('runAllStatus');
            
            btn.disabled = true;
            const originalText = btn.textContent;
            btn.textContent = '⏳ Running...';
            statusEl.innerHTML = `<span style="color:#fcc419">Running ${failedOnly ? 'failed/pending' : 'all'} tests...</span>`;
            
            try {
                const res = await fetch('/api/run-all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model: 'gpt-5-mini', failed_only: failedOnly })
                });
                
                const result = await res.json();
                
                if (result.error) {
                    statusEl.innerHTML = `<span style="color:#ff6b6b">Error: ${result.error}</span>`;
                    return;
                }
                
                const passColor = result.failed === 0 ? '#51cf66' : '#fcc419';
                statusEl.innerHTML = `<span style="color:${passColor}">✓ ${result.passed}/${result.total} passed</span>`;
                
                // Refresh case list to update status colors
                await loadCasesList();
                
                // Show failed cases modal
                if (result.failed > 0) {
                    showFailedCasesModal(result.results.filter(r => !r.passed));
                } else {
                    alert(`All ${result.total} tests passed! 🎉`);
                }
                
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#ff6b6b">Error: ${e.message}</span>`;
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
        
        function showFailedCasesModal(failedCases) {
            // Remove existing modal if any
            const existing = document.getElementById('failedModal');
            if (existing) existing.remove();
            
            let html = `
                <div id="failedModal" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);z-index:1000;display:flex;align-items:center;justify-content:center;">
                    <div style="background:#1a1a2e;border:1px solid #444;border-radius:12px;max-width:800px;max-height:80vh;overflow:auto;padding:20px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                            <h2 style="color:#ff6b6b;margin:0;">❌ Failed Tests (${failedCases.length})</h2>
                            <button onclick="document.getElementById('failedModal').remove()" style="background:#333;border:none;color:#fff;padding:8px 16px;border-radius:6px;cursor:pointer;">Close</button>
                        </div>
                        <table style="width:100%;border-collapse:collapse;">
                            <tr style="background:#16213e;">
                                <th style="text-align:left;padding:10px;border-bottom:1px solid #333;">Case</th>
                                <th style="text-align:left;padding:10px;border-bottom:1px solid #333;">Bucket</th>
                                <th style="text-align:left;padding:10px;border-bottom:1px solid #333;">Errors</th>
                            </tr>
            `;
            
            for (const c of failedCases) {
                const errors = c.error ? [c.error] : (c.errors || []).slice(0, 3);
                html += `
                    <tr style="cursor:pointer;" onclick="document.getElementById('failedModal').remove(); document.getElementById('caseSelect').value='${c.case_id}'; loadCase('${c.case_id}');">
                        <td style="padding:10px;border-bottom:1px solid #333;color:#00d9ff;">${c.case_id}</td>
                        <td style="padding:10px;border-bottom:1px solid #333;">${c.bucket || '-'}</td>
                        <td style="padding:10px;border-bottom:1px solid #333;font-size:0.85rem;color:#ff9999;">${errors.join('<br>')}</td>
                    </tr>
                `;
            }
            
            html += '</table></div></div>';
            document.body.insertAdjacentHTML('beforeend', html);
        }
        
        function showView(viewName) {
            // Called from tab click
            switchToView(viewName);
        }
        
        function switchToView(viewName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.view-container > div').forEach(v => v.classList.remove('active'));
            
            // Find and activate the correct tab
            const tabs = document.querySelectorAll('.tab');
            const viewMap = {'compare': 0, 'side': 1, 'prompt': 2, 'model': 3, 'results': 4};
            if (viewMap[viewName] !== undefined && tabs[viewMap[viewName]]) {
                tabs[viewMap[viewName]].classList.add('active');
            }
            
            const view = document.getElementById(viewName + 'View');
            if (view) {
                view.classList.add('active');
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Initialize
        loadCasesList();
    </script>
</body>
</html>
'''


def main():
    parser = argparse.ArgumentParser(description='Serve the TaskGraph case viewer')
    parser.add_argument('--port', type=int, default=8765, help='Port (default: 8765)')
    parser.add_argument('--cases_dir', type=str, default='cases', help='Cases directory')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    parser.add_argument('--api-key', type=str, help='OpenAI API key')
    
    args = parser.parse_args()
    
    # Set API key from argument or try to read from file
    if args.api_key:
        os.environ['OPENAI_API_KEY'] = args.api_key
    elif not os.environ.get('OPENAI_API_KEY'):
        # Try to read from api_key.txt in project dir
        key_file = os.path.join(PROJECT_DIR, 'api_key.txt')
        if os.path.exists(key_file):
            with open(key_file) as f:
                os.environ['OPENAI_API_KEY'] = f.read().strip()
                print(f"Loaded API key from {key_file}")
    
    handler = lambda *a, **kw: ViewerHandler(*a, cases_dir=args.cases_dir, **kw)
    
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        url = f"http://localhost:{args.port}"
        print(f"Serving viewer at {url}")
        print("Press Ctrl+C to stop")
        
        if not args.no_browser:
            webbrowser.open(url)
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped")


if __name__ == '__main__':
    main()

