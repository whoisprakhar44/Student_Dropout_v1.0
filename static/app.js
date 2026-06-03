/* ═══════════════════════════════════════════════════════════════
   EduGuard — Frontend Logic
   Dashboard + Students + AI Chat + Auth
   ═══════════════════════════════════════════════════════════════ */

let studentsData = [];
let currentUser = null;
let currentThreadId = null;

// API base - connect to local backend
const API_BASE = window.location.origin;

// ── Auth ────────────────────────────────────────────────────────
async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/api/me`);
        if (res.ok) {
            currentUser = await res.json();
            document.getElementById('login-modal').classList.remove('open');
        } else {
            document.getElementById('login-modal').classList.add('open');
        }
    } catch (e) {
        document.getElementById('login-modal').classList.add('open');
    }
}

async function login(e) {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const res = await fetch(`${API_BASE}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    if (res.ok) {
        checkAuth();
    } else {
        alert("Login failed");
    }
}

async function register(e) {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const res = await fetch(`${API_BASE}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    if (res.ok) {
        alert("Registered. Now logging in.");
        login(e);
    } else {
        alert("Registration failed");
    }
}

async function logout() {
    await fetch(`${API_BASE}/api/logout`, { method: 'POST' });
    location.reload();
}

// ── Navigation ──────────────────────────────────────────────────
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
        const view = link.dataset.view;
        switchView(view);
    });
});

function switchView(viewName) {
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));

    const tab = document.querySelector(`[data-view="${viewName}"]`);
    if (tab) tab.classList.add('active');
    const view = document.getElementById(`view-${viewName}`);
    if (view) view.classList.add('active');
}

// ── Dashboard ───────────────────────────────────────────────────
async function loadDashboard() {
    try {
        const res = await fetch(`${API_BASE}/api/stats`);
        const stats = await res.json();

        document.getElementById('stat-total').textContent = stats.total_students;
        document.getElementById('stat-critical').textContent = stats.critical_risk;
        document.getElementById('stat-high').textContent = stats.high_risk;
        document.getElementById('stat-dropped').textContent = stats.dropped_out;
        document.getElementById('stat-gpa').textContent = stats.avg_gpa;
        document.getElementById('stat-attendance').textContent = stats.avg_attendance + '%';

        renderRiskChart(stats.risk_distribution, stats.total_students);
        renderStatusChart(stats.status_distribution);
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

function renderRiskChart(distribution, total) {
    const container = document.getElementById('risk-chart');
    if (!container) return;
    container.innerHTML = '';

    distribution.forEach(item => {
        const pct = Math.round((item.count / total) * 100);
        const row = document.createElement('div');
        row.className = 'risk-bar-row';
        row.innerHTML = `
            <span class="risk-bar-label">${item.risk_level}</span>
            <div class="risk-bar-track">
                <div class="risk-bar-fill ${item.risk_level}" style="width: 0%">${item.count} (${pct}%)</div>
            </div>
        `;
        container.appendChild(row);

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                row.querySelector('.risk-bar-fill').style.width = Math.max(pct, 15) + '%';
            });
        });
    });
}

function renderStatusChart(distribution) {
    const container = document.getElementById('status-chart');
    if(!container) return;
    container.innerHTML = '';

    distribution.forEach(item => {
        const div = document.createElement('div');
        div.className = 'status-item';
        const label = item.current_status.replace('_', ' ');
        div.innerHTML = `
            <span class="status-dot-indicator ${item.current_status}"></span>
            <span class="status-text">${label}</span>
            <span class="status-count">${item.count}</span>
        `;
        container.appendChild(div);
    });
}

// ── Student Modal ───────────────────────────────────────────────
function openStudentModal(s) {
    const modal = document.getElementById('student-modal');
    if(!modal) return;
    const body = document.getElementById('modal-body');

    const initials = s.name.split(' ').map(n => n[0]).join('');
    const bgClass = s.risk_level === 'critical' ? 'background:var(--gradient-danger)' :
                    s.risk_level === 'high' ? 'background:var(--gradient-warning)' :
                    s.risk_level === 'medium' ? 'background:linear-gradient(135deg,#f59e0b,#eab308)' :
                    'background:var(--gradient-success)';

    const income = s.parent_income ? `₹${s.parent_income.toLocaleString('en-IN')}` : '—';
    const factors = s.contributing_factors && s.contributing_factors !== 'none'
        ? s.contributing_factors.split(',').map(f => `<span class="factor-tag">${f.trim()}</span>`).join('')
        : '<span style="color:var(--text-muted)">None</span>';
    const interventions = s.recommended_intervention
        ? s.recommended_intervention.split(',').map(i => `<span class="intervention-tag">${i.trim()}</span>`).join('')
        : '<span style="color:var(--text-muted)">None</span>';

    body.innerHTML = `
        <div class="modal-student-header">
            <div class="modal-avatar" style="${bgClass}">${initials}</div>
            <div>
                <div class="modal-name">${s.name}</div>
                <div class="modal-subtitle">${s.gender === 'M' ? 'Male' : 'Female'} · Age ${s.age} · Grade ${s.school_name} · ${s.school_id}</div>
            </div>
        </div>

        <div class="modal-grid">
            <div class="modal-field">
                <div class="modal-field-label">Risk Level</div>
                <div class="modal-field-value"><span class="risk-pill ${s.risk_level}">● ${s.risk_level} (${(s.risk_score * 100).toFixed(0)}%)</span></div>
            </div>
            <div class="modal-field">
                <div class="modal-field-label">Status</div>
                <div class="modal-field-value"><span class="status-badge ${s.current_status}">${s.current_status.replace('_', ' ')}</span></div>
            </div>
        </div>
        <div class="modal-section-title">Contributing Risk Factors</div>
        <div class="modal-factors">${factors}</div>
    `;

    modal.classList.add('open');
}

function closeModal() {
    const modal = document.getElementById('student-modal');
    if(modal) modal.classList.remove('open');
}

// ── Chat & Feedback Loop ────────────────────────────────────────
let chatState = "idle";

async function loadChatHistory() {
    const res = await fetch(`${API_BASE}/api/chat/history`);
    if (!res.ok) return;
    const history = await res.json();
    const container = document.getElementById('historyList');
    if (!container) return;
    
    if (history.length === 0) {
        container.innerHTML = '<div class="hist-empty">No chat history yet</div>';
    } else {
        container.innerHTML = history.map(h => {
            const firstMsg = h.messages[0]?.content || "New Chat";
            return `<div class="history-item" onclick="alert('Viewing past threads is read-only. Start a new chat.')">
                <div class="hist-text">${escHtml(firstMsg)}</div>
                <div class="hist-date">${new Date(h.messages[0].timestamp).toLocaleString()}</div>
            </div>`;
        }).join('');
    }
}

function askSuggestion(btn) {
    const input = document.getElementById('chat-input');
    input.value = btn.textContent;
    sendMessage(new Event('submit'));
}

async function sendMessage(e) {
    e.preventDefault();
    if (chatState === "executing") return;

    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';

    const loadingId = 'loading-' + Date.now();
    
    if (chatState === "idle") {
        chatState = "executing";
        addChatMsg('user', `<div class="msg-text">${escHtml(text)}</div>`);
        addChatMsg('assistant', `<div class="loading-dots" id="${loadingId}"><span></span><span></span><span></span></div>`);
        
        try {
            const res = await fetch(`${API_BASE}/api/chat/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: text }),
            });
            
            if (res.status === 401) {
                document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
                alert("Session expired. Please log in again.");
                document.getElementById('login-modal').classList.add('open');
                chatState = "idle";
                return;
            }
            
            const data = await res.json();
            document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
            
            if (data.error && !data.proposed_sql) {
                addChatMsg('assistant', `<div class="msg-error">❌ ${escHtml(data.error)}</div>`);
                chatState = "idle";
            } else {
                currentThreadId = data.thread_id;
                renderProposedSQL(data.proposed_sql);
                chatState = "feedback";
            }
        } catch(err) {
            document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
            addChatMsg('assistant', `<div class="msg-error">❌ ${escHtml(err.message)}</div>`);
            chatState = "idle";
        }
    } else if (chatState === "feedback") {
        chatState = "executing";
        addChatMsg('user', `<div class="msg-text">Feedback: ${escHtml(text)}</div>`);
        addChatMsg('assistant', `<div class="loading-dots" id="${loadingId}"><span></span><span></span><span></span></div>`);
        
        try {
            const res = await fetch(`${API_BASE}/api/chat/feedback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ thread_id: currentThreadId, feedback: text }),
            });
            
            if (res.status === 401) {
                document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
                alert("Session expired. Please log in again.");
                document.getElementById('login-modal').classList.add('open');
                chatState = "idle";
                return;
            }
            
            const data = await res.json();
            document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
            
            if (data.error && !data.proposed_sql) {
                addChatMsg('assistant', `<div class="msg-error">❌ ${escHtml(data.error)}</div>`);
                chatState = "idle";
            } else {
                renderProposedSQL(data.proposed_sql);
                chatState = "feedback";
            }
        } catch(err) {
            document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
            addChatMsg('assistant', `<div class="msg-error">❌ ${escHtml(err.message)}</div>`);
            chatState = "idle";
        }
    }
}

function renderProposedSQL(sql) {
    const id = Date.now();
    let html = `<div class="msg-sql"><div class="msg-sql-label">Proposed SQL</div>${escHtml(sql)}</div>
        <div class="msg-actions" id="actions-${id}">
            <button class="btn btn-primary" onclick="approveSQL(${id})">Approve & Execute</button>
            <span style="font-size: 12px; color: var(--text-muted);">Or type feedback below to revise</span>
        </div>`;
    addChatMsg('assistant', html);
}

async function approveSQL(id) {
    if(chatState !== "feedback") return;
    document.getElementById(`actions-${id}`)?.remove();
    
    chatState = "executing";
    const loadingId = 'loading-' + Date.now();
    addChatMsg('assistant', `<div class="loading-dots" id="${loadingId}"><span></span><span></span><span></span></div>`);
    
    try {
        const res = await fetch(`${API_BASE}/api/chat/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ thread_id: currentThreadId }),
        });
        
        if (res.status === 401) {
            document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
            alert("Session expired. Please log in again.");
            document.getElementById('login-modal').classList.add('open');
            chatState = "idle";
            return;
        }
        
        const data = await res.json();
        document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
        
        if (data.error) {
            addChatMsg('assistant', `<div class="msg-error">⚠️ ${escHtml(data.error)}</div>`);
        } else {
            let html = '';
            if (data.summary) {
                html += `<div class="msg-text" style="margin-bottom:12px"><strong>Summary:</strong> ${escHtml(data.summary)}</div>`;
            }
            html += renderDataTable(data.data);
            addChatMsg('assistant', html);
        }
    } catch(err) {
        document.getElementById(loadingId)?.closest('.chat-msg')?.remove();
        addChatMsg('assistant', `<div class="msg-error">❌ ${escHtml(err.message)}</div>`);
    }
    chatState = "idle";
    currentThreadId = null;
    loadChatHistory();
}

function addChatMsg(role, innerHtml) {
    const welcome = document.querySelector('.chat-welcome');
    if (welcome) welcome.remove();
    
    const msgArea = document.getElementById('chatArea');
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.innerHTML = `
        <div class="msg-avatar">${role === 'user' ? '👤' : '🤖'}</div>
        <div class="msg-body">${innerHtml}</div>
    `;
    msgArea.appendChild(div);
    scrollChat();
}

function renderDataTable(rows) {
    if (!rows || !rows.length) return '<div class="msg-text" style="color:var(--text-muted)">No rows returned.</div>';
    const cols = Object.keys(rows[0]);
    let html = '<div class="msg-data-wrap"><table class="msg-data-table"><thead><tr>';
    cols.forEach(c => html += `<th>${escHtml(c)}</th>`);
    html += '</tr></thead><tbody>';
    rows.slice(0, 20).forEach(row => {
        html += '<tr>';
        cols.forEach(c => html += `<td>${escHtml(String(row[c] ?? ''))}</td>`);
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    if (rows.length > 20) {
        html += `<div class="msg-meta" style="margin-top:4px">Showing 20 of ${rows.length} rows</div>`;
    }
    return html;
}

function scrollChat() {
    const el = document.getElementById('chatArea');
    if(el) setTimeout(() => el.scrollTop = el.scrollHeight, 50);
}

function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ── Init ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
});
