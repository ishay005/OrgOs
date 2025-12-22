// OrgOs Web App - Complete Functionality

const API_BASE = window.location.origin;
let currentUser = null;

// ============================================================================
// Toast Notification System (replaces ugly browser alerts)
// ============================================================================

function showToast(message, type = 'info', duration = 3000) {
    // Create toast container if not exists
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10001;
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
        `;
        document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    const colors = {
        success: { bg: '#dcfce7', border: '#22c55e', text: '#166534' },
        error: { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
        warning: { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
        info: { bg: '#e0f2fe', border: '#0284c7', text: '#075985' }
    };
    const c = colors[type] || colors.info;
    
    toast.innerHTML = `
        <span style="font-size: 1.1rem; margin-right: 8px;">${icons[type] || icons.info}</span>
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="margin-left: 12px; background: none; border: none; cursor: pointer; font-size: 1.1rem; opacity: 0.7;">×</button>
    `;
    toast.style.cssText = `
        display: flex;
        align-items: center;
        padding: 12px 16px;
        background: ${c.bg};
        border: 1px solid ${c.border};
        border-left: 4px solid ${c.border};
        border-radius: 8px;
        color: ${c.text};
        font-weight: 500;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        pointer-events: auto;
        animation: slideIn 0.3s ease;
        max-width: 400px;
    `;
    
    container.appendChild(toast);
    
    // Auto-remove after duration
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Add animation styles
const toastStyles = document.createElement('style');
toastStyles.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(toastStyles);

// ============================================================================
// Custom Confirmation Modal (replaces ugly browser confirm)
// ============================================================================

function showConfirmDialog(message, onConfirm, options = {}) {
    const title = options.title || 'Confirm';
    const confirmText = options.confirmText || 'Confirm';
    const cancelText = options.cancelText || 'Cancel';
    const type = options.type || 'warning'; // warning, danger, info
    
    const colors = {
        warning: { btn: '#f59e0b', hover: '#d97706' },
        danger: { btn: '#dc2626', hover: '#b91c1c' },
        info: { btn: '#3b82f6', hover: '#2563eb' }
    };
    const c = colors[type] || colors.warning;
    
    const modalHtml = `
        <div id="confirm-modal" class="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 10000;">
            <div class="modal-content" style="background: white; padding: 24px; border-radius: 12px; max-width: 400px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                <h3 style="margin: 0 0 16px 0; color: #1e293b;">${title}</h3>
                <p style="margin: 0 0 20px 0; color: #64748b; line-height: 1.5;">${message}</p>
                <div style="display: flex; gap: 12px; justify-content: flex-end;">
                    <button onclick="closeConfirmModal(false)" style="padding: 10px 20px; border: 2px solid #e2e8f0; border-radius: 8px; background: white; cursor: pointer; font-size: 1rem;">${cancelText}</button>
                    <button onclick="closeConfirmModal(true)" style="padding: 10px 20px; border: none; border-radius: 8px; background: ${c.btn}; color: white; cursor: pointer; font-size: 1rem; font-weight: 600;">${confirmText}</button>
                </div>
            </div>
        </div>
    `;
    
    // Store callback
    window._confirmCallback = onConfirm;
    
    // Remove existing modal
    const existing = document.getElementById('confirm-modal');
    if (existing) existing.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeConfirmModal(confirmed) {
    const modal = document.getElementById('confirm-modal');
    if (modal) modal.remove();
    
    if (confirmed && window._confirmCallback) {
        window._confirmCallback();
    }
    window._confirmCallback = null;
}

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
        showDashboard();
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
    showDashboard();
}

// ============================================================================
// Page Navigation
// ============================================================================

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
}

function showDashboard() {
    if (!currentUser) {
        showPage('auth-page');
        return;
    }
    
    document.getElementById('dashboard-user-name').textContent = currentUser.name;
    showPage('dashboard-page');
    
    // Initialize Robin sidebar
    initSidebarResize();
    loadRobinChat();
    
    // Restore saved tab or default to Pending Questions
    const savedTab = localStorage.getItem('currentTab') || 'pending';
    showSection(savedTab);
    
    // Load other dashboard data in background
    loadMisalignments();
}

/**
 * Toggle Robin sidebar between expanded and minimized states.
 * When minimized, shows a floating button to reopen.
 */
function toggleRobinSidebar() {
    const sidebar = document.getElementById('robin-sidebar');
    const floatBtn = document.getElementById('robin-float-btn');
    
    if (!sidebar || !floatBtn) return;
    
    const isMinimized = sidebar.classList.toggle('minimized');
    floatBtn.classList.toggle('visible', isMinimized);
    
    // Save state
    localStorage.setItem('robinSidebarMinimized', isMinimized ? 'true' : 'false');
}

/**
 * Toggle Robin sidebar between docked sidebar and floating popup modes.
 */
function toggleRobinPopup() {
    const sidebar = document.getElementById('robin-sidebar');
    const popoutBtn = document.getElementById('robin-popout-btn');
    
    if (!sidebar) return;
    
    const isPopup = sidebar.classList.toggle('popup-mode');
    
    // Update button icon
    if (popoutBtn) {
        popoutBtn.textContent = isPopup ? '⬛' : '⬜';
        popoutBtn.title = isPopup ? 'Dock to sidebar' : 'Pop out window';
    }
    
    // Initialize drag if in popup mode
    if (isPopup) {
        initRobinDrag();
        // Restore saved position
        const savedPos = localStorage.getItem('robinPopupPosition');
        if (savedPos) {
            const pos = JSON.parse(savedPos);
            sidebar.style.top = pos.top;
            sidebar.style.right = pos.right;
            sidebar.style.left = pos.left || 'auto';
        }
    } else {
        // Reset inline styles when docking
        sidebar.style.top = '';
        sidebar.style.right = '';
        sidebar.style.left = '';
    }
    
    // Save mode
    localStorage.setItem('robinPopupMode', isPopup ? 'true' : 'false');
}

/**
 * Toggle Robin settings panel visibility.
 */
function toggleRobinSettings() {
    const panel = document.getElementById('robin-settings-panel');
    if (panel) {
        panel.classList.toggle('visible');
    }
}

/**
 * Update chat text size.
 */
function updateChatTextSize(size) {
    const chatContainer = document.querySelector('.chat-messages-list');
    const display = document.getElementById('text-size-display');
    
    if (chatContainer) {
        chatContainer.style.fontSize = `${size}px`;
    }
    if (display) {
        display.textContent = `${size}px`;
    }
    
    localStorage.setItem('robinChatTextSize', size);
}

/**
 * Update chat message spacing.
 */
function updateChatSpacing(spacing) {
    const chatContainer = document.querySelector('.chat-messages-list');
    if (!chatContainer) return;
    
    // Remove existing spacing classes
    chatContainer.classList.remove('spacing-compact', 'spacing-normal', 'spacing-relaxed');
    chatContainer.classList.add(`spacing-${spacing}`);
    
    localStorage.setItem('robinChatSpacing', spacing);
}

/**
 * Update chat theme.
 */
function updateChatTheme(theme) {
    const sidebar = document.getElementById('robin-sidebar');
    if (!sidebar) return;
    
    // Remove existing theme classes
    sidebar.classList.remove('theme-default', 'theme-high-contrast', 'theme-soft');
    sidebar.classList.add(`theme-${theme}`);
    
    localStorage.setItem('robinChatTheme', theme);
}

/**
 * Initialize resizable table columns.
 */
function initResizableColumns(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const handles = table.querySelectorAll('.resize-handle');
    
    handles.forEach(handle => {
        let startX, startWidth, th;
        
        const onMouseDown = (e) => {
            th = handle.parentElement;
            startX = e.pageX;
            startWidth = th.offsetWidth;
            handle.classList.add('active');
            
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            e.preventDefault();
        };
        
        const onMouseMove = (e) => {
            const diff = e.pageX - startX;
            const newWidth = Math.max(40, startWidth + diff);
            th.style.width = `${newWidth}px`;
        };
        
        const onMouseUp = () => {
            handle.classList.remove('active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            
            // Save column widths to localStorage
            saveColumnWidths(tableId);
        };
        
        handle.addEventListener('mousedown', onMouseDown);
    });
    
    // Restore saved widths
    restoreColumnWidths(tableId);
}

function saveColumnWidths(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const ths = table.querySelectorAll('thead th');
    const widths = Array.from(ths).map(th => th.offsetWidth);
    localStorage.setItem(`colWidths_${tableId}`, JSON.stringify(widths));
}

function restoreColumnWidths(tableId) {
    const saved = localStorage.getItem(`colWidths_${tableId}`);
    if (!saved) return;
    
    try {
        const widths = JSON.parse(saved);
        const table = document.getElementById(tableId);
        if (!table) return;
        
        const ths = table.querySelectorAll('thead th');
        ths.forEach((th, i) => {
            if (widths[i]) {
                th.style.width = `${widths[i]}px`;
            }
        });
    } catch (e) {
        console.warn('Failed to restore column widths:', e);
    }
}

/**
 * Toggle task graph filters visibility.
 */
function toggleTaskFilters() {
    const filtersRow = document.getElementById('task-filters-row');
    const toggleBtn = document.getElementById('filter-toggle-btn');
    
    if (filtersRow && toggleBtn) {
        const isHidden = filtersRow.classList.toggle('hidden');
        toggleBtn.classList.toggle('collapsed', isHidden);
        localStorage.setItem('taskFiltersHidden', isHidden ? 'true' : 'false');
    }
}

/**
 * Initialize task filters visibility state.
 */
function initTaskFiltersState() {
    const wasHidden = localStorage.getItem('taskFiltersHidden') === 'true';
    const filtersRow = document.getElementById('task-filters-row');
    const toggleBtn = document.getElementById('filter-toggle-btn');
    
    if (wasHidden && filtersRow && toggleBtn) {
        filtersRow.classList.add('hidden');
        toggleBtn.classList.add('collapsed');
    }
}

/**
 * Load saved chat settings.
 */
function loadChatSettings() {
    // Text size
    const savedSize = localStorage.getItem('robinChatTextSize');
    if (savedSize) {
        const sizeInput = document.getElementById('chat-text-size');
        if (sizeInput) sizeInput.value = savedSize;
        updateChatTextSize(savedSize);
    }
    
    // Spacing
    const savedSpacing = localStorage.getItem('robinChatSpacing');
    if (savedSpacing) {
        const spacingSelect = document.getElementById('chat-spacing');
        if (spacingSelect) spacingSelect.value = savedSpacing;
        updateChatSpacing(savedSpacing);
    }
    
}

/**
 * Initialize drag functionality for Robin popup mode.
 */
function initRobinDrag() {
    const sidebar = document.getElementById('robin-sidebar');
    const handle = document.getElementById('robin-drag-handle');
    
    if (!sidebar || !handle) return;
    
    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let startTop = 0;
    let startLeft = 0;
    
    const onMouseDown = (e) => {
        // Only drag if in popup mode and clicking on header (not buttons)
        if (!sidebar.classList.contains('popup-mode')) return;
        if (e.target.tagName === 'BUTTON') return;
        
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        
        const rect = sidebar.getBoundingClientRect();
        startTop = rect.top;
        startLeft = rect.left;
        
        document.body.style.cursor = 'move';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    };
    
    const onMouseMove = (e) => {
        if (!isDragging) return;
        
        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;
        
        let newTop = startTop + deltaY;
        let newLeft = startLeft + deltaX;
        
        // Keep within viewport
        newTop = Math.max(0, Math.min(window.innerHeight - 100, newTop));
        newLeft = Math.max(0, Math.min(window.innerWidth - 100, newLeft));
        
        sidebar.style.top = `${newTop}px`;
        sidebar.style.left = `${newLeft}px`;
        sidebar.style.right = 'auto';
    };
    
    const onMouseUp = () => {
        if (!isDragging) return;
        
        isDragging = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        
        // Save position
        localStorage.setItem('robinPopupPosition', JSON.stringify({
            top: sidebar.style.top,
            left: sidebar.style.left,
            right: sidebar.style.right
        }));
    };
    
    // Remove old listeners if any
    handle.removeEventListener('mousedown', handle._dragHandler);
    
    // Add new listener
    handle._dragHandler = onMouseDown;
    handle.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
}

/**
 * Initialize the Robin sidebar resize functionality.
 * Allows dragging the left edge to resize the sidebar.
 * Persists width to localStorage.
 */
function initSidebarResize() {
    const sidebar = document.getElementById('robin-sidebar');
    const handle = document.getElementById('sidebar-resize-handle');
    const floatBtn = document.getElementById('robin-float-btn');
    const popoutBtn = document.getElementById('robin-popout-btn');
    
    if (!sidebar || !handle) return;
    
    // Restore popup mode state
    const wasPopup = localStorage.getItem('robinPopupMode') === 'true';
    if (wasPopup) {
        sidebar.classList.add('popup-mode');
        if (popoutBtn) {
            popoutBtn.textContent = '⬛';
            popoutBtn.title = 'Dock to sidebar';
        }
        initRobinDrag();
        // Restore saved position
        const savedPos = localStorage.getItem('robinPopupPosition');
        if (savedPos) {
            const pos = JSON.parse(savedPos);
            sidebar.style.top = pos.top;
            sidebar.style.right = pos.right;
            sidebar.style.left = pos.left || 'auto';
        }
    }
    
    // Restore minimized state (only if not in popup mode)
    const wasMinimized = localStorage.getItem('robinSidebarMinimized') === 'true';
    if (wasMinimized && !wasPopup) {
        sidebar.classList.add('minimized');
        if (floatBtn) floatBtn.classList.add('visible');
    }
    
    // Restore saved width
    const savedWidth = localStorage.getItem('robinSidebarWidth');
    if (savedWidth) {
        const width = parseInt(savedWidth, 10);
        if (width >= 280) {
            sidebar.style.width = `${width}px`;
        }
    }
    
    // Load chat settings (text size, spacing, theme)
    loadChatSettings();
    
    let isResizing = false;
    let startX = 0;
    let startWidth = 0;
    
    handle.addEventListener('mousedown', (e) => {
        isResizing = true;
        startX = e.clientX;
        startWidth = sidebar.offsetWidth;
        handle.classList.add('active');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        
        // Calculate new width (dragging left increases width, right decreases)
        const deltaX = startX - e.clientX;
        let newWidth = startWidth + deltaX;
        
        // Clamp to min/max
        newWidth = Math.max(280, Math.min(600, newWidth));
        
        sidebar.style.width = `${newWidth}px`;
    });
    
    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        
        isResizing = false;
        handle.classList.remove('active');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        
        // Save width to localStorage
        localStorage.setItem('robinSidebarWidth', sidebar.offsetWidth.toString());
    });
}

function showSection(sectionName) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.top-nav-btn').forEach(b => b.classList.remove('active'));
    
    document.getElementById(`${sectionName}-section`).classList.add('active');
    document.getElementById(`${sectionName}-nav`).classList.add('active');
    
    // Save current tab to persist across refresh
    localStorage.setItem('currentTab', sectionName);
    
    // Load data for specific sections
    if (sectionName === 'pending') {
        loadPendingQuestions();
    } else if (sectionName === 'prompts') {
        loadPrompts().catch(err => console.error('Error loading prompts:', err));
    } else if (sectionName === 'misalignments') {
        loadMisalignments();
    } else if (sectionName === 'graph') {
        loadTaskGraph();
    } else if (sectionName === 'ontology') {
        displayOntology();
    } else if (sectionName === 'orgchart') {
        loadOrgChart();
    } else if (sectionName === 'mcp-tools') {
        loadMcpTools();
    } else if (sectionName === 'decisions') {
        loadPendingDecisions();
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
                name: "owner",
                label: "Task Owner",
                type: "user_reference",
                description: "The user who owns and is responsible for this task",
                entity_type: "task"
            },
            {
                name: "created_by",
                label: "Task Creator",
                type: "user_reference",
                description: "The user who created/suggested this task",
                entity_type: "task"
            },
            {
                name: "state",
                label: "Task State",
                type: "enum",
                description: "Lifecycle state of the task (DRAFT, ACTIVE, REJECTED, ARCHIVED)",
                allowed_values: ["DRAFT", "ACTIVE", "REJECTED", "ARCHIVED"],
                entity_type: "task"
            },
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
                description: "Tasks that this task depends on (with status: PROPOSED, CONFIRMED, REJECTED, REMOVED)",
                entity_type: "task"
            },
            {
                name: "aliases",
                label: "Task Aliases",
                type: "reference_list",
                description: "Previous task titles that were merged into this task",
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

/**
 * Center the org chart view on the current user's node.
 */
function centerOnCurrentUser() {
    const container = document.getElementById('org-chart-container');
    if (!container || !orgChartView.currentUserPosition) return;
    
    const containerRect = container.getBoundingClientRect();
    const centerX = containerRect.width / 2;
    const centerY = containerRect.height / 3; // A bit above center
    
    // Calculate translation to center the user
    orgChartView.translateX = centerX - orgChartView.currentUserPosition.x * orgChartView.scale;
    orgChartView.translateY = centerY - orgChartView.currentUserPosition.y * orgChartView.scale;
    
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
    const NODE_WIDTH = 200;
    const NODE_HEIGHT = 100;
    const HORIZONTAL_GAP = 50;
    const VERTICAL_GAP = 120;
    
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
        
        // Store current user position for centering
        if (isCurrentUser) {
            orgChartView.currentUserPosition = { 
                x: node.x + NODE_WIDTH / 2, 
                y: node.y + NODE_HEIGHT / 2 
            };
        }
        
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
        name.setAttribute('y', 22);
        name.setAttribute('text-anchor', 'middle');
        name.setAttribute('fill', '#000000'); // Always black for readability
        name.textContent = node.name;
        if (isCurrentUser) {
            name.textContent += ' (You)';
            name.setAttribute('font-weight', 'bold');
        }
        group.appendChild(name);
        
        // Role line (if available)
        if (node.role) {
            const roleLine = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            roleLine.setAttribute('class', 'org-node-role');
            roleLine.setAttribute('x', NODE_WIDTH / 2);
            roleLine.setAttribute('y', 38);
            roleLine.setAttribute('text-anchor', 'middle');
            roleLine.setAttribute('fill', '#555555');
            roleLine.setAttribute('font-size', '11');
            roleLine.setAttribute('font-style', 'italic');
            roleLine.textContent = node.role;
            group.appendChild(roleLine);
        }
        
        // Team line (if available)
        if (node.team) {
            const teamLine = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            teamLine.setAttribute('class', 'org-node-team');
            teamLine.setAttribute('x', NODE_WIDTH / 2);
            teamLine.setAttribute('y', node.role ? 52 : 38);
            teamLine.setAttribute('text-anchor', 'middle');
            teamLine.setAttribute('fill', '#6366f1');
            teamLine.setAttribute('font-size', '10');
            teamLine.textContent = `📁 ${node.team}`;
            group.appendChild(teamLine);
        }
        
        // Info line 1 - task count (always shown)
        const info1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        info1.setAttribute('class', 'org-node-info');
        info1.setAttribute('x', NODE_WIDTH / 2);
        info1.setAttribute('y', node.role && node.team ? 68 : (node.role || node.team ? 55 : 45));
        info1.setAttribute('text-anchor', 'middle');
        info1.setAttribute('fill', '#000000');
        info1.setAttribute('font-size', '10');
        
        // Show both task count and alignment if enabled
        if (showAlignment && userAlignmentStats[node.id] !== undefined) {
            info1.textContent = `${node.task_count} tasks • ${Math.round(userAlignmentStats[node.id])}% aligned`;
        } else {
            info1.textContent = `${node.task_count} task${node.task_count !== 1 ? 's' : ''}`;
        }
        group.appendChild(info1);
        
        // Info line 2 - reports count
        const info2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        info2.setAttribute('class', 'org-node-info');
        info2.setAttribute('x', NODE_WIDTH / 2);
        info2.setAttribute('y', node.role && node.team ? 82 : (node.role || node.team ? 70 : 60));
        info2.setAttribute('text-anchor', 'middle');
        info2.setAttribute('fill', '#888888');
        info2.setAttribute('font-size', '10');
        info2.textContent = node.employee_count > 0 
            ? `${node.employee_count} report${node.employee_count !== 1 ? 's' : ''}`
            : 'IC';
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
    
    // Center view on current user (first time only)
    if (!orgChartView.initialCenterDone) {
        orgChartView.initialCenterDone = true;
        setTimeout(() => centerOnCurrentUser(), 100);
    }
}


/**
 * Show misalignments for a specific user in a popup
 * Uses alignment-stats to calculate real misalignment data
 */
async function showUserMisalignments(userId, userName) {
    console.log('showUserMisalignments called for:', userName, userId);
    
    try {
        const modal = document.getElementById('user-misalignment-modal');
        const modalTitle = document.getElementById('user-misalignment-title');
        const modalContent = document.getElementById('user-misalignment-content');
        
        if (!modal || !modalTitle || !modalContent) {
            console.error('Modal elements not found!');
            return;
        }
        
        modalTitle.textContent = `Alignment Details for ${userName}`;
        modalContent.innerHTML = '<div class="loading">Loading alignment data...</div>';
        modal.classList.remove('hidden');
        
        // Fetch all answers for this user's tasks to compare with others
        const [userTasks, allAnswers] = await Promise.all([
            apiCall(`/tasks?owner_id=${userId}`).catch(() => []),
            apiCall(`/users/${userId}/alignment-details`).catch(() => null)
        ]);
        
        // If we have the alignment-details endpoint, use it
        if (allAnswers && allAnswers.comparisons && allAnswers.comparisons.length > 0) {
            let html = `
                <div style="background: #f0f9ff; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                    <strong>Alignment Score:</strong> ${allAnswers.overall_alignment}%
                    <br><small>Based on ${allAnswers.total_comparisons} attribute comparisons</small>
                </div>
            `;
            
            // Group by task
            const byTask = {};
            allAnswers.comparisons.forEach(c => {
                if (!byTask[c.task_title]) byTask[c.task_title] = [];
                byTask[c.task_title].push(c);
            });
            
            for (const [taskTitle, comps] of Object.entries(byTask)) {
                const taskAligned = comps.filter(c => c.is_aligned).length;
                const taskTotal = comps.length;
                const taskPct = Math.round((taskAligned / taskTotal) * 100);
                
                html += `
                    <div style="margin-bottom: 16px; padding: 12px; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;">
                        <h4 style="margin: 0 0 8px 0; display: flex; justify-content: space-between;">
                            <span>📋 ${escapeHtml(taskTitle)}</span>
                            <span style="color: ${taskPct >= 70 ? '#22c55e' : taskPct >= 40 ? '#f59e0b' : '#ef4444'};">${taskPct}%</span>
                        </h4>
                        <table style="width: 100%; font-size: 0.9rem; border-collapse: collapse;">
                            <tr style="border-bottom: 1px solid #e2e8f0;">
                                <th style="text-align: left; padding: 4px;">Attribute</th>
                                <th style="text-align: left; padding: 4px;">${userName}</th>
                                <th style="text-align: left; padding: 4px;">Other</th>
                                <th style="text-align: center; padding: 4px;">Match</th>
                            </tr>
                            ${comps.map(c => `
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td style="padding: 4px;">${escapeHtml(c.attribute)}</td>
                                    <td style="padding: 4px; color: #666;">${escapeHtml(c.user_value || 'N/A')}</td>
                                    <td style="padding: 4px; color: #666;">${escapeHtml(c.other_value || 'N/A')}</td>
                                    <td style="padding: 4px; text-align: center;">${c.is_aligned ? '✅' : '❌'}</td>
                                </tr>
                            `).join('')}
                        </table>
                    </div>
                `;
            }
            
            modalContent.innerHTML = html;
            return;
        }
        
        // Fallback: try to get misalignments the old way (for backward compatibility)
        const misalignments = await apiCall('/misalignments?include_all=true', { 
            headers: { 'X-User-Id': userId } 
        }).catch(() => []);
        
        if (!misalignments || misalignments.length === 0) {
            // Show user alignment from stats
            const alignmentPct = userAlignmentStats[userId];
            modalContent.innerHTML = `
                <div style="text-align: center; padding: 40px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">${alignmentPct >= 70 ? '✅' : alignmentPct >= 40 ? '⚠️' : '❌'}</div>
                    <h3 style="margin: 0 0 8px 0;">Alignment: ${alignmentPct !== undefined ? Math.round(alignmentPct) + '%' : 'N/A'}</h3>
                    <p style="color: #666;">No detailed comparison data available.</p>
                    <p style="color: #999; font-size: 0.9rem;">This may mean no other users have answered about the same tasks/attributes.</p>
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

// Dashboard - Tasks
// ============================================================================


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
    // Check if user is logged in
    if (!currentUser || !currentUser.id) {
        console.error('No current user - cannot load misalignments');
        const statsDiv = document.getElementById('misalignment-stats');
        if (statsDiv) statsDiv.innerHTML = '<div class="error">Please log in to view misalignments.</div>';
        return;
    }
    
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
    
    // Initialize filter visibility state
    initTaskFiltersState();
    
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
        
        // Populate state filter (multi-select) - pull from actual task data
        const stateFilterContent = document.getElementById('filter-content-state');
        const states = [...new Set(tasks.map(t => t.state).filter(s => s))].sort();
        
        if (stateFilterContent) {
            stateFilterContent.innerHTML = states.map(state => `
                <div class="filter-option" onclick="event.stopPropagation()">
                    <input type="checkbox" id="filter-state-${state}" 
                           value="${state}" data-attr-name="state" onchange="updateStateFilter()">
                    <label for="filter-state-${state}" style="cursor: pointer">${getStateLabel(state)}</label>
                </div>
            `).join('');
        }
        
        // Populate team filter from actual user teams
        try {
            const orgData = await apiCall('/users/org-chart', { skipAuth: true });
            const teams = [...new Set(orgData.users.map(u => u.team).filter(t => t))];
            const teamSelect = document.getElementById('filter-team');
            if (teamSelect) {
                teamSelect.innerHTML = '<option value="">All Teams</option>' + 
                    teams.map(team => `<option value="${team}">${team}</option>`).join('');
            }
            // Store users data for team filtering
            window.orgChartUsers = orgData.users;
        } catch (e) {
            console.log('Could not load teams for filter:', e);
        }
        
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
// Task Details Popup (Compact Tabs Layout)
// ============================================================================

async function showTaskDetails(taskId) {
    const modal = document.getElementById('task-details-modal');
    const title = document.getElementById('task-details-title');
    const content = document.getElementById('task-details-content');
    
    title.textContent = 'Loading...';
    content.innerHTML = '<div class="loading">Loading task details...</div>';
    modal.classList.remove('hidden');
    
    try {
        // Fetch all data in parallel
        const [data, relevantUsers, permissions, allUsers, taskAttributes, dependencies, allTasks, fullDetails] = await Promise.all([
            apiCall(`/tasks/${taskId}/answers`, { skipAuth: true }),
            apiCall(`/tasks/${taskId}/relevant-users`).catch(() => []),
            apiCall(`/tasks/${taskId}/permissions`).catch(() => ({})),
            apiCall('/users').catch(() => []),
            apiCall('/task-attributes').catch(() => []),
            apiCall(`/tasks/${taskId}/dependencies`).catch(() => []),
            apiCall('/tasks?include_self=true&include_aligned=true').catch(() => []),
            apiCall(`/tasks/${taskId}/full-details`).catch(() => ({}))
        ]);
        
        // Store task data for save operations
        window.currentEditingTask = {
            id: taskId,
            title: data.task_title,
            description: data.task_description || '',
            owner_id: data.owner_id,
            owner_name: data.owner_name,
            permissions: permissions,
            relevantUsers: relevantUsers,
            allUsers: allUsers,
            taskAttributes: taskAttributes,
            answers: data.answers_by_attribute
        };
        
        const taskState = fullDetails.state || 'ACTIVE';
        const stateColors = {
            'DRAFT': '#6b7280',
            'ACTIVE': '#3b82f6',
            'REJECTED': '#ef4444',
            'ARCHIVED': '#9ca3af'
        };
        const stateColor = stateColors[taskState] || stateColors.ACTIVE;
        
        // Compact title with state badge
        title.innerHTML = `
            <span style="display: flex; align-items: center; gap: 8px;">
                ${escapeHtml(data.task_title)}
                <span style="background: ${stateColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">${taskState}</span>
            </span>
        `;
        
        // Build tabbed content
        const hasPendingProposals = (fullDetails.merge_proposals?.length > 0) || (fullDetails.alt_dependency_proposals?.length > 0);
        const hasAliases = fullDetails.aliases?.length > 0;
        
        let html = `
        <style>
            .task-tabs { display: flex; gap: 0; border-bottom: 2px solid #e2e8f0; margin-bottom: 12px; }
            .task-tab { padding: 8px 16px; cursor: pointer; border: none; background: none; font-size: 13px; font-weight: 500; color: #64748b; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; }
            .task-tab:hover { color: #3b82f6; background: #f8fafc; }
            .task-tab.active { color: #3b82f6; border-bottom-color: #3b82f6; }
            .task-tab-content { display: none; }
            .task-tab-content.active { display: block; }
            .task-row { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
            .task-row:last-child { border-bottom: none; }
            .task-label { color: #64748b; min-width: 80px; flex-shrink: 0; }
            .task-value { flex: 1; color: #1e293b; }
            .task-input { padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; width: 100%; }
            .task-input:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1); }
            .task-section { margin-bottom: 12px; }
            .task-section-title { font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }
            .compact-tag { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; background: #f1f5f9; border-radius: 4px; font-size: 12px; margin: 2px; }
            .compact-tag .remove-btn { background: none; border: none; cursor: pointer; color: #94a3b8; font-size: 14px; padding: 0 2px; }
            .compact-tag .remove-btn:hover { color: #ef4444; }
            .compact-btn { padding: 6px 12px; border: none; border-radius: 6px; font-size: 12px; cursor: pointer; font-weight: 500; }
            .compact-btn-primary { background: #3b82f6; color: white; }
            .compact-btn-primary:hover { background: #2563eb; }
            .compact-btn-danger { background: #fee2e2; color: #dc2626; }
            .compact-btn-danger:hover { background: #fecaca; }
            .compact-select { padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 12px; flex: 1; }
            .status-badge { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }
            .status-confirmed { background: #dcfce7; color: #166534; }
            .status-proposed { background: #fef3c7; color: #92400e; }
            .dep-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
            .perception-table { width: 100%; border-collapse: collapse; font-size: 12px; }
            .perception-table th, .perception-table td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #f1f5f9; }
            .perception-table th { background: #f8fafc; font-weight: 600; color: #64748b; }
            .perception-table input, .perception-table select { padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px; font-size: 12px; width: 100%; }
            .proposal-card { background: #fef2f2; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px; font-size: 12px; border-left: 3px solid #ef4444; }
            .alias-card { background: #fef3c7; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px; font-size: 12px; border-left: 3px solid #f59e0b; }
        </style>
        
        <!-- Compact Header Info -->
        <div style="display: flex; gap: 16px; flex-wrap: wrap; padding: 8px 12px; background: #f8fafc; border-radius: 8px; margin-bottom: 12px; font-size: 13px;">
            <span><strong>Owner:</strong> ${escapeHtml(fullDetails.owner?.name || data.owner_name)}</span>
            ${fullDetails.creator && fullDetails.creator.id !== fullDetails.owner?.id ? 
                `<span><strong>Created by:</strong> ${escapeHtml(fullDetails.creator.name)}</span>` : ''}
            ${fullDetails.state_reason ? `<span style="color: #64748b;"><strong>Reason:</strong> ${escapeHtml(fullDetails.state_reason)}</span>` : ''}
        </div>
        
        <!-- Tabs -->
        <div class="task-tabs">
            <button class="task-tab active" onclick="switchTaskTab(event, 'info')">📋 Info</button>
            <button class="task-tab" onclick="switchTaskTab(event, 'deps')">🔗 Dependencies</button>
            <button class="task-tab" onclick="switchTaskTab(event, 'perceptions')">💭 Perceptions</button>
            <button class="task-tab" onclick="switchTaskTab(event, 'team')">👥 Team</button>
            ${hasPendingProposals || hasAliases ? `<button class="task-tab" onclick="switchTaskTab(event, 'more')" style="color: #f59e0b;">⚡ More</button>` : ''}
        </div>
        `;
        
        // === TAB: Info ===
        html += `<div id="task-tab-info" class="task-tab-content active">`;
        
        if (permissions.can_edit_task) {
            const childIds = (data.children || []).map(c => c.id);
            const availableParents = allTasks.filter(t => t.id !== taskId && !childIds.includes(t.id));
            const availableChildren = allTasks.filter(t => t.id !== taskId && !childIds.includes(t.id) && t.id !== data.parent?.id);
            
            html += `
                <div class="task-section">
                    <div class="task-row">
                        <span class="task-label">Title</span>
                        <input type="text" id="edit-task-title" value="${escapeHtml(data.task_title)}" class="task-input">
                    </div>
                    <div class="task-row">
                        <span class="task-label">Description</span>
                        <textarea id="edit-task-description" class="task-input" rows="2">${escapeHtml(data.task_description || '')}</textarea>
                    </div>
                    <div class="task-row">
                        <span class="task-label">Owner</span>
                        <select id="edit-task-owner" class="task-input">
                            ${allUsers.map(u => `<option value="${u.id}" ${u.id === data.owner_id ? 'selected' : ''}>${u.name}</option>`).join('')}
                        </select>
                    </div>
                    <div class="task-row">
                        <span class="task-label">Parent</span>
                        <select id="edit-task-parent" class="task-input">
                            <option value="">None (Top Level)</option>
                            ${availableParents.map(t => `<option value="${t.id}" ${data.parent?.id === t.id ? 'selected' : ''}>${t.title}</option>`).join('')}
                        </select>
                    </div>
                    <div style="margin-top: 8px;">
                        <button onclick="saveTaskInfo('${taskId}')" class="compact-btn compact-btn-primary">💾 Save Changes</button>
                    </div>
                </div>
                
                <div class="task-section">
                    <div class="task-section-title">Children Tasks</div>
                    ${data.children?.length > 0 ? 
                        `<div style="margin-bottom: 8px;">${data.children.map(c => `
                            <span class="compact-tag">${escapeHtml(c.title)} <button class="remove-btn" onclick="removeChildTask('${taskId}', '${c.id}')">×</button></span>
                        `).join('')}</div>` : 
                        `<div style="color: #94a3b8; font-size: 12px; margin-bottom: 8px;">No children</div>`}
                    <div style="display: flex; gap: 8px;">
                        <select id="add-child-select" class="compact-select">
                            <option value="">Add child task...</option>
                            ${availableChildren.map(t => `<option value="${t.id}">${t.title}</option>`).join('')}
                        </select>
                        <button onclick="addChildTask('${taskId}')" class="compact-btn compact-btn-primary">➕</button>
                    </div>
                </div>
            `;
        } else {
            html += `
                <div class="task-section">
                    <div class="task-row"><span class="task-label">Owner</span><span class="task-value">${escapeHtml(data.owner_name)}</span></div>
                    ${data.task_description ? `<div class="task-row"><span class="task-label">Description</span><span class="task-value">${escapeHtml(data.task_description)}</span></div>` : ''}
                    ${data.parent ? `<div class="task-row"><span class="task-label">Parent</span><span class="task-value">${escapeHtml(data.parent.title)}</span></div>` : ''}
                    ${data.children?.length > 0 ? `<div class="task-row"><span class="task-label">Children</span><span class="task-value">${data.children.map(c => c.title).join(', ')}</span></div>` : ''}
                </div>
            `;
        }
        
        // Delete button
        if (permissions.can_delete) {
            html += `<div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid #fee2e2;">
                <button onclick="deleteTask('${taskId}', '${escapeHtml(data.task_title)}')" class="compact-btn compact-btn-danger">🗑️ Delete Task</button>
            </div>`;
        }
        html += `</div>`;
        
        // === TAB: Dependencies ===
        html += `<div id="task-tab-deps" class="task-tab-content">`;
        
        // Dependencies V2 (with status)
        const depsV2 = fullDetails.dependencies_v2 || [];
        const outgoing = depsV2.filter(d => d.direction === 'outgoing');
        const incoming = depsV2.filter(d => d.direction === 'incoming');
        
        if (outgoing.length > 0) {
            html += `<div class="task-section"><div class="task-section-title">This task depends on</div>`;
            outgoing.forEach(dep => {
                const statusClass = dep.status === 'CONFIRMED' ? 'status-confirmed' : 'status-proposed';
                const statusText = dep.status === 'CONFIRMED' ? '✓ Confirmed' : '⏳ Proposed';
                html += `<div class="dep-item">
                    <span>${escapeHtml(dep.task_title)}</span>
                    <span style="color: #94a3b8;">(${escapeHtml(dep.task_owner)})</span>
                    <span class="status-badge ${statusClass}">${statusText}</span>
                </div>`;
            });
            html += `</div>`;
        }
        
        if (incoming.length > 0) {
            html += `<div class="task-section"><div class="task-section-title">Tasks depending on this</div>`;
            incoming.forEach(dep => {
                const statusClass = dep.status === 'CONFIRMED' ? 'status-confirmed' : 'status-proposed';
                const statusText = dep.status === 'CONFIRMED' ? '✓ Confirmed' : '⏳ Proposed';
                html += `<div class="dep-item">
                    <span>${escapeHtml(dep.task_title)}</span>
                    <span style="color: #94a3b8;">(${escapeHtml(dep.task_owner)})</span>
                    <span class="status-badge ${statusClass}">${statusText}</span>
                </div>`;
            });
            html += `</div>`;
        }
        
        // Legacy dependencies
        if (dependencies.length > 0 && depsV2.length === 0) {
            html += `<div class="task-section"><div class="task-section-title">Dependencies</div>`;
            dependencies.forEach(dep => {
                html += `<div class="dep-item">
                    <span>${escapeHtml(dep.task_title)}</span>
                    <span style="color: #94a3b8;">(${escapeHtml(dep.owner_name)})</span>
                    ${permissions.can_manage_dependencies ? `<button class="compact-tag remove-btn" onclick="removeDependency('${taskId}', '${dep.task_id}')">×</button>` : ''}
                </div>`;
            });
            html += `</div>`;
        }
        
        if (outgoing.length === 0 && incoming.length === 0 && dependencies.length === 0) {
            html += `<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">No dependencies</div>`;
        }
        
        // Add dependency
        if (permissions.can_manage_dependencies) {
            const availableTasks = allTasks.filter(t => t.id !== taskId && !dependencies.some(d => d.task_id === t.id));
            html += `<div style="display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0;">
                <select id="add-dependency-select" class="compact-select">
                    <option value="">Add dependency...</option>
                    ${availableTasks.map(t => `<option value="${t.id}">${t.title}</option>`).join('')}
                </select>
                <button onclick="addDependency('${taskId}')" class="compact-btn compact-btn-primary">➕</button>
            </div>`;
        }
        html += `</div>`;
        
        // === TAB: Perceptions ===
        html += `<div id="task-tab-perceptions" class="task-tab-content">`;
        
        const attributeKeys = Object.keys(data.answers_by_attribute);
        const answeringUsers = new Set();
        attributeKeys.forEach(attrKey => {
            const attr = data.answers_by_attribute[attrKey];
            if (attr.answers) {
                attr.answers.forEach(answer => {
                    answeringUsers.add(JSON.stringify({ id: answer.user_id, name: answer.user_name, is_owner: answer.is_owner }));
                });
            }
        });
        
        const users = Array.from(answeringUsers).map(u => JSON.parse(u));
        users.sort((a, b) => b.is_owner - a.is_owner);
        if (currentUser && !users.find(u => u.id === currentUser.id)) {
            users.push({ id: currentUser.id, name: currentUser.name, is_owner: false, is_current: true });
        }
        
        if (taskAttributes.length > 0) {
            html += `<table class="perception-table"><thead><tr><th>Attribute</th>`;
            users.forEach(user => {
                const ownerLabel = user.is_owner ? ' 👑' : '';
                html += `<th>${escapeHtml(user.name)}${ownerLabel}</th>`;
            });
            html += `</tr></thead><tbody>`;
            
            taskAttributes.forEach(attr => {
                const existingData = data.answers_by_attribute[attr.name];
                html += `<tr><td style="font-weight: 500;">${escapeHtml(attr.label)}</td>`;
                
                users.forEach(user => {
                    const existingAnswer = existingData?.answers?.find(a => a.user_id === user.id);
                    const currentValue = existingAnswer?.value || '';
                    const isCurrentUser = user.id === currentUser?.id;
                    
                    if (isCurrentUser && permissions.can_edit_own_perception) {
                        const inputId = `perception-${attr.name}-${user.id}`;
                        if (attr.type === 'enum' && attr.allowed_values) {
                            html += `<td><select id="${inputId}" class="perception-input" data-attr="${attr.name}" data-target="${data.owner_id}">
                                <option value="">-</option>
                                ${attr.allowed_values.map(v => `<option value="${v}" ${currentValue === v ? 'selected' : ''}>${v}</option>`).join('')}
                            </select></td>`;
                        } else {
                            html += `<td><input type="text" id="${inputId}" class="perception-input" value="${escapeHtml(currentValue)}" data-attr="${attr.name}" data-target="${data.owner_id}" placeholder="-"></td>`;
                        }
                    } else {
                        html += `<td>${escapeHtml(currentValue) || '-'}</td>`;
                    }
                });
                html += `</tr>`;
            });
            html += `</tbody></table>`;
            
            if (permissions.can_edit_own_perception) {
                html += `<div style="margin-top: 12px;"><button onclick="savePerceptions('${taskId}', '${data.owner_id}')" class="compact-btn compact-btn-primary">💾 Save My Perceptions</button></div>`;
            }
        } else {
            html += `<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">No attributes defined</div>`;
        }
        html += `</div>`;
        
        // === TAB: Team ===
        html += `<div id="task-tab-team" class="task-tab-content">`;
        html += `<div class="task-section"><div class="task-section-title">Relevant Users</div>`;
        
        if (relevantUsers.length > 0) {
            html += `<div style="margin-bottom: 8px;">`;
            relevantUsers.forEach(ru => {
                const canRemove = permissions.can_manage_all_relevant || (permissions.can_manage_self_relevant && ru.user_id === currentUser?.id);
                html += `<span class="compact-tag">${escapeHtml(ru.user_name)}${canRemove ? `<button class="remove-btn" onclick="removeRelevantUser('${taskId}', '${ru.user_id}')">×</button>` : ''}</span>`;
            });
            html += `</div>`;
        } else {
            html += `<div style="color: #94a3b8; font-size: 12px; margin-bottom: 8px;">No relevant users assigned</div>`;
        }
        
        const currentUserInList = relevantUsers.some(ru => ru.user_id === currentUser?.id);
        if (permissions.can_manage_self_relevant && !currentUserInList) {
            html += `<button onclick="addRelevantUser('${taskId}', '${currentUser?.id}')" class="compact-btn compact-btn-primary" style="margin-bottom: 8px;">➕ Add Myself</button>`;
        }
        
        if (permissions.can_manage_all_relevant) {
            html += `<div style="display: flex; gap: 8px;">
                <select id="add-relevant-user-select" class="compact-select">
                    <option value="">Add user...</option>
                    ${allUsers.filter(u => !relevantUsers.some(ru => ru.user_id === u.id)).map(u => `<option value="${u.id}">${u.name}</option>`).join('')}
                </select>
                <button onclick="addSelectedRelevantUser('${taskId}')" class="compact-btn compact-btn-primary">➕</button>
            </div>`;
        }
        html += `</div></div>`;
        
        // === TAB: More (Proposals & Aliases) ===
        if (hasPendingProposals || hasAliases) {
            html += `<div id="task-tab-more" class="task-tab-content">`;
            
            if (hasAliases) {
                html += `<div class="task-section"><div class="task-section-title">🔀 Merged Task Aliases</div>`;
                fullDetails.aliases.forEach(alias => {
                    html += `<div class="alias-card">"${escapeHtml(alias.title)}" <span style="color: #92400e;">by ${escapeHtml(alias.creator_name)}</span></div>`;
                });
                html += `</div>`;
            }
            
            if (hasPendingProposals) {
                html += `<div class="task-section"><div class="task-section-title">⏳ Pending Proposals</div>`;
                
                if (fullDetails.merge_proposals?.length > 0) {
                    fullDetails.merge_proposals.forEach(p => {
                        html += `<div class="proposal-card">
                            <strong>🔀 Merge:</strong> "${escapeHtml(p.from_task_title)}" → "${escapeHtml(p.to_task_title)}"<br>
                            <span style="color: #991b1b;">By ${escapeHtml(p.proposed_by)}: ${escapeHtml(p.reason)}</span>
                        </div>`;
                    });
                }
                
                if (fullDetails.alt_dependency_proposals?.length > 0) {
                    fullDetails.alt_dependency_proposals.forEach(p => {
                        html += `<div class="proposal-card">
                            <strong>↔️ Alt Dependency:</strong> Replace "${escapeHtml(p.original_upstream)}" with "${escapeHtml(p.suggested_upstream)}"<br>
                            <span style="color: #991b1b;">By ${escapeHtml(p.proposed_by)}: ${escapeHtml(p.reason)}</span>
                        </div>`;
                    });
                }
                html += `</div>`;
            }
            html += `</div>`;
        }
        
        content.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading task details:', error);
        content.innerHTML = `<div class="message error">Failed to load task details: ${error.message}</div>`;
    }
}

// Tab switching function
function switchTaskTab(event, tabId) {
    // Update tab buttons
    document.querySelectorAll('.task-tab').forEach(tab => tab.classList.remove('active'));
    event.target.classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.task-tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`task-tab-${tabId}`).classList.add('active');
}

// Helper function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Save task info (title, description, owner, parent)
async function saveTaskInfo(taskId) {
    const title = document.getElementById('edit-task-title')?.value;
    const description = document.getElementById('edit-task-description')?.value;
    const ownerId = document.getElementById('edit-task-owner')?.value;
    const parentSelect = document.getElementById('edit-task-parent');
    
    // Build update object
    const updateData = {
        title: title,
        description: description,
        owner_user_id: ownerId
    };
    
    // Only include parent_id if the select exists (permission to edit)
    if (parentSelect) {
        // Empty string means "clear parent", otherwise send the UUID
        updateData.parent_id = parentSelect.value || "";
    }
    
    try {
        await apiCall(`/tasks/${taskId}`, {
            method: 'PATCH',
            body: JSON.stringify(updateData)
        });
        
        showToast('Task info saved successfully!', 'success');
        // Refresh the popup
        showTaskDetails(taskId);
        // Refresh the graph if visible
        if (document.getElementById('graph-section')?.classList.contains('active')) {
            loadTaskGraph();
        }
    } catch (error) {
        showToast('Failed to save task info: ' + error.message, 'error');
    }
}

// Save perceptions
async function savePerceptions(taskId, targetUserId) {
    const inputs = document.querySelectorAll('.perception-input');
    const updates = [];
    
    inputs.forEach(input => {
        const attrName = input.dataset.attr;
        const value = input.value.trim();
        
        if (value) {
            updates.push({
                task_id: taskId,
                target_user_id: targetUserId,
                attribute_name: attrName,
                value: value
            });
        }
    });
    
    try {
        for (const update of updates) {
            await apiCall('/pending-questions/answer', {
                method: 'POST',
                body: JSON.stringify(update)
            });
        }
        
        showToast(`Saved ${updates.length} perception(s)!`, 'success');
        // Refresh the popup
        showTaskDetails(taskId);
        // Refresh misalignment stats if visible
        if (document.getElementById('misalignments-section')?.classList.contains('active')) {
            loadMisalignments();
        }
    } catch (error) {
        showToast('Failed to save perceptions: ' + error.message, 'error');
    }
}

// Add relevant user
async function addRelevantUser(taskId, userId) {
    try {
        await apiCall(`/tasks/${taskId}/relevant-users/${userId}`, { method: 'POST' });
        showToast('User added to relevant list!', 'success');
        showTaskDetails(taskId);
    } catch (error) {
        showToast('Failed to add user: ' + error.message, 'error');
    }
}

// Add selected relevant user from dropdown
async function addSelectedRelevantUser(taskId) {
    const select = document.getElementById('add-relevant-user-select');
    const userId = select?.value;
    if (!userId) {
        showToast('Please select a user first', 'warning');
        return;
    }
    await addRelevantUser(taskId, userId);
}

// Remove relevant user
async function removeRelevantUser(taskId, userId) {
    if (!confirm('Remove this user from the relevant list?')) return;
    
    try {
        await apiCall(`/tasks/${taskId}/relevant-users/${userId}`, { method: 'DELETE' });
        showToast('User removed from relevant list!', 'success');
        showTaskDetails(taskId);
    } catch (error) {
        showToast('Failed to remove user: ' + error.message, 'error');
    }
}

// Toast notification helper
function showToast(message, type = 'info') {
    // Remove existing toast
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) existingToast.remove();
    
    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Add dependency
async function addDependency(taskId) {
    const select = document.getElementById('add-dependency-select');
    const dependsOnId = select?.value;
    if (!dependsOnId) {
        showToast('Please select a task first', 'warning');
        return;
    }
    
    try {
        await apiCall(`/tasks/${taskId}/dependencies/${dependsOnId}`, { method: 'POST' });
        showToast('Dependency added!', 'success');
        showTaskDetails(taskId);
        // Refresh graph if visible
        if (document.getElementById('graph-section')?.classList.contains('active')) {
            loadTaskGraph();
        }
    } catch (error) {
        showToast('Failed to add dependency: ' + error.message, 'error');
    }
}

// Remove dependency
async function removeDependency(taskId, dependsOnId) {
    if (!confirm('Remove this dependency?')) return;
    
    try {
        await apiCall(`/tasks/${taskId}/dependencies/${dependsOnId}`, { method: 'DELETE' });
        showToast('Dependency removed!', 'success');
        showTaskDetails(taskId);
        // Refresh graph if visible
        if (document.getElementById('graph-section')?.classList.contains('active')) {
            loadTaskGraph();
        }
    } catch (error) {
        showToast('Failed to remove dependency: ' + error.message, 'error');
    }
}

// Delete task
async function deleteTask(taskId, taskTitle) {
    if (!confirm(`Are you sure you want to delete "${taskTitle}"?\n\nThis action cannot be undone.`)) return;
    
    try {
        await apiCall(`/tasks/${taskId}`, { method: 'DELETE' });
        showToast('Task deleted!', 'success');
        closeTaskDetails();
        // Refresh the graph
        if (document.getElementById('graph-section')?.classList.contains('active')) {
            loadTaskGraph();
        }
    } catch (error) {
        showToast('Failed to delete task: ' + error.message, 'error');
    }
}

// Remove child task (sets child's parent to null)
async function removeChildTask(parentTaskId, childTaskId) {
    if (!confirm('Remove this task from children? (The child task will become a top-level task)')) return;
    
    try {
        // Update the child task to have no parent
        await apiCall(`/tasks/${childTaskId}`, {
            method: 'PATCH',
            body: JSON.stringify({ parent_id: "" })
        });
        showToast('Child removed!', 'success');
        showTaskDetails(parentTaskId);
        // Refresh graph if visible
        if (document.getElementById('graph-section')?.classList.contains('active')) {
            loadTaskGraph();
        }
    } catch (error) {
        showToast('Failed to remove child: ' + error.message, 'error');
    }
}

// Add child task (sets selected task's parent to current task)
async function addChildTask(parentTaskId) {
    const select = document.getElementById('add-child-select');
    const childTaskId = select?.value;
    if (!childTaskId) {
        showToast('Please select a task first', 'warning');
        return;
    }
    
    try {
        // Update the selected task to have current task as parent
        await apiCall(`/tasks/${childTaskId}`, {
            method: 'PATCH',
            body: JSON.stringify({ parent_id: parentTaskId })
        });
        showToast('Child added!', 'success');
        showTaskDetails(parentTaskId);
        // Refresh graph if visible
        if (document.getElementById('graph-section')?.classList.contains('active')) {
            loadTaskGraph();
        }
    } catch (error) {
        showToast('Failed to add child: ' + error.message, 'error');
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
        
        // Use allowed_values from attribute definition (system schema)
        // This ensures filter options always match what's defined in the system
        const values = attr.allowed_values || [];
        
        if (values.length === 0) return; // Skip if no allowed values defined
        
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
        
        values.forEach(val => {
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

function updateStateFilter() {
    const checkboxes = document.querySelectorAll('input[data-attr-name="state"]:checked');
    const button = document.getElementById('filter-btn-state');
    if (!button) return;
    
    const span = button.querySelector('span:first-child');
    
    if (checkboxes.length === 0) {
        span.textContent = 'All';
        button.classList.remove('has-selection');
    } else if (checkboxes.length === 1) {
        span.textContent = getStateLabel(checkboxes[0].value);
        button.classList.add('has-selection');
    } else {
        span.textContent = `${checkboxes.length} selected`;
        button.classList.add('has-selection');
    }
    
    applyFilters();
}

function getStateLabel(state) {
    const stateLabels = {
        'DRAFT': '📝 Draft',
        'ACTIVE': '✅ Active',
        'REJECTED': '❌ Rejected',
        'ARCHIVED': '📦 Archived'
    };
    return stateLabels[state] || state;
}

async function applyFilters() {
    // Owner filter (multi-select)
    const ownerCheckboxes = document.querySelectorAll('input[data-attr-name="owner"]:checked');
    if (ownerCheckboxes.length > 0) {
        graphFilters.owner = Array.from(ownerCheckboxes).map(cb => cb.value);
    } else {
        graphFilters.owner = null;
    }
    
    // Team filter - filter by actual team name from user data
    const teamFilter = document.getElementById('filter-team');
    const selectedTeam = teamFilter ? teamFilter.value : '';
    
    if (selectedTeam) {
        // Use cached org chart data or fetch if needed
        const users = window.orgChartUsers || [];
        if (users.length > 0) {
            // Get all users who belong to this team
            const teamMemberNames = users
                .filter(u => u.team === selectedTeam)
                .map(u => u.name);
            
            console.log(`Team '${selectedTeam}' members:`, teamMemberNames);
            if (teamMemberNames.length > 0) {
                graphFilters.owner = teamMemberNames;
            }
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
    
    // State filter (multi-select)
    const stateCheckboxes = document.querySelectorAll('input[data-attr-name="state"]:checked');
    if (stateCheckboxes.length > 0) {
        graphFilters.state = Array.from(stateCheckboxes).map(cb => cb.value);
    } else {
        graphFilters.state = null;
    }
    
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
    
    // Update state filter button
    updateStateFilter();
    
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
    
    // Filter by state (multi-select support)
    if (graphFilters.state && graphFilters.state.length > 0) {
        filteredTasks = filteredTasks.filter(t => {
            return t.state && graphFilters.state.includes(t.state);
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
        // Check for active Daily Sync session
        await checkDailySyncStatus();
        if (dailySyncActive) {
            console.log(`📅 Active Daily Sync session detected (phase: ${dailySyncPhase})`);
        }
        updateDailySyncButton();
        
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
    
    // Check for segments in metadata for rich/clickable rendering
    const segments = message.metadata?.segments;
    let contentHTML;
    
    if (segments && Array.isArray(segments) && segments.length > 0) {
        // Render segments with clickable task links
        contentHTML = `<p>${renderSegments(segments)}</p>`;
    } else {
        // Fallback to plain text rendering
        contentHTML = `<p>${escapeHtml(message.text).replace(/\n/g, '<br>')}</p>`;
    }
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div>
            <div class="message-content">
                ${contentHTML}
            </div>
            ${metadataHTML}
            <div class="message-timestamp">${formatTimestamp(message.created_at)}</div>
        </div>
    `;
    
    // Add click handler for Robin messages to show debug data
    if (message.sender === 'robin' && message.id) {
        messageDiv.style.cursor = 'pointer';
        messageDiv.title = 'Click to view debug data (prompt + response)';
        messageDiv.dataset.messageId = message.id;
        messageDiv.addEventListener('click', () => showMessageDebugData(message.id));
    }
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

/**
 * Render segments array into HTML with clickable task links.
 * Falls back to text display if segment parsing fails.
 */
function renderSegments(segments) {
    try {
        return segments.map(seg => {
            if (seg.type === 'text') {
                return escapeHtml(seg.text || '').replace(/\n/g, '<br>');
            } else if (seg.type === 'task_ref') {
                // Clickable task reference - opens task details popup
                return `<span class="task-link" onclick="event.stopPropagation(); showTaskDetails('${escapeHtml(seg.task_id)}')">${escapeHtml(seg.label || 'Task')}</span>`;
            } else if (seg.type === 'attribute_ref') {
                // Clickable attribute reference - opens small attribute edit popover
                const taskId = escapeHtml(seg.task_id || '');
                const attrName = escapeHtml(seg.attribute_name || '');
                return `<span class="attribute-link" onclick="event.stopPropagation(); showAttributeEditPopup('${taskId}', '${attrName}', event)">${escapeHtml(seg.label || 'Attribute')}</span>`;
            }
            return '';
        }).join('');
    } catch (error) {
        console.error('Error rendering segments:', error);
        return '';
    }
}

/**
 * Show a small popover to edit a specific attribute value for a task.
 * Positioned near the clicked element, doesn't block the rest of the screen.
 */
async function showAttributeEditPopup(taskId, attributeName, event) {
    // Remove any existing attribute popover
    const existing = document.getElementById('attr-edit-popover');
    if (existing) existing.remove();
    
    try {
        // Fetch task details and attribute definitions in parallel
        const [task, taskAttributes] = await Promise.all([
            apiCall(`/tasks/${taskId}/full-details`),
            apiCall('/task-attributes')
        ]);
        
        // Find the attribute definition
        const attrDef = taskAttributes.find(a => a.name === attributeName);
        const allowedValues = attrDef?.allowed_values || [];
        const displayName = attrDef?.label || attributeName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        
        // Find current value for this attribute (from current user's answers)
        let currentValue = '';
        // Check if we have answers in the task details
        if (task.answers_by_attribute && task.answers_by_attribute[attributeName]) {
            const answers = task.answers_by_attribute[attributeName].answers || [];
            const myAnswer = answers.find(a => a.user_id === currentUser?.id);
            if (myAnswer) {
                currentValue = myAnswer.value || '';
            }
        }
        
        // Calculate position near the click
        const clickX = event?.clientX || window.innerWidth / 2;
        const clickY = event?.clientY || window.innerHeight / 2;
        
        // Create popover
        const popover = document.createElement('div');
        popover.id = 'attr-edit-popover';
        popover.style.cssText = `
            position: fixed;
            left: ${Math.min(clickX + 10, window.innerWidth - 280)}px;
            top: ${Math.min(clickY - 20, window.innerHeight - 200)}px;
            background: var(--color-bg-secondary, #1e1e2e);
            border-radius: 10px;
            padding: 12px 14px;
            width: 250px;
            box-shadow: 0 6px 24px rgba(0,0,0,0.5);
            border: 1px solid var(--color-border, #333);
            z-index: 10000;
        `;
        
        // Build input HTML based on attribute type
        let inputHTML;
        if (allowedValues && allowedValues.length > 0) {
            // Dropdown for attributes with allowed values
            const optionsHTML = allowedValues.map(v => 
                `<option value="${escapeHtml(v)}" ${v === currentValue ? 'selected' : ''}>${escapeHtml(v)}</option>`
            ).join('');
            inputHTML = `
                <select id="attr-edit-value" style="width:100%;padding:8px;border:1px solid var(--color-border, #333);border-radius:6px;background:var(--color-bg-primary, #12121a);color:var(--color-text-primary, #e0e0e0);font-size:13px;box-sizing:border-box;">
                    <option value="">-- Select --</option>
                    ${optionsHTML}
                </select>
            `;
        } else {
            // Text input for free-form attributes
            inputHTML = `
                <input type="text" id="attr-edit-value" value="${escapeHtml(currentValue)}" 
                    style="width:100%;padding:8px;border:1px solid var(--color-border, #333);border-radius:6px;background:var(--color-bg-primary, #12121a);color:var(--color-text-primary, #e0e0e0);font-size:13px;box-sizing:border-box;"
                    placeholder="Enter value..."
                />
            `;
        }
        
        popover.innerHTML = `
            <div style="font-size:11px;color:var(--color-text-tertiary, #666);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escapeHtml(task.title || '')}">
                ${escapeHtml(task.title || 'Task')}
            </div>
            <div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--color-text-primary, #e0e0e0);">
                ${displayName}
            </div>
            ${inputHTML}
            <div style="display:flex;gap:6px;margin-top:10px;justify-content:flex-end;">
                <button id="attr-cancel-btn" style="padding:6px 12px;border:none;border-radius:5px;background:var(--color-bg-tertiary, #2a2a3a);color:var(--color-text-primary, #e0e0e0);cursor:pointer;font-size:12px;">Cancel</button>
                <button id="attr-save-btn" style="padding:6px 12px;border:none;border-radius:5px;background:var(--color-accent, #7c3aed);color:white;cursor:pointer;font-size:12px;font-weight:500;">Save</button>
            </div>
        `;
        
        document.body.appendChild(popover);
        
        // Focus input
        const input = document.getElementById('attr-edit-value');
        input.focus();
        if (input.tagName === 'INPUT') input.select();
        
        // Handle save
        const saveValue = async () => {
            const newValue = input.value.trim();
            if (!newValue) {
                showToast('Please select or enter a value', 'error');
                return;
            }
            try {
                await apiCall('/pending-questions/answer', {
                    method: 'POST',
                    body: JSON.stringify({
                        task_id: taskId,
                        target_user_id: task.owner_user_id || task.owner?.id,
                        attribute_name: attributeName,
                        value: newValue,
                        refused: false
                    })
                });
                showToast('Saved!', 'success');
                popover.remove();
            } catch (error) {
                showToast('Failed: ' + error.message, 'error');
            }
        };
        
        document.getElementById('attr-save-btn').onclick = saveValue;
        document.getElementById('attr-cancel-btn').onclick = () => popover.remove();
        
        // Close on Escape
        const escHandler = (e) => { 
            if (e.key === 'Escape') { 
                popover.remove(); 
                document.removeEventListener('keydown', escHandler); 
            } 
        };
        document.addEventListener('keydown', escHandler);
        
        // Submit on Enter (for text input)
        if (input.tagName === 'INPUT') {
            input.addEventListener('keydown', (e) => { if (e.key === 'Enter') saveValue(); });
        }
        
        // Close when clicking outside (after a small delay to avoid immediate close)
        setTimeout(() => {
            const outsideClickHandler = (e) => {
                if (!popover.contains(e.target)) {
                    popover.remove();
                    document.removeEventListener('click', outsideClickHandler);
                }
            };
            document.addEventListener('click', outsideClickHandler);
        }, 100);
        
    } catch (error) {
        console.error('Error loading attribute:', error);
        showToast('Failed to load: ' + error.message, 'error');
    }
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
        
        // Check if we're in Daily Sync mode (but allow "morning_brief" to bypass)
        if (dailySyncActive && text !== 'morning_brief') {
            console.log('📅 Routing to Daily Sync endpoint');
            hideTypingIndicator();
            await sendDailySyncMessage(text);
            sendBtn.disabled = false;
            sendBtn.classList.remove('loading');
            return;
        }
        
        // If "morning_brief" while in Daily Sync, end the session first
        if (dailySyncActive && text === 'morning_brief') {
            console.log('⚠️ Ending Daily Sync to trigger morning_brief');
            dailySyncActive = false;
            dailySyncSessionId = null;
            dailySyncPhase = null;
        }
        
        // Send to backend (normal chat)
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
            
            // Capture debug prompt and full response from Robin's message metadata
            if (msg.sender === 'robin' && msg.metadata) {
                if (msg.metadata.debug_prompt) {
                    lastRobinPrompt = msg.metadata.debug_prompt;
                    console.log('🐛 Debug prompt captured for last message');
                }
                if (msg.metadata.full_response) {
                    lastRobinResponse = msg.metadata.full_response;
                    console.log('📊 Full response captured for last message');
                }
            }
        });
        
        // Reload dashboard data if updates were applied
        const hasUpdates = data.messages.some(m => m.metadata && m.metadata.updates_applied);
        if (hasUpdates) {
            setTimeout(() => {
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
    // End any active Daily Sync first
    if (dailySyncActive) {
        console.log('⚠️ Ending Daily Sync to trigger morning brief');
        dailySyncActive = false;
        dailySyncSessionId = null;
        dailySyncPhase = null;
        updateDailySyncIndicator();
    }
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        const response = await fetch('/chat/brief', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': currentUser.id
            }
        });
        
        hideTypingIndicator();
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        // Add messages to UI
        for (const msg of data.messages) {
            appendMessageToUI(msg);
        }
        
        scrollToBottom();
    } catch (error) {
        hideTypingIndicator();
        console.error('Error getting morning brief:', error);
        appendMessageToUI({
            sender: 'robin',
            text: 'Sorry, I had trouble generating your morning brief. Please try again.',
            created_at: new Date().toISOString()
        });
    }
}

// ===== Daily Sync Functions =====
let dailySyncActive = false;
let dailySyncSessionId = null;
let dailySyncPhase = null;

async function checkDailySyncStatus() {
    try {
        const response = await fetch('/daily/status', {
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.has_active_session) {
                dailySyncActive = true;
                dailySyncSessionId = data.session_id;
                dailySyncPhase = data.phase;
                return true;
            }
        }
        
        dailySyncActive = false;
        dailySyncSessionId = null;
        dailySyncPhase = null;
        return false;
    } catch (error) {
        console.error('Error checking Daily Sync status:', error);
        return false;
    }
}

function updateDailySyncButton() {
    const btn = document.getElementById('daily-sync-btn');
    if (!btn) return;
    
    if (dailySyncActive) {
        btn.textContent = '🛑 Stop Daily';
        btn.style.background = 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)';
    } else {
        btn.textContent = '🌅 Start Daily';
        btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
    }
    
    updateDailySyncIndicator();
}

function updateDailySyncIndicator() {
    const indicator = document.getElementById('daily-sync-indicator');
    const phaseText = document.getElementById('daily-sync-phase-text');
    
    if (!indicator || !phaseText) return;
    
    if (dailySyncActive && dailySyncPhase) {
        // Show indicator with current phase
        indicator.style.display = 'block';
        
        // Format phase name nicely
        const phaseNames = {
            'opening_brief': '🌅 Opening Brief',
            'questions': '💬 Questions',
            'summary': '📝 Summary',
            'done': '✅ Complete'
        };
        
        const phaseName = phaseNames[dailySyncPhase] || dailySyncPhase;
        phaseText.textContent = `Daily Sync Mode: ${phaseName}`;
    } else {
        // Hide indicator
        indicator.style.display = 'none';
    }
}

async function toggleDailySync() {
    if (dailySyncActive) {
        // Stop Daily Sync - call backend to end session
        try {
            const response = await fetch('/daily/end', {
                method: 'POST',
                headers: {
                    'X-User-Id': currentUser.id
                }
            });
            
            if (!response.ok) {
                console.error('Failed to end Daily Sync session');
            }
        } catch (error) {
            console.error('Error ending Daily Sync:', error);
        }
        
        // Update frontend state
        dailySyncActive = false;
        dailySyncSessionId = null;
        dailySyncPhase = null;
        updateDailySyncButton();
        updateDailySyncIndicator();
        
        const container = document.getElementById('robin-messages');
        const systemMsg = document.createElement('div');
        systemMsg.className = 'chat-message system';
        systemMsg.innerHTML = `
            <div class="message-avatar">ℹ️</div>
            <div>
                <div class="message-content">
                    <p>Daily Sync ended. You can now use normal chat.</p>
                </div>
                <div class="message-timestamp">${formatTimestamp(new Date().toISOString())}</div>
            </div>
        `;
        container.appendChild(systemMsg);
        scrollToBottom();
    } else {
        // Start Daily Sync
        await startDailySync();
    }
}

async function startDailySync() {
    if (!currentUser) {
        alert('Please log in first');
        return;
    }
    
    try {
        // Check if already in progress
        const hasActive = await checkDailySyncStatus();
        if (hasActive) {
            alert(`Daily Sync already in progress (phase: ${dailySyncPhase})`);
            return;
        }
        
        // Update UI immediately (optimistic update)
        dailySyncActive = true;
        updateDailySyncButton();
        // Don't update indicator yet - we don't have the phase!
        
        // Show typing indicator while waiting for LLM
        showTypingIndicator();
        
        // Start new Daily Sync
        const response = await fetch('/daily/start', {
            method: 'POST',
            headers: {
                'X-User-Id': currentUser.id,
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const error = await response.json();
            // Hide typing indicator and revert button state on error
            hideTypingIndicator();
            dailySyncActive = false;
            updateDailySyncButton();
            updateDailySyncIndicator();
            alert(`Failed to start Daily Sync: ${error.detail || 'Unknown error'}`);
            return;
        }
        
        const data = await response.json();
        
        // Hide typing indicator before showing real messages
        hideTypingIndicator();
        
        // Update state with actual session data
        dailySyncSessionId = data.session_id;
        dailySyncPhase = data.phase;
        updateDailySyncIndicator();
        
        // Display messages
        for (const msg of data.messages) {
            appendMessageToUI(msg);
        }
        
        scrollToBottom();
        
        console.log('✅ Daily Sync started:', data);
    } catch (error) {
        console.error('Error starting Daily Sync:', error);
        // Hide typing indicator and revert button state on error
        hideTypingIndicator();
        dailySyncActive = false;
        updateDailySyncButton();
        updateDailySyncIndicator();
        alert('Failed to start Daily Sync. Check console for details.');
    }
}

async function sendDailySyncMessage(text) {
    try {
        // Show typing indicator while waiting for LLM
        showTypingIndicator();
        
        const response = await fetch('/daily/send', {
            method: 'POST',
            headers: {
                'X-User-Id': currentUser.id,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text })
        });
        
        if (!response.ok) {
            const error = await response.json();
            hideTypingIndicator();
            throw new Error(error.detail || 'Unknown error');
        }
        
        const data = await response.json();
        
        // Hide typing indicator before showing real messages
        hideTypingIndicator();
        
        // Update phase
        dailySyncPhase = data.phase;
        updateDailySyncIndicator();
        
        // If complete, deactivate
        if (data.is_complete) {
            dailySyncActive = false;
            dailySyncSessionId = null;
            dailySyncPhase = null;
            updateDailySyncButton();
            console.log('✅ Daily Sync completed');
        }
        
        // Display Robin's messages
        for (const msg of data.messages) {
            appendMessageToUI(msg);
        }
        
        scrollToBottom();
    } catch (error) {
        console.error('Error sending Daily Sync message:', error);
        hideTypingIndicator();
        appendMessageToUI({
            sender: 'system',
            text: `Error: ${error.message}`,
            created_at: new Date().toISOString()
        });
    }
}

function scrollToBottom() {
    const container = document.getElementById('robin-messages');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 100);
}

function formatTimestamp(isoString) {
    // Backend sends UTC timestamps without 'Z' suffix - add it for correct parsing
    const isoStringUTC = isoString.endsWith('Z') ? isoString : isoString + 'Z';
    const date = new Date(isoStringUTC);
    const now = new Date();
    
    // Calculate difference in milliseconds
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    
    // For older messages, show the actual date in local time
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
}

// Alias for formatTimestamp
function formatRelativeTime(isoString) {
    return formatTimestamp(isoString);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// Pending Questions Functions
// ============================================================================

async function loadPendingQuestions() {
    if (!currentUser || !currentUser.id) {
        console.error('No current user found');
        return;
    }
    
    // Populate owner dropdown
    await populateTaskOwnerDropdown();
    
    const container = document.getElementById('pending-questions-container');
    container.innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">Loading pending questions...</p>';
    
    try {
        const response = await fetch('/pending-questions', {
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to load pending questions');
        }
        
        const pending = await response.json();
        
        if (pending.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 60px 20px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                    <h3 style="color: #2c5f2d; margin-bottom: 8px;">All Caught Up!</h3>
                    <p style="color: #666;">You have no pending questions. All your task attributes are up to date.</p>
                </div>
            `;
            return;
        }
        
        // Group by reason
        const grouped = {
            missing: pending.filter(p => p.reason === 'missing'),
            stale: pending.filter(p => p.reason === 'stale'),
            misaligned: pending.filter(p => p.reason === 'misaligned')
        };
        
        let html = `
            <div style="margin-bottom: 20px; padding: 16px; background: #f8f9fa; border-radius: 8px;">
                <h4 style="margin: 0 0 8px 0; color: #333;">Summary</h4>
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <div style="padding: 8px 16px; background: #fff3cd; border-radius: 6px; border-left: 3px solid #ffc107;">
                        <strong>${grouped.missing.length}</strong> Missing
                    </div>
                    <div style="padding: 8px 16px; background: #cce5ff; border-radius: 6px; border-left: 3px solid #0066cc;">
                        <strong>${grouped.stale.length}</strong> Stale (>7 days)
                    </div>
                    <div style="padding: 8px 16px; background: #f8d7da; border-radius: 6px; border-left: 3px solid #dc3545;">
                        <strong>${grouped.misaligned.length}</strong> Misaligned
                    </div>
                </div>
            </div>
        `;
        
        // Display as a table with answer inputs
        html += `
            <div style="overflow-x: auto;">
                <table class="resizable-table" id="pending-questions-table">
                    <thead>
                        <tr>
                            <th class="col-priority resizable">#<span class="resize-handle" data-col="0"></span></th>
                            <th class="col-reason resizable">Reason<span class="resize-handle" data-col="1"></span></th>
                            <th class="col-task resizable">Task<span class="resize-handle" data-col="2"></span></th>
                            <th class="col-attribute resizable">Attribute<span class="resize-handle" data-col="3"></span></th>
                            <th class="col-answer resizable">Your Answer<span class="resize-handle" data-col="4"></span></th>
                            <th class="col-about resizable">About<span class="resize-handle" data-col="5"></span></th>
                            <th class="col-action">Action</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const p of pending) {
            const reasonColor = p.reason === 'missing' ? '#ffc107' : 
                              p.reason === 'stale' ? '#0066cc' : '#dc3545';
            const reasonBadge = `<span style="display: inline-block; padding: 4px 8px; background: ${reasonColor}; color: white; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">${p.reason.toUpperCase()}</span>`;
            
            // Create appropriate input based on attribute type
            let inputHtml = '';
            if (p.attribute_type === 'enum' && p.allowed_values) {
                const options = p.allowed_values.map(v => `<option value="${v}">${v}</option>`).join('');
                inputHtml = `<select id="input-${p.id}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;">
                    <option value="">Select...</option>
                    ${options}
                </select>`;
            } else if (p.attribute_type === 'bool') {
                inputHtml = `<select id="input-${p.id}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;">
                    <option value="">Select...</option>
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                </select>`;
            } else if (p.attribute_type === 'int' || p.attribute_type === 'float') {
                const step = p.attribute_type === 'float' ? '0.1' : '1';
                inputHtml = `<input type="number" id="input-${p.id}" step="${step}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;" placeholder="Enter number">`;
            } else {
                // String or other
                inputHtml = `<input type="text" id="input-${p.id}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;" placeholder="Type your answer">`;
            }
            
            // Make task title clickable if task_id exists
            const taskCell = p.task_id 
                ? `<span class="task-link" onclick="showTaskDetails('${p.task_id}')">${escapeHtml(p.task_title)}</span>`
                : 'User-level';
            
            html += `
                <tr id="row-${p.id}">
                    <td>#${p.priority}</td>
                    <td>${reasonBadge}</td>
                    <td class="task-cell">${taskCell}</td>
                    <td class="attr-cell">${p.attribute_label}</td>
                    <td>${inputHtml}</td>
                    <td class="secondary-text">${p.target_user_name}</td>
                    <td class="action-cell">
                        <button onclick="savePendingAnswer('${p.id}', '${p.task_id}', '${p.target_user_id}', '${p.attribute_name}')" class="table-action-btn primary">💾</button>
                        <button onclick="ignorePendingQuestion('${p.id}', '${p.task_id}', '${p.target_user_id}', '${p.attribute_name}')" class="table-action-btn danger" title="Ignore">🚫</button>
                    </td>
                </tr>
            `;
        }
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
        
        html += `
            <div style="margin-top: 24px; padding: 16px; background: #e7f3ff; border-radius: 8px; border-left: 4px solid #0066cc;">
                <h4 style="margin: 0 0 8px 0; color: #004085;">💡 Tip</h4>
                <p style="margin: 0; color: #004085; line-height: 1.6;">
                    Fill in your answers above and click <strong>💾 Save</strong> for each one. 
                    Or, go to <strong>🤖 Chat with Robin</strong> and type <code style="background: white; padding: 2px 6px; border-radius: 3px;">collect_data</code> 
                    to have Robin guide you through answering these questions conversationally.
                </p>
            </div>
        `;
        
        container.innerHTML = html;
        
        // Initialize resizable columns
        initResizableColumns('pending-questions-table');
        
    } catch (error) {
        console.error('Error loading pending questions:', error);
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #dc3545;">
                <div style="font-size: 48px; margin-bottom: 16px;">❌</div>
                <p>Failed to load pending questions. Please try again.</p>
                <button onclick="loadPendingQuestions()" class="primary-btn" style="margin-top: 16px;">Retry</button>
            </div>
        `;
    }
}

async function savePendingAnswer(pendingId, taskId, targetUserId, attributeName) {
    const input = document.getElementById(`input-${pendingId}`);
    const value = input.value.trim();
    
    if (!value) {
        alert('Please enter a value before saving');
        return;
    }
    
    try {
        // Call the direct answer API
        const response = await apiCall('/pending-questions/answer', {
            method: 'POST',
            body: JSON.stringify({
                task_id: taskId === 'null' ? null : taskId,
                target_user_id: targetUserId,
                attribute_name: attributeName,
                value: value,
                refused: false
            })
        });
        
        // Success! Just fade out the row - no refresh
        const row = document.getElementById(`row-${pendingId}`);
        if (row) {
            row.style.transition = 'all 0.4s ease-out';
            row.style.backgroundColor = '#d4edda';
            
            setTimeout(() => {
                row.style.opacity = '0';
                row.style.height = '0';
                row.style.padding = '0';
                row.style.overflow = 'hidden';
            }, 200);
            
            // Remove from DOM after animation
            setTimeout(() => {
                row.remove();
            }, 600);
        }
        
    } catch (error) {
        console.error('Error saving answer:', error);
        alert('Failed to save answer: ' + error.message);
    }
}

async function ignorePendingQuestion(pendingId, taskId, targetUserId, attributeName) {
    try {
        await apiCall('/pending-questions/ignore', {
            method: 'POST',
            body: JSON.stringify({
                task_id: taskId === 'null' ? null : taskId,
                target_user_id: targetUserId,
                attribute_name: attributeName
            })
        });
        
        // Fade out the row
        const row = document.getElementById(`row-${pendingId}`);
        if (row) {
            row.style.transition = 'all 0.4s ease-out';
            row.style.backgroundColor = '#f8d7da';
            
            setTimeout(() => {
                row.style.opacity = '0';
                row.style.height = '0';
                row.style.padding = '0';
                row.style.overflow = 'hidden';
            }, 200);
            
            setTimeout(() => {
                row.remove();
            }, 600);
        }
    } catch (error) {
        console.error('Error ignoring question:', error);
        alert('Failed to ignore question: ' + error.message);
    }
}

async function populateTaskOwnerDropdown() {
    try {
        // apiCall already returns parsed JSON
        const users = await apiCall('/users', {
            method: 'GET'
        });
        
        const dropdown = document.getElementById('quick-task-owner');
        
        if (dropdown) {
            // Set current user as default
            dropdown.innerHTML = users.map(u => {
                const isCurrentUser = currentUser && u.id === currentUser.id;
                const label = isCurrentUser ? `${u.name} (You)` : u.name;
                const selected = isCurrentUser ? 'selected' : '';
                return `<option value="${u.id}" ${selected}>${label}</option>`;
            }).join('');
        }
        
    } catch (error) {
        console.error('Error loading users for task owner dropdown:', error);
    }
}

// Toggle quick add expanded form
function toggleQuickAddExpand() {
    const expanded = document.getElementById('quick-add-expanded');
    const btn = document.getElementById('quick-add-expand-btn');
    if (expanded.style.display === 'none') {
        expanded.style.display = 'block';
        btn.textContent = '📝 Hide Fields';
        loadTasksForParentDropdown();
        loadUsersForRelevantDropdown();
    } else {
        expanded.style.display = 'none';
        btn.textContent = '📝 Show All Fields';
    }
}

// Load tasks for parent dropdown
async function loadTasksForParentDropdown() {
    try {
        const tasks = await apiCall('/tasks');
        const sel = document.getElementById('quick-task-parent');
        sel.innerHTML = '<option value="">No parent</option>';
        tasks.forEach(t => {
            sel.innerHTML += `<option value="${t.id}">${t.title}</option>`;
        });
    } catch (e) { console.error(e); }
}

// Load users for relevant users dropdown
async function loadUsersForRelevantDropdown() {
    try {
        const users = await apiCall('/users');
        const sel = document.getElementById('quick-task-relevant-users');
        sel.innerHTML = '';
        users.forEach(u => {
            sel.innerHTML += `<option value="${u.id}">${u.name}</option>`;
        });
    } catch (e) { console.error(e); }
}

async function quickAddTask() {
    const nameInput = document.getElementById('quick-task-name');
    const ownerSelect = document.getElementById('quick-task-owner');
    const taskName = nameInput.value.trim();
    const ownerId = ownerSelect.value;
    
    if (!taskName) { alert('Please enter a task name'); return; }
    if (!ownerId) { alert('Please select a task owner'); return; }
    
    // Optional fields
    const desc = document.getElementById('quick-task-description')?.value?.trim() || '';
    const parentId = document.getElementById('quick-task-parent')?.value || null;
    const priority = document.getElementById('quick-task-priority')?.value || null;
    const status = document.getElementById('quick-task-status')?.value || null;
    const deps = document.getElementById('quick-task-dependencies')?.value?.trim() || '';
    const resources = document.getElementById('quick-task-resources')?.value?.trim() || '';
    
    // Get selected relevant users
    const relevantUsersSelect = document.getElementById('quick-task-relevant-users');
    const relevantUserIds = relevantUsersSelect ? Array.from(relevantUsersSelect.selectedOptions).map(o => o.value) : [];
    
    try {
        const newTask = await apiCall('/tasks', {
            method: 'POST',
            body: JSON.stringify({ title: taskName, description: desc, owner_user_id: ownerId, parent_id: parentId })
        });
        
        // Save optional attributes
        const attrs = [];
        if (priority) attrs.push({a:'priority',v:priority});
        if (status) attrs.push({a:'status',v:status});
        if (deps) attrs.push({a:'dependency',v:deps});
        if (resources) attrs.push({a:'resources',v:resources});
        for (const at of attrs) {
            try {
                await apiCall('/pending-questions/answer', { method: 'POST',
                    body: JSON.stringify({ task_id: newTask.id, attribute_name: at.a, value: at.v, target_user_id: ownerId })
                });
            } catch(e) { console.log('attr save err:', e); }
        }
        
        // Add relevant users
        for (const userId of relevantUserIds) {
            try {
                await apiCall(`/tasks/${newTask.id}/relevant-users/${userId}`, { method: 'POST' });
            } catch(e) { console.log('relevant user err:', e); }
        }
        
        // Show success feedback
        nameInput.value = '';
        nameInput.style.borderColor = '#10b981';
        nameInput.style.background = '#d1fae5';
        nameInput.placeholder = `✅ Task "${taskName}" created!`;
        
        // Clear all extra fields
        ['quick-task-description','quick-task-parent','quick-task-priority','quick-task-status','quick-task-dependencies','quick-task-resources'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        // Clear relevant users multi-select
        const ruSel = document.getElementById('quick-task-relevant-users');
        if (ruSel) Array.from(ruSel.options).forEach(o => o.selected = false);
        
        // Reset after 2 seconds
        setTimeout(() => {
            nameInput.style.borderColor = '#e0e7ff';
            nameInput.style.background = 'white';
            nameInput.placeholder = 'Task name *';
        }, 2000);
        
        console.log('✅ Task created:', newTask);
        
    } catch (error) {
        console.error('Error creating task:', error);
        alert('Failed to create task: ' + error.message);
    }
}


// ============================================================================
// Debug Functions
// ============================================================================

let lastRobinPrompt = null;
let lastRobinResponse = null;

function showLastPrompt() {
    if (!lastRobinPrompt) {
        alert('No prompt available yet. Send a message to Robin first!');
        return;
    }
    
    const modal = document.getElementById('debug-prompt-modal');
    const content = document.getElementById('debug-prompt-content');
    
    // Format the prompt with syntax highlighting
    const formatted = JSON.stringify(lastRobinPrompt, null, 2);
    
    // Apply simple syntax highlighting
    const highlighted = formatted
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
            let cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-boolean';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return '<span class="' + cls + '">' + match + '</span>';
        });
    
    content.innerHTML = `<pre style="margin: 0;">${highlighted}</pre>`;
    
    modal.classList.remove('hidden');
}

function closeDebugPrompt() {
    document.getElementById('debug-prompt-modal').classList.add('hidden');
}

function showLastResponse() {
    if (!lastRobinResponse) {
        alert('No response available yet. Send a message to Robin first!');
        return;
    }
    
    const modal = document.getElementById('debug-prompt-modal');
    const content = document.getElementById('debug-prompt-content');
    
    // Format the response with syntax highlighting
    const formatted = JSON.stringify(lastRobinResponse, null, 2);
    
    // Apply simple syntax highlighting
    const highlighted = formatted
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
            let cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-boolean';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return '<span class="' + cls + '">' + match + '</span>';
        });
    
    content.innerHTML = `<pre style="margin: 0;">${highlighted}</pre>`;
    modal.classList.remove('hidden');
}

async function showMessageDebugData(messageId) {
    if (!currentUser || !currentUser.id) {
        alert('Please log in first');
        return;
    }
    
    try {
        const response = await fetch(`/chat/message/${messageId}/debug`, {
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            if (response.status === 404) {
                alert('No debug data available for this message');
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
            return;
        }
        
        const data = await response.json();
        const fullResponse = data.full_response || {};
        
        // Helper for syntax-highlighted JSON
        const prettyJson = (obj) => {
            const json = JSON.stringify(obj, null, 2);
            return json
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?)/g, (match) => {
                    if (/:$/.test(match)) {
                        return `<span class="json-key">${match}</span>`;
                    }
                    return `<span class="json-string">${match}</span>`;
                })
                .replace(/\b(true|false)\b/g, '<span class="json-boolean">$1</span>')
                .replace(/\bnull\b/g, '<span class="json-null">null</span>')
                .replace(/\b(-?\d+\.?\d*)\b/g, '<span class="json-number">$1</span>');
        };
        
        // Build compact debug view
        const mode = fullResponse.mode || 'N/A';
        const submode = fullResponse.submode || '—';
        const toolCalls = fullResponse.tool_calls_made || [];
        const updates = fullResponse.updates || [];
        const control = fullResponse.control || {};
        const prompt = data.full_prompt || [];
        const parsedResponse = fullResponse.parsed_response || {};
        const rawContent = fullResponse.raw_content || '';
        
        let html = `
        <div class="debug-header">
            <span class="debug-badge">${mode}</span>
            ${submode !== '—' ? `<span class="debug-badge secondary">${submode}</span>` : ''}
            <span class="debug-badge ${control.conversation_done ? 'done' : 'active'}">
                ${control.conversation_done ? '✓ Done' : '◉ Active'}
            </span>
            ${control.next_phase ? `<span class="debug-badge warning">→ ${control.next_phase}</span>` : ''}
        </div>
        
        <div class="debug-row">
            <span class="debug-label">🔧 Tools:</span>
            <span>${toolCalls.length > 0 ? toolCalls.map(t => `<code>${typeof t === 'object' ? t.name : t}</code>`).join(' ') : '<em>none</em>'}</span>
        </div>
        
        <div class="debug-row">
            <span class="debug-label">📝 Updates:</span>
            <span>${updates.length > 0 ? `${updates.length} update(s)` : '<em>none</em>'}</span>
        </div>`;
        
        // Tool calls detail (if any)
        if (toolCalls.length > 0 && typeof toolCalls[0] === 'object') {
            html += `<details class="debug-details"><summary>🔧 Tool Calls & Results (${toolCalls.length})</summary>
                <div class="tool-calls-container">`;
            for (const tc of toolCalls) {
                html += `<div class="tool-call-item">
                    <div class="tool-call-header"><code>${tc.name}</code></div>
                    <div class="tool-call-args"><strong>Args:</strong><pre class="debug-json-pretty">${prettyJson(tc.args || {})}</pre></div>
                    <div class="tool-call-result"><strong>Result:</strong><pre class="debug-json-pretty">${prettyJson(tc.result || {})}</pre></div>
                </div>`;
            }
            html += `</div></details>`;
        }
        
        // Updates detail (if any)
        if (updates.length > 0) {
            html += `<details class="debug-details"><summary>📝 Updates Applied</summary>
                <pre class="debug-json-pretty">${prettyJson(updates)}</pre></details>`;
        }
        
        // Prompt section
        html += `<details class="debug-details"><summary>📥 Prompt (${prompt.length} messages)</summary>
            <pre class="debug-json-pretty">${prettyJson(prompt)}</pre></details>`;
        
        // Response section
        html += `<details class="debug-details"><summary>📤 Response</summary>
            <pre class="debug-json-pretty">${prettyJson(parsedResponse)}</pre></details>`;
        
        // Raw output (if different/exists)
        if (rawContent && rawContent.length > 10) {
            let rawPretty = rawContent;
            try {
                // Try to parse and pretty-print if it's valid JSON
                const parsed = JSON.parse(rawContent);
                rawPretty = prettyJson(parsed);
            } catch (e) {
                // If not valid JSON, just escape it
                rawPretty = escapeHtml(rawContent);
            }
            html += `<details class="debug-details"><summary>📄 Raw Output</summary>
                <pre class="debug-json-pretty">${rawPretty}</pre></details>`;
        }
        
        html += `<div class="debug-footer">⏰ ${data.created_at}</div>`;
        
        const modal = document.getElementById('debug-prompt-modal');
        const content = document.getElementById('debug-prompt-content');
        content.innerHTML = html;
        modal.classList.remove('hidden');
        
    } catch (error) {
        console.error('Error fetching debug data:', error);
        alert('Failed to load debug data: ' + error.message);
    }
}

// ============================================================================
// Initialization
// ============================================================================

window.addEventListener('DOMContentLoaded', () => {
    if (loadUser()) {
        showDashboard();
    } else {
        showPage('auth-page');
    }
});


// ============================================================================
// Prompt Editor Functions
// ============================================================================

let currentPrompts = {};
let promptVersionHistory = {};

async function loadPrompts() {
    console.log('loadPrompts() called');
    
    try {
        if (!currentUser || !currentUser.id) {
            console.error('No user logged in');
            return;
        }
        
        console.log('Fetching prompts from API...');
        const response = await fetch('/prompts/', {
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const prompts = await response.json();
        console.log('Received prompts:', prompts.length);
        
        // Store prompts by mode (new simplified structure)
        currentPrompts = {};
        prompts.forEach(p => {
            // Store by mode only (no more has_pending distinction)
            if (!currentPrompts[p.mode] || p.version > currentPrompts[p.mode].version) {
                currentPrompts[p.mode] = p;
                console.log(`Stored prompt: ${p.mode} v${p.version}`);
            }
        });
        
        console.log('All prompts stored:', Object.keys(currentPrompts));
        
        // Load the selected prompt
        await loadPromptForMode();
        
        console.log('Prompts loaded successfully!');
        
    } catch (error) {
        console.error('Error loading prompts:', error);
        showPromptStatus('Failed to load prompts: ' + error.message, 'error');
        
        const promptText = document.getElementById('prompt-text');
        if (promptText) {
            promptText.value = `Error loading prompts: ${error.message}\n\nPlease check the browser console for details.`;
        }
    }
}

async function loadPromptForMode() {
    const select = document.getElementById('prompt-mode-select');
    const mode = select.value;
    
    console.log(`Loading prompt for mode: ${mode}`);
    
    const prompt = currentPrompts[mode];
    const promptTextEl = document.getElementById('prompt-text');
    const versionInfo = document.getElementById('prompt-version-info');
    const preview = document.getElementById('prompt-preview');
    
    if (prompt) {
        promptTextEl.value = prompt.prompt_text || '';
        versionInfo.textContent = `Version ${prompt.version} | ${prompt.notes || 'No notes'}`;
        
        // Update preview
        if (preview) {
            preview.innerHTML = `<span style="color: #9cdcfe;">${escapeHtml(prompt.prompt_text || '')}</span>`;
        }
    } else {
        promptTextEl.value = `No prompt found for mode: ${mode}\n\nRun seed_mcp_prompts.py to create initial prompts.`;
        versionInfo.textContent = 'No prompt loaded';
    }
    
    // Load version history
    await loadVersionHistory(mode);
}

// Event listeners are now set up via onchange in HTML

// loadSelectedPrompt is now replaced by loadPromptForMode

async function loadVersionHistory(mode) {
    try {
        // Use false for has_pending since it's not used in MCP architecture
        const response = await fetch(`/prompts/history/${mode}/false`, {
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const versions = await response.json();
        promptVersionHistory[mode] = versions;
        
        // Populate version dropdown
        const versionSelect = document.getElementById('prompt-version-select');
        if (versionSelect) {
            versionSelect.innerHTML = versions.map(v => {
                const label = v.is_active 
                    ? `v${v.version} (Active) - ${v.notes || 'No description'}` 
                    : `v${v.version} - ${v.notes || 'No description'}`;
                return `<option value="${v.id}">${label}</option>`;
            }).join('');
        }
        
    } catch (error) {
        console.error('Error loading version history:', error);
    }
}

function populatePromptForm(prompt) {
    // Populate prompt text
    const promptTextArea = document.getElementById('prompt-text');
    if (promptTextArea) {
        promptTextArea.value = prompt.prompt_text || '';
    }
    
    // Clear notes and show version
    const notesField = document.getElementById('prompt-notes');
    if (notesField) notesField.value = '';
    
    const versionInfo = document.getElementById('prompt-version-info');
    if (versionInfo) {
        const createdDate = new Date(prompt.created_at).toLocaleDateString();
        const activeStatus = prompt.is_active ? '🟢 Active' : '⚪ Inactive';
        versionInfo.textContent = `Version ${prompt.version} | ${activeStatus} | Created: ${createdDate} | By: ${prompt.created_by || 'System'}`;
    }
    
    // Update preview
    const preview = document.getElementById('prompt-preview');
    if (preview) {
        preview.innerHTML = `<span style="color: #9cdcfe;">${escapeHtml(prompt.prompt_text || '')}</span>`;
    }
}

async function loadPromptVersion() {
    const versionSelect = document.getElementById('prompt-version-select');
    const promptId = versionSelect.value;
    
    const select = document.getElementById('prompt-mode-select');
    const key = select.value;
    const versions = promptVersionHistory[key] || [];
    
    const selectedVersion = versions.find(v => v.id === promptId);
    
    if (selectedVersion) {
        populatePromptForm(selectedVersion);
    }
}

async function savePrompt() {
    const select = document.getElementById('prompt-mode-select');
    const mode = select.value;
    
    const promptTextEl = document.getElementById('prompt-text');
    const promptText = promptTextEl ? promptTextEl.value : '';
    const notes = document.getElementById('prompt-notes').value;
    
    console.log('💾 Saving prompt...');
    console.log('Mode:', mode);
    console.log('Prompt text length:', promptText.length);
    console.log('Notes:', notes);
    
    if (!promptText.trim()) {
        showPromptStatus('❌ Prompt text cannot be empty', 'error');
        return;
    }
    
    if (!notes.trim()) {
        showPromptStatus('❌ Commit message is required', 'error');
        return;
    }
    
    try {
        const payload = {
            mode: mode,
            has_pending: false,  // Not used in MCP architecture
            prompt_text: promptText,
            context_config: {},  // Not used in MCP architecture
            created_by: currentUser.name,
            notes: notes || null
        };
        
        console.log('📤 Sending payload:', JSON.stringify(payload).substring(0, 200) + '...');
        
        const response = await fetch('/prompts/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': currentUser.id
            },
            body: JSON.stringify(payload)
        });
        
        console.log('📥 Response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ Server error:', errorText);
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const newPrompt = await response.json();
        console.log('✅ Saved successfully! New version:', newPrompt.version);
        
        showPromptStatus(`✅ Saved! New version ${newPrompt.version} is now active.`, 'success');
        
        // Reload prompts
        await loadPrompts();
        
    } catch (error) {
        console.error('❌ Error saving prompt:', error);
        showPromptStatus('Failed to save prompt: ' + error.message, 'error');
    }
}

function showPromptStatus(message, type) {
    const statusDiv = document.getElementById('prompt-save-status');
    statusDiv.textContent = message;
    statusDiv.style.display = 'block';
    statusDiv.style.backgroundColor = type === 'success' ? '#d4edda' : '#f8d7da';
    statusDiv.style.color = type === 'success' ? '#155724' : '#721c24';
    statusDiv.style.border = `1px solid ${type === 'success' ? '#c3e6cb' : '#f5c6cb'}`;
    
    // Hide after 5 seconds
    setTimeout(() => {
        statusDiv.style.display = 'none';
    }, 5000);
}

async function activateSelectedVersion() {
    const versionSelect = document.getElementById('prompt-version-select');
    const promptId = versionSelect.value;
    
    if (!promptId) {
        showPromptStatus('❌ No version selected', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/prompts/${promptId}/activate`, {
            method: 'POST',
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        showPromptStatus(`✅ ${result.message}`, 'success');
        
        // Reload to refresh active status
        await loadPrompts();
        
    } catch (error) {
        console.error('Error activating version:', error);
        showPromptStatus('❌ Failed to activate version: ' + error.message, 'error');
    }
}

async function updatePromptPreview() {
    const promptText = document.getElementById('prompt-text')?.value || '';
    const previewDiv = document.getElementById('prompt-preview');
    const modeSelect = document.getElementById('prompt-mode-select');
    
    if (!previewDiv || !modeSelect || !currentUser) return;
    
    // Show loading
    previewDiv.innerHTML = '<span style="color: #888;">Loading preview...</span>';
    
    const key = modeSelect.value;
    // Split on the LAST underscore to handle modes like "morning_brief"
    const lastUnderscore = key.lastIndexOf('_');
    const mode = key.substring(0, lastUnderscore);
    const hasPendingStr = key.substring(lastUnderscore + 1);
    const hasPending = hasPendingStr === 'true';
    
    // Build context config from form
    const contextConfig = {
        history_size: parseInt(document.getElementById('ctx-history-size')?.value) || 2,
        include_personal_tasks: document.getElementById('ctx-include-personal-tasks')?.checked || false,
        include_manager_tasks: document.getElementById('ctx-include-manager-tasks')?.checked || false,
        include_employee_tasks: document.getElementById('ctx-include-employee-tasks')?.checked || false,
        include_aligned_tasks: document.getElementById('ctx-include-aligned-tasks')?.checked || false,
        include_all_org_tasks: document.getElementById('ctx-include-all-org-tasks')?.checked || false,
        include_user_info: true,
        include_manager: true,
        include_employees: document.getElementById('ctx-include-employees')?.checked || false,
        include_aligned_users: document.getElementById('ctx-include-aligned-users')?.checked || false,
        include_all_users: document.getElementById('ctx-include-all-users')?.checked || false,
        include_pending: document.getElementById('ctx-include-pending')?.checked || false
    };
    
    try {
        const response = await fetch('/prompts/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': currentUser.id
            },
            body: JSON.stringify({
                mode: mode,
                has_pending: hasPending,
                prompt_text: promptText,
                context_config: contextConfig
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format exactly like the debug prompt - as JSON with syntax highlighting
        const formatted = JSON.stringify(data.full_prompt, null, 2);
        
        // Apply syntax highlighting (same as showLastPrompt)
        const highlighted = formatted
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
                let cls = 'json-number';
                if (/^"/.test(match)) {
                    if (/:$/.test(match)) {
                        cls = 'json-key';
                    } else {
                        cls = 'json-string';
                    }
                } else if (/true|false/.test(match)) {
                    cls = 'json-boolean';
                } else if (/null/.test(match)) {
                    cls = 'json-null';
                }
                return '<span class="' + cls + '">' + match + '</span>';
            });
        
        previewDiv.innerHTML = `<pre style="margin: 0;">${highlighted}</pre>`;
        
    } catch (error) {
        console.error('Error updating preview:', error);
        previewDiv.innerHTML = `<span style="color: #f48771;">Error loading preview: ${error.message}</span>`;
    }
}


// ============================================================================
// Import/Export Functions
// ============================================================================

async function exportData() {
    if (!currentUser || !currentUser.id) {
        showImportExportStatus('❌ Please log in to export data', 'error');
        return;
    }
    
    try {
        showImportExportStatus('📊 Generating export file...', 'info');
        
        const response = await fetch('/import-export/export', {
            method: 'GET',
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            throw new Error(`Export failed: ${response.statusText}`);
        }
        
        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `orgos_data_export_${new Date().toISOString().slice(0,10)}.xlsx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showImportExportStatus('✅ Export successful! File downloaded.', 'success');
        
    } catch (error) {
        console.error('Export error:', error);
        showImportExportStatus('❌ Export failed: ' + error.message, 'error');
    }
}

async function exportTemplate() {
    if (!currentUser || !currentUser.id) {
        showImportExportStatus('❌ Please log in to download template', 'error');
        return;
    }
    
    try {
        showImportExportStatus('📋 Generating template file...', 'info');
        
        const response = await fetch('/import-export/template', {
            method: 'GET',
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            throw new Error(`Template export failed: ${response.statusText}`);
        }
        
        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'orgos_import_template.xlsx';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showImportExportStatus('✅ Template downloaded! Fill it in and import.', 'success');
        
    } catch (error) {
        console.error('Template export error:', error);
        showImportExportStatus('❌ Template export failed: ' + error.message, 'error');
    }
}

async function handleImportFile(replaceMode) {
    if (!currentUser || !currentUser.id) {
        showImportExportStatus('❌ Please log in to import data', 'error');
        return;
    }
    
    const fileInput = replaceMode ? document.getElementById('import-replace-file') : document.getElementById('import-file');
    const file = fileInput.files[0];
    
    if (!file) {
        showImportExportStatus('❌ No file selected', 'error');
        return;
    }
    
    // Show confirmation for replace mode
    if (replaceMode) {
        const confirmed = confirm(
            '⚠️ REPLACE MODE WARNING ⚠️\n\n' +
            'This will DELETE all existing users, tasks, and their data!\n\n' +
            'Prompts will be kept, but new prompts from the file will be added as latest versions.\n\n' +
            'Are you ABSOLUTELY SURE you want to continue?'
        );
        
        if (!confirmed) {
            fileInput.value = '';  // Clear selection
            return;
        }
    }
    
    try {
        const mode = replaceMode ? 'REPLACE' : 'APPEND';
        showImportExportStatus(`📥 Importing data (${mode} mode)...`, 'info');
        
        const formData = new FormData();
        formData.append('file', file);
        
        const endpoint = replaceMode ? '/import-export/import-replace' : '/import-export/import';
        
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'X-User-Id': currentUser.id
            },
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            // Show validation errors
            if (result.detail && result.detail.errors) {
                const errorList = result.detail.errors.map(e => `  • ${e}`).join('\n');
                showImportExportStatus(
                    `❌ Import Failed - File Format Errors:\n\n${errorList}\n\nPlease fix these errors and try again.`,
                    'error'
                );
            } else {
                throw new Error(result.detail || 'Import failed');
            }
        } else {
            // Success!
            let message = `✅ ${result.message}\n\n`;
            message += '📊 Statistics:\n';
            message += `  • Users imported: ${result.stats.users_imported}`;
            if (result.stats.users_skipped > 0) message += ` (${result.stats.users_skipped} skipped)`;
            message += '\n';
            message += `  • Tasks imported: ${result.stats.tasks_imported}`;
            if (result.stats.tasks_skipped > 0) message += ` (${result.stats.tasks_skipped} skipped)`;
            message += '\n';
            message += `  • Dependencies: ${result.stats.dependencies_imported}\n`;
            message += `  • Prompts: ${result.stats.prompts_imported}\n`;
            message += `  • Attributes: ${result.stats.attributes_imported || 0}`;
            if (result.stats.attributes_skipped > 0) message += ` (${result.stats.attributes_skipped} skipped)`;
            message += '\n';
            message += `  • Perception Data: ${result.stats.perception_imported || 0}`;
            if (result.stats.perception_skipped > 0) message += ` (${result.stats.perception_skipped} skipped)`;
            message += '\n';
            message += '\nℹ️ Similarity scores will be calculated automatically when viewed.\n';
            
            if (result.warnings && result.warnings.length > 0) {
                message += '\n⚠️ Warnings:\n';
                message += result.warnings.map(w => `  • ${w}`).join('\n');
            }
            
            showImportExportStatus(message, 'success');
            
            // Reload the page after a short delay to show new data
            setTimeout(() => {
                window.location.reload();
            }, 3000);
        }
        
        // Clear file input
        fileInput.value = '';
        
    } catch (error) {
        console.error('Import error:', error);
        showImportExportStatus('❌ Import failed: ' + error.message, 'error');
        fileInput.value = '';
    }
}

function confirmReplace() {
    if (!currentUser || !currentUser.id) {
        showImportExportStatus('❌ Please log in to import data', 'error');
        return;
    }
    
    const confirmed = confirm(
        '⚠️ REPLACE MODE ⚠️\n\n' +
        'You are about to use REPLACE mode.\n\n' +
        'This will DELETE ALL existing:\n' +
        '  • Users\n' +
        '  • Tasks\n' +
        '  • Answers\n' +
        '  • Alignments\n\n' +
        'And replace them with data from your file.\n\n' +
        'Prompts will be kept (new prompts are added).\n\n' +
        'Do you want to continue?'
    );
    
    if (confirmed) {
        document.getElementById('import-replace-file').click();
    }
}

function showImportExportStatus(message, type) {
    const statusDiv = document.getElementById('import-export-status');
    statusDiv.textContent = message;
    statusDiv.style.display = 'block';
    statusDiv.style.whiteSpace = 'pre-wrap';
    statusDiv.style.fontFamily = 'monospace';
    
    if (type === 'success') {
        statusDiv.style.backgroundColor = '#d4edda';
        statusDiv.style.color = '#155724';
        statusDiv.style.border = '2px solid #c3e6cb';
    } else if (type === 'error') {
        statusDiv.style.backgroundColor = '#f8d7da';
        statusDiv.style.color = '#721c24';
        statusDiv.style.border = '2px solid #f5c6cb';
    } else {
        statusDiv.style.backgroundColor = '#d1ecf1';
        statusDiv.style.color = '#0c5460';
        statusDiv.style.border = '2px solid #bee5eb';
    }
    
    // Auto-hide after 10 seconds for success/info
    if (type !== 'error') {
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 10000);
    }
}

// ============================================================================
// MCP Tools Debugger
// ============================================================================

let mcpToolsCache = [];
let mcpLastResult = null;

async function loadMcpTools() {
    try {
        const tools = await apiCall('/mcp-tools/list');
        mcpToolsCache = tools;
        
        const select = document.getElementById('mcp-tool-select');
        if (!select) return;
        
        // Clear existing options except the first one
        select.innerHTML = '<option value="">-- Choose a tool --</option>';
        
        // Group tools by category (based on name prefix)
        const categories = {
            'Context': [],
            'Org/People': [],
            'Tasks': [],
            'Alignment': [],
            'Data Collection': [],
            'Other': []
        };
        
        tools.forEach(tool => {
            if (tool.name.includes('context') || tool.name.includes('questions')) {
                categories['Context'].push(tool);
            } else if (tool.name.includes('org') || tool.name.includes('user') || tool.name.includes('neighbor')) {
                categories['Org/People'].push(tool);
            } else if (tool.name.includes('task')) {
                categories['Tasks'].push(tool);
            } else if (tool.name.includes('alignment') || tool.name.includes('hotspot')) {
                categories['Alignment'].push(tool);
            } else if (tool.name.includes('attribute') || tool.name.includes('upsert') || tool.name.includes('record')) {
                categories['Data Collection'].push(tool);
            } else {
                categories['Other'].push(tool);
            }
        });
        
        // Add grouped options
        for (const [category, catTools] of Object.entries(categories)) {
            if (catTools.length > 0) {
                const optgroup = document.createElement('optgroup');
                optgroup.label = category;
                catTools.forEach(tool => {
                    const option = document.createElement('option');
                    option.value = tool.name;
                    option.textContent = tool.name;
                    optgroup.appendChild(option);
                });
                select.appendChild(optgroup);
            }
        }
        
    } catch (error) {
        console.error('Error loading MCP tools:', error);
    }
}

function onMcpToolSelect() {
    const select = document.getElementById('mcp-tool-select');
    const toolName = select.value;
    const descDiv = document.getElementById('mcp-tool-description');
    const paramsDiv = document.getElementById('mcp-tool-params');
    const executeBtn = document.getElementById('mcp-execute-btn');
    
    if (!toolName) {
        descDiv.style.display = 'none';
        paramsDiv.innerHTML = '';
        executeBtn.disabled = true;
        return;
    }
    
    const tool = mcpToolsCache.find(t => t.name === toolName);
    if (!tool) return;
    
    // Show description
    descDiv.textContent = tool.description;
    descDiv.style.display = 'block';
    
    // Build parameter inputs
    const params = tool.parameters;
    const properties = params.properties || {};
    const required = params.required || [];
    
    let html = '';
    
    if (Object.keys(properties).length === 0) {
        html = '<p style="color: #888; font-size: 13px;">This tool requires no parameters.</p>';
    } else {
        html = '<div style="display: flex; flex-direction: column; gap: 12px;">';
        
        for (const [name, prop] of Object.entries(properties)) {
            const isRequired = required.includes(name);
            const type = prop.type;
            const desc = prop.description || '';
            const enumValues = prop.enum;
            
            html += `
                <div class="mcp-param">
                    <label style="display: block; font-weight: 500; margin-bottom: 4px; font-size: 13px;">
                        ${name}${isRequired ? ' <span style="color: #ef4444;">*</span>' : ''}
                        <span style="color: #888; font-weight: normal; font-size: 11px;">(${type})</span>
                    </label>
            `;
            
            if (enumValues) {
                html += `<select id="mcp-param-${name}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px;">
                    <option value="">-- Select --</option>
                    ${enumValues.map(v => `<option value="${v}">${v}</option>`).join('')}
                </select>`;
            } else if (type === 'boolean') {
                html += `<select id="mcp-param-${name}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px;">
                    <option value="">-- Select --</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                </select>`;
            } else if (type === 'integer') {
                html += `<input type="number" id="mcp-param-${name}" placeholder="${desc}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; box-sizing: border-box;">`;
            } else {
                // Default to text input, but check if it might be a user_id
                const placeholder = name.includes('user_id') ? 'Enter user UUID or leave blank for current user' : desc;
                html += `<input type="text" id="mcp-param-${name}" placeholder="${placeholder}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; box-sizing: border-box;">`;
            }
            
            if (desc && !enumValues) {
                html += `<small style="color: #888; font-size: 11px; display: block; margin-top: 2px;">${desc}</small>`;
            }
            
            html += '</div>';
        }
        
        html += '</div>';
    }
    
    paramsDiv.innerHTML = html;
    executeBtn.disabled = false;
}

async function executeMcpTool() {
    const select = document.getElementById('mcp-tool-select');
    const toolName = select.value;
    const resultDiv = document.getElementById('mcp-result');
    
    if (!toolName) return;
    
    const tool = mcpToolsCache.find(t => t.name === toolName);
    if (!tool) return;
    
    // Gather parameter values
    const args = {};
    const properties = tool.parameters.properties || {};
    
    for (const name of Object.keys(properties)) {
        const input = document.getElementById(`mcp-param-${name}`);
        if (input && input.value) {
            let value = input.value;
            
            // Convert types
            if (properties[name].type === 'integer') {
                value = parseInt(value, 10);
            } else if (properties[name].type === 'boolean') {
                value = value === 'true';
            }
            
            args[name] = value;
        }
    }
    
    // Auto-fill user_id with current user if needed and not provided
    if (properties.user_id && !args.user_id && currentUser) {
        args.user_id = currentUser.id;
    }
    
    // Show loading state
    resultDiv.innerHTML = '<span style="color: #f0a;">⏳ Executing...</span>';
    
    try {
        const startTime = performance.now();
        
        const response = await apiCall('/mcp-tools/execute', {
            method: 'POST',
            body: JSON.stringify({
                tool_name: toolName,
                args: args
            })
        });
        
        const duration = (performance.now() - startTime).toFixed(0);
        
        mcpLastResult = response;
        
        // Format the result with syntax highlighting
        resultDiv.innerHTML = formatMcpResult(response, toolName, args, duration);
        
    } catch (error) {
        resultDiv.innerHTML = `<span style="color: #f55;">❌ Error: ${error.message}</span>`;
    }
}

function formatMcpResult(response, toolName, args, duration) {
    const success = response.success;
    const result = response.result || response.error;
    
    let html = `
        <div style="margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #444;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: ${success ? '#4ade80' : '#f87171'}; font-weight: 600;">
                    ${success ? '✅ Success' : '❌ Error'}
                </span>
                <span style="color: #888; font-size: 12px;">⏱️ ${duration}ms</span>
            </div>
            <div style="color: #60a5fa; font-size: 14px; margin-top: 8px;">
                🔧 ${toolName}
            </div>
            ${Object.keys(args).length > 0 ? `
                <div style="color: #888; font-size: 12px; margin-top: 4px;">
                    Args: ${JSON.stringify(args)}
                </div>
            ` : ''}
        </div>
    `;
    
    // Pretty print the result
    html += syntaxHighlightJson(result);
    
    return html;
}

function syntaxHighlightJson(obj, indent = 0) {
    if (obj === null) return '<span style="color: #f97316;">null</span>';
    if (obj === undefined) return '<span style="color: #888;">undefined</span>';
    
    const type = typeof obj;
    
    if (type === 'string') {
        // Escape HTML and add quotes
        const escaped = obj.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return `<span style="color: #a5d6ff;">"${escaped}"</span>`;
    }
    if (type === 'number') {
        return `<span style="color: #79c0ff;">${obj}</span>`;
    }
    if (type === 'boolean') {
        return `<span style="color: #ff7b72;">${obj}</span>`;
    }
    if (Array.isArray(obj)) {
        if (obj.length === 0) return '<span style="color: #888;">[]</span>';
        
        const items = obj.map((item, i) => {
            const prefix = '  '.repeat(indent + 1);
            return prefix + syntaxHighlightJson(item, indent + 1);
        });
        
        return `<span style="color: #888;">[</span>\n${items.join(',\n')}\n${'  '.repeat(indent)}<span style="color: #888;">]</span>`;
    }
    if (type === 'object') {
        const keys = Object.keys(obj);
        if (keys.length === 0) return '<span style="color: #888;">{}</span>';
        
        const items = keys.map(key => {
            const prefix = '  '.repeat(indent + 1);
            const value = syntaxHighlightJson(obj[key], indent + 1);
            return `${prefix}<span style="color: #7ee787;">"${key}"</span>: ${value}`;
        });
        
        return `<span style="color: #888;">{</span>\n${items.join(',\n')}\n${'  '.repeat(indent)}<span style="color: #888;">}</span>`;
    }
    
    return String(obj);
}

function quickMcpTool(toolName) {
    const select = document.getElementById('mcp-tool-select');
    if (select) {
        select.value = toolName;
        onMcpToolSelect();
        executeMcpTool();
    }
}

function copyMcpResult() {
    if (mcpLastResult) {
        const text = JSON.stringify(mcpLastResult, null, 2);
        navigator.clipboard.writeText(text).then(() => {
            alert('Copied to clipboard!');
        }).catch(err => {
            console.error('Failed to copy:', err);
        });
    }
}

function clearMcpResult() {
    const resultDiv = document.getElementById('mcp-result');
    if (resultDiv) {
        resultDiv.innerHTML = '<span style="color: #888;">Select a tool and click Execute to see results...</span>';
    }
    mcpLastResult = null;
}


// ============================================================================
// Pending Decisions Section
// ============================================================================

async function loadPendingDecisions() {
    const container = document.getElementById('decisions-container');
    const badge = document.getElementById('decisions-badge');
    
    container.innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">Loading pending decisions...</p>';
    
    try {
        const data = await apiCall('/decisions/pending');
        const decisions = data.decisions || [];
        
        // Update badge
        if (badge) {
            badge.textContent = decisions.length;
            badge.style.display = decisions.length > 0 ? 'inline-block' : 'none';
        }
        
        if (decisions.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 60px 20px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                    <h3 style="color: #2c5f2d; margin-bottom: 8px;">All Caught Up!</h3>
                    <p style="color: #666;">No pending decisions require your attention.</p>
                </div>
            `;
            return;
        }
        
        // Group by type
        const grouped = {
            task: decisions.filter(d => d.type === 'TASK_ACCEPTANCE'),
            merge: decisions.filter(d => d.type === 'MERGE_CONSENT'),
            dependency: decisions.filter(d => d.type === 'DEPENDENCY_ACCEPTANCE'),
            alternative: decisions.filter(d => d.type === 'ALTERNATIVE_DEP_ACCEPTANCE')
        };
        
        let html = `
            <div style="margin-bottom: 20px; padding: 16px; background: #f8f9fa; border-radius: 8px;">
                <h4 style="margin: 0 0 8px 0; color: #333;">Summary</h4>
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <div style="padding: 8px 16px; background: #e0f2fe; border-radius: 6px; border-left: 3px solid #0284c7;">
                        <strong>${grouped.task.length}</strong> Tasks
                    </div>
                    <div style="padding: 8px 16px; background: #ede9fe; border-radius: 6px; border-left: 3px solid #7c3aed;">
                        <strong>${grouped.merge.length}</strong> Merges
                    </div>
                    <div style="padding: 8px 16px; background: #fef3c7; border-radius: 6px; border-left: 3px solid #d97706;">
                        <strong>${grouped.dependency.length}</strong> Dependencies
                    </div>
                    <div style="padding: 8px 16px; background: #fce7f3; border-radius: 6px; border-left: 3px solid #db2777;">
                        <strong>${grouped.alternative.length}</strong> Alternatives
                    </div>
                </div>
            </div>
        `;
        
        // Display as compact table
        html += `
            <div style="overflow-x: auto;">
                <table class="resizable-table" id="pending-decisions-table">
                    <thead>
                        <tr>
                            <th class="col-type resizable" style="width: 100px;">Type<span class="resize-handle" data-col="0"></span></th>
                            <th class="col-desc resizable" style="width: 280px;">Description<span class="resize-handle" data-col="1"></span></th>
                            <th class="col-from resizable" style="width: 100px;">From<span class="resize-handle" data-col="2"></span></th>
                            <th class="col-time resizable" style="width: 100px;">Time<span class="resize-handle" data-col="3"></span></th>
                            <th class="col-actions" style="width: 150px; text-align: center;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const decision of decisions) {
            html += renderDecisionRow(decision);
        }
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
        
        container.innerHTML = html;
        
        // Initialize resizable columns
        initResizableColumns('pending-decisions-table');
        
    } catch (error) {
        console.error('Error loading pending decisions:', error);
        container.innerHTML = `<div class="error">Failed to load pending decisions: ${error.message}</div>`;
    }
}

function renderDecisionRow(decision) {
    const typeConfig = {
        'TASK_ACCEPTANCE': { label: '📝 Task', color: '#0284c7', bg: '#e0f2fe' },
        'MERGE_CONSENT': { label: '🔀 Merge', color: '#7c3aed', bg: '#ede9fe' },
        'DEPENDENCY_ACCEPTANCE': { label: '🔗 Dep', color: '#d97706', bg: '#fef3c7' },
        'ALTERNATIVE_DEP_ACCEPTANCE': { label: '↔️ Alt', color: '#db2777', bg: '#fce7f3' }
    };
    
    const config = typeConfig[decision.type] || { label: decision.type, color: '#666', bg: '#f3f4f6' };
    const context = decision.context || {};
    
    // Build description with clickable task names
    let desc = '';
    let from = '';
    
    const isRejectedTask = decision.type === 'TASK_ACCEPTANCE' && context.task_state === 'REJECTED';
    
    // Helper to create clickable task link
    const taskLink = (taskId, title) => taskId 
        ? `<span class="task-link" onclick="showTaskDetails('${taskId}')">${escapeHtml(title || 'Unknown task')}</span>`
        : escapeHtml(title || 'Unknown task');
    
    if (decision.type === 'TASK_ACCEPTANCE') {
        desc = taskLink(context.task_id, context.task_title);
        from = escapeHtml(context.creator_name || 'Unknown');
    } else if (decision.type === 'MERGE_CONSENT') {
        desc = `${taskLink(context.from_task_id, context.from_task_title)} → ${taskLink(context.to_task_id, context.to_task_title)}`;
        from = escapeHtml(context.proposer_name || 'Unknown');
    } else if (decision.type === 'DEPENDENCY_ACCEPTANCE') {
        desc = `${taskLink(context.downstream_task_id, context.downstream_task)} → ${taskLink(context.upstream_task_id, context.upstream_task)}`;
        from = 'Dependency';
    } else if (decision.type === 'ALTERNATIVE_DEP_ACCEPTANCE') {
        desc = `${taskLink(context.downstream_task_id, context.downstream_task)}: Instead of ${taskLink(context.original_upstream_id, context.original_upstream)} → ${taskLink(context.suggested_upstream_id, context.suggested_upstream)}`;
        from = escapeHtml(context.proposer_name || 'Unknown');
    }
    
    // Build action buttons
    let actions = '';
    const hasPendingMerge = context.has_pending_merge === true;
    
    if (decision.type === 'TASK_ACCEPTANCE') {
        if (isRejectedTask) {
            actions = `
                <button onclick="archiveRejectedTask('${context.task_id}')" 
                    style="padding: 4px 8px; font-size: 0.8rem; background: #fee2e2; border: 1px solid #fecaca; border-radius: 4px; cursor: pointer; color: #991b1b;" 
                    title="Archive">📦</button>
                <button onclick="showEditRejectedTaskDialog('${context.task_id}')" 
                    style="padding: 4px 8px; font-size: 0.8rem; background: #e0f2fe; border: 1px solid #bfdbfe; border-radius: 4px; cursor: pointer; color: #1d4ed8;" 
                    title="Edit & Reassign">✏️</button>
            `;
        } else if (hasPendingMerge) {
            actions = `
                <button onclick="cancelMergeProposal('${context.pending_merge_id}')" 
                    style="padding: 4px 8px; font-size: 0.8rem; background: #fef3c7; border: 1px solid #fbbf24; border-radius: 4px; cursor: pointer; color: #92400e;" 
                    title="Cancel merge suggestion">↩️</button>
            `;
        } else {
            actions = `
                <button onclick="decideOnTask('${context.task_id}', 'accept')" 
                    style="padding: 4px 8px; font-size: 0.8rem; background: #dcfce7; border: 1px solid #86efac; border-radius: 4px; cursor: pointer; color: #166534;" 
                    title="Accept">✅</button>
                <button onclick="showRejectDialog('task', '${context.task_id}')" 
                    style="padding: 4px 8px; font-size: 0.8rem; background: #fee2e2; border: 1px solid #fecaca; border-radius: 4px; cursor: pointer; color: #991b1b;" 
                    title="Reject">❌</button>
                <button onclick="showMergeTaskDialog('${context.task_id}')" 
                    style="padding: 4px 8px; font-size: 0.8rem; background: #ede9fe; border: 1px solid #c4b5fd; border-radius: 4px; cursor: pointer; color: #5b21b6;" 
                    title="Merge">🔀</button>
            `;
        }
    } else if (decision.type === 'MERGE_CONSENT') {
        actions = `
            <button onclick="decideOnMerge('${context.proposal_id}', 'accept')" 
                style="padding: 4px 8px; font-size: 0.8rem; background: #dcfce7; border: 1px solid #86efac; border-radius: 4px; cursor: pointer; color: #166534;" 
                title="Accept">✅</button>
            <button onclick="showRejectDialog('merge', '${context.proposal_id}')" 
                style="padding: 4px 8px; font-size: 0.8rem; background: #fee2e2; border: 1px solid #fecaca; border-radius: 4px; cursor: pointer; color: #991b1b;" 
                title="Reject">❌</button>
        `;
    } else if (decision.type === 'DEPENDENCY_ACCEPTANCE') {
        actions = `
            <button onclick="decideOnDependency('${context.dependency_id}', 'accept')" 
                style="padding: 4px 8px; font-size: 0.8rem; background: #dcfce7; border: 1px solid #86efac; border-radius: 4px; cursor: pointer; color: #166534;" 
                title="Accept">✅</button>
            <button onclick="showRejectDialog('dependency', '${context.dependency_id}')" 
                style="padding: 4px 8px; font-size: 0.8rem; background: #fee2e2; border: 1px solid #fecaca; border-radius: 4px; cursor: pointer; color: #991b1b;" 
                title="Reject">❌</button>
            <button onclick="showAlternativeDialog('${context.dependency_id}')" 
                style="padding: 4px 8px; font-size: 0.8rem; background: #fce7f3; border: 1px solid #f9a8d4; border-radius: 4px; cursor: pointer; color: #9d174d;" 
                title="Suggest Alternative">↔️</button>
        `;
    } else if (decision.type === 'ALTERNATIVE_DEP_ACCEPTANCE') {
        actions = `
            <button onclick="decideOnAlternative('${context.proposal_id}', 'accept')" 
                style="padding: 4px 8px; font-size: 0.8rem; background: #dcfce7; border: 1px solid #86efac; border-radius: 4px; cursor: pointer; color: #166534;" 
                title="Accept">✅</button>
            <button onclick="showRejectDialog('alternative', '${context.proposal_id}')" 
                style="padding: 4px 8px; font-size: 0.8rem; background: #fee2e2; border: 1px solid #fecaca; border-radius: 4px; cursor: pointer; color: #991b1b;" 
                title="Reject">❌</button>
        `;
    }
    
    const rejectedBadge = isRejectedTask ? `<span style="margin-left:6px; padding:2px 6px; background:#fee2e2; color:#b91c1c; border-radius:4px; font-size:0.75rem; font-weight:700;">Rejected</span>` : '';
    const typeBadge = `<span style="display: inline-flex; align-items:center; padding: 4px 8px; background: ${config.bg}; color: ${config.color}; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">${config.label}${rejectedBadge}</span>`;
    
    return `
        <tr style="border-bottom: 1px solid #dee2e6;">
            <td style="padding: 12px;">${typeBadge}</td>
            <td style="padding: 12px; font-weight: 500; color: #333; max-width: 300px; overflow: hidden; text-overflow: ellipsis;">${desc}</td>
            <td style="padding: 12px; color: #666;">${from}</td>
            <td style="padding: 12px; color: #999; font-size: 0.85rem;">${formatRelativeTime(decision.created_at)}</td>
            <td style="padding: 8px; text-align: center;">
                <div style="display: flex; gap: 4px; justify-content: center;">
                    ${actions}
                </div>
            </td>
        </tr>
    `;
}

async function decideOnTask(taskId, action, reason = null, mergeIntoTaskId = null) {
    try {
        const body = { action };
        if (reason) body.reason = reason;
        if (mergeIntoTaskId) body.merge_into_task_id = mergeIntoTaskId;
        
        await apiCall(`/decisions/task/${taskId}`, {
            method: 'POST',
            body: JSON.stringify(body)
        });
        
        showToast(`Task ${action}ed successfully!`, 'success');
        loadPendingDecisions();
        loadTaskGraph();  // refresh graph in case state changed
        
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function archiveRejectedTask(taskId) {
    try {
        await apiCall(`/tasks/${taskId}`, { method: 'DELETE' });
        showToast('Task archived', 'success');
        loadPendingDecisions();
        loadTaskGraph();
    } catch (error) {
        showToast('Failed to archive task: ' + error.message, 'error');
    }
}

async function showEditRejectedTaskDialog(taskId) {
    try {
        const details = await apiCall(`/tasks/${taskId}/full-details`);
        const task = details.task || details || {};
        const owners = details.all_users || (details.users || []);
        const currentOwnerId = task.owner_id || task.owner_user_id || (task.owner && task.owner.id);
        
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top:0; left:0; right:0; bottom:0;
            background: rgba(0,0,0,0.5);
            display: flex; align-items: center; justify-content: center;
            z-index: 10000;
        `;
        
        const content = document.createElement('div');
        content.style.cssText = `
            background: white; padding: 20px; border-radius: 10px;
            width: 420px; max-width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.25);
        `;
        
        content.innerHTML = `
            <h3 style="margin-top:0; margin-bottom:12px;">Edit Rejected Task</h3>
            <label style="display:block; margin-bottom:8px; font-weight:600;">Title</label>
            <input id="rej-title" type="text" value="${escapeHtml(task.title || '')}" style="width:100%; padding:8px; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:12px;">
            <label style="display:block; margin-bottom:8px; font-weight:600;">Description</label>
            <textarea id="rej-desc" style="width:100%; padding:8px; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:12px; min-height:80px;">${escapeHtml(task.description || '')}</textarea>
            <label style="display:block; margin-bottom:8px; font-weight:600;">Owner</label>
            <select id="rej-owner" style="width:100%; padding:8px; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:16px;">
                ${(owners || []).map(u => `<option value="${u.id}" ${u.id === currentOwnerId ? 'selected' : ''}>${escapeHtml(u.name)}</option>`).join('')}
            </select>
            <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:4px;">
                <button id="rej-cancel" style="padding:8px 12px; border:1px solid #e2e8f0; background:white; border-radius:6px; cursor:pointer;">Cancel</button>
                <button id="rej-save" style="padding:8px 12px; border:none; background:#3b82f6; color:white; border-radius:6px; cursor:pointer; font-weight:600;">Save</button>
            </div>
            <p style="margin-top:10px; color:#64748b; font-size:12px;">If owner = creator → task becomes ACTIVE. Otherwise it returns to DRAFT for the new owner's acceptance.</p>
        `;
        
        modal.appendChild(content);
        document.body.appendChild(modal);
        
        document.getElementById('rej-cancel').onclick = () => modal.remove();
        document.getElementById('rej-save').onclick = async () => {
            const title = document.getElementById('rej-title').value.trim();
            const desc = document.getElementById('rej-desc').value.trim();
            const owner = document.getElementById('rej-owner').value;
            try {
                await apiCall(`/tasks/${taskId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title,
                        description: desc,
                        owner_user_id: owner
                    })
                });
                showToast('Task updated', 'success');
                modal.remove();
                loadPendingDecisions();
                loadTaskGraph();
            } catch (error) {
                showToast('Failed to update task: ' + error.message, 'error');
            }
        };
        
    } catch (error) {
        showToast('Failed to load task details: ' + error.message, 'error');
    }
}

async function decideOnMerge(proposalId, action, reason = null) {
    try {
        const body = { action };
        if (reason) body.reason = reason;
        
        await apiCall(`/decisions/merge/${proposalId}`, {
            method: 'POST',
            body: JSON.stringify(body)
        });
        
        showToast(`Merge ${action}ed successfully!`, 'success');
        loadPendingDecisions();
        
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function cancelMergeProposal(proposalId) {
    showConfirmDialog(
        'Are you sure you want to cancel your merge suggestion?',
        async () => {
            await doCancelMergeProposal(proposalId);
        },
        { title: 'Cancel Merge Suggestion', confirmText: 'Yes, Cancel', type: 'warning' }
    );
}

async function doCancelMergeProposal(proposalId) {
    
    try {
        await apiCall(`/decisions/merge/${proposalId}`, {
            method: 'DELETE'
        });
        
        showToast('Merge suggestion cancelled', 'success');
        loadPendingDecisions();
        
    } catch (error) {
        showToast('Error cancelling merge: ' + error.message, 'error');
    }
}

async function decideOnDependency(dependencyId, action, reason = null, alternativeTaskId = null) {
    try {
        const body = { action };
        if (reason) body.reason = reason;
        if (alternativeTaskId) body.alternative_task_id = alternativeTaskId;
        
        await apiCall(`/decisions/dependency/${dependencyId}`, {
            method: 'POST',
            body: JSON.stringify(body)
        });
        
        showToast(`Dependency ${action}ed successfully!`, 'success');
        loadPendingDecisions();
        
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function decideOnAlternative(proposalId, action, reason = null) {
    try {
        const body = { action };
        if (reason) body.reason = reason;
        
        await apiCall(`/decisions/alternative/${proposalId}`, {
            method: 'POST',
            body: JSON.stringify(body)
        });
        
        showToast(`Alternative ${action}ed successfully!`, 'success');
        loadPendingDecisions();
        
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

function showRejectDialog(type, entityId) {
    const titles = {
        'task': 'Reject Task',
        'merge': 'Reject Merge Proposal',
        'dependency': 'Reject Dependency',
        'alternative': 'Reject Alternative'
    };
    
    const placeholders = {
        'task': 'Why are you rejecting this task?',
        'merge': 'Why are you rejecting this merge proposal?',
        'dependency': 'Why are you rejecting this dependency?',
        'alternative': 'Why are you rejecting this alternative?'
    };
    
    const modalHtml = `
        <div id="reject-modal" class="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 10000;">
            <div class="modal-content" style="background: white; padding: 24px; border-radius: 12px; max-width: 450px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                <h3 style="margin: 0 0 16px 0; color: #991b1b;">❌ ${titles[type] || 'Reject'}</h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #374151;">Reason for rejection:</label>
                    <textarea id="reject-reason" placeholder="${placeholders[type] || 'Provide a reason...'}" 
                        style="width: 100%; padding: 12px; border: 2px solid #fecaca; border-radius: 8px; font-size: 1rem; min-height: 80px; resize: vertical; box-sizing: border-box;"></textarea>
                </div>
                
                <div style="display: flex; gap: 12px; justify-content: flex-end;">
                    <button onclick="closeRejectModal()" style="padding: 10px 20px; border: 2px solid #e2e8f0; border-radius: 8px; background: white; cursor: pointer; font-size: 1rem;">Cancel</button>
                    <button onclick="submitRejection('${type}', '${entityId}')" style="padding: 10px 20px; border: none; border-radius: 8px; background: #dc2626; color: white; cursor: pointer; font-size: 1rem; font-weight: 600;">❌ Reject</button>
                </div>
            </div>
        </div>
    `;
    
    closeRejectModal();
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    setTimeout(() => document.getElementById('reject-reason')?.focus(), 100);
}

function closeRejectModal() {
    const modal = document.getElementById('reject-modal');
    if (modal) modal.remove();
}

function submitRejection(type, entityId) {
    const reasonInput = document.getElementById('reject-reason');
    const reason = reasonInput?.value?.trim();
    
    if (!reason) {
        alert('Please provide a reason for rejection.');
        return;
    }
    
    closeRejectModal();
    
    if (type === 'task') {
        decideOnTask(entityId, 'reject', reason);
    } else if (type === 'merge') {
        decideOnMerge(entityId, 'reject', reason);
    } else if (type === 'dependency') {
        decideOnDependency(entityId, 'reject', reason);
    } else if (type === 'alternative') {
        decideOnAlternative(entityId, 'reject', reason);
    }
}

// Legacy function kept for compatibility
function showRejectTaskDialog(taskId) {
    showRejectDialog('task', taskId);
}

async function showMergeTaskDialog(taskId) {
    try {
        // Only get tasks owned by current user (can only propose merging into your own tasks)
        const tasks = await apiCall('/tasks?include_self=true&include_aligned=false');
        const myTasks = tasks.filter(t => t.id !== taskId && t.owner_user_id === currentUser.id);
        
        if (myTasks.length === 0) {
            alert('You have no other tasks to merge into. You can only propose merging into your own tasks.');
            return;
        }
        
        // Create a proper modal dialog
        const modalHtml = `
            <div id="merge-modal" class="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 10000;">
                <div class="modal-content" style="background: white; padding: 24px; border-radius: 12px; max-width: 500px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                    <h3 style="margin: 0 0 16px 0; color: #1e293b;">🔀 Propose Task Merge</h3>
                    <p style="color: #64748b; margin-bottom: 16px;">Select one of your tasks to merge this task into:</p>
                    
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #374151;">Merge into:</label>
                        <select id="merge-target-select" style="width: 100%; padding: 12px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; background: white;">
                            <option value="">-- Select a task --</option>
                            ${myTasks.map(t => `<option value="${t.id}">${escapeHtml(t.title)}</option>`).join('')}
                        </select>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #374151;">Reason for merge:</label>
                        <textarea id="merge-reason" placeholder="Why should these tasks be merged?" 
                            style="width: 100%; padding: 12px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; min-height: 80px; resize: vertical;"></textarea>
                    </div>
                    
                    <div style="display: flex; gap: 12px; justify-content: flex-end;">
                        <button onclick="closeMergeModal()" style="padding: 10px 20px; border: 2px solid #e2e8f0; border-radius: 8px; background: white; cursor: pointer; font-size: 1rem;">Cancel</button>
                        <button onclick="submitMergeProposal('${taskId}')" style="padding: 10px 20px; border: none; border-radius: 8px; background: #6366f1; color: white; cursor: pointer; font-size: 1rem; font-weight: 600;">🔀 Propose Merge</button>
                    </div>
                </div>
            </div>
        `;
        
        // Remove any existing modal
        closeMergeModal();
        
        // Add modal to page
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Focus the select
        setTimeout(() => document.getElementById('merge-target-select')?.focus(), 100);
        
    } catch (error) {
        alert('Error loading tasks: ' + error.message);
    }
}

function closeMergeModal() {
    const modal = document.getElementById('merge-modal');
    if (modal) modal.remove();
}

function submitMergeProposal(taskId) {
    const targetSelect = document.getElementById('merge-target-select');
    const reasonInput = document.getElementById('merge-reason');
    
    const targetTaskId = targetSelect?.value;
    const reason = reasonInput?.value?.trim();
    
    if (!targetTaskId) {
        alert('Please select a task to merge into.');
        return;
    }
    
    if (!reason) {
        alert('Please provide a reason for the merge.');
        return;
    }
    
    closeMergeModal();
    decideOnTask(taskId, 'propose_merge', reason, targetTaskId);
}

function showRejectMergeDialog(proposalId) {
    showRejectDialog('merge', proposalId);
}

function showRejectDependencyDialog(dependencyId) {
    showRejectDialog('dependency', dependencyId);
}

async function showAlternativeDialog(dependencyId) {
    try {
        // Only show user's own tasks as alternatives
        const tasks = await apiCall('/tasks?include_self=true&include_aligned=false');
        const myTasks = tasks.filter(t => t.owner_user_id === currentUser.id);
        
        if (myTasks.length === 0) {
            alert('You have no tasks to suggest as alternatives.');
            return;
        }
        
        // Create a proper modal dialog
        const modalHtml = `
            <div id="alt-dep-modal" class="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 10000;">
                <div class="modal-content" style="background: white; padding: 24px; border-radius: 12px; max-width: 500px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                    <h3 style="margin: 0 0 16px 0; color: #1e293b;">↔️ Suggest Alternative Dependency</h3>
                    <p style="color: #64748b; margin-bottom: 16px;">Select one of your tasks as an alternative:</p>
                    
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #374151;">Alternative task:</label>
                        <select id="alt-task-select" style="width: 100%; padding: 12px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; background: white;">
                            <option value="">-- Select a task --</option>
                            ${myTasks.map(t => `<option value="${t.id}">${escapeHtml(t.title)}</option>`).join('')}
                        </select>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #374151;">Reason:</label>
                        <textarea id="alt-reason" placeholder="Why is this a better dependency?" 
                            style="width: 100%; padding: 12px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; min-height: 80px; resize: vertical;"></textarea>
                    </div>
                    
                    <div style="display: flex; gap: 12px; justify-content: flex-end;">
                        <button onclick="closeAltDepModal()" style="padding: 10px 20px; border: 2px solid #e2e8f0; border-radius: 8px; background: white; cursor: pointer; font-size: 1rem;">Cancel</button>
                        <button onclick="submitAltDependency('${dependencyId}')" style="padding: 10px 20px; border: none; border-radius: 8px; background: #6366f1; color: white; cursor: pointer; font-size: 1rem; font-weight: 600;">↔️ Suggest</button>
                    </div>
                </div>
            </div>
        `;
        
        // Remove any existing modal
        closeAltDepModal();
        
        // Add modal to page
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Focus the select
        setTimeout(() => document.getElementById('alt-task-select')?.focus(), 100);
        
    } catch (error) {
        alert('Error loading tasks: ' + error.message);
    }
}

function closeAltDepModal() {
    const modal = document.getElementById('alt-dep-modal');
    if (modal) modal.remove();
}

function submitAltDependency(dependencyId) {
    const altSelect = document.getElementById('alt-task-select');
    const reasonInput = document.getElementById('alt-reason');
    
    const altTaskId = altSelect?.value;
    const reason = reasonInput?.value?.trim();
    
    if (!altTaskId) {
        alert('Please select an alternative task.');
        return;
    }
    
    closeAltDepModal();
    decideOnDependency(dependencyId, 'alternative', reason || 'Suggested alternative', altTaskId);
}


function showRejectAlternativeDialog(proposalId) {
    showRejectDialog('alternative', proposalId);
}


