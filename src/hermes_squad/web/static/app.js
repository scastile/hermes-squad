/**
 * Hermes Squad Dashboard — client-side app.
 *
 * Handles:
 *  - Theme toggle (dark/light)
 *  - Team/task fetching and kanban rendering
 *  - Four mailbox windows for all agents simultaneously
 *  - Auto-polling for live updates
 */

const POLL_INTERVAL = 5000; // 5 seconds

// ── State ──────────────────────────────────────────────────────────────────

let currentTeamId = null;
let pollTimer = null;

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    setupThemeToggle();
    setupTeamSelector();
    loadTeams();
});

// ── Theme ──────────────────────────────────────────────────────────────────

function setupThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    const icon = btn.querySelector('.icon');

    btn.addEventListener('click', () => {
        const html = document.documentElement;
        const current = html.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        icon.textContent = next === 'dark' ? '🌙' : '☀️';
        localStorage.setItem('hermes-squad-theme', next);
    });

    // Load saved preference
    const saved = localStorage.getItem('hermes-squad-theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
        icon.textContent = saved === 'dark' ? '🌙' : '☀️';
    }
}

// ── Teams ──────────────────────────────────────────────────────────────────

async function loadTeams() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        const selector = document.getElementById('team-selector');
        selector.innerHTML = '<option value="">Select team...</option>';

        if (data.teams) {
            for (const team of data.teams) {
                const opt = document.createElement('option');
                opt.value = team.team_id;
                opt.textContent = `${team.team_id.slice(0, 12)}... (${team.task_count} tasks)`;
                selector.appendChild(opt);
            }
        } else if (data.team_id) {
            const opt = document.createElement('option');
            opt.value = data.team_id;
            opt.textContent = data.team_id.slice(0, 12) + '...';
            selector.appendChild(opt);
        }
    } catch (err) {
        console.error('Failed to load teams:', err);
        document.getElementById('status-text').textContent = 'Disconnected';
        document.querySelector('.dot').classList.add('error');
    }
}

function setupTeamSelector() {
    const selector = document.getElementById('team-selector');
    selector.addEventListener('change', () => {
        currentTeamId = selector.value || null;
        if (currentTeamId) {
            loadTasks();
            loadAllMailboxes();
            startPolling();
        } else {
            // Reset mailbox grid to empty state
            renderMailboxGrid([]);
        }
    });
}

// ── Tasks ──────────────────────────────────────────────────────────────────

async function loadTasks() {
    if (!currentTeamId) return;

    try {
        const res = await fetch(`/api/tasks?team_id=${currentTeamId}`);
        const data = await res.json();
        renderTasks(data.tasks || []);
    } catch (err) {
        console.error('Failed to load tasks:', err);
    }
}

function renderTasks(tasks) {
    // Clear all columns
    ['pending', 'in_progress', 'completed', 'failed'].forEach(status => {
        const list = document.getElementById(`list-${status}`);
        const count = document.getElementById(`count-${status}`);
        list.innerHTML = '';
        count.textContent = '0';
    });

    const counts = { pending: 0, in_progress: 0, completed: 0, failed: 0 };

    for (const task of tasks) {
        const status = task.status || 'pending';
        counts[status] = (counts[status] || 0) + 1;

        const list = document.getElementById(`list-${status}`);
        if (!list) continue;

        const card = document.createElement('div');
        card.className = 'task-card';
        card.title = task.description || '';

        let depsHtml = '';
        if (task.blocked_by && task.blocked_by.length > 0) {
            depsHtml = `<span class="task-deps">⛓ ${task.blocked_by.length} dep(s)</span>`;
        }

        card.innerHTML = `
            <div class="task-subject">${escapeHtml(task.subject)}</div>
            <div class="task-meta">
                ${task.owner ? `<span class="task-owner">${escapeHtml(task.owner)}</span>` : ''}
                <span>${task.short_id}</span>
                ${depsHtml}
            </div>
        `;

        list.appendChild(card);
    }

    // Update counts
    for (const [status, count] of Object.entries(counts)) {
        const el = document.getElementById(`count-${status}`);
        if (el) el.textContent = count;
    }
}

// ── Mailboxes (all agents) ─────────────────────────────────────────────────

async function loadAllMailboxes() {
    if (!currentTeamId) return;

    try {
        // First get the members and their unread counts
        const statusRes = await fetch(`/api/status?team_id=${currentTeamId}`);
        const status = await statusRes.json();
        const members = status.members || [];
        const unreadCounts = status.unread_counts || {};

        if (members.length === 0) {
            renderMailboxGrid([]);
            return;
        }

        // Fetch all agent mailboxes in parallel
        const results = await Promise.all(
            members.map(async (agentId) => {
                try {
                    const res = await fetch(
                        `/api/mailbox/${agentId}?team_id=${currentTeamId}&history=true`
                    );
                    const data = await res.json();
                    return {
                        agentId,
                        messages: data.messages || [],
                        unread: unreadCounts[agentId] || 0,
                    };
                } catch (err) {
                    console.error(`Failed to load mailbox for ${agentId}:`, err);
                    return { agentId, messages: [], unread: 0 };
                }
            })
        );

        renderMailboxGrid(results);
    } catch (err) {
        console.error('Failed to load mailboxes:', err);
    }
}

function renderMailboxGrid(agentMailboxes) {
    const grid = document.getElementById('mailbox-grid');

    if (agentMailboxes.length === 0) {
        grid.innerHTML = `
            <div class="empty-state mailbox-empty">
                <p>No agents in this team</p>
            </div>`;
        return;
    }

    grid.innerHTML = agentMailboxes
        .map(({ agentId, messages, unread }) => {
            const msgCount = messages.length;
            const statusDot = unread > 0 ? 'pending' : 'completed';
            const hasUnread = unread > 0;
            const titleExtra = hasUnread ? ` (${unread} unread)` : '';

            let messagesHtml;
            if (msgCount === 0) {
                messagesHtml = '<div class="empty-state"><p>No messages</p></div>';
            } else {
                messagesHtml = messages
                    .slice()
                    .reverse()
                    .map(
                        (msg) => `
                <div class="message-item${msg.read === 0 ? ' unread' : ''}">
                    <div class="msg-header">
                        <span class="msg-from">${escapeHtml(msg.from_agent_id)}</span>
                        <span>${new Date(msg.created_at).toLocaleTimeString()}</span>
                    </div>
                    ${msg.subject ? `<div class="msg-subject">${escapeHtml(msg.subject)}</div>` : ''}
                    <div class="msg-preview">${escapeHtml((msg.content || '').slice(0, 150))}</div>
                </div>
            `
                    )
                    .join('');
            }

            return `
            <div class="mailbox-window">
                <div class="mailbox-window-header">
                    <div class="mailbox-agent-name">
                        <span class="dot" style="background: var(--${statusDot})"></span>
                        ${escapeHtml(agentId)}${titleExtra}
                    </div>
                    <span class="mailbox-msg-count">${msgCount} msg${msgCount !== 1 ? 's' : ''}</span>
                </div>
                <div class="message-list">
                    ${messagesHtml}
                </div>
            </div>`;
        })
        .join('');
}

// ── Polling ────────────────────────────────────────────────────────────────

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
        if (currentTeamId) {
            loadTasks();
            loadAllMailboxes();
        }
        loadTeams();
    }, POLL_INTERVAL);
}

// ── Helpers ────────────────────────────────────────────────────────────────

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function toast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}
