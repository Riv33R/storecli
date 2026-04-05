/**
 * app.js — StorCLI RAID Monitor Dashboard v2.2
 *
 * Поддержка:
 *  - Множество хостов с CRUD
 *  - Множество контроллеров
 *  - Управление: Locate, SMART, Rebuild, Hot Spare, CC, Patrol Read, Alarm
 *  - Подтверждение операционных команд
 */

// ────────────────────────────────────────────────────────
// Состояние
// ────────────────────────────────────────────────────────
let isLoading = false;
let hosts = [];
let activeHostId = null;
let pendingAction = null; // Для модалки подтверждения

// ────────────────────────────────────────────────────────
// Утилиты
// ────────────────────────────────────────────────────────

function badge(state, health) {
    return `<span class="status-badge ${health}"><span class="dot"></span>${esc(state)}</span>`;
}

function esc(t) {
    if (t == null) return '';
    const d = document.createElement('div');
    d.textContent = String(t);
    return d.innerHTML;
}

function rowCls(h) {
    return h === 'degraded' ? 'row-degraded' : h === 'critical' ? 'row-critical' : '';
}

function fmtTime(iso) {
    try {
        return new Date(iso).toLocaleString('ru-RU', {
            day:'2-digit', month:'2-digit', year:'numeric',
            hour:'2-digit', minute:'2-digit', second:'2-digit',
        });
    } catch { return iso; }
}

/**
 * Парсит EID:Slot строку вида "252:0" в { eid, slot }.
 */
function parseEidSlot(eidSlot) {
    const parts = String(eidSlot).split(':');
    return { eid: parts[0] || '', slot: parts[1] || '' };
}

/**
 * Парсит DG/VD строку вида "0/0" в { dg, vd }.
 */
function parseDgVd(dgVd) {
    const parts = String(dgVd).split('/');
    return { dg: parseInt(parts[0]) || 0, vd: parseInt(parts[1]) || 0 };
}

// ────────────────────────────────────────────────────────
// Loader & Error
// ────────────────────────────────────────────────────────
function showLoader() {
    document.getElementById('loader').classList.add('active');
    const b = document.getElementById('btn-refresh'); b.classList.add('loading'); b.disabled = true;
}
function hideLoader() {
    document.getElementById('loader').classList.remove('active');
    const b = document.getElementById('btn-refresh'); b.classList.remove('loading'); b.disabled = false;
}
function showError(title, msg) {
    document.getElementById('error-title').textContent = title;
    document.getElementById('error-message').textContent = msg;
    document.getElementById('error-banner').classList.add('visible');
}
function hideError() { document.getElementById('error-banner').classList.remove('visible'); }

// ────────────────────────────────────────────────────────
// Секции
// ────────────────────────────────────────────────────────
function toggleSection(id) {
    const b = document.getElementById(`body-${id}`);
    const t = document.getElementById(`toggle-${id}`);
    if (b && t) { b.classList.toggle('collapsed'); t.classList.toggle('collapsed'); }
}

// ────────────────────────────────────────────────────────
// Хосты
// ────────────────────────────────────────────────────────
async function loadHosts() {
    try {
        const r = await fetch('/api/hosts');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const res = await r.json();
        if (res.success && res.hosts) {
            hosts = res.hosts;
            renderHostTabs();
            if (hosts.length > 0) selectHost(hosts[0].id);
            else showError('Нет серверов', 'Нажмите «Добавить» чтобы настроить первый сервер.');
        }
    } catch (e) { showError('Ошибка', `Не удалось загрузить хосты: ${e.message}`); }
}

function renderHostTabs() {
    document.getElementById('host-tabs').innerHTML = hosts.map(h => `
        <button class="host-tab" id="host-tab-${h.id}" onclick="selectHost('${h.id}')" title="${esc(h.description||h.host)}">
            <span class="host-tab-indicator" id="host-indicator-${h.id}"></span>
            <div class="host-tab-content">
                <span class="host-tab-name">${esc(h.name)}</span>
                <span class="host-tab-address">${esc(h.host)}:${h.port}</span>
            </div>
        </button>`).join('');
}

function selectHost(hostId) {
    activeHostId = hostId;
    document.querySelectorAll('.host-tab').forEach(t => t.classList.remove('active'));
    const tab = document.getElementById(`host-tab-${hostId}`);
    if (tab) tab.classList.add('active');
    fetchRaidStatus(hostId);
}

function refreshCurrentHost() { if (activeHostId) fetchRaidStatus(activeHostId); }

// ────────────────────────────────────────────────────────
// Host CRUD Modal
// ────────────────────────────────────────────────────────
function openModal() { document.getElementById('host-modal').classList.add('active'); }
function closeModal() {
    document.getElementById('host-modal').classList.remove('active');
    document.getElementById('host-form').reset();
    document.getElementById('form-host-id').value = '';
    document.getElementById('form-mode').value = 'create';
    document.getElementById('password-hint').style.display = 'none';
    toggleAuthFields();
}

function toggleAuthFields() {
    const m = document.getElementById('form-ssh-auth').value;
    document.getElementById('auth-password-fields').style.display = m === 'password' ? '' : 'none';
    document.getElementById('auth-key-fields').style.display = m === 'key' ? '' : 'none';
}

function openAddHostModal() {
    closeModal();
    document.getElementById('modal-title').textContent = 'Добавить сервер';
    document.getElementById('form-submit-btn').innerHTML = '<span class="icon" style="transform:none !important;">+</span> Добавить';
    document.getElementById('form-mode').value = 'create';
    openModal();
}

async function openEditHostModal(hostId) {
    closeModal();
    document.getElementById('modal-title').textContent = 'Редактировать сервер';
    document.getElementById('form-submit-btn').innerHTML = '<span class="icon" style="transform:none !important;">💾</span> Сохранить';
    document.getElementById('form-mode').value = 'edit';
    document.getElementById('form-host-id').value = hostId;
    try {
        const r = await fetch(`/api/hosts/${encodeURIComponent(hostId)}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const res = await r.json();
        const h = res.host, ssh = h.ssh || {}, storcli = h.storcli || {};
        document.getElementById('form-name').value = h.name || '';
        document.getElementById('form-description').value = h.description || '';
        document.getElementById('form-ssh-host').value = ssh.host || '';
        document.getElementById('form-ssh-port').value = ssh.port || 22;
        document.getElementById('form-ssh-user').value = ssh.user || 'root';
        document.getElementById('form-ssh-auth').value = ssh.auth_method || 'password';
        document.getElementById('form-ssh-key').value = ssh.key_path || '';
        document.getElementById('form-ssh-passphrase').value = '';
        document.getElementById('form-ssh-password').value = '';
        document.getElementById('form-storcli-path').value = storcli.path || '/opt/lsi/storcli/storcli';
        const sel = document.getElementById('form-storcli-ctrl');
        const cv = storcli.controller || '/call';
        if (!Array.from(sel.options).some(o => o.value === cv)) {
            const opt = document.createElement('option'); opt.value = cv; opt.textContent = cv; sel.appendChild(opt);
        }
        sel.value = cv;
        if (ssh.password_masked) document.getElementById('password-hint').style.display = '';
        toggleAuthFields();
        openModal();
    } catch (e) { showError('Ошибка', `Загрузка хоста: ${e.message}`); }
}

async function saveHost(event) {
    event.preventDefault();
    const mode = document.getElementById('form-mode').value;
    const hostId = document.getElementById('form-host-id').value;
    const payload = {
        name: document.getElementById('form-name').value.trim(),
        description: document.getElementById('form-description').value.trim(),
        ssh_host: document.getElementById('form-ssh-host').value.trim(),
        ssh_port: parseInt(document.getElementById('form-ssh-port').value) || 22,
        ssh_user: document.getElementById('form-ssh-user').value.trim() || 'root',
        ssh_auth_method: document.getElementById('form-ssh-auth').value,
        ssh_key_path: document.getElementById('form-ssh-key').value.trim(),
        ssh_password: document.getElementById('form-ssh-password').value,
        ssh_key_passphrase: document.getElementById('form-ssh-passphrase').value,
        storcli_path: document.getElementById('form-storcli-path').value.trim(),
        storcli_controller: document.getElementById('form-storcli-ctrl').value,
    };
    if (mode === 'edit' && !payload.ssh_password) payload.ssh_password_keep = true;
    try {
        const r = mode === 'edit'
            ? await fetch(`/api/hosts/${encodeURIComponent(hostId)}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) })
            : await fetch('/api/hosts', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail?.message || `HTTP ${r.status}`); }
        closeModal();
        await loadHosts();
        if (mode === 'edit') selectHost(hostId);
        else if (hosts.length > 0) selectHost(hosts[hosts.length - 1].id);
    } catch (e) { showError('Ошибка сохранения', e.message); }
    return false;
}

async function confirmDeleteHost(hostId) {
    const h = hosts.find(x => x.id === hostId);
    if (!confirm(`Удалить сервер «${h ? h.name : hostId}»?\n\nЭто действие необратимо.`)) return;
    try {
        const r = await fetch(`/api/hosts/${encodeURIComponent(hostId)}`, { method:'DELETE' });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail?.message || `HTTP ${r.status}`); }
        await loadHosts();
    } catch (e) { showError('Ошибка удаления', e.message); }
}

// ────────────────────────────────────────────────────────
// Действия: подтверждение и выполнение
// ────────────────────────────────────────────────────────

/**
 * Инициирует действие. Safe — сразу, operational — через модалку.
 */
function triggerAction(action, controllerIndex, opts = {}) {
    const actionData = { action, controller_index: controllerIndex, ...opts };

    // Получаем инфо о команде из глобального реестра (загружен при старте)
    // Для safe — сразу выполняем
    // Для operational — показываем подтверждение
    const level = opts._level || 'safe';
    const confirmText = opts._confirm || '';
    const label = opts._label || action;

    // Убираем вспомогательные поля
    delete actionData._level;
    delete actionData._confirm;
    delete actionData._label;

    if (level === 'operational') {
        // Показываем модалку подтверждения
        pendingAction = actionData;
        document.getElementById('confirm-text').textContent = confirmText;
        const hostObj = hosts.find(h => h.id === activeHostId);
        document.getElementById('confirm-host').textContent = `Сервер: ${hostObj ? hostObj.name : activeHostId}`;
        document.getElementById('confirm-action').textContent = `Действие: ${label}`;
        document.getElementById('confirm-modal').classList.add('active');
    } else {
        // Safe — сразу выполняем
        executeAction(actionData);
    }
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').classList.remove('active');
    pendingAction = null;
}

function executeConfirmedAction() {
    if (pendingAction) {
        const action = { ...pendingAction };
        closeConfirmModal();
        executeAction(action);
    }
}

async function executeAction(actionData) {
    if (!activeHostId) return;

    // Показываем loader для действия
    showLoader();

    try {
        const r = await fetch(`/api/action/${encodeURIComponent(activeHostId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(actionData),
        });

        const res = await r.json();

        if (r.ok && res.success) {
            showResultModal(true, res.result);
        } else {
            const detail = res.detail || {};
            showResultModal(false, {
                label: detail.label || actionData.action,
                output: detail.message || `Ошибка: HTTP ${r.status}`,
                command: '',
            });
        }
    } catch (e) {
        showResultModal(false, { label: actionData.action, output: `Ошибка сети: ${e.message}`, command: '' });
    } finally {
        hideLoader();
    }
}

// ────────────────────────────────────────────────────────
// Modal: Результат
// ────────────────────────────────────────────────────────

function showResultModal(success, result) {
    const title = document.getElementById('result-title');
    const status = document.getElementById('result-status');
    const meta = document.getElementById('result-meta');
    const output = document.getElementById('result-output');

    title.textContent = success ? '✅ Команда выполнена' : '❌ Ошибка выполнения';
    status.className = `result-status ${success ? 'result-success' : 'result-error'}`;
    status.textContent = result.label || '';
    meta.innerHTML = result.command ? `<code>${esc(result.command)}</code>` : '';
    output.textContent = result.output || 'Нет вывода';

    document.getElementById('result-modal').classList.add('active');
}

function closeResultModal() {
    document.getElementById('result-modal').classList.remove('active');
    // Обновляем данные хоста после действия
    if (activeHostId) fetchRaidStatus(activeHostId);
}

// ────────────────────────────────────────────────────────
// Рендеринг дашборда
// ────────────────────────────────────────────────────────

function renderDashboard(data) {
    renderOverallStatus(data.overall_status);
    if (data.host) renderHostInfo(data.host);
    if (data.host?.id) updateHostIndicator(data.host.id, data.overall_status);

    const container = document.getElementById('controllers-container');
    container.innerHTML = '';

    (data.controllers || []).forEach((ctrl, i) => {
        container.appendChild(renderControllerBlock(ctrl, i, data.controllers.length));
    });

    document.getElementById('last-update').textContent = fmtTime(data.timestamp);
    document.getElementById('footer-info').style.display = '';

    container.querySelectorAll('.controller-block').forEach((el, i) => {
        el.classList.remove('fade-in');
        setTimeout(() => el.classList.add('fade-in'), i * 120);
    });
}

function renderControllerBlock(ctrl, index, total) {
    const ci = ctrl.controller_index;
    const pfx = `c${ci}`;
    const c = ctrl.controller;
    const st = ctrl.overall_status;
    const block = document.createElement('div');
    block.className = 'controller-block';

    const header = total > 1 ? `
        <div class="controller-header ${st}">
            <div class="controller-header-left">
                <span class="controller-index">C${ci}</span>
                <div><div class="controller-model">${esc(c.model)}</div><div class="controller-serial">S/N: ${esc(c.serial_number)}</div></div>
            </div>
            <div class="controller-header-right">${badge(c.status, st)}</div>
        </div>` : '';

    const err = ctrl.error ? `<div class="controller-error"><span>⚠️</span> ${esc(ctrl.error)}</div>` : '';

    const cards = `
        <div class="stats-grid fade-in">
            <div class="stat-card"><div class="stat-label">Контроллер</div><div class="stat-value small">${esc(c.model)}</div></div>
            <div class="stat-card"><div class="stat-label">S/N</div><div class="stat-value small">${esc(c.serial_number)}</div></div>
            <div class="stat-card"><div class="stat-label">Статус</div><div class="stat-value small">${badge(c.status, st)}</div></div>
            <div class="stat-card"><div class="stat-label">Прошивка</div><div class="stat-value small">${esc(c.firmware_version)}</div></div>
            <div class="stat-card"><div class="stat-label">Память / Кэш</div><div class="stat-value small">${esc(c.memory_size)} / ${c.cache_size_mb} MB</div></div>
            <div class="stat-card"><div class="stat-label">VD / PD</div><div class="stat-value">${ctrl.virtual_drives.length} / ${ctrl.physical_drives.length}</div></div>
        </div>`;

    // Кнопки управления контроллером
    const ctrlActions = `
        <div class="ctrl-actions">
            <button class="action-btn" onclick="triggerAction('ctrl_event_log', ${ci}, {_level:'safe', _label:'Event Log'})" title="Event Log">📋 Event Log</button>
            <button class="action-btn action-btn-warn" onclick="triggerAction('ctrl_start_patrol', ${ci}, {_level:'operational', _confirm:'Запустить Patrol Read на C${ci}?', _label:'Start Patrol Read'})" title="Patrol Read">🔍 Patrol Read</button>
            <button class="action-btn action-btn-warn" onclick="triggerAction('ctrl_stop_patrol', ${ci}, {_level:'operational', _confirm:'Остановить Patrol Read на C${ci}?', _label:'Stop Patrol Read'})" title="Stop Patrol">⏹️ Stop Patrol</button>
            <button class="action-btn action-btn-warn" onclick="triggerAction('ctrl_silence_alarm', ${ci}, {_level:'operational', _confirm:'Выключить сигнал на C${ci}?', _label:'Silence Alarm'})" title="Silence Alarm">🔇 Silence Alarm</button>
        </div>`;

    // VD с кнопками действий
    const vd = tblSection(pfx+'-vd', '💿', 'Virtual Drives', ctrl.virtual_drives,
        ['DG/VD','RAID','State','Size','Access','Cache','Consist','Name','Действия'],
        v => {
            const {dg, vd: vdx} = parseDgVd(v.dg_vd);
            return `<td>${esc(v.dg_vd)}</td><td>${esc(v.type)}</td><td>${badge(v.state,v.health)}</td><td>${esc(v.size)}</td><td>${esc(v.access)}</td><td>${esc(v.cache)}</td><td>${esc(v.consistent)}</td><td>${esc(v.name)||'—'}</td>
            <td class="actions-cell">
                <div class="action-group">
                    <button class="action-btn-sm action-btn-warn" onclick="triggerAction('vd_start_cc',${ci},{vd_index:${vdx},_level:'operational',_confirm:'Запустить CC на VD ${v.dg_vd}?',_label:'Start CC'})" title="Start CC">✅</button>
                    <button class="action-btn-sm action-btn-warn" onclick="triggerAction('vd_stop_cc',${ci},{vd_index:${vdx},_level:'operational',_confirm:'Остановить CC на VD ${v.dg_vd}?',_label:'Stop CC'})" title="Stop CC">⏹️</button>
                </div>
            </td>`;
        });

    // PD с кнопками действий
    const pd = tblSection(pfx+'-pd', '💾', 'Physical Drives', ctrl.physical_drives,
        ['EID:Slot','DID','State','DG','Size','Intf','Media','Model','Действия'],
        p => {
            const {eid, slot} = parseEidSlot(p.eid_slot);
            const dg = p.drive_group;
            const isHotSpare = String(p.state).toLowerCase().includes('hotspare') || ['ghs','dhs'].includes(String(p.state).toLowerCase());
            return `<td>${esc(p.eid_slot)}</td><td>${esc(p.did)}</td><td>${badge(p.state,p.health)}</td><td>${esc(p.drive_group)}</td><td>${esc(p.size)}</td><td>${esc(p.interface)}</td><td>${esc(p.media)}</td><td>${esc(p.model)}</td>
            <td class="actions-cell">
                <div class="action-group">
                    <button class="action-btn-sm" onclick="triggerAction('pd_locate_start',${ci},{eid:'${eid}',slot:'${slot}',_level:'safe',_label:'LED ON'})" title="LED ON">📍</button>
                    <button class="action-btn-sm" onclick="triggerAction('pd_locate_stop',${ci},{eid:'${eid}',slot:'${slot}',_level:'safe',_label:'LED OFF'})" title="LED OFF">💡</button>
                    <button class="action-btn-sm" onclick="triggerAction('pd_smart',${ci},{eid:'${eid}',slot:'${slot}',_level:'safe',_label:'SMART'})" title="SMART">📊</button>
                    ${!isHotSpare ? `<button class="action-btn-sm action-btn-warn" onclick="triggerAction('pd_add_hotspare_global',${ci},{eid:'${eid}',slot:'${slot}',_level:'operational',_confirm:'Назначить ${p.eid_slot} Global HS?',_label:'Global HS'})" title="Global HS">♨️</button>` : ''}
                    ${isHotSpare ? `<button class="action-btn-sm action-btn-warn" onclick="triggerAction('pd_remove_hotspare',${ci},{eid:'${eid}',slot:'${slot}',_level:'operational',_confirm:'Убрать HS с ${p.eid_slot}?',_label:'Remove HS'})" title="Remove HS">❌</button>` : ''}
                </div>
            </td>`;
        });

    const topo = tblSection(pfx+'-topo', '🔗', 'Topology', ctrl.topology,
        ['DG','Array','Row','EID:Slot','DID','Type','State','Size'],
        t => `<td>${esc(t.dg)}</td><td>${esc(t.arr)}</td><td>${esc(t.row)}</td><td>${esc(t.eid_slot)}</td><td>${esc(t.did)}</td><td>${esc(t.type)}</td><td>${badge(t.state,t.health)}</td><td>${esc(t.size)}</td>`);

    const bbu = tblSection(pfx+'-bbu', '🔋', 'BBU', ctrl.bbu,
        ['Model','State','Retention','Temp','Mfg Date','Next Learn'],
        b => `<td>${esc(b.model)}</td><td>${badge(b.state,b.health)}</td><td>${esc(b.retention_time)}</td><td>${esc(b.temperature)}</td><td>${esc(b.mfg_date)}</td><td>${esc(b.next_learn)}</td>`,
        'BBU не обнаружен');

    block.innerHTML = header + err + cards + ctrlActions + vd + pd + topo + bbu;
    return block;
}

function tblSection(id, icon, title, items, headers, rowFn, emptyText) {
    const ths = headers.map(h => `<th>${esc(h)}</th>`).join('');
    const rows = items.length === 0
        ? `<tr><td colspan="${headers.length}" style="text-align:center;color:var(--text-muted)">${esc(emptyText||'Нет данных')}</td></tr>`
        : items.map(i => `<tr class="${rowCls(i.health)}">${rowFn(i)}</tr>`).join('');
    return `<div class="section"><div class="section-card">
        <div class="section-header" onclick="toggleSection('${id}')">
            <div class="section-header-left"><span class="section-icon">${icon}</span><span class="section-title">${esc(title)}</span><span class="section-count">${items.length}</span></div>
            <span class="section-toggle" id="toggle-${id}">▼</span>
        </div>
        <div class="section-body" id="body-${id}"><table class="data-table"><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table></div>
    </div></div>`;
}

// ────────────────────────────────────────────────────────
// Вспомогательные рендеры
// ────────────────────────────────────────────────────────
function updateHostIndicator(id, s) {
    const el = document.getElementById(`host-indicator-${id}`);
    if (el) el.className = `host-tab-indicator ${s}`;
}
function renderHostInfo(h) {
    const b = document.getElementById('host-info');
    if (!h) { b.style.display='none'; return; }
    b.style.display='';
    document.getElementById('host-info-name').textContent = h.name;
    document.getElementById('host-info-detail').textContent = `${h.address}${h.description ? ' — '+h.description : ''}`;
}
function renderOverallStatus(s) {
    const b = document.getElementById('overall-status'); b.style.display='';
    b.className = `overall-badge ${s}`;
    document.getElementById('overall-status-text').textContent =
        {optimal:'Всё в норме', degraded:'Деградация', critical:'Критическая ошибка'}[s] || s;
}

// ────────────────────────────────────────────────────────
// Fetch RAID
// ────────────────────────────────────────────────────────
async function fetchRaidStatus(hostId) {
    if (isLoading) return;
    isLoading = true;
    showLoader(); hideError();
    document.getElementById('controllers-container').innerHTML = '';
    document.getElementById('host-info').style.display = 'none';
    try {
        const r = await fetch(hostId ? `/api/raid-status/${encodeURIComponent(hostId)}` : '/api/raid-status');
        if (!r.ok) {
            let d; try { d = (await r.json()).detail; } catch { d = {}; }
            showError(d?.error||'Ошибка', d?.message||`Код ${r.status}`);
            if (hostId) updateHostIndicator(hostId, 'critical');
            return;
        }
        const res = await r.json();
        if (res.success && res.data) renderDashboard(res.data);
        else showError('Ошибка', 'Неожиданная структура ответа');
    } catch (e) { showError('Ошибка сети', `Бэкенд недоступен: ${e.message}`); }
    finally { hideLoader(); isLoading = false; }
}

// ────────────────────────────────────────────────────────
// Инициализация
// ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadHosts();
    // Закрытие модалок
    ['host-modal','confirm-modal','result-modal'].forEach(id => {
        document.getElementById(id).addEventListener('click', e => {
            if (e.target.id === id) {
                if (id === 'host-modal') closeModal();
                else if (id === 'confirm-modal') closeConfirmModal();
                else closeResultModal();
            }
        });
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') { closeModal(); closeConfirmModal(); closeResultModal(); }
    });
});
