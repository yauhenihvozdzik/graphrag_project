/**
 * GraphRAG Platform — App Controller
 *
 * SPA controller handling auth, navigation, chat, document management,
 * admin panel, tests execution, and infrastructure display.
 *
 * @module app
 */

document.addEventListener('DOMContentLoaded', () => {
    // ─── Utility Shortcuts ───────────────────────
    const $ = (s) => document.querySelector(s);
    const $$ = (s) => document.querySelectorAll(s);

    const API_B = window.location.hostname === 'localhost'
        ? 'http://localhost:8000/api/v1'
        : '/api/v1';

    // ─── Password Toggle ────────────────────────
    $$('.toggle-pwd').forEach((btn) => {
        btn.addEventListener('click', () => {
            const inp = btn.parentElement.querySelector('input');
            if (!inp) return;
            const isPass = inp.type === 'password';
            inp.type = isPass ? 'text' : 'password';
            btn.textContent = isPass ? '🙈' : '👁️';
        });
    });

    // ─── Constants ──────────────────────────────
    const CLR = {
        0: 'Открытый',
        1: 'Конфиденциальный',
        2: 'Секретный',
        3: 'Сов. секретно',
    };

    const RO = { viewer: 0, analyst: 1, admin: 2 };

    // ─── State ──────────────────────────────────
    let curUser = null;
    let dPage = 1;
    let dTotal = 1;
    let dOrder = 'desc';
    let uPage = 1;
    let uTotal = 1;
    let uOrder = 'asc';
    let uTimer;
    let deptList = [];

    // ─── Department Helpers ─────────────────────
    function deptName(code) {
        const d = deptList.find((x) => x.code === code);
        return d ? d.name : code;
    }

    async function loadDepartments() {
        try {
            deptList = (await api.getDepartments()) || [];
        } catch (e) {
            deptList = [];
        }
    }

    function populateDeptSelect(el, defaultVal) {
        if (!el) return;
        const val = defaultVal !== undefined ? defaultVal : el.value;
        el.innerHTML = '';
        for (const d of deptList) {
            const o = document.createElement('option');
            o.value = d.code;
            o.textContent = d.name;
            if (d.code === val) o.selected = true;
            el.appendChild(o);
        }
    }

    function populateAllDeptSelects() {
        populateDeptSelect($('#ingest-department'));
        populateDeptSelect($('#doc-filter-dept'));
        populateDeptSelect($('#user-filter-dept'));
    }

    // ─── Toast Notification System ──────────────
    // sticky mode — toast stays until manually dismissed (for ingest progress)
    // non-sticky mode — auto-fades after duration based on type
    function toast(m, t = 'info', opts = {}) {
        let stack = $('#toast-stack');
        if (!stack) {
            stack = document.createElement('div');
            stack.id = 'toast-stack';
            stack.style.cssText =
                'position:fixed;bottom:1rem;right:1rem;z-index:9999;' +
                'display:flex;flex-direction:column-reverse;gap:0.5rem;max-width:420px;';
            document.body.appendChild(stack);
        }

        const id = 'toast-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
        const el = document.createElement('div');
        el.id = id;
        el.className = 'toast-item';
        el.style.cssText =
            'background:var(--bg-card);border:1px solid var(--border);' +
            'border-radius:var(--radius);padding:0.8rem 1rem;min-width:280px;' +
            'box-shadow:0 4px 20px rgba(0,0,0,0.5);font-size:0.9rem;' +
            'display:flex;justify-content:space-between;align-items:flex-start;' +
            'gap:0.5rem;animation:toastIn 0.25s ease;';

        const colorMap = {
            info: 'var(--text)',
            success: 'var(--success)',
            error: 'var(--error)',
            warning: 'var(--warning)',
        };
        const color = colorMap[t] || 'var(--text)';
        el.style.color = color;

        const isSticky = opts.sticky === true;

        el.innerHTML =
            `<span class="toast-msg">${m}</span>` +
            `<button class="toast-close" style="background:none;border:none;` +
            `color:var(--text-muted);cursor:pointer;font-size:1.1rem;` +
            `line-height:1;padding:0;flex-shrink:0;">×</button>`;

        const closeBtn = el.querySelector('.toast-close');

        // Shared dismiss helper
        function dismiss() {
            if (el._dismissed) return;
            el._dismissed = true;
            if (el._dismissTimer) clearTimeout(el._dismissTimer);
            el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            el.style.opacity = '0';
            el.style.transform = 'translateX(30px)';
            setTimeout(() => el.remove(), 300);
        }

        closeBtn.onclick = () => dismiss();
        el._dismiss = dismiss;

        // Store sticky flag for updT logic
        el._sticky = isSticky;

        // Non-sticky: auto-dismiss after duration
        if (!isSticky) {
            const durations = { success: 4000, error: 7000, warning: 5000, info: 4500 };
            const dur = opts.duration || durations[t] || 4500;
            el._dismissTimer = setTimeout(() => dismiss(), dur);
        }

        stack.appendChild(el);
        return el;
    }

    function updT(el, m, t) {
        if (!el) return;
        const msg = el.querySelector('.toast-msg');
        if (msg) {
            msg.textContent = m;
        }
        const colorMap = {
            info: 'var(--text)',
            success: 'var(--success)',
            error: 'var(--error)',
            warning: 'var(--warning)',
        };
        const color = colorMap[t] || 'var(--text)';
        el.style.color = color;

        // When a sticky toast transitions to success/error/warning — schedule auto-dismiss
        if (el._sticky && (t === 'success' || t === 'error' || t === 'warning')) {
            el._sticky = false;
            const dur = (t === 'error') ? 8000 : 5000;
            el._dismissTimer = setTimeout(() => {
                if (el._dismiss) el._dismiss();
            }, dur);
        }
    }

    // ─── Ingest Status Polling ──────────────────
    // STEP_LABELS maps step_name to a user-friendly system label
    const STEP_LABELS = {
        'starting': '🚀 Запуск',
        'uploading': '📤 Загрузка в S3',
        'extraction': '🔍 Извлечение сущностей',
        'graph': '🕸️ Граф знаний',
        'vectors': '🧮 Векторизация',
    };

    function stepLabel(name) {
        return STEP_LABELS[name] || `⏳ ${name}`;
    }

    // Returns {status, phaseLabel} — phaseLabel is updated on each poll cycle
    async function pollPhase(docId) {
        for (let i = 0; i < 90; i++) {
            await new Promise((r) => setTimeout(r, 1500));
            try {
                const s = await api.getIngestStatus(docId);
                if (s.status === 'completed') {
                    return { status: 'ok', phaseLabel: '✅ Завершён' };
                }
                if (s.status === 'failed') {
                    return { status: 'error', phaseLabel: `❌ ${s.error || 'Ошибка'}` };
                }
                const label = stepLabel(s.step_name || '');
                return { status: 'processing', phaseLabel: label };
            } catch {
                return { status: 'error', phaseLabel: '❌ Ошибка сети' };
            }
        }
        return { status: 'timeout', phaseLabel: '⏱️ Таймаут' };
    }

    // ─── Document Download ──────────────────────
    async function downloadDoc(docId, title) {
        try {
            const r = await fetch(`${API_B}/graph/document/${docId}/content`, {
                headers: api.headers,
            });
            if (!r.ok) throw new Error('Ошибка скачивания');
            const blob = await r.blob();

            const src = r.headers.get('X-Download-Source') || '?';
            const srcMap = {
                'minio-s3': '☁️ MinIO S3',
                'neo4j-full_text': '🗄️ Neo4j (полный текст)',
                'neo4j-chunks': '🧩 Neo4j (чанки)',
                'minio-original': '📁 Оригинал',
            };

            const disp = r.headers.get('Content-Disposition') || '';
            const m1 = disp.match(/filename\*=UTF-8''(.+)/);
            const m2 = disp.match(/filename="?([^";]+)"?/);
            const fname = m1
                ? decodeURIComponent(m1[1])
                : m2
                    ? m2[1]
                    : `${title || docId}.bin`;

            toast(`📥 Скачан «${fname}» — ${srcMap[src] || src}`, 'success');

            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fname;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            toast(`✗ ${e.message}`, 'error');
        }
    }

    // ─── Modal ──────────────────────────────────
    function modal(tt, ms) {
        return new Promise((resolve) => {
            const overlay = $('#modal-overlay');
            $('#modal-title').textContent = tt;
            $('#modal-message').textContent = ms;
            overlay.classList.remove('hidden');

            const close = (value) => {
                overlay.classList.add('hidden');
                resolve(value);
            };

            $('#modal-confirm').onclick = () => close(true);
            $('#modal-cancel').onclick = () => close(false);
            overlay.onclick = (e) => {
                if (e.target === overlay) close(false);
            };
        });
    }

    // ─── Role-Based Navigation ──────────────────
    function roleNav(role) {
        const userLevel = RO[role] || 0;
        $$('.nav-btn').forEach((btn) => {
            const minRole = RO[btn.dataset.minRole || 'viewer'] || 0;
            btn.style.display = userLevel >= minRole ? '' : 'none';
        });
    }

    function canAccess(tn) {
        if (!curUser) return tn === 'chat';
        const btn = $(`.nav-btn[data-tab="${tn}"]`);
        if (!btn) return false;
        const userLevel = RO[curUser.role] || 0;
        const required = RO[btn.dataset.minRole || 'viewer'] || 0;
        return userLevel >= required;
    }

    // ─── Auth Screen Handlers ───────────────────
    const authSc = $('#auth-screen');
    const appSc = $('#app-screen');

    $('#show-register').onclick = (e) => {
        e.preventDefault();
        $('#login-form').classList.remove('active');
        $('#register-form').classList.add('active');
    };

    $('#show-login').onclick = (e) => {
        e.preventDefault();
        $('#register-form').classList.remove('active');
        $('#login-form').classList.add('active');
    };

    $('#login-form').onsubmit = async (e) => {
        e.preventDefault();
        $('#login-error').classList.add('hidden');
        try {
            await api.login(
                $('#login-email').value.trim(),
                $('#login-password').value
            );
            const u = await api.getMe();
            localStorage.setItem('graphrag_user', JSON.stringify(u));
            showApp(u);
        } catch (er) {
            $('#login-error').textContent = er.message;
            $('#login-error').classList.remove('hidden');
        }
    };

    $('#register-form').onsubmit = async (e) => {
        e.preventDefault();
        $('#register-error').classList.add('hidden');
        try {
            await api.register(
                $('#reg-name').value.trim(),
                $('#reg-email').value.trim(),
                $('#reg-password').value
            );
            toast('✓ Регистрация успешна! Письмо отправлено. Ожидайте активации.', 'success');
            $('#login-form').classList.add('active');
            $('#register-form').classList.remove('active');
        } catch (er) {
            $('#register-error').textContent = er.message;
            $('#register-error').classList.remove('hidden');
        }
    };

    $('#logout-btn').onclick = () => {
        if (api.adminToken) {
            api.restoreAdminToken();
            location.hash = '#admin';
            showApp(null);
        } else {
            api.clearToken();
            appSc.classList.add('hidden');
            authSc.classList.remove('hidden');
        }
    };

    // ─── Show App (Auth → App transition) ───────
    async function showApp(user) {
        if (!user) {
            try {
                user = await api.getMe();
            } catch {
                return;
            }
        }

        curUser = user;
        authSc.classList.add('hidden');
        appSc.classList.remove('hidden');

        $('#user-email').textContent = user.email || '';
        $('#user-role').textContent = user.role || 'user';
        roleNav(user.role);

        await loadDepartments();
        populateAllDeptSelects();

        const tab = location.hash.replace('#', '') || 'chat';
        activateTab(tab);

        // Load chat history
        chatMsgs.innerHTML =
            '<div class="message system"><p>Загрузка истории...</p></div>';
        try {
            const h = await api.getChatHistory(100);
            chatMsgs.innerHTML = '';
            if (h.messages?.length) {
                for (const m of h.messages) {
                    addMsg(m.content, m.role, m.sources || null);
                }
            } else {
                chatMsgs.innerHTML =
                    '<div class="message system"><p>Добро пожаловать! Задайте вопрос.</p></div>';
            }
        } catch (e) {
            chatMsgs.innerHTML =
                '<div class="message system"><p>Не удалось загрузить историю.</p></div>';
        }
    }

    // ─── Tab Navigation ─────────────────────────
    function activateTab(tn) {
        if (!canAccess(tn)) {
            tn = 'chat';
            history.replaceState(null, '', '#chat');
        }

        $$('.nav-btn').forEach((b) => b.classList.remove('active'));
        $(`.nav-btn[data-tab="${tn}"]`)?.classList.add('active');

        $$('.tab-content').forEach((t) => t.classList.remove('active'));
        $(`#tab-${tn}`)?.classList.add('active');

        if (location.hash !== `#${tn}`) {
            history.replaceState(null, '', `#${tn}`);
        }

        if (tn === 'docs') {
            dPage = 1;
            loadDocs();
        }
        if (tn === 'admin' && curUser?.role === 'admin') {
            populateAllDeptSelects();
            uPage = 1;
            activateAdminSubtab('users');
        }
    }

    $$('.nav-btn').forEach((b) => {
        b.addEventListener('click', () => activateTab(b.dataset.tab));
    });

    // ─── Admin Sub-Tabs ────────────────────────
    let adminTab = localStorage.getItem('graphrag_admintab') || 'users';

    function activateAdminSubtab(st) {
        adminTab = st;
        localStorage.setItem('graphrag_admintab', st);

        $$('.ingest-type-btn[data-admintab]').forEach((b) =>
            b.classList.remove('active')
        );
        $(`.ingest-type-btn[data-admintab="${st}"]`)?.classList.add('active');

        $$('.admintab-card').forEach((c) => c.classList.remove('active'));
        $(`#admintab-${st}`)?.classList.add('active');

        if (st === 'users') {
            uPage = 1;
            loadUsers();
        } else if (st === 'departments') {
            loadDeptTable();
        }
    }

    $$('.ingest-type-btn[data-admintab]').forEach((b) => {
        b.addEventListener('click', () => activateAdminSubtab(b.dataset.admintab));
    });

    // Initialize admin sub-tab
    (() => {
        activateAdminSubtab(adminTab);
    })();

    // ─── Departments Table CRUD ─────────────────
    async function loadDeptTable() {
        const tbody = $('#departments-tbody');
        tbody.innerHTML =
            '<tr><td colspan="5" style="padding:1rem;text-align:center;' +
            'color:var(--text-muted);">⏳ Загрузка...</td></tr>';

        try {
            await loadDepartments();
            populateAllDeptSelects();

            if (!deptList.length) {
                tbody.innerHTML =
                    '<tr><td colspan="5" style="padding:1rem;' +
                    'text-align:center;color:var(--text-muted);">Нет отделов</td></tr>';
                return;
            }

            tbody.innerHTML = deptList
                .map((d) => {
                    return `<tr>
                        <td style="padding:0.5rem;">${d.id}</td>
                        <td style="padding:0.5rem;"><code>${d.code}</code></td>
                        <td style="padding:0.5rem;">
                            <input type="text" value="${d.name}" data-dn="${d.id}"
                                style="background-color:var(--bg-input);border:1px solid var(--border);
                                color:var(--text);padding:0.3rem 0.5rem;border-radius:var(--radius);
                                font-size:0.85rem;width:140px;">
                        </td>
                        <td style="padding:0.5rem;">
                            <input type="text" value="${d.description || ''}" data-dd="${d.id}"
                                style="background-color:var(--bg-input);border:1px solid var(--border);
                                color:var(--text);padding:0.3rem 0.5rem;border-radius:var(--radius);
                                font-size:0.85rem;width:200px;">
                        </td>
                        <td style="padding:0.5rem;text-align:center;white-space:nowrap;">
                            <button data-dsave="${d.id}" data-dcode="${d.code}"
                                class="btn btn-sm" style="color:var(--success);">💾</button>
                            <button data-ddel="${d.id}" data-dcode="${d.code}"
                                class="btn btn-sm" style="color:var(--error);">🗑️</button>
                        </td>
                    </tr>`;
                })
                .join('');

            // Save handler
            tbody.querySelectorAll('[data-dsave]').forEach((b) => {
                b.onclick = async () => {
                    const id = parseInt(b.dataset.dsave);
                    const code = b.dataset.dcode;
                    const name =
                        document.querySelector(`[data-dn="${id}"]`)?.value || '';
                    const desc =
                        document.querySelector(`[data-dd="${id}"]`)?.value || '';
                    try {
                        await api.updateDepartment(id, name, code, desc);
                        toast('✓ Отдел обновлён', 'success');
                        await loadDeptTable();
                    } catch (e) {
                        toast(`✗ ${e.message}`, 'error');
                    }
                };
            });

            // Delete handler
            tbody.querySelectorAll('[data-ddel]').forEach((b) => {
                b.onclick = async () => {
                    const id = parseInt(b.dataset.ddel);
                    const ok = await modal(
                        'Удалить отдел',
                        `Удалить отдел #${id}?`
                    );
                    if (!ok) return;
                    try {
                        await api.deleteDepartment(id);
                        toast('✓ Отдел удалён', 'success');
                        await loadDeptTable();
                    } catch (e) {
                        toast(`✗ ${e.message}`, 'error');
                    }
                };
            });
        } catch (e) {
            tbody.innerHTML =
                `<tr><td colspan="5" style="padding:1rem;color:var(--error);">${e.message}</td></tr>`;
        }
    }

    // Create department button
    $('#dep-create-btn')?.addEventListener('click', async () => {
        const name = $('#dep-name')?.value?.trim();
        const code = $('#dep-code')?.value?.trim();
        const desc = $('#dep-desc')?.value?.trim();

        if (!name || !code) {
            toast('Название и код обязательны', 'warning');
            return;
        }

        try {
            await api.createDepartment(name, code, desc || null);
            toast('✓ Отдел создан', 'success');
            $('#dep-name').value = '';
            $('#dep-code').value = '';
            $('#dep-desc').value = '';
            await loadDeptTable();
        } catch (e) {
            toast(`✗ ${e.message}`, 'error');
        }
    });

    // ─── Chat System ────────────────────────────
    const chatMsgs = $('#chat-messages');
    const chatInp = $('#chat-input');
    const sendBtn = $('#send-btn');

    function renderMd(text) {
        if (typeof marked !== 'undefined') {
            marked.setOptions({ breaks: true });
            return marked.parse(text);
        }
        // Fallback: basic HTML escaping + line breaks
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');
    }

    function addMsg(c, t = 'user', src = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${t}`;

        const body = document.createElement('div');
        body.className = 'msg-body';
        body.innerHTML =
            t === 'user'
                ? c
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/\n/g, '<br>')
                : renderMd(c);

        msgDiv.appendChild(body);

        // Sources
        if (src?.length) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'sources';

            const seen = new Set();
            const uniqueSources = [];
            for (const x of src) {
                const key = x.document_id || x.title ||
                    (typeof x === 'string' ? x : '');
                if (!seen.has(key)) {
                    seen.add(key);
                    const docId = x.document_id;
                    const title = x.title || x.document_id || key;
                    if (docId) {
                        uniqueSources.push(
                            `<span data-dl="${docId}" style="color:var(--primary);` +
                            `text-decoration:underline;cursor:pointer;" title="Скачать документ">${title}</span>`
                        );
                    } else {
                        uniqueSources.push(title);
                    }
                }
            }

            sourcesDiv.innerHTML = '📎 Источники: ' + uniqueSources.join(', ');
            msgDiv.appendChild(sourcesDiv);

            sourcesDiv.querySelectorAll('[data-dl]').forEach((sp) => {
                sp.onclick = () => downloadDoc(sp.dataset.dl, sp.textContent);
            });
        }

        chatMsgs.appendChild(msgDiv);
        chatMsgs.scrollTop = chatMsgs.scrollHeight;
        return msgDiv;
    }

    function typing() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message assistant';
        typingDiv.id = 'typing';
        typingDiv.innerHTML =
            '<div class="typing-indicator"><span></span><span></span><span></span></div>';
        chatMsgs.appendChild(typingDiv);
        chatMsgs.scrollTop = chatMsgs.scrollHeight;
        return typingDiv;
    }

    async function send() {
        const tx = chatInp.value.trim();
        if (!tx) return;

        chatInp.value = '';
        sendBtn.disabled = true;

        addMsg(tx, 'user');
        const te = typing();

        try {
            const r = await api.sendMessage(tx);
            te.remove();

            const am = r.messages?.find((m) => m.role === 'assistant');
            addMsg(
                am?.content ?? r.response ?? r.answer ?? 'Нет ответа',
                'assistant',
                r.sources
            );
        } catch (e) {
            te.remove();
            addMsg(`Ошибка: ${e.message}`, 'system');
        } finally {
            sendBtn.disabled = false;
            chatInp.focus();
        }
    }

    sendBtn.onclick = send;

    chatInp.onkeydown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    };

    $('#clear-history-btn').onclick = async () => {
        const ok = await modal(
            'Очистить историю',
            'Все сообщения будут удалены.'
        );
        if (!ok) return;

        try {
            await api.clearChatHistory();
            chatMsgs.innerHTML =
                '<div class="message system"><p>История очищена.</p></div>';
        } catch (e) {
            toast(`✗ ${e.message}`, 'error');
        }
    };

    // ─── Ingest System ──────────────────────────
    let selFiles = [];

    $('#ingest-file').onchange = () => {
        selFiles = Array.from($('#ingest-file').files);
        const label = document.querySelector('label[for="ingest-file"]');

        if (selFiles.length) {
            const totalSize = selFiles.reduce((s, f) => s + f.size, 0);
            label.textContent = `📎 ${selFiles.length} файл(ов) (${(totalSize / 1024).toFixed(1)} KB)`;
            label.style.borderColor = 'var(--primary)';
            label.style.color = 'var(--text)';
        }
    };

    function clearFiles() {
        selFiles = [];
        $('#ingest-file').value = '';
        const label = document.querySelector('label[for="ingest-file"]');
        if (label) {
            label.textContent = '📎 Выберите файлы (PDF, DOCX, TXT, MD, XML)';
            label.style.borderColor = '';
            label.style.color = '';
        }
    }

    // Ingest type sub-tabs
    let ci = localStorage.getItem('graphrag_ingest_type') || 'text';

    function apIng() {
        $$('.ingest-type-btn[data-ingest]').forEach((b) =>
            b.classList.remove('active')
        );
        $(`.ingest-type-btn[data-ingest="${ci}"]`)?.classList.add('active');
        $$('.ingest-card').forEach((c) => c.classList.remove('active'));
        $(`#ingest-card-${ci}`)?.classList.add('active');
    }

    apIng();

    $$('.ingest-type-btn[data-ingest]').forEach((b) => {
        b.addEventListener('click', () => {
            ci = b.dataset.ingest;
            localStorage.setItem('graphrag_ingest_type', ci);
            apIng();
        });
    });

    // Document sub-tabs (upload / list)
    let cd = localStorage.getItem('graphrag_docstab') || 'upload';

    function apDoc() {
        $$('.ingest-type-btn[data-docstab]').forEach((b) =>
            b.classList.remove('active')
        );
        $(`.ingest-type-btn[data-docstab="${cd}"]`)?.classList.add('active');
        $$('.docstab-card').forEach((c) => c.classList.remove('active'));
        $(`#docstab-${cd}`)?.classList.add('active');

        if (cd === 'list') {
            dPage = 1;
            loadDocs();
            loadGraphStats();
        }
    }

    apDoc();

    $$('.ingest-type-btn[data-docstab]').forEach((b) => {
        b.addEventListener('click', () => {
            cd = b.dataset.docstab;
            localStorage.setItem('graphrag_docstab', cd);
            apDoc();
        });
    });

    function resetIngestForm() {
        $('#ingest-title').value = '';
        $('#ingest-text').value = '';
        $('#ingest-url').value = '';
        $('#url-title').value = '';
        clearFiles();
        $('#ingest-clearance').value = '0';
        $('#ingest-department').value = 'all';
    }

    $('#ingest-submit-btn').onclick = async () => {
        const cl = $('#ingest-clearance').value;
        const dp = $('#ingest-department').value;

        try {
            if (ci === 'text') {
                const ti = $('#ingest-title').value.trim();
                const tx = $('#ingest-text').value.trim();

                if (!tx) {
                    alert('Введите текст');
                    return;
                }

                const progressToast = toast('⏳ Загрузка...', 'info');
                try {
                    const r = await api.ingestText(ti || 'Без названия', tx, cl, dp);
                    const res = await poll(r.document_id, progressToast);

                    if (res === 'ok') {
                        updT(progressToast, '✓ Загружено', 'success');
                        resetIngestForm();
                    } else {
                        updT(progressToast, '✗ Ошибка', 'error');
                    }
                } catch (e) {
                    const isWarning = (e.message || '').includes('уже загружен');
                    updT(
                        progressToast,
                        `✗ ${e.message}`,
                        isWarning ? 'warning' : 'error'
                    );
                }
                setTimeout(() => progressToast?.remove(), 6000);
            } else if (ci === 'file') {
                if (!selFiles.length) {
                    alert('Выберите файлы');
                    return;
                }

                const CONCURRENCY = 3; // одновременных загрузок
                const totalFiles = selFiles.length;

                // Сводный тост с прогрессом всех файлов
                const summaryToast = toast('⏳ Подготовка...', 'info', { sticky: true });
                
                let okCount = 0;
                let failCount = 0;
                let completedCount = 0;
                let nextIndex = 0;
                const resultsLog = []; // {name, status, error, time}

                function updateSummary() {
                    const done = okCount + failCount;
                    const remaining = totalFiles - done;
                    updT(summaryToast,
                        `📊 ${done}/${totalFiles} (${okCount} ✓, ${failCount} ✗)${remaining > 0 ? ` · в очереди ${remaining}` : ''}`,
                        'info');
                }

                // Обработка одного файла с повторными попытками при сетевых ошибках
                async function processOne(file) {
                    const startTime = new Date();

                    let docId;
                    // Retry upload до 2 раз
                    for (let uploadAttempt = 0; uploadAttempt < 2; uploadAttempt++) {
                        try {
                            const r = await api.ingestFile(file, cl, dp);
                            docId = r.document_id;
                            break;
                        } catch (e) {
                            if (uploadAttempt === 1) {
                                const endTime = new Date();
                                resultsLog.push({ name: file.name, status: '❌ Ошибка загрузки', error: e.message, time: (endTime - startTime) / 1000 });
                                return { ok: false, error: e.message };
                            }
                            await new Promise(r => setTimeout(r, 1000));
                        }
                    }

                    // Poll статуса с retry при временных сетевых ошибках
                    const maxPolls = 90;
                    const pollInterval = 1500;
                    let consecutiveErrors = 0;
                    const maxConsecutiveErrors = 5;

                    for (let i = 0; i < maxPolls; i++) {
                        await new Promise(r => setTimeout(r, pollInterval));
                        try {
                            const s = await api.getIngestStatus(docId);
                            consecutiveErrors = 0; // сброс счётчика ошибок
                            if (s.status === 'completed') {
                                const endTime = new Date();
                                resultsLog.push({ name: file.name, status: '✅ Успех', error: null, time: (endTime - startTime) / 1000 });
                                return { ok: true };
                            }
                            if (s.status === 'failed') {
                                const endTime = new Date();
                                const errMsg = s.error || 'Неизвестная ошибка';
                                resultsLog.push({ name: file.name, status: '❌ Ошибка обработки', error: errMsg, time: (endTime - startTime) / 1000 });
                                return { ok: false, error: errMsg };
                            }
                        } catch {
                            consecutiveErrors++;
                            if (consecutiveErrors >= maxConsecutiveErrors) {
                                const endTime = new Date();
                                resultsLog.push({ name: file.name, status: '❌ Ошибка сети', error: `Нет ответа от сервера (${consecutiveErrors} попыток подряд)`, time: (endTime - startTime) / 1000 });
                                return { ok: false, error: 'Сетевые ошибки при опросе статуса' };
                            }
                            // Уменьшаем интервал между retry при ошибках
                            await new Promise(r => setTimeout(r, 500));
                        }
                    }
                    const endTime = new Date();
                    resultsLog.push({ name: file.name, status: '⏱️ Таймаут', error: 'Превышено время ожидания (90×1.5с)', time: (endTime - startTime) / 1000 });
                    return { ok: false, error: 'Таймаут обработки' };
                }

                // Динамическая очередь: как только файл завершается — запускается следующий
                async function runDynamicQueue() {
                    const slots = new Array(CONCURRENCY).fill(null); // null = свободен
                    
                    for (let i = 0; i < CONCURRENCY && i < totalFiles; i++) {
                        slots[i] = processOne(selFiles[i]);
                        nextIndex = i + 1;
                    }

                    while (completedCount < totalFiles) {
                        const donePromises = slots.map((p, idx) => p ? p.then(r => ({ idx, r })) : null).filter(Boolean);
                        const { idx: finishedIdx, r: result } = await Promise.race(donePromises);
                        
                        completedCount++;
                        if (result.ok) {
                            okCount++;
                        } else {
                            failCount++;
                        }
                        updateSummary();

                        if (nextIndex < totalFiles) {
                            slots[finishedIdx] = processOne(selFiles[nextIndex]);
                            nextIndex++;
                        } else {
                            slots[finishedIdx] = null;
                        }
                    }
                }

                await runDynamicQueue();

                // ── Generate and download upload log ──
                try {
                    const now = new Date();
                    const dateStr = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
                    const logLines = [
                        `=== Лог загрузки файлов — ${now.toLocaleString('ru-RU')} ===`,
                        `Всего файлов: ${totalFiles}`,
                        `Успешно: ${okCount}`,
                        `С ошибками: ${failCount}`,
                        ``,
                        `--- Пофайловый отчёт ---`,
                    ];
                    for (const entry of resultsLog) {
                        const timeStr = entry.time != null ? ` (${entry.time.toFixed(1)}с)` : '';
                        logLines.push(`[${entry.status}] ${entry.name}${timeStr}`);
                        if (entry.error) {
                            logLines.push(`  Причина: ${entry.error}`);
                        }
                    }
                    logLines.push('');
                    logLines.push('=== Конец лога ===');

                    const logText = logLines.join('\n');
                    const blob = new Blob([logText], { type: 'text/plain;charset=utf-8' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `upload-log-${dateStr}.txt`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                } catch (logErr) {
                    // Non-critical — don't interrupt the flow
                    console.warn('Failed to generate upload log', logErr);
                }

                // Финальный статус
                if (failCount === 0) {
                    updT(summaryToast, `✅ Все ${okCount} файлов загружены · лог скачан`, 'success');
                    resetIngestForm();
                } else if (failCount === totalFiles) {
                    updT(summaryToast, `❌ Все ${failCount} файлов с ошибкой · лог скачан`, 'error');
                } else {
                    updT(summaryToast, `⚠️ ${okCount} загружено, ${failCount} с ошибками · лог скачан`, 'warning');
                }
            } else if (ci === 'url') {
                const u = $('#ingest-url').value.trim();
                const ti = $('#url-title').value.trim();

                if (!u) {
                    alert('Введите URL');
                    return;
                }

                const progressToast = toast('⏳ Загрузка по URL...', 'info');
                try {
                    const r = await api.ingestUrl(u, ti, cl, dp);
                    const res = await poll(r.document_id, progressToast);

                    if (res === 'ok') {
                        updT(progressToast, '✓ URL загружен', 'success');
                        resetIngestForm();
                    } else {
                        updT(progressToast, '✗ Ошибка', 'error');
                    }
                } catch (e) {
                    const isWarning = (e.message || '').includes('уже загружен');
                    updT(
                        progressToast,
                        `✗ ${e.message}`,
                        isWarning ? 'warning' : 'error'
                    );
                }
                setTimeout(() => progressToast?.remove(), 6000);
            }
        } catch (e) {
            toast(`✗ ${e.message}`, 'error');
        }
    };

    // ─── Infrastructure Display ─────────────────
    const INFRA_ICONS = {
        neo4j: '🔗',
        minio: '🗄️',
        qdrant: '🧮',
        ollama: '🤖',
        openwebui: '💬',
        mailpit: '📬',
        jaeger: '🔍',
        grafana: '📊',
        prometheus: '📈',
        pgadmin: '🐘',
    };

    const INFRA_ORDER = [
        'neo4j',
        'minio',
        'qdrant',
        'ollama',
        'openwebui',
        'mailpit',
        'jaeger',
        'grafana',
        'prometheus',
        'pgadmin',
    ];

    async function loadInfra() {
        const tbody = $('#infra-tbody');
        tbody.innerHTML =
            '<tr><td colspan="5" style="padding:1rem;text-align:center;' +
            'color:var(--text-muted);">⏳ Загрузка...</td></tr>';

        try {
            const cfg = await api.getServiceConfig();
            const svcMap = cfg.services || {};
            const rows = [];

            for (const key of INFRA_ORDER) {
                const svc = svcMap[key];
                if (!svc) continue;

                const url = svc.browser_url || svc.rest_url || svc.base_url || '';
                if (!url) continue;

                const icon = INFRA_ICONS[key] || '🔧';
                const user = svc.user || '—';
                const pass = svc.password || '—';

                const dbInfo =
                    svc.db_user && svc.db_password
                        ? `<br><span style="font-size:11px;color:var(--text-muted);">` +
                        `🗄️ БД: ${svc.db_user} / ${svc.db_password}</span>`
                        : '';

                rows.push(`<tr>
                    <td style="padding:0.5rem;white-space:nowrap;">
                        ${icon} ${svc.label || key}
                    </td>
                    <td style="padding:0.5rem;font-size:0.8rem;max-width:250px;word-break:break-all;">
                        <a href="${url}" target="_blank" rel="noopener"
                            style="color:var(--primary);">${url}</a>
                    </td>
                    <td style="padding:0.5rem;font-size:0.85rem;">
                        <code>${user}</code>${dbInfo}
                    </td>
                    <td style="padding:0.5rem;font-size:0.85rem;">
                        <code>${pass}</code>
                    </td>
                    <td style="padding:0.5rem;text-align:center;white-space:nowrap;">
                        <a href="${url}" target="_blank" rel="noopener"
                            class="btn btn-sm" style="color:var(--primary);">🚀 Открыть</a>
                    </td>
                </tr>`);
            }

            tbody.innerHTML = rows.length
                ? rows.join('')
                : '<tr><td colspan="5" style="padding:1rem;text-align:center;' +
                'color:var(--text-muted);">Нет доступных сервисов</td></tr>';
        } catch (e) {
            tbody.innerHTML =
                `<tr><td colspan="5" style="padding:1rem;text-align:center;` +
                `color:var(--error);">Ошибка: ${e.message}</td></tr>`;
        }
    }

    async function loadGraphStats() {
        try {
            const s = await api.getGraphStats();
            const g = s?.graph || {};
            const stats = $('#graph-stats');

            if (stats) {
                const btnHtml = '<button id="clear-all-btn" class="btn btn-sm" style="margin-left:auto;color:var(--error);border-color:var(--error);" title="Удалить ВСЕ документы, граф, векторы и S3">🗑️ Очистить всё</button>';
                stats.innerHTML =
                    `<span>📊 Узлы: ${g.node_count ?? '—'}</span>` +
                    `<span>🔗 Связи: ${g.edge_count ?? '—'}</span>` +
                    `<span>📄 Документы: ${g.documents ?? '—'}</span>` +
                    `<span>🧩 Сущности: ${g.entities ?? '—'}</span>` +
                    btnHtml;
                // Bind clear-all button after DOM update
                const clearBtn = stats.querySelector('#clear-all-btn');
                if (clearBtn) {
                    clearBtn.onclick = async () => {
                        const ok = await modal(
                            '🗑️ Очистить все данные',
                            'Вы уверены? Это действие НЕОБРАТИМО.\n\n' +
                            'Будут удалены:\n' +
                            '• Все документы из Neo4j\n' +
                            '• Все векторы из Qdrant\n' +
                            '• Все файлы из MinIO S3\n' +
                            '• Все сущности и связи графа знаний\n\n' +
                            'После очистки страница будет перезагружена.'
                        );
                        if (!ok) return;

                        const progressToast = toast('⏳ Очистка всех данных...', 'info', { sticky: true });
                        try {
                            const result = await api.clearGraphData();
                            updT(progressToast, `✅ ${result.message || 'Данные очищены'}`, 'success');
                            // Reload after a short delay
                            setTimeout(() => {
                                dPage = 1;
                                loadDocs();
                                loadGraphStats();
                            }, 1500);
                        } catch (e) {
                            updT(progressToast, `❌ ${e.message}`, 'error');
                        }
                    };
                }
            }
        } catch (e) {
            // Stats are non-critical; silently fail
        }
    }

    // ─── Tab Activation Hooks ───────────────────
    const origActivate = activateTab;
    activateTab = function (tn) {
        origActivate(tn);
        if (tn === 'infra') {
            loadInfra();
        }
    };

    const origSA2 = showApp;
    showApp = function (u) {
        origSA2(u);
        setTimeout(() => {
            api.getServiceConfig().catch(() => {});
        }, 500);
    };

    // ─── Document List & Pagination ─────────────
    async function loadDocs(p = 1) {
        dPage = p;

        const q = new URLSearchParams({
            page: p,
            page_size: 15,
            sort: $('#doc-sort')?.value || 'created_at',
            order: dOrder,
        });

        const de = $('#doc-filter-dept')?.value || 'all';
        if (de !== 'all') q.set('department', de);

        const cl = parseInt($('#doc-filter-clearance')?.value || '-1');
        if (cl >= 0) q.set('clearance', cl);

        try {
            const r = await fetch(`${API_B}/graph/documents?${q}`, {
                headers: api.headers,
            });
            if (!r.ok) throw new Error('Ошибка');

            const d = await r.json();
            dTotal = Math.ceil((d.total || 0) / 15) || 1;
            const docs = d.documents || [];

            if (docs.length === 0) {
                $('#docs-tbody').innerHTML =
                    '<tr><td colspan="6" style="padding:1rem;' +
                    'text-align:center;color:var(--text-muted);">Нет документов</td></tr>';
            } else {
                $('#docs-tbody').innerHTML = docs
                    .map((doc) => {
                        const deptOpts = deptList
                            .map(
                                (d) =>
                                    `<option value="${d.code}" ${doc.department === d.code ? 'selected' : ''
                                    }>${d.name}</option>`
                            )
                            .join('');

                        return `<tr>
                            <td style="padding:0.5rem;">
                                <span data-dl="${doc.id}"
                                    style="color:var(--primary);text-decoration:underline;
                                    cursor:pointer;" title="Скачать документ">
                                    ${doc.title || doc.id}
                                </span>
                            </td>
                            <td style="padding:0.5rem;text-align:center;">
                                <select data-ddept="${doc.id}" class="form-select"
                                    style="background-color:var(--bg-input);color:var(--text);width:130px;">
                                    ${deptOpts}
                                </select>
                            </td>
                            <td style="padding:0.5rem;text-align:center;">
                                <select data-dclr="${doc.id}" class="form-select"
                                    style="background-color:var(--bg-input);color:var(--text);width:130px;">
                                    ${[0, 1, 2, 3]
                                    .map(
                                        (v) =>
                                            `<option value="${v}" ${(doc.clearance_level ?? 0) === v ? 'selected' : ''
                                            }>${CLR[v]}</option>`
                                    )
                                    .join('')}
                                </select>
                            </td>
                            <td style="padding:0.5rem;text-align:center;">
                                ${doc.chunks ?? '—'}
                            </td>
                            <td style="padding:0.5rem;text-align:center;
                                font-size:0.8rem;color:var(--text-muted);">
                                ${doc.created_at
                                    ? new Date(doc.created_at).toLocaleString('ru-RU')
                                    : '—'
                                }
                            </td>
                            <td style="padding:0.5rem;text-align:center;white-space:nowrap;">
                                <button data-dsave="${doc.id}" class="btn btn-sm"
                                    style="color:var(--success);margin-right:0.2rem;">💾</button>
                                <button data-dd="${doc.id}" class="btn btn-sm"
                                    style="color:var(--error);">🗑️</button>
                            </td>
                        </tr>`;
                    })
                    .join('');
            }

            // Save document
            document.querySelectorAll('[data-dsave]').forEach((b) => {
                b.onclick = async () => {
                    const docId = b.dataset.dsave;
                    const dept =
                        document.querySelector(`[data-ddept="${docId}"]`)?.value ||
                        'all';
                    const clr =
                        document.querySelector(`[data-dclr="${docId}"]`)?.value ||
                        '0';
                    try {
                        await api.updateDocument(docId, clr, dept);
                        toast('✓ Документ обновлён', 'success');
                    } catch (e) {
                        toast(`✗ ${e.message}`, 'error');
                    }
                };
            });

            // Download document
            document.querySelectorAll('[data-dl]').forEach((b) => {
                b.onclick = () =>
                    downloadDoc(b.dataset.dl, b.textContent.trim());
            });

            // Delete document
            document.querySelectorAll('[data-dd]').forEach((b) => {
                b.onclick = async () => {
                    const id = b.dataset.dd;
                    const ok = await modal('Удалить', `"${id}"?`);
                    if (!ok) return;

                    try {
                        await fetch(`${API_B}/graph/document/${id}`, {
                            method: 'DELETE',
                            headers: api.headers,
                        });
                        toast('✓ Удалён', 'success');
                        loadDocs(dPage);
                        loadGraphStats();
                    } catch (e) {
                        toast(`✗ ${e.message}`, 'error');
                    }
                };
            });

            // Pagination
            const pag = $('#docs-pagination');
            pag.style.display = dTotal > 1 ? 'flex' : 'none';
            $('#docs-page-info').textContent =
                `Страница ${dPage} из ${dTotal}`;
            $('#docs-prev').disabled = dPage <= 1;
            $('#docs-next').disabled = dPage >= dTotal;
        } catch (e) {
            $('#docs-tbody').innerHTML =
                `<tr><td colspan="6" style="padding:1rem;color:var(--error);">${e.message}</td></tr>`;
        }
    }

    // Document toolbar handlers
    $('#doc-filter-dept').onchange = () => {
        dPage = 1;
        loadDocs();
    };
    $('#doc-filter-clearance').onchange = () => {
        dPage = 1;
        loadDocs();
    };
    $('#doc-sort').onchange = () => {
        dPage = 1;
        loadDocs();
    };
    $('#doc-order-btn').onclick = () => {
        dOrder = dOrder === 'desc' ? 'asc' : 'desc';
        $('#doc-order-btn').textContent = dOrder === 'desc' ? '↓' : '↑';
        loadDocs();
    };
    $('#docs-prev').onclick = () => {
        if (dPage > 1) loadDocs(dPage - 1);
    };
    $('#docs-next').onclick = () => {
        if (dPage < dTotal) loadDocs(dPage + 1);
    };

    // ─── User Management ────────────────────────
    async function loadUsers(p = 1) {
        uPage = p;

        const q = new URLSearchParams({
            page: p,
            page_size: 15,
            sort: $('#user-sort')?.value || 'id',
            order: uOrder,
        });

        const role = $('#user-filter-role')?.value || 'all';
        if (role !== 'all') q.set('role', role);

        const dept = $('#user-filter-dept')?.value || 'all';
        if (dept !== 'all') q.set('department', dept);

        const clr = parseInt($('#user-filter-clr')?.value || '-1');
        if (clr >= 0) q.set('clearance', clr);

        const srch = $('#user-search')?.value.trim();
        if (srch) q.set('email', srch);

        try {
            const d = await api.getUsers(Object.fromEntries(q));
            uTotal = Math.ceil((d.total || 0) / 15) || 1;
            const tbody = $('#users-tbody');

            tbody.innerHTML = d.users
                .map((u) => {
                    const deptOpts = deptList
                        .map(
                            (d) =>
                                `<option value="${d.code}" ${u.department === d.code ? 'selected' : ''
                                }>${d.name}</option>`
                        )
                        .join('');

                    return `<tr>
                        <td style="padding:0.5rem;">${u.id}</td>
                        <td style="padding:0.5rem;">${u.username || '—'}</td>
                        <td style="padding:0.5rem;">${u.email}</td>
                        <td style="padding:0.5rem;text-align:center;">
                            <select data-ur="${u.id}" class="form-select"
                                style="background-color:var(--bg-input);color:var(--text);width:130px;">
                                <option value="viewer" ${u.role === 'viewer' ? 'selected' : ''
                                    }>Читатель</option>
                                <option value="analyst" ${u.role === 'analyst' ? 'selected' : ''
                                    }>Аналитик</option>
                                <option value="admin" ${u.role === 'admin' ? 'selected' : ''
                                    }>Администратор</option>
                            </select>
                        </td>
                        <td style="padding:0.5rem;text-align:center;">
                            <select data-ud="${u.id}" class="form-select"
                                style="background-color:var(--bg-input);color:var(--text);width:130px;">
                                ${deptOpts}
                            </select>
                        </td>
                        <td style="padding:0.5rem;text-align:center;">
                            <select data-uc="${u.id}" class="form-select"
                                style="background-color:var(--bg-input);color:var(--text);width:130px;">
                                <option value="0" ${u.clearance_level === 0 ? 'selected' : ''
                                    }>Открытый</option>
                                <option value="1" ${u.clearance_level === 1 ? 'selected' : ''
                                    }>Конфиденциальный</option>
                                <option value="2" ${u.clearance_level === 2 ? 'selected' : ''
                                    }>Секретный</option>
                                <option value="3" ${u.clearance_level === 3 ? 'selected' : ''
                                    }>Сов. секретно</option>
                            </select>
                        </td>
                        <td style="padding:0.5rem;text-align:center;">
                            <input type="checkbox" data-ua="${u.id}"
                                ${u.is_active ? 'checked' : ''}
                                style="width:16px;height:16px;accent-color:var(--success);">
                        </td>
                        <td style="padding:0.5rem;text-align:center;white-space:nowrap;">
                            <button data-imp="${u.id}" class="btn btn-sm"
                                style="color:var(--primary);${u.id === curUser?.id ? 'display:none;' : ''
                                }"
                                title="Войти как пользователь">🎭</button>
                            <button data-save="${u.id}" class="btn btn-sm"
                                style="color:var(--success);">💾</button>
                            <button data-del="${u.id}" class="btn btn-sm"
                                style="color:var(--error);">🗑️</button>
                        </td>
                    </tr>`;
                })
                .join('');

            // Impersonate handler
            tbody.querySelectorAll('[data-imp]').forEach((b) => {
                if (parseInt(b.dataset.imp) === curUser?.id) return;
                b.onclick = async () => {
                    const id = parseInt(b.dataset.imp);
                    try {
                        await api.impersonate(id);
                        const me = await api.getMe();
                        localStorage.setItem('graphrag_user', JSON.stringify(me));
                        history.replaceState(null, '', '#chat');
                        showApp(me);
                        toast('🎭 Вы вошли как ' + me.email, 'info');
                    } catch (e) {
                        api.restoreAdminToken();
                        toast(`✗ ${e.message}`, 'error');
                    }
                };
            });

            // Save handler
            tbody.querySelectorAll('[data-save]').forEach((b) => {
                b.onclick = async () => {
                    const uid = parseInt(b.dataset.save);
                    try {
                        await api.updateUser(uid, {
                            role: document.querySelector(`[data-ur="${uid}"]`).value,
                            department: document.querySelector(`[data-ud="${uid}"]`)
                                .value,
                            clearance_level: parseInt(
                                document.querySelector(`[data-uc="${uid}"]`).value
                            ),
                            is_active: document.querySelector(`[data-ua="${uid}"]`)
                                .checked,
                        });
                        toast('✓ Обновлён', 'success');
                    } catch (e) {
                        toast(`✗ ${e.message}`, 'error');
                    }
                };
            });

            // Delete handler
            tbody.querySelectorAll('[data-del]').forEach((b) => {
                b.onclick = async () => {
                    const uid = parseInt(b.dataset.del);
                    const ok = await modal('Удалить', `Удалить #${uid}?`);
                    if (!ok) return;
                    try {
                        await api.deleteUser(uid);
                        toast('✓ Удалён', 'success');
                        loadUsers(uPage);
                    } catch (e) {
                        toast(`✗ ${e.message}`, 'error');
                    }
                };
            });

            // Pagination
            const pag = $('#users-pagination');
            pag.style.display = uTotal > 1 ? 'flex' : 'none';
            $('#users-page-info').textContent =
                `Страница ${uPage} из ${uTotal}`;
            $('#users-prev').disabled = uPage <= 1;
            $('#users-next').disabled = uPage >= uTotal;
        } catch (e) {
            $('#users-tbody').innerHTML =
                `<tr><td colspan="8" style="padding:1rem;color:var(--error);">${e.message}</td></tr>`;
        }
    }

    // User toolbar handlers
    $('#user-search').oninput = () => {
        clearTimeout(uTimer);
        uTimer = setTimeout(() => {
            uPage = 1;
            loadUsers();
        }, 400);
    };
    $('#user-filter-role').onchange = () => {
        uPage = 1;
        loadUsers();
    };
    $('#user-filter-dept').onchange = () => {
        uPage = 1;
        loadUsers();
    };
    $('#user-filter-clr').onchange = () => {
        uPage = 1;
        loadUsers();
    };
    $('#user-sort').onchange = () => {
        uPage = 1;
        loadUsers();
    };
    $('#user-order-btn').onclick = () => {
        uOrder = uOrder === 'asc' ? 'desc' : 'asc';
        $('#user-order-btn').textContent = uOrder === 'asc' ? '↑' : '↓';
        loadUsers();
    };
    $('#users-prev').onclick = () => {
        if (uPage > 1) loadUsers(uPage - 1);
    };
    $('#users-next').onclick = () => {
        if (uPage < uTotal) loadUsers(uPage + 1);
    };

    // ─── Test Runner (SSE streaming) ────────────
    $('#run-tests-btn')?.addEventListener('click', async () => {
        const btn = $('#run-tests-btn');
        const out = $('#tests-output');
        const status = $('#tests-status');

        btn.disabled = true;
        btn.textContent = '⏳ Выполнение...';
        status.textContent = 'Тесты запущены, ожидайте...';
        out.innerHTML = '<span class="info">⏳ Запуск pytest...</span>\n';

        try {
            const response = await fetch(`${API_B}/tests/run`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${api.token}`,
                },
            });

            if (!response.ok) {
                const e = await response.json().catch(() => ({}));
                throw new Error(
                    e.detail || e.message || `HTTP ${response.status}`
                );
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;

                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;

                    try {
                        const parsed = JSON.parse(data);

                        if (parsed.event === 'line') {
                            const text = parsed.data || '';
                            let cls = 'info';
                            if (/PASSED/.test(text)) cls = 'pass';
                            else if (/FAILED/.test(text)) cls = 'fail';
                            else if (/ERROR/.test(text)) cls = 'err';
                            else if (/^={3,}/.test(text) || /^_{3,}/.test(text))
                                cls = 'head';
                            else if (
                                /passed|failed|error/i.test(text) &&
                                /\d/.test(text)
                            )
                                cls = 'sum';

                            const span = document.createElement('span');
                            span.className = cls;
                            span.textContent = text + '\n';
                            out.appendChild(span);
                            out.scrollTop = out.scrollHeight;
                        } else if (parsed.event === 'status') {
                            status.textContent = parsed.data;
                        } else if (parsed.event === 'done') {
                            const d = parsed.data;

                            // Plural helper for Russian
                            const pl = (n, w) => {
                                const forms = w.split('|');
                                if (n % 10 === 1 && n % 100 !== 11)
                                    return forms[0];
                                if (
                                    n % 10 >= 2 &&
                                    n % 10 <= 4 &&
                                    (n % 100 < 10 || n % 100 >= 20)
                                )
                                    return forms[1];
                                return forms[2];
                            };

                            if (d.success) {
                                status.innerHTML =
                                    `<span style="color:var(--success);">✅ Все ${d.total} ` +
                                    `${pl(d.total, 'тест|теста|тестов')} пройдены!</span>`;
                            } else {
                                const parts = [];
                                if (d.passed) parts.push(`${d.passed} ✅`);
                                if (d.failed) parts.push(`${d.failed} ❌`);
                                if (d.errors) parts.push(`${d.errors} ⚠️`);
                                status.innerHTML =
                                    `<span style="color:${d.failed || d.errors ? 'var(--error)' : 'var(--warning)'
                                    };">⚠️ ${parts.join(', ')} из ${d.total}</span>`;
                            }
                        } else if (parsed.event === 'error') {
                            const span = document.createElement('span');
                            span.className = 'err';
                            span.textContent = '❌ ' + parsed.data + '\n';
                            out.appendChild(span);
                            status.innerHTML =
                                '<span style="color:var(--error);">❌ Ошибка</span>';
                        }
                    } catch {
                        const span = document.createElement('span');
                        span.className = 'info';
                        span.textContent = data + '\n';
                        out.appendChild(span);
                    }
                }
            }
        } catch (e) {
            status.innerHTML =
                `<span style="color:var(--error);">❌ ${e.message}</span>`;
            const span = document.createElement('span');
            span.className = 'err';
            span.textContent = 'Ошибка: ' + e.message + '\n';
            out.appendChild(span);
        } finally {
            btn.disabled = false;
            btn.textContent = '▶️ Запустить тесты';
        }
    });

    // ─── Auto-Login on Page Load ────────────────
    if (api.token) {
        api.getMe()
            .then((u) => {
                localStorage.setItem('graphrag_user', JSON.stringify(u));
                showApp(u);
            })
            .catch(() => api.clearToken());
    }
});