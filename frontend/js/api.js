/**
 * GraphRAG Platform — API Client
 */

const API_BASE = window.location.hostname === 'localhost' ? 'http://localhost:8000/api/v1' : '/api/v1';

function parseValidationError(errBody) {
    if (errBody.errors && errBody.errors.length > 0) {
        const msgs = errBody.errors.map(e => e.msg || '').filter(Boolean);
        if (msgs.length) return msgs.join('. ');
    }
    return errBody.detail || errBody.message || 'Ошибка запроса';
}

class GraphRAGApi {
    constructor() { this.token = localStorage.getItem('graphrag_token'); this.adminToken = localStorage.getItem('graphrag_admin_token'); }

    get headers() { const h = { 'Content-Type': 'application/json' }; if (this.token) h['Authorization'] = `Bearer ${this.token}`; return h; }

    setToken(token) { this.token = token; localStorage.setItem('graphrag_token', token); }
    clearToken() { this.token = null; localStorage.removeItem('graphrag_token'); localStorage.removeItem('graphrag_user'); }

    // ── Generic HTTP helpers ─────────────────────
    async get(path) {
        const r = await fetch(`${API_BASE}${path}`, { headers: this.headers });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || e.message || 'Ошибка запроса'); }
        return r.json();
    }

    async post(path, body = {}) {
        const r = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: this.headers, body: JSON.stringify(body) });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || e.message || 'Ошибка запроса'); }
        return r.json();
    }

    async put(path, body = {}) {
        const r = await fetch(`${API_BASE}${path}`, { method: 'PUT', headers: this.headers, body: JSON.stringify(body) });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || e.message || 'Ошибка запроса'); }
        return r.json();
    }

    async del(path) {
        const r = await fetch(`${API_BASE}${path}`, { method: 'DELETE', headers: this.headers });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || e.message || 'Ошибка запроса'); }
        return r.json();
    }

    setAdminToken(token) { this.adminToken = token; localStorage.setItem('graphrag_admin_token', token); }
    restoreAdminToken() {
        if (this.adminToken) { this.setToken(this.adminToken); this.adminToken = null; localStorage.removeItem('graphrag_admin_token'); return true; }
        return false;
    }

    async login(email, password) {
        const r = await fetch(`${API_BASE}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); }
        const d = await r.json(); this.setToken(d.access_token); return d;
    }

    async register(fn, email, password) {
        const r = await fetch(`${API_BASE}/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: fn, email, password }) });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); }
        return r.json();
    }

    async getMe() { const r = await fetch(`${API_BASE}/auth/me`, { headers: this.headers }); if (!r.ok) { this.clearToken(); throw new Error('Не авторизован'); } return r.json(); }

    async getUsers(params = {}) {
        const qs = new URLSearchParams(params); const r = await fetch(`${API_BASE}/auth/users?${qs}`, { headers: this.headers });
        if (!r.ok) throw new Error('Ошибка загрузки пользователей'); return r.json();
    }
    async updateUser(uid, d) { const r = await fetch(`${API_BASE}/auth/users/${uid}`, { method: 'PUT', headers: this.headers, body: JSON.stringify(d) }); if (!r.ok) throw new Error('Ошибка обновления'); return r.json(); }
    async deleteUser(uid) { const r = await fetch(`${API_BASE}/auth/users/${uid}`, { method: 'DELETE', headers: this.headers }); if (!r.ok) throw new Error('Ошибка удаления'); return r.json(); }

    async impersonate(uid) {
        this.setAdminToken(this.token);
        try {
            const r = await fetch(`${API_BASE}/auth/users/${uid}/impersonate`, { method: 'POST', headers: this.headers });
            if (!r.ok) { const e = await r.json().catch(() => ({})); this.restoreAdminToken(); throw new Error(parseValidationError(e)); }
            const d = await r.json(); this.setToken(d.access_token); return d;
        } catch (e) { this.restoreAdminToken(); throw e; }
    }

    async sendMessage(m, sid = null) {
        const b = { messages: [{ role: "user", content: m }] }; if (sid) b.session_id = sid;
        const r = await fetch(`${API_BASE}/chat`, { method: 'POST', headers: this.headers, body: JSON.stringify(b) });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); } return r.json();
    }

    async getIngestStatus(did) { const r = await fetch(`${API_BASE}/ingest/status/${did}`, { headers: this.headers }); if (!r.ok) throw new Error('Статус не найден'); return r.json(); }
    async ingestText(t, tx, cl, dp) { const r = await fetch(`${API_BASE}/ingest`, { method: 'POST', headers: this.headers, body: JSON.stringify({ title: t, content: tx, clearance_level: parseInt(cl) || 0, department: dp }) }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); } return r.json(); }
    async ingestFile(f, cl, dp) { const fd = new FormData(); fd.append('file', f); fd.append('clearance_level', String(cl ?? 0)); fd.append('department', dp || 'all'); const r = await fetch(`${API_BASE}/ingest/file`, { method: 'POST', headers: { 'Authorization': `Bearer ${this.token}` }, body: fd }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Ошибка загрузки файла'); } return r.json(); }
    async ingestUrl(u, t, cl, dp) { const r = await fetch(`${API_BASE}/ingest/url`, { method: 'POST', headers: this.headers, body: JSON.stringify({ url: u, title: t, clearance_level: parseInt(cl) || 0, department: dp }) }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Ошибка загрузки URL'); } return r.json(); }
            async ingestAzureWiki(repoUrl, patToken, cl, dp) { const r = await fetch(`${API_BASE}/ingest/azure-wiki`, { method: 'POST', headers: this.headers, body: JSON.stringify({ repo_url: repoUrl, pat_token: patToken || '', clearance_level: parseInt(cl) || 0, department: dp }) }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || e.message || 'Ошибка импорта Wiki'); } return r.json(); }
    async getChatHistory(l = 100) { const r = await fetch(`${API_BASE}/chat/history?limit=${l}`, { headers: this.headers }); if (!r.ok) return { messages: [] }; return r.json(); }
    async clearChatHistory() { const r = await fetch(`${API_BASE}/chat/history`, { method: 'DELETE', headers: this.headers }); if (!r.ok) throw new Error('Ошибка очистки истории'); return r.json(); }
    async clearGraphData() { const r = await fetch(`${API_BASE}/graph/clear`, { method: 'DELETE', headers: this.headers }); if (!r.ok) throw new Error('Ошибка очистки графа'); return r.json(); }
    async updateDocument(docId, clearance, department) { const r = await fetch(`${API_BASE}/graph/document/${docId}`, { method: 'PUT', headers: this.headers, body: JSON.stringify({ clearance_level: parseInt(clearance), department }) }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); } return r.json(); }
    async getServiceConfig() { const r = await fetch(`${API_BASE}/config/services`, { headers: this.headers }); if (!r.ok) throw new Error('Ошибка конфигурации'); return r.json(); }
    async getGraphStats() { const r = await fetch(`${API_BASE}/graph/stats`, { headers: this.headers }); if (!r.ok) throw new Error('Ошибка статистики'); return r.json(); }
    async runTests() { const r = await fetch(`${API_BASE}/tests/run`, { method: 'POST', headers: this.headers }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); } return r.json(); }
    async getDepartments() { const r = await fetch(`${API_BASE}/departments/`, { headers: this.headers }); if (!r.ok) throw new Error('Ошибка загрузки отделов'); return r.json(); }
    async createDepartment(name, code, desc) { const r = await fetch(`${API_BASE}/departments/`, { method: 'POST', headers: this.headers, body: JSON.stringify({ name, code, description: desc || null }) }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); } return r.json(); }
    async updateDepartment(id, name, code, desc) { const r = await fetch(`${API_BASE}/departments/${id}`, { method: 'PUT', headers: this.headers, body: JSON.stringify({ name, code, description: desc || null }) }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); } return r.json(); }
    async deleteDepartment(id) { const r = await fetch(`${API_BASE}/departments/${id}`, { method: 'DELETE', headers: this.headers }); if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(parseValidationError(e)); } return r.json(); }
}

// ── Admin Settings API ────────────────────────────
const AdminAPI = {
    getAllSettings: () => api.get('/admin/settings'),
    getCategorySettings: (category) => api.get(`/admin/settings/${category}`),
    updateSetting: (id, value) => api.put(`/admin/settings/${id}`, { value }),
    updateCategory: (category, settings) => api.put(`/admin/settings/category/${category}`, { settings }),
    reloadSettings: () => api.post('/admin/settings/reload'),
    getHistory: (limit = 50, offset = 0) => api.get(`/admin/settings/history?limit=${limit}&offset=${offset}`),
};

window.api = new GraphRAGApi();