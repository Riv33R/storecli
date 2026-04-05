/**
 * app.js — Клиентская логика StorCLI RAID Monitor Dashboard.
 *
 * Поддержка:
 *  - Множество хостов (табы, /api/hosts)
 *  - Множество контроллеров на каждом хосте
 *  - Динамический рендеринг секций VD/PD/Topology/BBU для каждого контроллера
 */

// ────────────────────────────────────────────────────────
// Состояние приложения
// ────────────────────────────────────────────────────────
let isLoading = false;
let hosts = [];
let activeHostId = null;

// ────────────────────────────────────────────────────────
// Утилиты
// ────────────────────────────────────────────────────────

function renderStatusBadge(state, health) {
    return `<span class="status-badge ${health}"><span class="dot"></span>${escapeHtml(state)}</span>`;
}

function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function rowClass(health) {
    if (health === 'degraded') return 'row-degraded';
    if (health === 'critical') return 'row-critical';
    return '';
}

function formatTimestamp(isoString) {
    try {
        const d = new Date(isoString);
        return d.toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
    } catch {
        return isoString;
    }
}

// ────────────────────────────────────────────────────────
// Loader & Error
// ────────────────────────────────────────────────────────

function showLoader() {
    document.getElementById('loader').classList.add('active');
    const btn = document.getElementById('btn-refresh');
    btn.classList.add('loading');
    btn.disabled = true;
}

function hideLoader() {
    document.getElementById('loader').classList.remove('active');
    const btn = document.getElementById('btn-refresh');
    btn.classList.remove('loading');
    btn.disabled = false;
}

function showError(title, message) {
    const banner = document.getElementById('error-banner');
    document.getElementById('error-title').textContent = title;
    document.getElementById('error-message').textContent = message;
    banner.classList.add('visible');
}

function hideError() {
    document.getElementById('error-banner').classList.remove('visible');
}

// ────────────────────────────────────────────────────────
// Секции: сворачивание / разворачивание
// ────────────────────────────────────────────────────────

function toggleSection(sectionId) {
    const body = document.getElementById(`body-${sectionId}`);
    const toggle = document.getElementById(`toggle-${sectionId}`);
    if (body && toggle) {
        body.classList.toggle('collapsed');
        toggle.classList.toggle('collapsed');
    }
}

// ────────────────────────────────────────────────────────
// Хосты: загрузка и переключение
// ────────────────────────────────────────────────────────

async function loadHosts() {
    try {
        const response = await fetch('/api/hosts');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const result = await response.json();
        if (result.success && result.hosts) {
            hosts = result.hosts;
            renderHostTabs();
            if (hosts.length > 0) {
                selectHost(hosts[0].id);
            } else {
                showError('Нет хостов', 'Добавьте серверы в файл hosts.json и перезапустите приложение.');
            }
        }
    } catch (err) {
        showError('Ошибка загрузки', `Не удалось загрузить список хостов: ${err.message}`);
    }
}

function renderHostTabs() {
    const container = document.getElementById('host-tabs');
    container.innerHTML = hosts.map(h => `
        <button class="host-tab" id="host-tab-${h.id}"
                onclick="selectHost('${h.id}')"
                title="${escapeHtml(h.description || h.host)}">
            <span class="host-tab-indicator" id="host-indicator-${h.id}"></span>
            <div class="host-tab-content">
                <span class="host-tab-name">${escapeHtml(h.name)}</span>
                <span class="host-tab-address">${escapeHtml(h.host)}:${h.port}</span>
            </div>
        </button>
    `).join('');
}

function selectHost(hostId) {
    activeHostId = hostId;
    document.querySelectorAll('.host-tab').forEach(t => t.classList.remove('active'));
    const tab = document.getElementById(`host-tab-${hostId}`);
    if (tab) tab.classList.add('active');
    fetchRaidStatus(hostId);
}

function refreshCurrentHost() {
    if (activeHostId) fetchRaidStatus(activeHostId);
}

// ────────────────────────────────────────────────────────
// Рендеринг данных (мультиконтроллер)
// ────────────────────────────────────────────────────────

/**
 * Основная функция рендеринга дашборда.
 * Принимает данные с controllers[] — массивом контроллеров.
 */
function renderDashboard(data) {
    // Глобальный статус
    renderOverallStatus(data.overall_status);

    // Информация о хосте
    if (data.host) renderHostInfo(data.host);

    // Индикатор хоста
    if (data.host?.id) updateHostIndicator(data.host.id, data.overall_status);

    // Контейнер для всех контроллеров
    const container = document.getElementById('controllers-container');
    container.innerHTML = '';

    const controllers = data.controllers || [];

    controllers.forEach((ctrl, i) => {
        const ctrlEl = renderControllerBlock(ctrl, i, controllers.length);
        container.appendChild(ctrlEl);
    });

    // Время обновления
    document.getElementById('last-update').textContent = formatTimestamp(data.timestamp);
    document.getElementById('footer-info').style.display = '';

    // Анимация появления
    container.querySelectorAll('.controller-block').forEach((el, i) => {
        el.classList.remove('fade-in');
        setTimeout(() => el.classList.add('fade-in'), i * 120);
    });
}

/**
 * Рендерит полный блок одного контроллера со всеми секциями.
 */
function renderControllerBlock(ctrl, index, totalControllers) {
    const prefix = `c${ctrl.controller_index}`;
    const c = ctrl.controller;
    const statusClass = ctrl.overall_status;

    const block = document.createElement('div');
    block.className = 'controller-block';

    // Заголовок контроллера (показываем если контроллеров > 1)
    const headerHtml = totalControllers > 1 ? `
        <div class="controller-header ${statusClass}">
            <div class="controller-header-left">
                <span class="controller-index">C${ctrl.controller_index}</span>
                <div>
                    <div class="controller-model">${escapeHtml(c.model)}</div>
                    <div class="controller-serial">S/N: ${escapeHtml(c.serial_number)}</div>
                </div>
            </div>
            <div class="controller-header-right">
                ${renderStatusBadge(c.status, statusClass)}
            </div>
        </div>
    ` : '';

    // Ошибка парсинга этого контроллера
    const errorHtml = ctrl.error ? `
        <div class="controller-error">
            <span>⚠️</span> ${escapeHtml(ctrl.error)}
        </div>
    ` : '';

    // Карточки
    const cardsHtml = `
        <div class="stats-grid fade-in">
            <div class="stat-card">
                <div class="stat-label">Контроллер</div>
                <div class="stat-value small">${escapeHtml(c.model)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Серийный номер</div>
                <div class="stat-value small">${escapeHtml(c.serial_number)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Статус</div>
                <div class="stat-value small">${renderStatusBadge(c.status, statusClass)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Прошивка</div>
                <div class="stat-value small">${escapeHtml(c.firmware_version)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Память / Кэш</div>
                <div class="stat-value small">${escapeHtml(c.memory_size)} / ${c.cache_size_mb} MB</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">VD / PD</div>
                <div class="stat-value">${ctrl.virtual_drives.length} / ${ctrl.physical_drives.length}</div>
            </div>
        </div>
    `;

    // Секции таблиц
    const vdHtml = renderTableSection(prefix + '-vd', '💿', 'Virtual Drives', ctrl.virtual_drives,
        ['DG/VD', 'RAID Level', 'State', 'Size', 'Access', 'Cache', 'Consistent', 'Name'],
        vd => `
            <td>${escapeHtml(vd.dg_vd)}</td>
            <td>${escapeHtml(vd.type)}</td>
            <td>${renderStatusBadge(vd.state, vd.health)}</td>
            <td>${escapeHtml(vd.size)}</td>
            <td>${escapeHtml(vd.access)}</td>
            <td>${escapeHtml(vd.cache)}</td>
            <td>${escapeHtml(vd.consistent)}</td>
            <td>${escapeHtml(vd.name) || '—'}</td>
        `
    );

    const pdHtml = renderTableSection(prefix + '-pd', '💾', 'Physical Drives', ctrl.physical_drives,
        ['EID:Slot', 'DID', 'State', 'DG', 'Size', 'Interface', 'Media', 'Model'],
        pd => `
            <td>${escapeHtml(pd.eid_slot)}</td>
            <td>${escapeHtml(pd.did)}</td>
            <td>${renderStatusBadge(pd.state, pd.health)}</td>
            <td>${escapeHtml(pd.drive_group)}</td>
            <td>${escapeHtml(pd.size)}</td>
            <td>${escapeHtml(pd.interface)}</td>
            <td>${escapeHtml(pd.media)}</td>
            <td>${escapeHtml(pd.model)}</td>
        `
    );

    const topoHtml = renderTableSection(prefix + '-topo', '🔗', 'Topology', ctrl.topology,
        ['DG', 'Array', 'Row', 'EID:Slot', 'DID', 'Type', 'State', 'Size'],
        item => `
            <td>${escapeHtml(item.dg)}</td>
            <td>${escapeHtml(item.arr)}</td>
            <td>${escapeHtml(item.row)}</td>
            <td>${escapeHtml(item.eid_slot)}</td>
            <td>${escapeHtml(item.did)}</td>
            <td>${escapeHtml(item.type)}</td>
            <td>${renderStatusBadge(item.state, item.health)}</td>
            <td>${escapeHtml(item.size)}</td>
        `
    );

    const bbuHtml = renderTableSection(prefix + '-bbu', '🔋', 'Battery Backup Unit (BBU)', ctrl.bbu,
        ['Model', 'State', 'Retention Time', 'Temp', 'Mfg Date', 'Next Learn'],
        bbu => `
            <td>${escapeHtml(bbu.model)}</td>
            <td>${renderStatusBadge(bbu.state, bbu.health)}</td>
            <td>${escapeHtml(bbu.retention_time)}</td>
            <td>${escapeHtml(bbu.temperature)}</td>
            <td>${escapeHtml(bbu.mfg_date)}</td>
            <td>${escapeHtml(bbu.next_learn)}</td>
        `,
        'BBU не обнаружен'
    );

    block.innerHTML = headerHtml + errorHtml + cardsHtml + vdHtml + pdHtml + topoHtml + bbuHtml;
    return block;
}

/**
 * Универсальная функция рендеринга секции с таблицей.
 */
function renderTableSection(sectionId, icon, title, items, headers, rowRenderer, emptyText) {
    const headerCells = headers.map(h => `<th>${escapeHtml(h)}</th>`).join('');

    let bodyRows;
    if (items.length === 0) {
        bodyRows = `<tr><td colspan="${headers.length}" style="text-align:center; color:var(--text-muted);">${escapeHtml(emptyText || 'Нет данных')}</td></tr>`;
    } else {
        bodyRows = items.map(item => {
            const health = item.health || 'unknown';
            return `<tr class="${rowClass(health)}">${rowRenderer(item)}</tr>`;
        }).join('');
    }

    return `
        <div class="section">
            <div class="section-card">
                <div class="section-header" onclick="toggleSection('${sectionId}')">
                    <div class="section-header-left">
                        <span class="section-icon">${icon}</span>
                        <span class="section-title">${escapeHtml(title)}</span>
                        <span class="section-count">${items.length}</span>
                    </div>
                    <span class="section-toggle" id="toggle-${sectionId}">▼</span>
                </div>
                <div class="section-body" id="body-${sectionId}">
                    <table class="data-table">
                        <thead><tr>${headerCells}</tr></thead>
                        <tbody>${bodyRows}</tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// ────────────────────────────────────────────────────────
// Вспомогательные рендеры
// ────────────────────────────────────────────────────────

function updateHostIndicator(hostId, status) {
    const indicator = document.getElementById(`host-indicator-${hostId}`);
    if (indicator) indicator.className = `host-tab-indicator ${status}`;
}

function renderHostInfo(hostData) {
    const banner = document.getElementById('host-info');
    if (!hostData) { banner.style.display = 'none'; return; }
    banner.style.display = '';
    document.getElementById('host-info-name').textContent = hostData.name;
    document.getElementById('host-info-detail').textContent =
        `${hostData.address}${hostData.description ? ' — ' + hostData.description : ''}`;
}

function renderOverallStatus(status) {
    const badge = document.getElementById('overall-status');
    const text = document.getElementById('overall-status-text');
    badge.style.display = '';
    badge.className = `overall-badge ${status}`;
    const labels = { optimal: 'Всё в норме', degraded: 'Деградация', critical: 'Критическая ошибка' };
    text.textContent = labels[status] || status;
}

// ────────────────────────────────────────────────────────
// Fetch данных с API
// ────────────────────────────────────────────────────────

async function fetchRaidStatus(hostId) {
    if (isLoading) return;
    isLoading = true;

    showLoader();
    hideError();

    // Очищаем контент
    document.getElementById('controllers-container').innerHTML = '';
    document.getElementById('host-info').style.display = 'none';

    const url = hostId ? `/api/raid-status/${encodeURIComponent(hostId)}` : '/api/raid-status';

    try {
        const response = await fetch(url);

        if (!response.ok) {
            let errorDetail;
            try {
                const errBody = await response.json();
                errorDetail = errBody.detail;
            } catch {
                errorDetail = { message: `HTTP ${response.status}: ${response.statusText}` };
            }
            showError(errorDetail?.error || 'Ошибка', errorDetail?.message || `Код ${response.status}`);
            if (hostId) updateHostIndicator(hostId, 'critical');
            return;
        }

        const result = await response.json();

        if (result.success && result.data) {
            renderDashboard(result.data);
        } else {
            showError('Ошибка', 'Неожиданная структура ответа');
        }

    } catch (err) {
        showError('Ошибка сети', `Не удалось связаться с бэкендом: ${err.message}`);
    } finally {
        hideLoader();
        isLoading = false;
    }
}

// ────────────────────────────────────────────────────────
// Инициализация
// ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadHosts();
});
