// OrgOs Web App - Complete Functionality

const API_BASE = window.location.origin;
let currentUser = null;
let currentQuestions = [];
let currentQuestionIndex = 0;

// ============================================================================
// Storage & Auth
// ============================================================================

function saveUser(user) {
    localStorage.setItem('orgos_user_id', user.id);
    localStorage.setItem('orgos_user_name', user.name);
    currentUser = user;
}

function loadUser() {
    const id = localStorage.getItem('orgos_user_id');
    const name = localStorage.getItem('orgos_user_name');
    if (id && name) {
        currentUser = { id, name };
        return true;
    }
    return false;
}

function logout() {
    localStorage.clear();
    currentUser = null;
    location.reload();
}

// ============================================================================
// API Calls
// ============================================================================

async function apiCall(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (currentUser && !options.skipAuth) {
        headers['X-User-Id'] = currentUser.id;
    }
    
    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers
    });
    
    if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`);
    }
    
    return response.json();
}

// ============================================================================
// Registration & Login
// ============================================================================

async function register() {
    const name = document.getElementById('user-name').value.trim();
    const email = document.getElementById('user-email').value.trim();
    
    if (!name) {
        alert('Please enter your name');
        return;
    }
    
    try {
        const user = await apiCall('/users', {
            method: 'POST',
            body: JSON.stringify({ name, email: email || null }),
            skipAuth: true
        });
        
        saveUser(user);
        showChat();
    } catch (error) {
        alert('Registration failed: ' + error.message);
    }
}

async function showUserList() {
    try {
        const users = await apiCall('/users', { skipAuth: true });
        const listDiv = document.getElementById('user-list');
        
        listDiv.innerHTML = users.map(user => `
            <div class="user-item" onclick="loginAsUser('${user.id}', '${user.name}')">
                👤 ${user.name}
            </div>
        `).join('');
        
        document.getElementById('user-list-modal').classList.remove('hidden');
    } catch (error) {
        alert('Failed to load users: ' + error.message);
    }
}

function hideUserList() {
    document.getElementById('user-list-modal').classList.add('hidden');
}

function loginAsUser(id, name) {
    saveUser({ id, name });
    hideUserList();
    showChat();
}

// ============================================================================
// Page Navigation
// ============================================================================

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
}

function showChat() {
    if (!currentUser) {
        showPage('auth-page');
        return;
    }
    
    document.getElementById('current-user-name').textContent = currentUser.name;
    showPage('chat-page');
    
    // Auto-load questions
    loadQuestions();
}

function showDashboard() {
    if (!currentUser) {
        showPage('auth-page');
        return;
    }
    
    document.getElementById('dashboard-user-name').textContent = currentUser.name;
    showPage('dashboard-page');
    
    // Load dashboard data
    loadTasks();
    loadAlignments();
    loadMisalignments();
}

function showSection(sectionName) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    
    document.getElementById(`${sectionName}-section`).classList.add('active');
    document.getElementById(`${sectionName}-nav`).classList.add('active');
    
    // Load data for specific sections
    if (sectionName === 'tasks') {
        loadTasks();
    } else if (sectionName === 'alignments') {
        loadAlignments();
    } else if (sectionName === 'misalignments') {
        loadMisalignments();
    } else if (sectionName === 'graph') {
        loadTaskGraph();
    }
}

// ============================================================================
// Questions & Chat Interface
// ============================================================================

async function loadQuestions() {
    const chatDiv = document.getElementById('chat-messages');
    chatDiv.innerHTML = '<div class="loading">Loading questions</div>';
    
    try {
        currentQuestions = await apiCall('/questions/next?max_questions=10');
        
        if (currentQuestions.length === 0) {
            chatDiv.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">✅</div>
                    <h3>All caught up!</h3>
                    <p>No questions available right now.</p>
                    <p>Check back later or ask teammates to create tasks.</p>
                </div>
            `;
            return;
        }
        
        currentQuestionIndex = 0;
        displayCurrentQuestion();
    } catch (error) {
        chatDiv.innerHTML = `<div class="message error">Failed to load questions: ${error.message}</div>`;
    }
}

function displayCurrentQuestion() {
    const question = currentQuestions[currentQuestionIndex];
    const chatDiv = document.getElementById('chat-messages');
    const inputDiv = document.getElementById('question-input');
    
    // Determine if this is about own task or someone else's
    const isOwnTask = question.target_user_id === currentUser.id;
    const contextLabel = isOwnTask 
        ? `📝 Your task: ${question.task_title || 'Your profile'}`
        : `👤 ${question.target_user_name}'s task: ${question.task_title || 'Their profile'}`;
    
    // Display question message
    const questionHTML = `
        <div class="chat-message system">
            <div class="question-header">
                <span class="question-meta">
                    ${contextLabel}
                </span>
                <span class="question-meta">
                    ${currentQuestionIndex + 1}/${currentQuestions.length}
                </span>
            </div>
            <div class="question-context">
                ${isOwnTask 
                    ? `<strong>About your ${question.task_title ? 'task' : 'profile'}</strong>` 
                    : `<strong>What do YOU think about ${question.target_user_name}'s ${question.task_title ? 'task' : 'profile'}?</strong>`
                }
            </div>
            <div class="question-text">${question.question_text}</div>
            ${question.is_followup ? '<div class="question-meta">⏱ Follow-up question</div>' : ''}
            ${!isOwnTask ? '<div class="question-hint">💡 We\'re asking for YOUR perception of their work</div>' : ''}
        </div>
    `;
    
    chatDiv.innerHTML = questionHTML;
    
    // Create appropriate input
    let inputHTML = '';
    
    if (question.attribute_type === 'enum') {
        const options = question.allowed_values.map(v => 
            `<option value="${v}">${v}</option>`
        ).join('');
        inputHTML = `
            <select id="answer-value" class="answer-input">
                <option value="">Select...</option>
                ${options}
            </select>
        `;
    } else if (question.attribute_type === 'bool') {
        inputHTML = `
            <div class="answer-input">
                <label class="toggle-container" style="margin: 0;">
                    <span>Yes / No</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="answer-value">
                        <span class="slider"></span>
                    </label>
                </label>
            </div>
        `;
    } else if (question.attribute_type === 'int' || question.attribute_type === 'float') {
        inputHTML = `
            <input type="number" id="answer-value" class="answer-input" 
                   placeholder="Enter a number" min="1" max="5" step="${question.attribute_type === 'float' ? '0.1' : '1'}">
        `;
    } else {
        // String or other
        const isLongText = question.attribute_name === 'main_goal' || 
                          question.attribute_name === 'blocking_reason';
        
        inputHTML = isLongText ? `
            <textarea id="answer-value" class="answer-input" rows="4" 
                      placeholder="Type your answer..."></textarea>
        ` : `
            <input type="text" id="answer-value" class="answer-input" 
                   placeholder="Type your answer...">
        `;
    }
    
    inputDiv.innerHTML = `
        <div class="card">
            ${inputHTML}
            <div class="checkbox-container">
                <input type="checkbox" id="answer-refused">
                <label for="answer-refused">I don't want to answer this</label>
            </div>
            <div class="button-group">
                <button onclick="submitAnswer()" class="primary-btn">Submit Answer</button>
                ${currentQuestionIndex < currentQuestions.length - 1 ? 
                    '<button onclick="skipToNext()" class="secondary-btn">Skip</button>' : ''}
            </div>
        </div>
    `;
    
    inputDiv.classList.remove('hidden');
}

async function submitAnswer() {
    const question = currentQuestions[currentQuestionIndex];
    const refused = document.getElementById('answer-refused').checked;
    
    let value = null;
    if (!refused) {
        const valueInput = document.getElementById('answer-value');
        
        if (question.attribute_type === 'bool') {
            value = valueInput.checked ? 'true' : 'false';
        } else {
            value = valueInput.value.trim();
        }
        
        if (!value && !refused) {
            alert('Please provide an answer or check "I don\'t want to answer"');
            return;
        }
    }
    
    try {
        await apiCall('/answers', {
            method: 'POST',
            body: JSON.stringify({
                question_id: question.question_id,
                value: value,
                refused: refused
            })
        });
        
        // Show success and move to next
        showAnswerSuccess();
        
        setTimeout(() => {
            if (currentQuestionIndex < currentQuestions.length - 1) {
                currentQuestionIndex++;
                displayCurrentQuestion();
            } else {
                // All done!
                showAllDone();
            }
        }, 1000);
        
    } catch (error) {
        alert('Failed to submit answer: ' + error.message);
    }
}

function skipToNext() {
    if (currentQuestionIndex < currentQuestions.length - 1) {
        currentQuestionIndex++;
        displayCurrentQuestion();
    }
}

function showAnswerSuccess() {
    const inputDiv = document.getElementById('question-input');
    inputDiv.innerHTML = '<div class="message success">✅ Answer saved!</div>';
}

function showAllDone() {
    const chatDiv = document.getElementById('chat-messages');
    const inputDiv = document.getElementById('question-input');
    
    chatDiv.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">🎉</div>
            <h3>All questions answered!</h3>
            <p>Great job! You've completed all available questions.</p>
        </div>
    `;
    
    inputDiv.innerHTML = `
        <div class="button-group">
            <button onclick="loadQuestions()" class="primary-btn">Check for More</button>
            <button onclick="showDashboard()" class="secondary-btn">View Dashboard</button>
        </div>
    `;
}

// ============================================================================
// Dashboard - Tasks
// ============================================================================

async function loadTasks() {
    const listDiv = document.getElementById('tasks-list');
    listDiv.innerHTML = '<div class="loading">Loading tasks</div>';
    
    try {
        const tasks = await apiCall('/tasks');
        
        if (tasks.length === 0) {
            listDiv.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📋</div>
                    <p>No tasks yet. Create your first task!</p>
                </div>
            `;
            return;
        }
        
        listDiv.innerHTML = tasks.map(task => `
            <div class="task-item">
                <div class="task-item-header">
                    <span class="task-title">${task.title}</span>
                    <span class="task-owner">${task.owner_name}</span>
                </div>
                ${task.description ? `<div class="task-description">${task.description}</div>` : ''}
            </div>
        `).join('');
        
    } catch (error) {
        listDiv.innerHTML = `<div class="message error">Failed to load tasks: ${error.message}</div>`;
    }
}

async function showCreateTask() {
    // Load available tasks for parent and dependency selection
    try {
        const tasks = await apiCall('/tasks?include_self=true&include_aligned=true');
        
        const parentSelect = document.getElementById('task-parent');
        const depsSelect = document.getElementById('task-dependencies');
        
        parentSelect.innerHTML = '<option value="">None</option>' +
            tasks.map(t => `<option value="${t.id}">${t.title}</option>`).join('');
        
        depsSelect.innerHTML = tasks.map(t => 
            `<option value="${t.id}">${t.title} (${t.owner_name})</option>`
        ).join('');
        
        document.getElementById('create-task-modal').classList.remove('hidden');
    } catch (error) {
        alert('Failed to load tasks: ' + error.message);
    }
}

function hideCreateTask() {
    document.getElementById('create-task-modal').classList.add('hidden');
    document.getElementById('task-title').value = '';
    document.getElementById('task-description').value = '';
    document.getElementById('task-children').value = '';
}

async function createTask() {
    const title = document.getElementById('task-title').value.trim();
    const description = document.getElementById('task-description').value.trim();
    const parentId = document.getElementById('task-parent').value || null;
    const childrenInput = document.getElementById('task-children').value.trim();
    const dependenciesSelect = document.getElementById('task-dependencies');
    
    if (!title) {
        alert('Please enter a task title');
        return;
    }
    
    // Parse children (comma-separated task titles)
    const children = childrenInput ? 
        childrenInput.split(',').map(s => s.trim()).filter(s => s) : 
        null;
    
    // Get selected dependencies
    const dependencies = Array.from(dependenciesSelect.selectedOptions)
        .map(opt => opt.value)
        .filter(v => v);
    
    try {
        await apiCall('/tasks', {
            method: 'POST',
            body: JSON.stringify({ 
                title, 
                description: description || null,
                parent_id: parentId,
                children: children,
                dependencies: dependencies.length > 0 ? dependencies : null
            })
        });
        
        hideCreateTask();
        loadTasks();
        
        // Refresh graph if we're on that section
        const graphSection = document.getElementById('graph-section');
        if (graphSection && graphSection.classList.contains('active')) {
            loadTaskGraph();
        }
    } catch (error) {
        alert('Failed to create task: ' + error.message);
    }
}

// ============================================================================
// Dashboard - Alignments
// ============================================================================

async function loadAlignments() {
    const listDiv = document.getElementById('alignments-list');
    listDiv.innerHTML = '<div class="loading">Loading team members</div>';
    
    try {
        const [allUsers, alignments] = await Promise.all([
            apiCall('/users', { skipAuth: true }),
            apiCall('/alignments')
        ]);
        
        const alignedIds = new Set(alignments.map(a => a.target_user_id));
        
        // Filter out current user
        const otherUsers = allUsers.filter(u => u.id !== currentUser.id);
        
        if (otherUsers.length === 0) {
            listDiv.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">👥</div>
                    <p>No other users yet. Invite teammates to join!</p>
                </div>
            `;
            return;
        }
        
        listDiv.innerHTML = otherUsers.map(user => `
            <div class="toggle-container">
                <span>👤 ${user.name}</span>
                <label class="toggle-switch">
                    <input type="checkbox" 
                           ${alignedIds.has(user.id) ? 'checked' : ''} 
                           onchange="toggleAlignment('${user.id}', this.checked)">
                    <span class="slider"></span>
                </label>
            </div>
        `).join('');
        
    } catch (error) {
        listDiv.innerHTML = `<div class="message error">Failed to load alignments: ${error.message}</div>`;
    }
}

async function toggleAlignment(userId, align) {
    try {
        await apiCall('/alignments', {
            method: 'POST',
            body: JSON.stringify({ target_user_id: userId, align })
        });
    } catch (error) {
        alert('Failed to update alignment: ' + error.message);
        loadAlignments(); // Reload to reset state
    }
}

// ============================================================================
// Dashboard - Misalignments
// ============================================================================

let currentMisalignmentView = 'stats';

function showMisalignmentView(view) {
    currentMisalignmentView = view;
    
    // Update button states
    document.getElementById('stats-view-btn').classList.toggle('active', view === 'stats');
    document.getElementById('list-view-btn').classList.toggle('active', view === 'list');
    
    // Show/hide sections
    document.getElementById('misalignment-charts').style.display = view === 'stats' ? 'grid' : 'none';
    document.getElementById('misalignments-list').style.display = view === 'list' ? 'block' : 'none';
}

async function loadMisalignments() {
    const statsDiv = document.getElementById('misalignment-stats');
    const chartsDiv = document.getElementById('misalignment-charts');
    const listDiv = document.getElementById('misalignments-list');
    
    statsDiv.innerHTML = '<div class="loading">Loading statistics...</div>';
    chartsDiv.innerHTML = '';
    listDiv.innerHTML = '';
    
    try {
        // Load both statistics and detailed misalignments
        const [stats, misalignments] = await Promise.all([
            apiCall('/misalignments/statistics'),
            apiCall('/misalignments')
        ]);
        
        // Display statistics overview
        displayStatistics(stats);
        
        // Display charts
        displayCharts(stats);
        
        // Display detailed list
        displayMisalignmentsList(misalignments);
        
        // Update badge
        document.getElementById('misalignment-badge').textContent = misalignments.length;
        
    } catch (error) {
        statsDiv.innerHTML = `<div class="message error">Failed to load misalignments: ${error.message}</div>`;
    }
}

function displayStatistics(stats) {
    const statsDiv = document.getElementById('misalignment-stats');
    
    statsDiv.innerHTML = `
        <div class="stat-card">
            <div class="stat-label">Total Misalignments</div>
            <div class="stat-value">${stats.total_count}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Avg Similarity</div>
            <div class="stat-value">${(stats.average_similarity * 100).toFixed(0)}%</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">High Severity</div>
            <div class="stat-value" style="color: var(--danger)">${stats.by_severity.high}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Attributes Affected</div>
            <div class="stat-value">${Object.keys(stats.by_attribute).length}</div>
        </div>
    `;
}

function displayCharts(stats) {
    const chartsDiv = document.getElementById('misalignment-charts');
    
    if (stats.total_count === 0) {
        chartsDiv.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">✨</div>
                <h3>Perfect Alignment!</h3>
                <p>No perception gaps detected.</p>
            </div>
        `;
        return;
    }
    
    // Chart 1: Severity Distribution
    const severityHTML = `
        <div class="chart-card">
            <div class="chart-title">📊 Misalignment Severity</div>
            <div class="severity-chart">
                <div class="severity-item high">
                    <div class="severity-label">High</div>
                    <div class="severity-count">${stats.by_severity.high}</div>
                    <div class="severity-label">< 30% similar</div>
                </div>
                <div class="severity-item medium">
                    <div class="severity-label">Medium</div>
                    <div class="severity-count">${stats.by_severity.medium}</div>
                    <div class="severity-label">30-60% similar</div>
                </div>
                <div class="severity-item low">
                    <div class="severity-label">Low</div>
                    <div class="severity-count">${stats.by_severity.low}</div>
                    <div class="severity-label">> 60% similar</div>
                </div>
            </div>
        </div>
    `;
    
    // Chart 2: By Attribute
    const attrEntries = Object.entries(stats.by_attribute)
        .sort((a, b) => b[1].count - a[1].count)
        .slice(0, 5);
    
    const maxCount = Math.max(...attrEntries.map(([_, data]) => data.count));
    
    const attributeHTML = `
        <div class="chart-card">
            <div class="chart-title">📈 Misalignments by Attribute</div>
            <div class="bar-chart">
                ${attrEntries.map(([attr, data]) => `
                    <div class="bar-item">
                        <div class="bar-label">${attr}</div>
                        <div class="bar-container">
                            <div class="bar-fill" style="width: ${(data.count / maxCount * 100)}%">
                                <span class="bar-value">${data.count}</span>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    
    // Chart 3: By User
    const userHTML = `
        <div class="chart-card">
            <div class="chart-title">👥 Misalignments by Teammate</div>
            <div class="user-comparison">
                ${Object.entries(stats.by_user).map(([user, data]) => `
                    <div class="user-item">
                        <div class="user-name">${user}</div>
                        <div class="user-stats">
                            <div><span class="user-stat-value">${data.count}</span> gaps</div>
                            <div><span class="user-stat-value">${(data.avg_similarity * 100).toFixed(0)}%</span> avg</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    
    // Chart 4: Most Misaligned Tasks
    const tasksHTML = stats.most_misaligned_tasks && stats.most_misaligned_tasks.length > 0 ? `
        <div class="chart-card">
            <div class="chart-title">🎯 Most Misaligned Tasks</div>
            <div class="user-comparison">
                ${stats.most_misaligned_tasks.map(task => `
                    <div class="user-item">
                        <div class="user-name">${task.task}</div>
                        <div class="user-stats">
                            <div><span class="user-stat-value">${task.count}</span> gaps</div>
                            <div><span class="user-stat-value">${(task.avg_similarity * 100).toFixed(0)}%</span> similar</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    ` : '';
    
    chartsDiv.innerHTML = severityHTML + attributeHTML + userHTML + tasksHTML;
}

function displayMisalignmentsList(misalignments) {
    const listDiv = document.getElementById('misalignments-list');
    
    if (misalignments.length === 0) {
        listDiv.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">✨</div>
                <h3>Perfect Alignment!</h3>
                <p>No perception gaps detected with your teammates.</p>
                <p class="small">This means your views are aligned! 🎉</p>
            </div>
        `;
        return;
    }
    
    // Group by user
    const grouped = {};
    misalignments.forEach(m => {
        if (!grouped[m.other_user_name]) {
            grouped[m.other_user_name] = [];
        }
        grouped[m.other_user_name].push(m);
    });
    
    listDiv.innerHTML = Object.entries(grouped).map(([userName, items]) => {
        const itemsHTML = items.map(m => {
            const severity = m.similarity_score < 0.3 ? 'high' : 
                            m.similarity_score < 0.5 ? 'medium' : 'low';
            
            return `
                <div class="misalignment-item ${severity}">
                    <div class="misalignment-detail">
                        <strong>📝 ${m.task_title || 'General'}</strong>
                    </div>
                    <div class="misalignment-detail">
                        <strong>${m.attribute_label}</strong>
                    </div>
                    <div class="value-comparison">
                        <div class="value-box yours">
                            <div class="value-label">Your View</div>
                            <div class="value-text">${m.your_value}</div>
                        </div>
                        <div class="value-box theirs">
                            <div class="value-label">Their View</div>
                            <div class="value-text">${m.their_value}</div>
                        </div>
                    </div>
                    <div class="similarity-score ${severity}">
                        ${severity === 'high' ? '🚨 Very Different' : 
                          severity === 'medium' ? '⚠️ Somewhat Different' : 
                          '✓ Slightly Different'} 
                        (${(m.similarity_score * 100).toFixed(0)}% similar)
                    </div>
                </div>
            `;
        }).join('');
        
        return `
            <div class="misalignment-group">
                <div class="misalignment-group-header">
                    <h4>👤 ${userName}</h4>
                    <span class="badge">${items.length}</span>
                </div>
                ${itemsHTML}
            </div>
        `;
    }).join('');
}

// ============================================================================
// Task Graph Visualization
// ============================================================================

let allGraphTasks = [];
let taskAttributes = [];
let graphFilters = {
    owner: '',
    showParents: true,
    showChildren: true,
    showDependencies: true,
    attributes: {}
};

// Graph view state
let graphView = {
    zoom: 1,
    panX: 0,
    panY: 0,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    lastPanX: 0,
    lastPanY: 0
};

async function loadTaskGraph() {
    const canvas = document.getElementById('graph-canvas');
    canvas.innerHTML = '<div class="loading">Loading task graph...</div>';
    
    try {
        // Load tasks with attributes
        const [tasks, attributes] = await Promise.all([
            apiCall('/tasks/graph/with-attributes', { skipAuth: true }),
            apiCall('/task-attributes', { skipAuth: true })
        ]);
        
        allGraphTasks = tasks;
        taskAttributes = attributes;
        
        // Populate owner filter (multi-select)
        const ownerFilterContent = document.getElementById('filter-content-owner');
        const owners = [...new Set(tasks.map(t => t.owner_name))];
        
        ownerFilterContent.innerHTML = owners.map(owner => `
            <div class="filter-option" onclick="event.stopPropagation()">
                <input type="checkbox" id="filter-owner-${owner.replace(/\s/g, '_')}" 
                       value="${owner}" data-attr-name="owner" onchange="updateOwnerFilter()">
                <label for="filter-owner-${owner.replace(/\s/g, '_')}" style="cursor: pointer">${owner}</label>
            </div>
        `).join('');
        
        // Create attribute filters
        createAttributeFilters(attributes, tasks);
        
        // Setup graph interaction listeners
        setupGraphInteractions();
        
        renderGraph();
    } catch (error) {
        console.error('Graph load error:', error);
        canvas.innerHTML = `<div class="message error">Failed to load task graph: ${error.message}</div>`;
    }
}

function setupGraphInteractions() {
    const container = document.getElementById('graph-container');
    const canvas = document.getElementById('graph-canvas');
    
    // Remove old listeners if any
    const newContainer = container.cloneNode(true);
    container.parentNode.replaceChild(newContainer, container);
    const graphContainer = document.getElementById('graph-container');
    
    // Zoom with mouse wheel
    graphContainer.addEventListener('wheel', (e) => {
        e.preventDefault();
        
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        const newZoom = Math.min(Math.max(0.2, graphView.zoom * delta), 3);
        
        // Zoom towards mouse position
        const rect = graphContainer.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        const scale = newZoom / graphView.zoom;
        graphView.panX = mouseX - (mouseX - graphView.panX) * scale;
        graphView.panY = mouseY - (mouseY - graphView.panY) * scale;
        graphView.zoom = newZoom;
        
        updateGraphTransform();
    }, { passive: false });
    
    // Pan with mouse drag
    graphContainer.addEventListener('mousedown', (e) => {
        // Allow both left and right mouse buttons for dragging
        if (e.button === 0 || e.button === 2) {
            e.preventDefault();
            graphView.isDragging = true;
            graphView.dragStartX = e.clientX;
            graphView.dragStartY = e.clientY;
            graphView.lastPanX = graphView.panX;
            graphView.lastPanY = graphView.panY;
            graphContainer.classList.add('grabbing');
        }
    });
    
    graphContainer.addEventListener('mousemove', (e) => {
        if (graphView.isDragging) {
            const dx = e.clientX - graphView.dragStartX;
            const dy = e.clientY - graphView.dragStartY;
            graphView.panX = graphView.lastPanX + dx;
            graphView.panY = graphView.lastPanY + dy;
            updateGraphTransform();
        }
    });
    
    graphContainer.addEventListener('mouseup', () => {
        graphView.isDragging = false;
        graphContainer.classList.remove('grabbing');
    });
    
    graphContainer.addEventListener('mouseleave', () => {
        graphView.isDragging = false;
        graphContainer.classList.remove('grabbing');
    });
    
    // Prevent context menu on right click
    graphContainer.addEventListener('contextmenu', (e) => {
        e.preventDefault();
    });
}

function updateGraphTransform() {
    const canvas = document.getElementById('graph-canvas');
    if (canvas) {
        canvas.style.transform = `translate(${graphView.panX}px, ${graphView.panY}px) scale(${graphView.zoom})`;
    }
}

function resetGraphView() {
    graphView.zoom = 1;
    graphView.panX = 0;
    graphView.panY = 0;
    graphView.isDragging = false;
    updateGraphTransform();
}

// ============================================================================
// Task Details Popup
// ============================================================================

async function showTaskDetails(taskId) {
    const modal = document.getElementById('task-details-modal');
    const title = document.getElementById('task-details-title');
    const content = document.getElementById('task-details-content');
    
    title.textContent = 'Loading...';
    content.innerHTML = '<div class="loading">Loading task details...</div>';
    modal.classList.remove('hidden');
    
    try {
        const data = await apiCall(`/tasks/${taskId}/answers`, { skipAuth: true });
        
        // Update title
        title.textContent = data.task_title;
        
        // Build content
        let html = '';
        
        // Task info section
        html += `
            <div class="task-info-section">
                <h4>📋 Task Information</h4>
                <div class="task-info-row">
                    <span class="task-info-label">Owner:</span>
                    <span class="task-info-value">${data.owner_name}</span>
                </div>
                ${data.task_description ? `
                    <div class="task-info-row">
                        <span class="task-info-label">Description:</span>
                        <span class="task-info-value">${data.task_description}</span>
                    </div>
                ` : ''}
            </div>
        `;
        
        // Answers section as table
        const attributeKeys = Object.keys(data.answers_by_attribute);
        
        if (attributeKeys.length > 0) {
            // Get all unique users who answered
            const allUsers = new Set();
            attributeKeys.forEach(attrKey => {
                const attr = data.answers_by_attribute[attrKey];
                if (attr.answers) {
                    attr.answers.forEach(answer => {
                        allUsers.add(JSON.stringify({
                            id: answer.user_id,
                            name: answer.user_name,
                            is_owner: answer.is_owner
                        }));
                    });
                }
            });
            
            const users = Array.from(allUsers).map(u => JSON.parse(u));
            // Sort so owner is first
            users.sort((a, b) => b.is_owner - a.is_owner);
            
            html += '<div class="task-info-section"><h4>💭 What People Think</h4>';
            html += '<table class="answers-table">';
            
            // Header row
            html += '<thead><tr><th>Attribute</th>';
            users.forEach(user => {
                const ownerLabel = user.is_owner ? ' 👑' : '';
                html += `<th class="${user.is_owner ? 'owner-column' : ''}">${user.name}${ownerLabel}</th>`;
            });
            html += '</tr></thead>';
            
            // Data rows
            html += '<tbody>';
            attributeKeys.forEach(attrKey => {
                const attr = data.answers_by_attribute[attrKey];
                html += `<tr><td class="attr-label">${attr.attribute_label}</td>`;
                
                users.forEach(user => {
                    const answer = attr.answers?.find(a => a.user_id === user.id);
                    const cellClass = user.is_owner ? 'owner-column' : '';
                    html += `<td class="${cellClass}">${answer ? answer.value : '-'}</td>`;
                });
                
                html += '</tr>';
            });
            html += '</tbody></table></div>';
        } else {
            html += `
                <div class="task-info-section">
                    <div class="no-answers">
                        No one has answered questions about this task yet.
                    </div>
                </div>
            `;
        }
        
        content.innerHTML = html;
        
    } catch (error) {
        content.innerHTML = `<div class="message error">Failed to load task details: ${error.message}</div>`;
    }
}

function closeTaskDetails() {
    document.getElementById('task-details-modal').classList.add('hidden');
}

function createAttributeFilters(attributes, tasks) {
    const container = document.getElementById('attribute-filters');
    container.innerHTML = '';
    
    // Create filter for each attribute (only enum types for multi-select)
    attributes.forEach(attr => {
        if (attr.type !== 'enum') return; // Only show enum attributes as filters
        
        const filterDiv = document.createElement('div');
        filterDiv.className = 'attribute-filter';
        
        const label = document.createElement('label');
        label.textContent = attr.label + ':';
        filterDiv.appendChild(label);
        
        // Collect all unique values for this attribute from tasks
        const values = new Set();
        tasks.forEach(task => {
            if (task.attributes && task.attributes[attr.name]) {
                values.add(task.attributes[attr.name].value);
            }
        });
        
        if (values.size === 0) return; // Skip if no values
        
        // Create multi-select dropdown
        const dropdown = document.createElement('div');
        dropdown.className = 'filter-dropdown';
        dropdown.id = `filter-dropdown-${attr.name}`;
        
        const button = document.createElement('button');
        button.className = 'filter-button';
        button.id = `filter-btn-${attr.name}`;
        button.innerHTML = '<span>All</span><span>▼</span>';
        button.onclick = (e) => {
            e.stopPropagation();
            toggleFilterDropdown(attr.name);
        };
        
        const dropdownContent = document.createElement('div');
        dropdownContent.className = 'filter-dropdown-content';
        dropdownContent.id = `filter-content-${attr.name}`;
        
        Array.from(values).sort().forEach(val => {
            const option = document.createElement('div');
            option.className = 'filter-option';
            option.onclick = (e) => e.stopPropagation();
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `filter-${attr.name}-${val}`;
            checkbox.value = val;
            checkbox.dataset.attrName = attr.name;
            checkbox.onchange = () => updateFilterButton(attr.name);
            
            const labelEl = document.createElement('label');
            labelEl.htmlFor = checkbox.id;
            labelEl.textContent = val;
            labelEl.style.cursor = 'pointer';
            
            option.appendChild(checkbox);
            option.appendChild(labelEl);
            dropdownContent.appendChild(option);
        });
        
        dropdown.appendChild(button);
        dropdown.appendChild(dropdownContent);
        filterDiv.appendChild(dropdown);
        container.appendChild(filterDiv);
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', () => {
        document.querySelectorAll('.filter-dropdown-content').forEach(content => {
            content.classList.remove('show');
        });
    });
}

function toggleFilterDropdown(attrName) {
    const content = document.getElementById(`filter-content-${attrName}`);
    const wasShown = content.classList.contains('show');
    
    // Close all dropdowns
    document.querySelectorAll('.filter-dropdown-content').forEach(c => {
        c.classList.remove('show');
    });
    
    // Toggle this one
    if (!wasShown) {
        content.classList.add('show');
    }
}

function updateFilterButton(attrName) {
    const checkboxes = document.querySelectorAll(`input[data-attr-name="${attrName}"]:checked`);
    const button = document.getElementById(`filter-btn-${attrName}`);
    const span = button.querySelector('span:first-child');
    
    if (checkboxes.length === 0) {
        span.textContent = 'All';
        button.classList.remove('has-selection');
    } else if (checkboxes.length === 1) {
        span.textContent = checkboxes[0].value;
        button.classList.add('has-selection');
    } else {
        span.textContent = `${checkboxes.length} selected`;
        button.classList.add('has-selection');
    }
    
    applyFilters();
}

function updateOwnerFilter() {
    const checkboxes = document.querySelectorAll('input[data-attr-name="owner"]:checked');
    const button = document.getElementById('filter-btn-owner');
    const span = button.querySelector('span:first-child');
    
    if (checkboxes.length === 0) {
        span.textContent = 'All';
        button.classList.remove('has-selection');
    } else if (checkboxes.length === 1) {
        span.textContent = checkboxes[0].value;
        button.classList.add('has-selection');
    } else {
        span.textContent = `${checkboxes.length} selected`;
        button.classList.add('has-selection');
    }
    
    applyFilters();
}

function applyFilters() {
    // Owner filter (multi-select)
    const ownerCheckboxes = document.querySelectorAll('input[data-attr-name="owner"]:checked');
    if (ownerCheckboxes.length > 0) {
        graphFilters.owner = Array.from(ownerCheckboxes).map(cb => cb.value);
    } else {
        graphFilters.owner = null;
    }
    
    graphFilters.showParents = document.getElementById('show-parents').checked;
    graphFilters.showChildren = document.getElementById('show-children').checked;
    graphFilters.showDependencies = document.getElementById('show-dependencies').checked;
    
    // Collect attribute filters (multi-select)
    graphFilters.attributes = {};
    taskAttributes.forEach(attr => {
        if (attr.type === 'enum') {
            const checkboxes = document.querySelectorAll(`input[data-attr-name="${attr.name}"]:checked`);
            if (checkboxes.length > 0) {
                graphFilters.attributes[attr.name] = {
                    values: Array.from(checkboxes).map(cb => cb.value),
                    type: attr.type
                };
            }
        }
    });
    
    renderGraph();
}

function clearFilters() {
    // Clear all filter checkboxes
    document.querySelectorAll('.filter-dropdown-content input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    
    // Update owner filter button
    updateOwnerFilter();
    
    // Update all attribute filter buttons
    taskAttributes.forEach(attr => {
        if (attr.type === 'enum') {
            updateFilterButton(attr.name);
        }
    });
    
    // Reset checkboxes
    document.getElementById('show-parents').checked = true;
    document.getElementById('show-children').checked = true;
    document.getElementById('show-dependencies').checked = true;
    
    applyFilters();
}

function renderGraph() {
    const canvas = document.getElementById('graph-canvas');
    
    // Filter tasks
    let filteredTasks = allGraphTasks;
    
    // Filter by owner (multi-select support)
    if (graphFilters.owner && graphFilters.owner.length > 0) {
        filteredTasks = filteredTasks.filter(t => graphFilters.owner.includes(t.owner_name));
    }
    
    // Filter by attributes (multi-select support)
    Object.keys(graphFilters.attributes).forEach(attrName => {
        const filter = graphFilters.attributes[attrName];
        filteredTasks = filteredTasks.filter(task => {
            if (!task.attributes || !task.attributes[attrName]) {
                return false; // Task doesn't have this attribute answered
            }
            
            const taskValue = task.attributes[attrName].value;
            
            // Multi-select: check if task value is in any of the selected values
            return filter.values.some(filterValue => 
                taskValue.toLowerCase() === filterValue.toLowerCase()
            );
        });
    });
    
    if (filteredTasks.length === 0) {
        canvas.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📊</div>
                <p>No tasks match your filters</p>
                <button onclick="clearFilters()" class="secondary-btn">Clear Filters</button>
            </div>
        `;
        return;
    }
    
    // Create a hierarchical layout
    const layout = createGraphLayout(filteredTasks);
    
    // Render nodes and connections
    let html = '<svg width="100%" height="' + (layout.height + 100) + '" style="position: absolute; top: 0; left: 0; z-index: 1;">';
    
    // Draw connections first (behind nodes)
    layout.connections.forEach(conn => {
        if ((conn.type === 'parent' && graphFilters.showParents) ||
            (conn.type === 'child' && graphFilters.showChildren) ||
            (conn.type === 'dependency' && graphFilters.showDependencies)) {
            
            const lineClass = conn.type + '-line';
            html += `
                <line x1="${conn.x1}" y1="${conn.y1}" x2="${conn.x2}" y2="${conn.y2}" 
                      class="graph-line ${lineClass}" />
            `;
        }
    });
    
    html += '</svg>';
    
    // Draw nodes
    layout.nodes.forEach(node => {
        const task = node.task;
        const classes = [];
        if (task.parent_id) classes.push('has-parent');
        if (task.children_ids.length > 0) classes.push('has-children');
        if (task.dependency_ids.length > 0) classes.push('has-dependencies');
        
        html += `
            <div class="task-node ${classes.join(' ')}" 
                 style="left: ${node.x}px; top: ${node.y}px;"
                 title="${task.description || ''}"
                 onclick="showTaskDetails('${task.id}')">
                <div class="task-node-title">${task.title}</div>
                <div class="task-node-owner">${task.owner_name}</div>
            </div>
        `;
    });
    
    // Add legend
    html += `
        <div class="graph-legend">
            <div class="legend-item">
                <div class="legend-line parent"></div>
                <span>Parent Link (up)</span>
            </div>
            <div class="legend-item">
                <div class="legend-line child"></div>
                <span>Child Link (down)</span>
            </div>
            <div class="legend-item">
                <div class="legend-line dependency"></div>
                <span>Dependency (right)</span>
            </div>
        </div>
    `;
    
    canvas.innerHTML = html;
}

function createGraphLayout(tasks) {
    const NODE_WIDTH = 220;
    const NODE_HEIGHT = 80;
    const HORIZONTAL_GAP = 250;  // Much larger spacing
    const VERTICAL_GAP = 120;     // Much larger vertical spacing
    
    // Build task map
    const taskMap = new Map(tasks.map(t => [t.id, t]));
    
    // Find root tasks (no parent)
    const rootTasks = tasks.filter(t => !t.parent_id || !taskMap.has(t.parent_id));
    
    // Create hierarchy levels
    const levels = [];
    const positioned = new Set();
    
    // BFS to assign levels
    const queue = rootTasks.map(t => ({ task: t, level: 0 }));
    
    while (queue.length > 0) {
        const { task, level } = queue.shift();
        
        if (positioned.has(task.id)) continue;
        positioned.add(task.id);
        
        if (!levels[level]) levels[level] = [];
        levels[level].push(task);
        
        // Add children to next level
        task.children_ids.forEach(childId => {
            const child = taskMap.get(childId);
            if (child && !positioned.has(childId)) {
                queue.push({ task: child, level: level + 1 });
            }
        });
    }
    
    // Add any remaining tasks (orphaned)
    tasks.forEach(task => {
        if (!positioned.has(task.id)) {
            if (!levels[0]) levels[0] = [];
            levels[0].push(task);
        }
    });
    
    // Position nodes with guaranteed no overlap - use a grid system
    const nodes = [];
    const connections = [];
    const nodePositions = new Map();
    const usedPositions = new Set(); // Track used grid positions
    
    levels.forEach((levelTasks, levelIndex) => {
        const y = 50 + levelIndex * (NODE_HEIGHT + VERTICAL_GAP);
        
        levelTasks.forEach((task, taskIndex) => {
            // Find next available horizontal position for this level
            let gridX = taskIndex;
            let posKey = `${levelIndex}-${gridX}`;
            
            // If position is taken, find next available
            while (usedPositions.has(posKey)) {
                gridX++;
                posKey = `${levelIndex}-${gridX}`;
            }
            
            usedPositions.add(posKey);
            
            const x = 50 + gridX * (NODE_WIDTH + HORIZONTAL_GAP);
            const centerX = x + NODE_WIDTH / 2;
            const centerY = y + NODE_HEIGHT / 2;
            
            nodePositions.set(task.id, { x: centerX, y: centerY });
            
            nodes.push({
                task,
                x,
                y
            });
        });
    });
    
    // Create connections
    nodes.forEach(node => {
        const task = node.task;
        const fromPos = nodePositions.get(task.id);
        
        // Parent connection
        if (task.parent_id && nodePositions.has(task.parent_id)) {
            const toPos = nodePositions.get(task.parent_id);
            connections.push({
                type: 'parent',
                x1: fromPos.x,
                y1: fromPos.y - 20,
                x2: toPos.x,
                y2: toPos.y + 20
            });
        }
        
        // Dependency connections
        task.dependency_ids.forEach(depId => {
            if (nodePositions.has(depId)) {
                const toPos = nodePositions.get(depId);
                connections.push({
                    type: 'dependency',
                    x1: fromPos.x + 50,
                    y1: fromPos.y,
                    x2: toPos.x - 50,
                    y2: toPos.y
                });
            }
        });
    });
    
    const maxY = Math.max(...nodes.map(n => n.y), 0);
    
    return {
        nodes,
        connections,
        height: maxY + NODE_HEIGHT + 150
    };
}

// ============================================================================
// Initialization
// ============================================================================

window.addEventListener('DOMContentLoaded', () => {
    if (loadUser()) {
        showChat();
    } else {
        showPage('auth-page');
    }
});

