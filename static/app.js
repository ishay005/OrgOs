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
    
    // Load default section (Robin chat)
    showSection('robin');
    
    // Load other dashboard data in background
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
    if (sectionName === 'robin') {
        loadRobinChat();
    } else if (sectionName === 'tasks') {
        loadTasks();
    } else if (sectionName === 'alignments') {
        loadAlignments();
    } else if (sectionName === 'misalignments') {
        loadMisalignments();
    } else if (sectionName === 'graph') {
        loadTaskGraph();
    } else if (sectionName === 'ontology') {
        displayOntology();
    } else if (sectionName === 'orgchart') {
        loadOrgChart();
    }
}

function displayOntology() {
    loadOntology();
}

// ============================================================================
// Ontology/Schema Display
// ============================================================================

async function loadOntology() {
    const content = document.getElementById('ontology-content');
    content.innerHTML = '<div class="loading">Loading attributes...</div>';
    
    try {
        // Fetch task and user attributes from the API
        // These endpoints don't require authentication as they're just schema info
        const [taskAttrsRes, userAttrsRes] = await Promise.all([
            fetch('/task-attributes'),
            fetch('/user-attributes')
        ]);
        
        if (!taskAttrsRes.ok || !userAttrsRes.ok) {
            const error = taskAttrsRes.ok ? await userAttrsRes.text() : await taskAttrsRes.text();
            throw new Error('Failed to fetch attributes: ' + error);
        }
        
        const taskAttributes = await taskAttrsRes.json();
        const userAttributes = await userAttrsRes.json();
        
        // Also add structural fields
        const taskStructuralFields = [
            {
                name: "parent",
                label: "Parent Task",
                type: "reference",
                description: "Parent task in hierarchy (optional)",
                entity_type: "task"
            },
            {
                name: "children",
                label: "Child Tasks",
                type: "reference_list",
                description: "List of child tasks (auto-created if needed)",
                entity_type: "task"
            },
            {
                name: "dependencies",
                label: "Dependencies",
                type: "reference_list",
                description: "Tasks that this task depends on",
                entity_type: "task"
            }
        ];
        
        const userStructuralFields = [
            {
                name: "manager",
                label: "Manager / Team Lead",
                type: "user_reference",
                description: "Direct manager (for team hierarchy)",
                entity_type: "user"
            },
            {
                name: "employees",
                label: "Direct Reports",
                type: "user_reference_list",
                description: "List of employees reporting to this user",
                entity_type: "user"
            }
        ];
        
        displayAttributesPage(taskAttributes, userAttributes, taskStructuralFields, userStructuralFields);
        
    } catch (error) {
        console.error('Error loading attributes:', error);
        content.innerHTML = '<div class="error">Failed to load attributes. Please try again.</div>';
    }
}

function displayAttributesPage(taskAttributes, userAttributes, taskStructuralFields, userStructuralFields) {
    const content = document.getElementById('ontology-content');
    
    const allTaskFields = [...taskAttributes, ...taskStructuralFields];
    const allUserFields = [...userAttributes, ...userStructuralFields];
    
    content.innerHTML = `
        <div class="attributes-section">
            <div class="entity-card">
                <div class="entity-header">
                    <div>
                        <div class="entity-name">📝 Task Attributes</div>
                        <div class="entity-description">All attributes that can be tracked for tasks</div>
                    </div>
                    <span class="entity-badge">${allTaskFields.length} attributes</span>
                </div>
                <div class="entity-body">
                    <table class="field-table">
                        <thead>
                            <tr>
                                <th>Attribute</th>
                                <th>Type</th>
                                <th>Description</th>
                                <th>Options</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${allTaskFields.map(attr => `
                                <tr>
                                    <td>
                                        <span class="field-name">${attr.name}</span>
                                        ${attr.is_required ? ' <span style="color: var(--danger)">*</span>' : ''}
                                    </td>
                                    <td>
                                        <span class="field-type">${formatAttributeType(attr.type)}</span>
                                    </td>
                                    <td>${attr.description || attr.label || ''}</td>
                                    <td>
                                        ${attr.allowed_values && attr.allowed_values.length > 0 
                                            ? `<span class="allowed-values">${attr.allowed_values.join(', ')}</span>`
                                            : '<span style="color: var(--text-light); font-size: 0.85rem;">—</span>'}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
            
            ${allUserFields.length > 0 ? `
                <div class="entity-card">
                    <div class="entity-header">
                        <div>
                            <div class="entity-name">👤 User Attributes</div>
                            <div class="entity-description">All attributes that can be tracked for users</div>
                        </div>
                        <span class="entity-badge">${allUserFields.length} attributes</span>
                    </div>
                    <div class="entity-body">
                        <table class="field-table">
                            <thead>
                                <tr>
                                    <th>Attribute</th>
                                    <th>Type</th>
                                    <th>Description</th>
                                    <th>Options</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${allUserFields.map(attr => `
                                    <tr>
                                        <td>
                                            <span class="field-name">${attr.name}</span>
                                            ${attr.is_required ? ' <span style="color: var(--danger)">*</span>' : ''}
                                        </td>
                                        <td>
                                            <span class="field-type">${formatAttributeType(attr.type)}</span>
                                        </td>
                                        <td>${attr.description || attr.label || ''}</td>
                                        <td>
                                            ${attr.allowed_values && attr.allowed_values.length > 0 
                                                ? `<span class="allowed-values">${attr.allowed_values.join(', ')}</span>`
                                                : '<span style="color: var(--text-light); font-size: 0.85rem;">—</span>'}
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

function formatAttributeType(type) {
    const typeMap = {
        'string': 'Text',
        'enum': 'Choice',
        'int': 'Number',
        'float': 'Decimal',
        'bool': 'Yes/No',
        'date': 'Date',
        'reference': 'Task Reference',
        'reference_list': 'Task List',
        'user_reference': 'User Reference',
        'user_reference_list': 'User List'
    };
    return typeMap[type] || type;
}

// ============================================================================
// Org Chart Visualization
// ============================================================================

// ============================================================================
// Alignment Color Helpers
// ============================================================================

/**
 * Convert alignment percentage (0-100) to a color (red to green)
 * @param {number} alignmentPct - Alignment percentage (0-100)
 * @returns {string} - RGB color string
 */
function getAlignmentColor(alignmentPct) {
    // Clamp to 0-100
    alignmentPct = Math.max(0, Math.min(100, alignmentPct));
    
    // More gradual scale: Red (0%) → Orange (40%) → Yellow (60%) → Light Green (80%) → Green (100%)
    let r, g, b;
    
    if (alignmentPct < 40) {
        // Red to Orange (0-40%)
        r = 255;
        g = Math.round((alignmentPct / 40) * 165); // Orange is rgb(255, 165, 0)
        b = 0;
    } else if (alignmentPct < 60) {
        // Orange to Yellow (40-60%)
        r = 255;
        g = Math.round(165 + ((alignmentPct - 40) / 20) * 90); // 165 to 255
        b = 0;
    } else if (alignmentPct < 80) {
        // Yellow to Light Green (60-80%)
        r = Math.round(255 - ((alignmentPct - 60) / 20) * 165); // 255 to 90
        g = 255;
        b = Math.round(((alignmentPct - 60) / 20) * 50); // 0 to 50
    } else {
        // Light Green to Green (80-100%)
        r = Math.round(90 - ((alignmentPct - 80) / 20) * 90); // 90 to 0
        g = 255;
        b = Math.round(50 + ((alignmentPct - 80) / 20) * 50); // 50 to 100
    }
    
    return `rgb(${r}, ${g}, ${b})`;
}

// Global alignment stats
let userAlignmentStats = {};
let taskAlignmentStats = {};

/**
 * Fetch alignment statistics from backend
 */
async function fetchAlignmentStats() {
    try {
        const [userStats, taskStats] = await Promise.all([
            apiCall('/alignment-stats/users', { skipAuth: true }),
            apiCall('/alignment-stats/tasks', { skipAuth: true })
        ]);
        
        userAlignmentStats = userStats;
        taskAlignmentStats = taskStats;
        
        console.log('Alignment stats loaded:', { userStats, taskStats });
    } catch (error) {
        console.error('Failed to fetch alignment stats:', error);
    }
}

/**
 * Calculate alignment for a specific dependency connection
 * Compares different users' perceptions of what a task depends on
 */
function calculateDependencyAlignment(sourceTask, targetTaskId) {
    try {
        if (!sourceTask || !sourceTask.answers || !sourceTask.answers.perceived_dependencies) {
            return 100; // No data, default to aligned
        }
        
        const dependencyAnswers = sourceTask.answers.perceived_dependencies;
        const users = Object.keys(dependencyAnswers);
        
        if (users.length < 2) {
            return 100; // Need at least 2 users to compare
        }
        
        // Get target task to match its title in dependency answers
        let total = 0;
        let aligned = 0;
        
        // Compare each pair of users
        for (let i = 0; i < users.length; i++) {
            for (let j = i + 1; j < users.length; j++) {
                const answer1 = dependencyAnswers[users[i]]?.value;
                const answer2 = dependencyAnswers[users[j]]?.value;
                
                if (!answer1 || !answer2) continue;
                
                total++;
                
                // Simple comparison: do the answers match?
                const ans1Lower = answer1.toLowerCase().trim();
                const ans2Lower = answer2.toLowerCase().trim();
                
                // Consider aligned if answers are similar (exact match or high overlap)
                if (ans1Lower === ans2Lower) {
                    aligned++;
                } else {
                    // Check for partial match (at least 50% of words match)
                    const words1 = ans1Lower.split(/[,\s]+/).filter(w => w.length > 3);
                    const words2 = ans2Lower.split(/[,\s]+/).filter(w => w.length > 3);
                    const commonWords = words1.filter(w => words2.some(w2 => w2.includes(w) || w.includes(w2)));
                    const similarity = commonWords.length / Math.max(words1.length, words2.length, 1);
                    
                    if (similarity >= 0.5) {
                        aligned++;
                    }
                }
            }
        }
        
        return total > 0 ? (aligned / total) * 100 : 100;
    } catch (error) {
        console.error('Error calculating dependency alignment:', error);
        return 100; // Default to aligned on error
    }
}

// ============================================================================
// Org Chart
// ============================================================================

// Org chart view state
const orgChartView = {
    scale: 1,
    translateX: 0,
    translateY: 0,
    isDragging: false,
    startX: 0,
    startY: 0,
    dragStartX: 0,
    dragStartY: 0,
    clickedNodeId: null,
    clickedNodeName: null,
    listenersAdded: false
};

async function loadOrgChart() {
    const svg = document.getElementById('org-chart-svg');
    svg.innerHTML = '<text x="50" y="50" fill="var(--text-light)">Loading org chart...</text>';
    
    try {
        // Fetch org chart data
        const response = await fetch('/users/org-chart');
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to load org chart: ${response.status} - ${errorText}`);
        }
        
        const data = await response.json();
        console.log('Org chart data loaded:', data);
        
        if (!data.users || data.users.length === 0) {
            svg.innerHTML = `
                <text x="50" y="50" fill="var(--text-light)">No users found</text>
                <text x="50" y="80" fill="var(--text-light)" font-size="14">Create users to see org chart</text>
            `;
            return;
        }
        
        // Always fetch alignment stats when loading org chart
        // (needed for when user checks the checkbox later)
        await fetchAlignmentStats();
        
        renderOrgChart(data.users);
        initOrgChartControls();
    } catch (error) {
        console.error('Error loading org chart:', error);
        svg.innerHTML = `
            <text x="50" y="50" fill="var(--danger)">Failed to load org chart</text>
            <text x="50" y="80" fill="var(--text-light)" font-size="14">${error.message}</text>
        `;
    }
}

function initOrgChartControls() {
    const container = document.getElementById('org-chart-container');
    const svg = document.getElementById('org-chart-svg');
    
    // Add event listeners only once (not every render)
    if (!orgChartView.listenersAdded) {
        orgChartView.listenersAdded = true;
        
        // Mouse wheel zoom
        container.addEventListener('wheel', (e) => {
            e.preventDefault();
            // Slower zoom: 5% per scroll (was 10%)
            const delta = e.deltaY > 0 ? 0.95 : 1.05;
            orgChartView.scale *= delta;
            orgChartView.scale = Math.max(0.1, Math.min(5, orgChartView.scale));
            updateOrgChartTransform();
        });
        
        // Mouse drag to pan
        svg.addEventListener('mousedown', (e) => {
            orgChartView.isDragging = true;
            orgChartView.startX = e.clientX - orgChartView.translateX;
            orgChartView.startY = e.clientY - orgChartView.translateY;
            orgChartView.dragStartX = e.clientX;
            orgChartView.dragStartY = e.clientY;
            svg.style.cursor = 'grabbing';
        });
        
        document.addEventListener('mousemove', (e) => {
            if (!orgChartView.isDragging) return;
            orgChartView.translateX = e.clientX - orgChartView.startX;
            orgChartView.translateY = e.clientY - orgChartView.startY;
            updateOrgChartTransform();
        });
        
        document.addEventListener('mouseup', (e) => {
            if (orgChartView.isDragging) {
                orgChartView.isDragging = false;
                svg.style.cursor = 'grab';
                
                // Check if this was a click (minimal movement) vs a drag
                const deltaX = Math.abs(e.clientX - orgChartView.dragStartX);
                const deltaY = Math.abs(e.clientY - orgChartView.dragStartY);
                const isClick = deltaX < 5 && deltaY < 5;
                
                console.log('Org chart mouseup:', { deltaX, deltaY, isClick, clickedNodeId: orgChartView.clickedNodeId });
                
                // If it was a click and we have a clicked node, show popup
                if (isClick && orgChartView.clickedNodeId) {
                    console.log('Showing popup for user:', orgChartView.clickedNodeName);
                    showUserMisalignments(orgChartView.clickedNodeId, orgChartView.clickedNodeName);
                }
                
                // Reset clicked node
                orgChartView.clickedNodeId = null;
                orgChartView.clickedNodeName = null;
            }
        });
        
        // Double-click to reset
        svg.addEventListener('dblclick', () => {
            resetOrgChartView();
        });
    }
    
    svg.style.cursor = 'grab';
}

function updateOrgChartTransform() {
    const svg = document.getElementById('org-chart-svg');
    const g = svg.querySelector('g');
    if (g) {
        g.setAttribute('transform', 
            `translate(${orgChartView.translateX}, ${orgChartView.translateY}) scale(${orgChartView.scale})`);
    }
}

function resetOrgChartView() {
    orgChartView.scale = 1;
    orgChartView.translateX = 0;
    orgChartView.translateY = 0;
    updateOrgChartTransform();
}

function zoomOrgChart(factor) {
    orgChartView.scale *= factor;
    orgChartView.scale = Math.max(0.1, Math.min(5, orgChartView.scale));
    updateOrgChartTransform();
}

function renderOrgChart(users) {
    const svg = document.getElementById('org-chart-svg');
    svg.innerHTML = ''; // Clear existing content
    
    // Build hierarchy tree
    const userMap = new Map(users.map(u => [u.id, {...u, children: []}]));
    const roots = [];
    
    users.forEach(user => {
        const userNode = userMap.get(user.id);
        if (user.manager_id && userMap.has(user.manager_id)) {
            userMap.get(user.manager_id).children.push(userNode);
        } else {
            roots.push(userNode);
        }
    });
    
    // Layout parameters
    const NODE_WIDTH = 180;
    const NODE_HEIGHT = 80;
    const HORIZONTAL_GAP = 50;
    const VERTICAL_GAP = 100;
    
    // Calculate positions
    function calculateLayout(node, level, xOffset) {
        node.level = level;
        node.y = level * (NODE_HEIGHT + VERTICAL_GAP) + 50;
        
        if (node.children.length === 0) {
            node.x = xOffset;
            return xOffset + NODE_WIDTH + HORIZONTAL_GAP;
        }
        
        let childX = xOffset;
        node.children.forEach(child => {
            childX = calculateLayout(child, level + 1, childX);
        });
        
        // Center parent above children
        const firstChild = node.children[0];
        const lastChild = node.children[node.children.length - 1];
        node.x = (firstChild.x + lastChild.x) / 2;
        
        return childX;
    }
    
    let currentX = 50;
    roots.forEach(root => {
        currentX = calculateLayout(root, 0, currentX);
        currentX += HORIZONTAL_GAP * 2; // Extra space between root trees
    });
    
    // Set SVG viewBox
    const allNodes = Array.from(userMap.values());
    const maxX = Math.max(...allNodes.map(n => n.x || 0)) + NODE_WIDTH + 100;
    const maxY = Math.max(...allNodes.map(n => n.y || 0)) + NODE_HEIGHT + 100;
    svg.setAttribute('viewBox', `0 0 ${maxX} ${maxY}`);
    svg.setAttribute('width', maxX);
    svg.setAttribute('height', maxY);
    
    // Create main group for all elements (for zoom/pan)
    const mainGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    mainGroup.setAttribute('id', 'org-chart-main-group');
    
    // Draw connections first (so they're behind nodes)
    allNodes.forEach(node => {
        if (node.manager_id && userMap.has(node.manager_id)) {
            const parent = userMap.get(node.manager_id);
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            const d = `M ${parent.x + NODE_WIDTH/2} ${parent.y + NODE_HEIGHT} 
                       L ${parent.x + NODE_WIDTH/2} ${parent.y + NODE_HEIGHT + VERTICAL_GAP/2}
                       L ${node.x + NODE_WIDTH/2} ${parent.y + NODE_HEIGHT + VERTICAL_GAP/2}
                       L ${node.x + NODE_WIDTH/2} ${node.y}`;
            path.setAttribute('d', d);
            path.setAttribute('class', 'org-connection');
            mainGroup.appendChild(path);
        }
    });
    
    // Check if alignment coloring is enabled
    const showAlignment = document.getElementById('show-user-alignment')?.checked;
    const currentUserId = localStorage.getItem('userId');
    
    // Draw nodes
    allNodes.forEach(node => {
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        const isCurrentUser = node.id === currentUserId;
        group.setAttribute('class', `org-node ${node.employee_count > 0 ? 'org-node-manager' : ''} ${isCurrentUser ? 'current-user' : ''}`);
        group.setAttribute('transform', `translate(${node.x}, ${node.y})`);
        
        // Node rectangle
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('class', 'org-node-rect');
        rect.setAttribute('width', NODE_WIDTH);
        rect.setAttribute('height', NODE_HEIGHT);
        
        // Apply alignment color if enabled
        if (showAlignment && userAlignmentStats[node.id] !== undefined) {
            const alignmentPct = userAlignmentStats[node.id];
            const color = getAlignmentColor(alignmentPct);
            // Use inline style with !important to override CSS
            // Higher opacity for better visibility
            rect.setAttribute('style', `fill: ${color} !important; fill-opacity: 0.85 !important;`);
        }
        
        // Highlight current user with thick border
        if (isCurrentUser) {
            rect.setAttribute('stroke', '#4CAF50');
            rect.setAttribute('stroke-width', '4');
        }
        
        group.appendChild(rect);
        
        // Name
        const name = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        name.setAttribute('class', 'org-node-name');
        name.setAttribute('x', NODE_WIDTH / 2);
        name.setAttribute('y', 25);
        name.setAttribute('text-anchor', 'middle');
        name.setAttribute('fill', '#000000'); // Always black for readability
        name.textContent = node.name;
        if (isCurrentUser) {
            name.textContent += ' (You)';
            name.setAttribute('font-weight', 'bold');
        }
        group.appendChild(name);
        
        // Info line 1 - show alignment % if enabled
        const info1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        info1.setAttribute('class', 'org-node-info');
        info1.setAttribute('x', NODE_WIDTH / 2);
        info1.setAttribute('y', 45);
        info1.setAttribute('text-anchor', 'middle');
        info1.setAttribute('fill', '#000000'); // Always black for readability
        if (showAlignment && userAlignmentStats[node.id] !== undefined) {
            info1.textContent = `Alignment: ${Math.round(userAlignmentStats[node.id])}%`;
        } else {
            info1.textContent = `${node.task_count} task${node.task_count !== 1 ? 's' : ''}`;
        }
        group.appendChild(info1);
        
        // Info line 2
        const info2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        info2.setAttribute('class', 'org-node-info');
        info2.setAttribute('x', NODE_WIDTH / 2);
        info2.setAttribute('y', 62);
        info2.setAttribute('text-anchor', 'middle');
        info2.setAttribute('fill', '#000000'); // Always black for readability
        info2.textContent = node.employee_count > 0 
            ? `${node.employee_count} report${node.employee_count !== 1 ? 's' : ''}`
            : 'Individual Contributor';
        group.appendChild(info2);
        
        // Add click handler to show user misalignments
        group.style.cursor = 'pointer';
        group.addEventListener('mousedown', () => {
            // Store which node was clicked - don't stopPropagation so drag still works
            console.log('Node clicked:', node.name, node.id);
            orgChartView.clickedNodeId = node.id;
            orgChartView.clickedNodeName = node.name;
        });
        
        mainGroup.appendChild(group);
    });
    
    // Add main group to SVG
    svg.appendChild(mainGroup);
}


/**
 * Show misalignments for a specific user in a popup
 */
async function showUserMisalignments(userId, userName) {
    console.log('showUserMisalignments called for:', userName, userId);
    
    try {
        const modal = document.getElementById('user-misalignment-modal');
        const modalTitle = document.getElementById('user-misalignment-title');
        const modalContent = document.getElementById('user-misalignment-content');
        
        console.log('Modal elements:', { modal, modalTitle, modalContent });
        
        if (!modal || !modalTitle || !modalContent) {
            console.error('Modal elements not found!');
            return;
        }
        
        modalTitle.textContent = `Misalignments for ${userName}`;
        modalContent.innerHTML = '<div class="loading">Loading misalignments...</div>';
        
        console.log('Removing hidden class...');
        // Remove hidden class instead of setting display (hidden has !important)
        modal.classList.remove('hidden');
        console.log('Modal classes after remove:', modal.classList.toString());
        console.log('Modal display style:', window.getComputedStyle(modal).display);
        
        // Fetch misalignments for this user
        const misalignments = await apiCall('/misalignments', { 
            headers: { 'X-User-Id': userId } 
        });
        
        if (!misalignments || misalignments.length === 0) {
            modalContent.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">✅</div>
                    <p>No misalignments found for ${userName}</p>
                    <p>All perceptions are aligned!</p>
                </div>
            `;
            return;
        }
        
        // Group misalignments by task
        const byTask = {};
        misalignments.forEach(m => {
            const taskKey = m.task_id || 'general';
            if (!byTask[taskKey]) {
                byTask[taskKey] = {
                    task_id: m.task_id,
                    task_title: m.task_title || 'General',
                    other_user_name: m.other_user_name,
                    misalignments: []
                };
            }
            byTask[taskKey].misalignments.push(m);
        });
        
        // Create table for each task
        let html = `
            <div class="misalignment-summary">
                <strong>Total Misalignments:</strong> ${misalignments.length}
            </div>
        `;
        
        Object.values(byTask).forEach(taskGroup => {
            html += `
                <div class="task-misalignment-group">
                    <h4>📋 ${taskGroup.task_title}</h4>
                    <p class="misalignment-with">With: ${taskGroup.other_user_name}</p>
                    <table class="misalignment-table">
                        <thead>
                            <tr>
                                <th>Attribute</th>
                                <th>Your View</th>
                                <th>Their View</th>
                                <th>Alignment</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            
            taskGroup.misalignments.forEach(m => {
                const alignmentPct = (m.similarity_score * 100).toFixed(0);
                const colorClass = alignmentPct > 70 ? 'high' : alignmentPct > 40 ? 'medium' : 'low';
                
                html += `
                    <tr>
                        <td><strong>${m.attribute_label}</strong></td>
                        <td class="your-value">${m.your_value || 'N/A'}</td>
                        <td class="their-value">${m.their_value || 'N/A'}</td>
                        <td class="alignment-${colorClass}">${alignmentPct}%</td>
                    </tr>
                `;
            });
            
            html += `
                        </tbody>
                    </table>
                </div>
            `;
        });
        
        modalContent.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading user misalignments:', error);
        modalContent.innerHTML = `
            <div class="error">
                <p>Failed to load misalignments</p>
                <p>${error.message}</p>
            </div>
        `;
    }
}

function closeUserMisalignmentModal() {
    document.getElementById('user-misalignment-modal').classList.add('hidden');
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

async function loadMisalignments(userId = null, userName = null) {
    const statsDiv = document.getElementById('misalignment-stats');
    const chartsDiv = document.getElementById('misalignment-charts');
    const listDiv = document.getElementById('misalignments-list');
    const teamNav = document.getElementById('team-navigation');
    
    // Use provided userId or current user
    const targetUserId = userId || currentUser.id;
    const targetUserName = userName || currentUser.name;
    
    statsDiv.innerHTML = '<div class="loading">Loading statistics...</div>';
    chartsDiv.innerHTML = '';
    listDiv.innerHTML = '';
    
    try {
        // Check if current user is a manager and show team navigation
        if (!userId) {  // Only show when viewing own misalignments
            const orgChart = await apiCall('/users/org-chart', { skipAuth: true });
            const currentUserData = orgChart.users.find(u => u.id === currentUser.id);
            
            if (currentUserData && currentUserData.employee_count > 0) {
                // Current user is a manager - show team navigation
                const employees = orgChart.users.filter(u => u.manager_id === currentUser.id);
                
                let buttonsHtml = '<p class="team-nav-hint">Click to view team member\'s misalignments:</p><div class="button-group">';
                employees.forEach(emp => {
                    buttonsHtml += `
                        <button onclick="loadMisalignments('${emp.id}', '${emp.name}')" class="team-member-btn">
                            👤 ${emp.name}
                        </button>
                    `;
                });
                buttonsHtml += '</div>';
                
                document.getElementById('team-member-buttons').innerHTML = buttonsHtml;
                teamNav.style.display = 'block';
            } else {
                teamNav.style.display = 'none';
            }
        }
        
        // Update section header if viewing another user's misalignments
        const sectionHeader = document.querySelector('#misalignments-section .section-header h3');
        if (userId && userId !== currentUser.id) {
            sectionHeader.innerHTML = `
                ⚠️ Perception Gaps - ${targetUserName}
                <button onclick="loadMisalignments()" class="secondary-btn" style="margin-left: 15px; font-size: 0.9rem;">
                    ← Back to My Misalignments
                </button>
            `;
        } else {
            sectionHeader.textContent = '⚠️ Perception Gaps';
        }
        
        // Load both statistics and ALL comparisons (0-100% alignment) for target user
        const [stats, misalignments] = await Promise.all([
            apiCall('/misalignments/statistics', { headers: { 'X-User-Id': targetUserId } }),
            apiCall('/misalignments?include_all=true', { headers: { 'X-User-Id': targetUserId } })
        ]);
        
        // Sort by similarity score (ascending: worst misalignments first)
        misalignments.sort((a, b) => a.similarity_score - b.similarity_score);
        
        // Display statistics overview
        displayStatistics(stats);
        
        // Display charts
        displayCharts(stats);
        
        // Display detailed list
        displayMisalignmentsList(misalignments);
        
        // Update badge (only for current user)
        if (!userId || userId === currentUser.id) {
            document.getElementById('misalignment-badge').textContent = misalignments.length;
        }
        
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
                <div class="empty-state-icon">💼</div>
                <h3>No Data Yet</h3>
                <p>No comparisons available with your teammates.</p>
                <p class="small">Answer questions to see alignment data.</p>
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
    
    // Create compact table view with full alignment spectrum (0-100%)
    listDiv.innerHTML = Object.entries(grouped).map(([userName, items]) => {
        const tableRows = items.map(m => {
            const alignmentPct = m.similarity_score * 100;
            
            // Determine alignment level and color
            let alignmentClass, alignmentIcon;
            if (alignmentPct >= 80) {
                alignmentClass = 'high';
                alignmentIcon = '🟢';
            } else if (alignmentPct >= 60) {
                alignmentClass = 'medium';
                alignmentIcon = '🟡';
            } else if (alignmentPct >= 40) {
                alignmentClass = 'low';
                alignmentIcon = '🟠';
            } else {
                alignmentClass = 'very-low';
                alignmentIcon = '🔴';
            }
            
            return `
                <tr class="misalignment-row ${alignmentClass}">
                    <td class="severity-col">${alignmentIcon}</td>
                    <td class="task-col">${m.task_title || 'General'}</td>
                    <td class="attr-col">${m.attribute_label}</td>
                    <td class="value-col your-value">${m.your_value}</td>
                    <td class="value-col their-value">${m.their_value}</td>
                    <td class="similarity-col alignment-${alignmentClass}">${alignmentPct.toFixed(0)}%</td>
                </tr>
            `;
        }).join('');
        
        // Count alignment levels
        const perfect = items.filter(i => i.similarity_score >= 0.9).length;
        const good = items.filter(i => i.similarity_score >= 0.6 && i.similarity_score < 0.9).length;
        const gaps = items.filter(i => i.similarity_score < 0.6).length;
        
        return `
            <div class="misalignment-group-compact">
                <div class="misalignment-group-header">
                    <h4>👤 ${userName}</h4>
                    <span class="badge">${items.length} comparisons</span>
                    <span class="badge-mini" style="background: var(--success);">${perfect} perfect</span>
                    <span class="badge-mini" style="background: var(--warning);">${good} good</span>
                    <span class="badge-mini" style="background: var(--danger);">${gaps} gaps</span>
                </div>
                <table class="misalignment-table">
                    <thead>
                        <tr>
                            <th></th>
                            <th>Task</th>
                            <th>Attribute</th>
                            <th>Your View</th>
                            <th>Their View</th>
                            <th>Alignment</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>
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
        
        // Always fetch alignment stats when loading graph
        // (needed for when user checks the checkbox later)
        await fetchAlignmentStats();
        
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
        
        // Slower zoom: 5% per scroll (was 10%)
        const delta = e.deltaY > 0 ? 0.95 : 1.05;
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

async function applyFilters() {
    // Owner filter (multi-select)
    const ownerCheckboxes = document.querySelectorAll('input[data-attr-name="owner"]:checked');
    if (ownerCheckboxes.length > 0) {
        graphFilters.owner = Array.from(ownerCheckboxes).map(cb => cb.value);
    } else {
        graphFilters.owner = null;
    }
    
    // Team filter
    const teamFilter = document.getElementById('filter-team');
    const selectedTeam = teamFilter ? teamFilter.value : '';
    
    if (selectedTeam) {
        try {
            const response = await fetch('/users/org-chart');
            if (response.ok) {
                const data = await response.json();
                let teamLeadName = '';
                
                if (selectedTeam === 'platform') {
                    teamLeadName = 'Dana Cohen';
                } else if (selectedTeam === 'product') {
                    teamLeadName = 'Amir Levi';
                }
                
                // Find team lead
                const teamLead = data.users.find(u => u.name === teamLeadName);
                
                if (teamLead) {
                    // Get team members (employees of this lead + the lead)
                    const teamMemberNames = data.users
                        .filter(u => u.manager_id === teamLead.id || u.id === teamLead.id)
                        .map(u => u.name);
                    
                    console.log(`${selectedTeam} team members:`, teamMemberNames);
                    graphFilters.owner = teamMemberNames;
                }
            }
        } catch (error) {
            console.error('Error loading team filter:', error);
        }
    }
    
    // My Team filter (overrides team filter if both are checked)
    const myTeamChecked = document.getElementById('filter-my-team') ? document.getElementById('filter-my-team').checked : false;
    if (myTeamChecked && userId) {
        // Fetch org chart to get team members
        try {
            const response = await fetch('/users/org-chart');
            if (response.ok) {
                const data = await response.json();
                console.log('Org chart data for team filter:', data);
                console.log('Current user ID:', userId);
                
                // Find current user's employees
                const teamMemberIds = data.users
                    .filter(u => u.manager_id === userId)
                    .map(u => u.id);
                    
                // Add current user
                teamMemberIds.push(userId);
                
                console.log('Team member IDs:', teamMemberIds);
                
                // Also get the names for these IDs
                const teamMemberNames = data.users
                    .filter(u => teamMemberIds.includes(u.id))
                    .map(u => u.name);
                    
                console.log('Team member names:', teamMemberNames);
                
                // Set filter to use names (since that's what the task graph uses)
                graphFilters.owner = teamMemberNames;
            }
        } catch (error) {
            console.error('Error loading team members:', error);
        }
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
    
    // Reset checkboxes and selects
    if (document.getElementById('filter-my-team')) {
        document.getElementById('filter-my-team').checked = false;
    }
    if (document.getElementById('filter-team')) {
        document.getElementById('filter-team').value = '';
    }
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
        // Check if filtering by IDs or names
        const firstFilter = graphFilters.owner[0];
        const isFilteringByIds = typeof firstFilter === 'string' && firstFilter.includes('-');
        
        filteredTasks = filteredTasks.filter(t => {
            if (isFilteringByIds) {
                return graphFilters.owner.includes(t.owner_id);
            } else {
                return graphFilters.owner.includes(t.owner_name);
            }
        });
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
    // Create SVG with large viewBox to prevent clipping when zooming out
    const svgWidth = Math.max(layout.width + 200, 2000);
    const svgHeight = Math.max(layout.height + 200, 1000);
    let html = `<svg width="100%" height="100%" viewBox="0 0 ${svgWidth} ${svgHeight}" preserveAspectRatio="xMidYMid meet" style="position: absolute; top: 0; left: 0; z-index: 1; min-height: ${svgHeight}px; overflow: visible;">`;
    
    // Check if alignment coloring is enabled for tasks
    const showTaskAlignment = document.getElementById('show-task-alignment')?.checked;
    
    // Draw connections first (behind nodes) with curved paths
    layout.connections.forEach(conn => {
        if ((conn.type === 'parent' && graphFilters.showParents) ||
            (conn.type === 'child' && graphFilters.showChildren) ||
            (conn.type === 'dependency' && graphFilters.showDependencies)) {
            
            const lineClass = conn.type + '-line';
            
            // Calculate control points for curved line
            const dx = conn.x2 - conn.x1;
            const dy = conn.y2 - conn.y1;
            
            // Use bezier curve for smoother appearance
            const midX = conn.x1 + dx / 2;
            const midY = conn.y1 + dy / 2;
            
            // Adjust control points based on connection type
            let cp1x, cp1y, cp2x, cp2y;
            if (conn.type === 'parent' || conn.type === 'child') {
                // Vertical connections - curve horizontally
                cp1x = conn.x1;
                cp1y = midY;
                cp2x = conn.x2;
                cp2y = midY;
            } else {
                // Dependency - curve smoothly
                cp1x = midX;
                cp1y = conn.y1;
                cp2x = midX;
                cp2y = conn.y2;
            }
            
            const pathD = `M ${conn.x1} ${conn.y1} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${conn.x2} ${conn.y2}`;
            
            // Apply alignment color to lines if enabled
            let lineStyle = '';
            if (showTaskAlignment) {
                let alignmentPct = 100;
                
                if (conn.type === 'dependency') {
                    // For dependency lines, use dependency ATTRIBUTE alignment
                    // This compares what different users think the task depends on
                    const sourceTask = filteredTasks.find(t => t.id === conn.from);
                    if (sourceTask) {
                        alignmentPct = calculateDependencyAlignment(sourceTask, conn.to);
                    }
                } else {
                    // For parent/child lines, use task alignment
                    const sourceAlignment = taskAlignmentStats[conn.from] || 100;
                    const targetAlignment = taskAlignmentStats[conn.to] || 100;
                    alignmentPct = (sourceAlignment + targetAlignment) / 2;
                }
                
                const color = getAlignmentColor(alignmentPct);
                // Make lines MUCH thicker and more visible when colored
                // Dependency lines extra thick and dashed for clarity
                if (conn.type === 'dependency') {
                    lineStyle = `stroke="${color}" stroke-width="6" opacity="1.0" stroke-dasharray="10,5"`;
                } else {
                    lineStyle = `stroke="${color}" stroke-width="4" opacity="1.0"`;
                }
            }
            
            html += `
                <path d="${pathD}" 
                      class="graph-line ${lineClass}" 
                      fill="none" 
                      ${lineStyle} />
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
        
        // Get alignment color if enabled
        let bgStyle = '';
        if (showTaskAlignment && taskAlignmentStats[task.id] !== undefined) {
            const alignmentPct = taskAlignmentStats[task.id];
            const color = getAlignmentColor(alignmentPct);
            bgStyle = `background: linear-gradient(135deg, ${color} 0%, ${color} 100%); opacity: 0.9;`;
        }
        
        html += `
            <div class="task-node ${classes.join(' ')}" 
                 style="left: ${node.x}px; top: ${node.y}px; ${bgStyle}"
                 title="${task.description || ''}"
                 onclick="showTaskDetails('${task.id}')">
                <div class="task-node-title" style="color: #000000;">${task.title}</div>
                <div class="task-node-owner" style="color: #000000;">${task.owner_name}</div>
                ${showTaskAlignment && taskAlignmentStats[task.id] !== undefined 
                    ? `<div style="font-size: 10px; opacity: 0.8; color: #000000;">Alignment: ${Math.round(taskAlignmentStats[task.id])}%</div>` 
                    : ''}
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
// Robin Chat Functions
// ============================================================================

let robinChatHistory = [];
let isRobinTyping = false;

async function loadRobinChat() {
    try {
        const response = await fetch('/chat/history?limit=50', {
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) throw new Error('Failed to load chat history');
        
        const messages = await response.json();
        robinChatHistory = messages;
        
        // Clear and re-render messages
        const container = document.getElementById('robin-messages');
        container.innerHTML = '';
        
        // Add welcome message if no history
        if (messages.length === 0) {
            addWelcomeMessage(container);
        } else {
            // Render all messages
            messages.forEach(msg => {
                appendMessageToUI(msg);
            });
        }
        
        // Scroll to bottom
        scrollToBottom();
        
    } catch (error) {
        console.error('Error loading Robin chat:', error);
        console.error('Failed to load chat history');
    }
}

function addWelcomeMessage(container) {
    const welcomeMsg = document.createElement('div');
    welcomeMsg.className = 'chat-message system';
    welcomeMsg.innerHTML = `
        <div class="message-content">
            <p>Hi! I'm Robin, your AI assistant. I'm here to help you stay aligned with your team.</p>
            <p>I can:</p>
            <ul>
                <li>Give you status updates on your tasks</li>
                <li>Help you fill in task information</li>
                <li>Identify misalignments with your team</li>
            </ul>
            <p>Try asking me for a <strong>morning brief</strong> or tell me about your tasks!</p>
        </div>
    `;
    container.appendChild(welcomeMsg);
}

function appendMessageToUI(message) {
    const container = document.getElementById('robin-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${message.sender}`;
    
    const avatar = message.sender === 'user' ? '👤' : 
                   message.sender === 'robin' ? '🤖' : 'ℹ️';
    
    let metadataHTML = '';
    if (message.metadata && message.metadata.updates_applied) {
        metadataHTML = `<div class="message-metadata">✓ Applied ${message.metadata.updates_applied} update(s)</div>`;
    }
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div>
            <div class="message-content">
                <p>${escapeHtml(message.text).replace(/\n/g, '<br>')}</p>
            </div>
            ${metadataHTML}
            <div class="message-timestamp">${formatTimestamp(message.created_at)}</div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

function showTypingIndicator() {
    if (isRobinTyping) return;
    isRobinTyping = true;
    
    const container = document.getElementById('robin-messages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-message robin';
    typingDiv.id = 'typing-indicator';
    typingDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div>
            <div class="message-content typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    container.appendChild(typingDiv);
    scrollToBottom();
}

function hideTypingIndicator() {
    isRobinTyping = false;
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

async function sendMessageToRobin() {
    console.log('🤖 sendMessageToRobin called');
    
    const input = document.getElementById('robin-input');
    const sendBtn = document.getElementById('robin-send-btn');
    const text = input.value.trim();
    
    console.log('Input text:', text);
    console.log('Current user:', currentUser);
    
    if (!text) {
        console.log('No text, returning');
        return;
    }
    
    if (!currentUser || !currentUser.id) {
        console.error('No current user!');
        alert('Please sign in first');
        return;
    }
    
    // Clear input immediately
    input.value = '';
    
    // Disable send button
    sendBtn.disabled = true;
    sendBtn.classList.add('loading');
    
    try {
        console.log('Sending message to Robin...');
        
        // Show user message immediately (optimistic UI)
        const userMessage = {
            sender: 'user',
            text: text,
            created_at: new Date().toISOString()
        };
        appendMessageToUI(userMessage);
        
        // Show typing indicator
        showTypingIndicator();
        
        // Send to backend
        const response = await fetch('/chat/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': currentUser.id
            },
            body: JSON.stringify({ text })
        });
        
        console.log('Response status:', response.status);
        hideTypingIndicator();
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Error response:', errorText);
            throw new Error(`Failed to send message: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        
        // Remove the optimistic user message and add all messages from response
        const container = document.getElementById('robin-messages');
        const lastMessage = container.lastElementChild;
        if (lastMessage && lastMessage.classList.contains('user')) {
            lastMessage.remove();
        }
        
        // Add all messages from response
        data.messages.forEach(msg => {
            appendMessageToUI(msg);
            
            // Capture debug prompt from Robin's message metadata
            if (msg.sender === 'robin' && msg.metadata && msg.metadata.debug_prompt) {
                lastRobinPrompt = msg.metadata.debug_prompt;
                console.log('🐛 Debug prompt captured for last message');
            }
        });
        
        // Reload dashboard data if updates were applied
        const hasUpdates = data.messages.some(m => m.metadata && m.metadata.updates_applied);
        if (hasUpdates) {
            setTimeout(() => {
                loadTasks();
                loadMisalignments();
            }, 500);
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        hideTypingIndicator();
        
        // Show error message from Robin
        appendMessageToUI({
            sender: 'robin',
            text: 'Sorry, I encountered an error. Please try again. Check the browser console for details.',
            created_at: new Date().toISOString()
        });
    } finally {
        sendBtn.disabled = false;
        sendBtn.classList.remove('loading');
        input.focus();
    }
}

async function triggerMorningBrief() {
    const input = document.getElementById('robin-input');
    input.value = 'morning_brief';
    await sendMessageToRobin();
}

function scrollToBottom() {
    const container = document.getElementById('robin-messages');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 100);
}

function formatTimestamp(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// Debug Functions
// ============================================================================

let lastRobinPrompt = null;

function showLastPrompt() {
    if (!lastRobinPrompt) {
        alert('No prompt available yet. Send a message to Robin first!');
        return;
    }
    
    const modal = document.getElementById('debug-prompt-modal');
    const content = document.getElementById('debug-prompt-content');
    
    // Format the prompt nicely
    const formatted = JSON.stringify(lastRobinPrompt, null, 2);
    content.textContent = formatted;
    
    modal.classList.remove('hidden');
}

function closeDebugPrompt() {
    document.getElementById('debug-prompt-modal').classList.add('hidden');
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

