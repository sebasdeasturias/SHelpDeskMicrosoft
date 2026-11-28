// dashboard-admin.js — Panel del Administrador
const API = window.API_BASE_URL || 'http://localhost:8000/api';

const state = {
    authToken: localStorage.getItem('token') || sessionStorage.getItem('token'),
    userData: null,
    usuarios: [],
    workflows: [],
    respaldos: [],
    solicitudesPassword: [],
    currentPage: 'resumen'
};

const ROLES = ['solicitante', 'agente', 'coordinador', 'administrador'];

// ============================================
// API
// ============================================
async function apiFetch(path, options = {}) {
    const headers = {
        'Authorization': `Bearer ${state.authToken}`,
        ...(options.headers || {})
    };
    if (options.body && typeof options.body !== 'string') {
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
    }
    const res = await fetch(`${API}${path}`, { ...options, headers });
    if (res.status === 401) {
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        window.location.href = 'login.html';
        throw new Error('No autorizado');
    }
    if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
            const err = await res.json();
            if (err.detail) msg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
        } catch (_) {}
        throw new Error(msg);
    }
    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.blob();
}

// ============================================
// INICIALIZACIÓN
// ============================================
document.addEventListener('DOMContentLoaded', async () => {
    if (!state.authToken) {
        window.location.href = 'login.html';
        return;
    }
    try {
        const me = await apiFetch('/auth/me');
        state.userData = me;
        if (me.role !== 'administrador') {
            const destino = {
                'coordinador': 'dashboard-coordinador.html',
                'agente': 'dashboard-agente.html',
                'solicitante': 'dashboard-solicitante.html'
            }[me.role] || 'login.html';
            window.location.href = destino;
            return;
        }
        document.getElementById('userName').textContent = me.nombre || me.email;
    } catch (e) {
        console.error('Error de autenticación:', e);
        return;
    }

    initTheme();
    initNavigation();
    initModal();
    bindAcciones();
    await loadResumen();
});

function initTheme() {
    const toggle = document.getElementById('themeCheck');
    if (localStorage.getItem('theme') === 'night') {
        document.body.classList.add('night-mode');
        toggle.checked = true;
    }
    toggle.addEventListener('change', () => {
        document.body.classList.toggle('night-mode', toggle.checked);
        localStorage.setItem('theme', toggle.checked ? 'night' : 'day');
    });
    document.getElementById('logoutBtn').addEventListener('click', () => {
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        window.location.href = 'login.html';
    });
}

// ============================================
// NAVEGACIÓN
// ============================================
const LOADERS = {
    'resumen': loadResumen,
    'usuarios': loadUsuarios,
    'solicitudes': loadSolicitudesPassword,
    'bd': loadBD,
    'respaldos': loadRespaldos,
    'logs': () => {},
    'n8n': loadN8N,
    'ia': loadIA,
    'seguridad': loadMfa
};

function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => navigateTo(btn.dataset.page));
    });
}

function navigateTo(page) {
    state.currentPage = page;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.page === page));
    document.querySelectorAll('.page-content').forEach(p => p.classList.toggle('active', p.id === `page-${page}`));
    if (LOADERS[page]) LOADERS[page]();
}

// ============================================
// HELPERS UI
// ============================================
function mostrarToast(msg) {
    let toast = document.getElementById('adminToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'adminToast';
        toast.className = 'coord-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 3500);
}

function initModal() {
    document.getElementById('modalCancelar').addEventListener('click', cerrarModal);
    const btnCerrar = document.getElementById('modalCerrar');
    if (btnCerrar) btnCerrar.addEventListener('click', cerrarModal);
    document.getElementById('modalOverlay').addEventListener('click', e => {
        if (e.target.id === 'modalOverlay') cerrarModal();
    });
    document.addEventListener('keydown', e => {
        const overlay = document.getElementById('modalOverlay');
        if (e.key === 'Escape' && overlay && overlay.classList.contains('open')) cerrarModal();
    });
}

let _modalAceptar = null;

function abrirModal({ titulo, cuerpo, aceptarTexto = 'Aceptar', peligroso = false, onAceptar }) {
    document.getElementById('modalTitulo').textContent = titulo;
    document.getElementById('modalCuerpo').innerHTML = cuerpo;
    const icono = document.querySelector('#modalIcono i');
    if (icono) icono.className = 'fas ' + (peligroso ? 'fa-triangle-exclamation' : 'fa-circle-question');
    const btn = document.getElementById('modalAceptar');
    btn.textContent = aceptarTexto;
    btn.classList.toggle('danger', peligroso);
    _modalAceptar = onAceptar;
    const overlay = document.getElementById('modalOverlay');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
}

function cerrarModal() {
    const overlay = document.getElementById('modalOverlay');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    _modalAceptar = null;
}

document.getElementById('modalAceptar').addEventListener('click', () => {
    if (_modalAceptar) _modalAceptar();
    cerrarModal();
});

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// ============================================
// RESUMEN
// ============================================
async function loadResumen() {
    try {
        const [stats, usuarios] = await Promise.all([
            apiFetch('/coordinator/estadisticas'),
            apiFetch('/coordinator/usuarios')
        ]);
        state.usuarios = usuarios;
        const k = stats.kpis || {};
        const activos = usuarios.filter(u => u.estado === 'activo').length;

        const kpis = [
            ['blue', 'fa-ticket-alt', 'Tickets Totales Mes', k.total_tickets_mes ?? 0],
            ['green', 'fa-shield-halved', 'Cumplimiento de SLA', k.cumplimiento_sla != null ? `${k.cumplimiento_sla}%` : '—'],
            ['yellow', 'fa-users-gear', 'Usuarios Totales', usuarios.length],
            ['purple', 'fa-user-check', 'Usuarios Activos', activos]
        ];
        document.getElementById('kpiResumen').innerHTML = kpis.map(([color, icon, label, value]) => `
            <div class="kpi-card">
                <div class="kpi-icon ${color}"><i class="fas ${icon}"></i></div>
                <div class="kpi-content">
                    <span class="kpi-label">${label}</span>
                    <span class="kpi-value">${escapeHtml(value)}</span>
                </div>
            </div>`).join('');

        const porRol = {};
        usuarios.forEach(u => {
            porRol[u.rol] = porRol[u.rol] || { total: 0, activos: 0, inactivos: 0 };
            porRol[u.rol].total++;
            porRol[u.rol][u.estado === 'activo' ? 'activos' : 'inactivos']++;
        });
        document.getElementById('rolesBody').innerHTML = Object.entries(porRol).map(([rol, d]) => `
            <tr>
                <td><span class="role-pill ${escapeHtml(rol)}">${escapeHtml(rol)}</span></td>
                <td><strong>${d.total}</strong></td>
                <td>${d.activos}</td>
                <td>${d.inactivos}</td>
            </tr>`).join('');
    } catch (e) {
        mostrarToast(`Error al cargar resumen: ${e.message}`);
    }
}

// ============================================
// USUARIOS
// ============================================
async function loadUsuarios() {
    try {
        state.usuarios = await apiFetch('/coordinator/usuarios');
        renderUsuarios();
    } catch (e) {
        mostrarToast(`Error al cargar usuarios: ${e.message}`);
    }
}

function renderUsuarios() {
    const body = document.getElementById('usuariosBody');
    document.getElementById('usuariosCount').textContent = `${state.usuarios.length} usuarios`;
    body.innerHTML = state.usuarios.map(u => {
        const temporal = u.admin_temporal_hasta
            ? `<span class="item-meta">hasta ${new Date(u.admin_temporal_hasta).toLocaleString('es-ES')}${u.rol_anterior ? ` (vuelve a ${escapeHtml(u.rol_anterior)})` : ''}</span>`
            : '<span class="item-meta">—</span>';
        return `
        <tr data-uid="${u.id_usuario}">
            <td><strong>#${u.id_usuario}</strong></td>
            <td>${escapeHtml(u.nombre)}</td>
            <td>${escapeHtml(u.email)}</td>
            <td><span class="role-pill ${escapeHtml(u.rol)}">${escapeHtml(u.rol)}</span>${u.rol_anterior ? '<br><span class="item-meta">temporal</span>' : ''}</td>
            <td>${escapeHtml(u.area || 'N/A')}</td>
            <td><span class="status-pill ${escapeHtml(u.estado)}">${escapeHtml(u.estado)}</span></td>
            <td>${temporal}</td>
            <td>
                <button class="btn-mini" data-accion="rol"><i class="fas fa-user-shield"></i> Rol</button>
                <button class="btn-mini" data-accion="estado"><i class="fas fa-power-off"></i> ${u.estado === 'activo' ? 'Desactivar' : 'Activar'}</button>
                <button class="btn-mini" data-accion="password"><i class="fas fa-key"></i></button>
                <button class="btn-mini danger" data-accion="eliminar"><i class="fas fa-trash"></i></button>
            </td>
        </tr>`;
    }).join('');

    body.querySelectorAll('button[data-accion]').forEach(btn => {
        btn.addEventListener('click', () => {
            const uid = parseInt(btn.closest('tr').dataset.uid, 10);
            const usuario = state.usuarios.find(x => x.id_usuario === uid);
            const accion = btn.dataset.accion;
            if (accion === 'rol') modalCambiarRol(usuario);
            else if (accion === 'estado') toggleEstado(usuario);
            else if (accion === 'password') modalResetPassword(usuario);
            else if (accion === 'eliminar') modalEliminar(usuario);
        });
    });
}

function bindAcciones() {
    document.getElementById('btnNuevoUsuario').addEventListener('click', () => {
        const f = document.getElementById('formNuevoUsuario');
        f.style.display = f.style.display === 'none' ? 'block' : 'none';
    });
    document.getElementById('btnRefrescarUsuarios').addEventListener('click', loadUsuarios);
    document.getElementById('btnCrearUsuario').addEventListener('click', crearUsuario);
    document.getElementById('btnRefrescarSolicitudes').addEventListener('click', loadSolicitudesPassword);
    document.getElementById('filtroEstadoSolicitud').addEventListener('change', loadSolicitudesPassword);
    document.getElementById('btnRefrescarBD').addEventListener('click', loadBD);
    document.getElementById('btnCrearRespaldo').addEventListener('click', crearRespaldo);
    document.getElementById('btnVerLogs').addEventListener('click', verLogs);
    document.getElementById('btnRefrescarN8N').addEventListener('click', loadN8N);
    document.getElementById('btnIaPull').addEventListener('click', iaPull);
    document.getElementById('btnIaParams').addEventListener('click', guardarIaParams);
    document.getElementById('btnMfaSetup').addEventListener('click', mfaSetup);
    document.getElementById('btnMfaEnable').addEventListener('click', mfaEnable);
    document.getElementById('btnMfaDisable').addEventListener('click', mfaDisable);
    document.getElementById('btnMfaCancelar').addEventListener('click', () => {
        document.getElementById('mfaSetupBox').style.display = 'none';
        document.getElementById('mfaActions').style.display = 'block';
    });
}

async function crearUsuario() {
    const payload = {
        nombre: document.getElementById('nuNombre').value.trim(),
        email: document.getElementById('nuEmail').value.trim(),
        area: document.getElementById('nuArea').value.trim(),
        rol: document.getElementById('nuRol').value,
        password: document.getElementById('nuPass').value
    };
    if (!payload.nombre || !payload.email || !payload.password) {
        mostrarToast('Nombre, correo y contraseña son obligatorios');
        return;
    }
    try {
        await apiFetch('/coordinator/usuarios', { method: 'POST', body: payload });
        mostrarToast(`Usuario ${payload.email} creado con rol ${payload.rol}`);
        ['nuNombre', 'nuEmail', 'nuArea', 'nuPass'].forEach(id => document.getElementById(id).value = '');
        document.getElementById('formNuevoUsuario').style.display = 'none';
        loadUsuarios();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}

function modalCambiarRol(u) {
    abrirModal({
        titulo: `Cambiar rol — ${u.nombre}`,
        cuerpo: `
            <p>Rol actual: <span class="role-pill ${escapeHtml(u.rol)}">${escapeHtml(u.rol)}</span></p>
            <label class="filter-group" style="margin-top:10px;"><label>Nuevo rol</label>
                <select class="glass-select" id="modalNuevoRol">
                    ${ROLES.map(r => `<option value="${r}" ${r === u.rol ? 'selected' : ''}>${r}</option>`).join('')}
                </select>
            </label>
            <div style="margin-top:10px;">
                <label style="display:flex; gap:8px; align-items:center; color:var(--text-dark);">
                    <input type="checkbox" id="modalTemporal"> Temporal (solo al promover a administrador)
                </label>
                <input class="glass-input" id="modalHoras" type="number" min="1" max="720" value="24" disabled
                    style="margin-top:8px;" title="Duración en horas">
            </div>`,
        aceptarTexto: 'Aplicar',
        onAceptar: async () => {
            const rol = document.getElementById('modalNuevoRol').value;
            const temporal = document.getElementById('modalTemporal').checked;
            const horas = parseInt(document.getElementById('modalHoras').value, 10) || 24;
            document.getElementById('modalTemporal').addEventListener('change', () => {});
            try {
                const r = await apiFetch(`/coordinator/usuarios/${u.id_usuario}/rol`, {
                    method: 'PATCH',
                    body: { rol, temporal_horas: temporal ? horas : null }
                });
                mostrarToast(r.temporal_horas
                    ? `${u.nombre} es administrador por ${r.temporal_horas} h (volverá a ${r.rol_anterior})`
                    : `Rol de ${u.nombre}: ${rol}`);
                loadUsuarios();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
    document.getElementById('modalTemporal').addEventListener('change', e => {
        document.getElementById('modalHoras').disabled = !e.target.checked;
    });
}

function toggleEstado(u) {
    const nuevo = u.estado === 'activo' ? 'inactivo' : 'activo';
    abrirModal({
        titulo: `${nuevo === 'activo' ? 'Activar' : 'Desactivar'} usuario`,
        cuerpo: `<p>¿Marcar a <strong>${escapeHtml(u.nombre)}</strong> (${escapeHtml(u.email)}) como <strong>${nuevo}</strong>?</p>`,
        aceptarTexto: 'Sí, aplicar',
        peligroso: nuevo === 'inactivo',
        onAceptar: async () => {
            try {
                await apiFetch(`/coordinator/usuarios/${u.id_usuario}`, { method: 'PATCH', body: { estado: nuevo } });
                mostrarToast(`${u.nombre} ahora está ${nuevo}`);
                loadUsuarios();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

function modalResetPassword(u) {
    abrirModal({
        titulo: `Restablecer contraseña — ${u.nombre}`,
        cuerpo: `<p>Nueva contraseña para <strong>${escapeHtml(u.email)}</strong> (mínimo 8 caracteres):</p>
                 <p class="hint"><i class="fas fa-triangle-exclamation"></i> Antes de restablecer, valida la identidad del usuario <strong>en persona</strong>. La cuenta se desbloqueará y se cerrarán sus sesiones activas.</p>
                 <input class="glass-input" id="modalPass" type="password" autocomplete="new-password">`,
        aceptarTexto: 'Restablecer',
        onAceptar: async () => {
            const pass = document.getElementById('modalPass').value;
            try {
                await apiFetch(`/coordinator/usuarios/${u.id_usuario}`, { method: 'PATCH', body: { password: pass } });
                mostrarToast(`Contraseña de ${u.nombre} restablecida`);
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

function modalEliminar(u) {
    abrirModal({
        titulo: 'Eliminar usuario',
        cuerpo: `<p>¿Eliminar <strong>${escapeHtml(u.nombre)}</strong> (${escapeHtml(u.email)}) <strong>definitivamente</strong>?</p>
                 <p class="hint">Si tiene tickets o registros asociados, la BD lo impedirá: desactívalo en su lugar.</p>`,
        aceptarTexto: 'Eliminar',
        peligroso: true,
        onAceptar: async () => {
            try {
                await apiFetch(`/coordinator/usuarios/${u.id_usuario}`, { method: 'DELETE' });
                mostrarToast(`${u.nombre} eliminado`);
                loadUsuarios();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

// ============================================
// SOLICITUDES DE RESTABLECIMIENTO DE CONTRASEÑA
// ============================================
const ESTADO_SOLICITUD_LABEL = {
    pendiente: 'Pendiente',
    identidad_validada: 'Identidad validada',
    resuelta: 'Resuelta',
    rechazada: 'Rechazada',
    cancelada: 'Cancelada'
};

function fmtFecha(iso) {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleString('es-ES'); } catch (_) { return '—'; }
}

async function loadSolicitudesPassword() {
    try {
        const estado = document.getElementById('filtroEstadoSolicitud')?.value || '';
        const qs = estado ? `?estado=${encodeURIComponent(estado)}` : '';
        state.solicitudesPassword = await apiFetch(`/coordinator/solicitudes-password${qs}`);
        renderSolicitudesPassword();
    } catch (e) {
        mostrarToast(`Error al cargar solicitudes: ${e.message}`);
    }
}

function renderSolicitudesPassword() {
    const body = document.getElementById('solicitudesBody');
    if (!body) return;
    const lista = state.solicitudesPassword || [];
    document.getElementById('solicitudesCount').textContent = `${lista.length} solicitud(es)`;

    if (lista.length === 0) {
        body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:16px;">No hay solicitudes registradas</td></tr>';
        return;
    }

    body.innerHTML = lista.map(s => {
        const acciones = [];
        if (s.estado === 'pendiente') {
            acciones.push('<button class="btn-mini" data-accion="validar"><i class="fas fa-user-check"></i> Validar identidad</button>');
            acciones.push('<button class="btn-mini danger" data-accion="rechazar"><i class="fas fa-xmark"></i> Rechazar</button>');
        } else if (s.estado === 'identidad_validada') {
            acciones.push('<button class="btn-mini" data-accion="restablecer"><i class="fas fa-key"></i> Restablecer</button>');
            acciones.push('<button class="btn-mini danger" data-accion="rechazar"><i class="fas fa-xmark"></i> Rechazar</button>');
        } else {
            acciones.push('<button class="btn-mini" data-accion="detalle"><i class="fas fa-circle-info"></i> Detalle</button>');
        }

        let estadoExtra = '';
        if (s.estado === 'identidad_validada' && s.admin_valida) {
            estadoExtra = `<br><span class="item-meta">Validó: ${escapeHtml(s.admin_valida)} · ${fmtFecha(s.fecha_identidad)}</span>`;
        } else if ((s.estado === 'resuelta' || s.estado === 'rechazada') && s.admin_resuelve) {
            estadoExtra = `<br><span class="item-meta">${s.estado === 'resuelta' ? 'Resolvió' : 'Rechazó'}: ${escapeHtml(s.admin_resuelve)} · ${fmtFecha(s.fecha_resolucion)}</span>`;
        }
        if (s.estado === 'resuelta') {
            estadoExtra += s.cambio_pendiente
                ? '<br><span class="item-meta">Cambio de contraseña pendiente</span>'
                : '<br><span class="item-meta">Contraseña ya cambiada</span>';
        }

        return `
        <tr data-sid="${s.id_solicitud_password}">
            <td><strong>#${s.id_solicitud_password}</strong></td>
            <td>${escapeHtml(s.nombre || '—')}${s.estado_usuario && s.estado_usuario !== 'activo' ? `<br><span class="item-meta">cuenta ${escapeHtml(s.estado_usuario)}</span>` : ''}</td>
            <td>${escapeHtml(s.email || '—')}</td>
            <td>${s.rol ? `<span class="role-pill ${escapeHtml(s.rol)}">${escapeHtml(s.rol)}</span>` : '—'}</td>
            <td class="solicitud-motivo">${escapeHtml(s.motivo || '—')}</td>
            <td>${fmtFecha(s.fecha_creacion)}</td>
            <td><span class="status-pill ${escapeHtml(s.estado)}">${escapeHtml(ESTADO_SOLICITUD_LABEL[s.estado] || s.estado)}</span>${estadoExtra}</td>
            <td>${acciones.join('')}</td>
        </tr>`;
    }).join('');

    body.querySelectorAll('button[data-accion]').forEach(btn => {
        btn.addEventListener('click', () => {
            const sid = parseInt(btn.closest('tr').dataset.sid, 10);
            const s = state.solicitudesPassword.find(x => x.id_solicitud_password === sid);
            if (!s) return;
            if (btn.dataset.accion === 'validar') modalValidarIdentidad(s);
            else if (btn.dataset.accion === 'restablecer') modalRestablecerSolicitud(s);
            else if (btn.dataset.accion === 'rechazar') modalRechazarSolicitud(s);
            else if (btn.dataset.accion === 'detalle') modalDetalleSolicitud(s);
        });
    });
}

function modalValidarIdentidad(s) {
    abrirModal({
        titulo: `Validar identidad — ${s.nombre || s.email}`,
        cuerpo: `
            <p>Vas a confirmar que validaste la identidad de <strong>${escapeHtml(s.nombre || s.email)}</strong> <strong>en persona</strong>.</p>
            <p class="hint">Solicitud #${s.id_solicitud_password} · ${escapeHtml(s.email || '—')}</p>
            <div class="filter-group" style="margin-top:12px;">
                <label for="solNotaValidacion">Documento u observación (opcional)</label>
                <textarea class="glass-input" id="solNotaValidacion" rows="2" maxlength="500"
                          placeholder="Ej: DNI ****1234, validado en mesa de soporte"></textarea>
            </div>
            <p class="hint"><i class="fas fa-triangle-exclamation"></i> No continúes si no has verificado su identidad físicamente.</p>`,
        aceptarTexto: 'Identidad validada',
        onAceptar: async () => {
            try {
                const nota = document.getElementById('solNotaValidacion')?.value.trim() || null;
                await apiFetch(`/coordinator/solicitudes-password/${s.id_solicitud_password}/validar`, {
                    method: 'POST', body: { nota }
                });
                mostrarToast('Identidad validada. Ya puedes restablecer la contraseña.');
                loadSolicitudesPassword();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

function modalRestablecerSolicitud(s) {
    abrirModal({
        titulo: `Restablecer contraseña — ${s.nombre || s.email}`,
        cuerpo: `
            <p>Nueva contraseña para <strong>${escapeHtml(s.email || '—')}</strong>.</p>
            <p class="hint">Identidad validada por ${escapeHtml(s.admin_valida || '—')} el ${fmtFecha(s.fecha_identidad)}.</p>
            <div class="solicitud-opciones">
                <label><input type="radio" name="modoPassSolicitud" value="auto" checked> Generar contraseña temporal segura</label>
                <label><input type="radio" name="modoPassSolicitud" value="manual"> Definir contraseña manual</label>
            </div>
            <input class="glass-input" id="solPassManual" type="password" disabled maxlength="128"
                   placeholder="Contraseña manual (mínimo 8 caracteres)" autocomplete="new-password">`,
        aceptarTexto: 'Restablecer',
        onAceptar: async () => {
            const modo = document.querySelector('input[name="modoPassSolicitud"]:checked')?.value || 'auto';
            const manual = document.getElementById('solPassManual')?.value || '';
            if (modo === 'manual' && manual.length < 8) {
                mostrarToast('La contraseña manual debe tener al menos 8 caracteres');
                return;
            }
            try {
                const data = await apiFetch(`/coordinator/solicitudes-password/${s.id_solicitud_password}/restablecer`, {
                    method: 'POST',
                    body: modo === 'manual' ? { password: manual } : {}
                });
                if (data.password) {
                    mostrarPasswordTemporal(data.password, s);
                } else {
                    mostrarToast('Contraseña restablecida. El usuario deberá cambiarla en su próximo inicio de sesión.');
                }
                loadSolicitudesPassword();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });

    document.querySelectorAll('input[name="modoPassSolicitud"]').forEach(r => {
        r.addEventListener('change', () => {
            const manual = document.querySelector('input[name="modoPassSolicitud"]:checked')?.value === 'manual';
            const input = document.getElementById('solPassManual');
            if (input) {
                input.disabled = !manual;
                if (manual) input.focus();
            }
        });
    });
}

function mostrarPasswordTemporal(pwd, s) {
    abrirModal({
        titulo: 'Contraseña temporal generada',
        cuerpo: `
            <p>Entrega esta contraseña a <strong>${escapeHtml(s.nombre || s.email)}</strong> <strong>en persona</strong>.</p>
            <div class="password-reveal" id="passwordReveal">${escapeHtml(pwd)}</div>
            <p class="hint"><i class="fas fa-eye"></i> Se muestra una sola vez. No se guarda en el log ni se puede recuperar después.</p>
            <p class="hint"><i class="fas fa-user-shield"></i> Entrégala únicamente al titular de la cuenta, tras verificar su identidad.</p>
            <p class="hint"><i class="fas fa-right-to-bracket"></i> El usuario deberá cambiarla obligatoriamente en su próximo inicio de sesión.</p>
            <button class="btn-mini" id="btnCopiarPassword" type="button"><i class="fas fa-copy"></i> Copiar contraseña</button>`,
        aceptarTexto: 'Entendido',
        onAceptar: () => {}
    });

    document.getElementById('btnCopiarPassword')?.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(pwd);
            mostrarToast('Contraseña copiada al portapapeles');
        } catch (_) {
            mostrarToast('No se pudo copiar automáticamente; selecciónala manualmente');
        }
    });
}

function modalRechazarSolicitud(s) {
    abrirModal({
        titulo: `Rechazar solicitud — ${s.nombre || s.email}`,
        cuerpo: `
            <p>¿Rechazar la solicitud #${s.id_solicitud_password} de <strong>${escapeHtml(s.nombre || s.email)}</strong>?</p>
            <div class="filter-group" style="margin-top:12px;">
                <label for="solNotaRechazo">Motivo del rechazo (opcional)</label>
                <textarea class="glass-input" id="solNotaRechazo" rows="2" maxlength="500"
                          placeholder="Ej: no se presentó a validar su identidad"></textarea>
            </div>`,
        aceptarTexto: 'Rechazar',
        peligroso: true,
        onAceptar: async () => {
            try {
                const nota = document.getElementById('solNotaRechazo')?.value.trim() || null;
                await apiFetch(`/coordinator/solicitudes-password/${s.id_solicitud_password}/rechazar`, {
                    method: 'POST', body: { nota }
                });
                mostrarToast('Solicitud rechazada');
                loadSolicitudesPassword();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

function modalDetalleSolicitud(s) {
    const filas = [
        ['Solicitud', `#${s.id_solicitud_password}`],
        ['Usuario', s.nombre || '—'],
        ['Correo', s.email || '—'],
        ['Rol', s.rol || '—'],
        ['Estado', ESTADO_SOLICITUD_LABEL[s.estado] || s.estado],
        ['Motivo', s.motivo || '—'],
        ['Solicitada', fmtFecha(s.fecha_creacion)],
        ['Identidad validada', s.fecha_identidad ? `${fmtFecha(s.fecha_identidad)} · ${s.admin_valida || '—'}` : '—'],
        ['Nota de validación', s.nota_validacion || '—'],
        ['Resolución', s.fecha_resolucion ? `${fmtFecha(s.fecha_resolucion)} · ${s.admin_resuelve || '—'}` : '—'],
        ['Nota de resolución', s.nota_resolucion || '—']
    ];
    abrirModal({
        titulo: `Detalle de la solicitud #${s.id_solicitud_password}`,
        cuerpo: `<div class="solicitud-detalle">${filas.map(([k, v]) =>
            `<div class="detail-row"><span class="detail-key">${escapeHtml(k)}</span><span class="detail-val">${escapeHtml(v)}</span></div>`
        ).join('')}</div>`,
        aceptarTexto: 'Cerrar',
        onAceptar: () => {}
    });
}

// ============================================
// BASE DE DATOS
// ============================================
async function loadBD() {
    try {
        const tablas = await apiFetch('/coordinator/bd/tablas');
        document.getElementById('bdBody').innerHTML = tablas.map(t => `
            <tr><td><strong>${escapeHtml(t.tabla)}</strong></td><td>${t.filas ?? 0}</td></tr>`).join('');
    } catch (e) {
        mostrarToast(`Error al cargar tablas: ${e.message}`);
    }
}

// ============================================
// RESPALDOS
// ============================================
async function loadRespaldos() {
    try {
        state.respaldos = await apiFetch('/coordinator/respaldos');
        document.getElementById('respaldosCount').textContent = `${state.respaldos.length} respaldos`;
        document.getElementById('respaldosBody').innerHTML = state.respaldos.map(r => `
            <tr data-nombre="${escapeHtml(r.nombre)}">
                <td><strong>${escapeHtml(r.nombre)}</strong></td>
                <td>${(r.bytes / 1e6).toFixed(2)} MB</td>
                <td>${escapeHtml(r.fecha)}</td>
                <td>
                    <button class="btn-mini" data-accion="descargar"><i class="fas fa-download"></i></button>
                    <button class="btn-mini danger" data-accion="eliminar"><i class="fas fa-trash"></i></button>
                    <button class="btn-mini danger" data-accion="restaurar"><i class="fas fa-rotate-left"></i> Restaurar</button>
                </td>
            </tr>`).join('');

        document.querySelectorAll('#respaldosBody button[data-accion]').forEach(btn => {
            btn.addEventListener('click', () => {
                const nombre = btn.closest('tr').dataset.nombre;
                const accion = btn.dataset.accion;
                if (accion === 'descargar') descargarRespaldo(nombre);
                else if (accion === 'eliminar') {
                    abrirModal({
                        titulo: 'Eliminar respaldo',
                        cuerpo: `<p>¿Eliminar <strong>${escapeHtml(nombre)}</strong> permanentemente?</p>`,
                        aceptarTexto: 'Eliminar', peligroso: true,
                        onAceptar: async () => {
                            try {
                                await apiFetch(`/coordinator/respaldos/${encodeURIComponent(nombre)}`, { method: 'DELETE' });
                                mostrarToast('Respaldo eliminado');
                                loadRespaldos();
                            } catch (e) { mostrarToast(`Error: ${e.message}`); }
                        }
                    });
                } else if (accion === 'restaurar') {
                    abrirModal({
                        titulo: 'Restaurar base de datos',
                        cuerpo: `<p>Se ejecutará <code>pg_restore --clean</code> con <strong>${escapeHtml(nombre)}</strong>.</p>
                                 <p><strong>LA BD ACTUAL SERÁ REEMPLAZADA</strong> y todos los usuarios tendrán que volver a iniciar sesión.</p>`,
                        aceptarTexto: 'Restaurar ahora', peligroso: true,
                        onAceptar: async () => {
                            try {
                                mostrarToast('Restaurando (puede tardar un minuto)...');
                                await apiFetch(`/coordinator/respaldos/${encodeURIComponent(nombre)}/restaurar`, { method: 'POST' });
                                mostrarToast('Base de datos restaurada');
                            } catch (e) { mostrarToast(`Error: ${e.message}`); }
                        }
                    });
                }
            });
        });
    } catch (e) {
        mostrarToast(`Error al cargar respaldos: ${e.message}`);
    }
}

async function crearRespaldo() {
    const btn = document.getElementById('btnCrearRespaldo');
    btn.disabled = true;
    try {
        mostrarToast('Ejecutando pg_dump...');
        const r = await apiFetch('/coordinator/respaldos', { method: 'POST' });
        mostrarToast(`Respaldo creado: ${r.archivo}`);
        loadRespaldos();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    } finally {
        btn.disabled = false;
    }
}

async function descargarRespaldo(nombre) {
    try {
        mostrarToast('Preparando descarga...');
        const blob = await apiFetch(`/coordinator/respaldos/${encodeURIComponent(nombre)}/descargar`);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = nombre;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}

// ============================================
// LOGS
// ============================================
async function verLogs() {
    const contenedor = document.getElementById('logContenedor').value;
    const tail = document.getElementById('logTail').value;
    document.getElementById('logTitulo').textContent = `Logs: ${contenedor} (últimas ${tail} líneas)`;
    document.getElementById('logSalida').textContent = 'Cargando...';
    try {
        const r = await apiFetch(`/coordinator/logs/${contenedor}?tail=${tail}`);
        document.getElementById('logSalida').textContent = r.logs;
    } catch (e) {
        document.getElementById('logSalida').textContent = `Error: ${e.message}`;
    }
}

// ============================================
// N8N
// ============================================
async function loadN8N() {
    const lista = document.getElementById('n8nLista');
    lista.innerHTML = '<div class="item-glass"><span class="item-meta">Cargando workflows...</span></div>';
    try {
        state.workflows = await apiFetch('/coordinator/n8n/workflows');
        if (state.workflows.length === 0) {
            lista.innerHTML = '<div class="item-glass"><span class="item-meta">No hay workflows en esta instancia</span></div>';
            return;
        }
        lista.innerHTML = state.workflows.map(w => `
            <div class="item-glass" data-wid="${escapeHtml(String(w.id))}">
                <div>
                    <span class="item-titulo"><span class="punto" style="background:${w.activo ? '#22c55e' : '#9ca3af'};"></span>${escapeHtml(w.nombre)}</span>
                    <div class="item-meta">ID: ${escapeHtml(String(w.id))} · ${w.activo ? 'Activo' : 'Inactivo'}</div>
                </div>
                <button class="btn-mini" data-accion="toggle">${w.activo ? 'Desactivar' : 'Activar'}</button>
            </div>`).join('');

        lista.querySelectorAll('button[data-accion="toggle"]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const wid = btn.closest('.item-glass').dataset.wid;
                const wf = state.workflows.find(w => String(w.id) === wid);
                try {
                    await apiFetch(`/coordinator/n8n/workflows/${encodeURIComponent(wid)}/toggle`,
                        { method: 'POST', body: { activo: !wf.activo } });
                    mostrarToast(`Workflow '${wf.nombre}' ${wf.activo ? 'desactivado' : 'activado'}`);
                    loadN8N();
                } catch (e) {
                    mostrarToast(`Error: ${e.message}`);
                }
            });
        });
    } catch (e) {
        lista.innerHTML = `<div class="item-glass"><span class="item-meta">Error: ${escapeHtml(e.message)}</span></div>`;
    }
}

// ============================================
// IA
// ============================================
async function loadIA() {
    const lista = document.getElementById('iaModelos');
    lista.innerHTML = '<div class="item-glass"><span class="item-meta">Cargando modelos...</span></div>';
    try {
        const data = await apiFetch('/coordinator/ia');
        document.getElementById('iaTemp').value = data.config.temperatura ?? 0.8;
        document.getElementById('iaPredict').value = data.config.num_predict ?? 512;
        document.getElementById('iaTopP').value = data.config.top_p ?? 0.9;

        lista.innerHTML = data.modelos.map(m => `
            <div class="item-glass">
                <div>
                    <span class="item-titulo">${escapeHtml(m.name)}
                        ${m.name === data.modelo_activo
                            ? '<span class="role-pill administrador">(activo)</span>' : ''}</span>
                    <div class="item-meta">${(m.size / 1e9).toFixed(2)} GB</div>
                </div>
                <div>
                    ${m.name !== data.modelo_activo
                        ? `<button class="btn-mini" data-accion="usar" data-modelo="${escapeHtml(m.name)}">Usar</button>` : ''}
                    <button class="btn-mini" data-accion="probar" data-modelo="${escapeHtml(m.name)}">Probar</button>
                </div>
            </div>`).join('');

        lista.querySelectorAll('button[data-accion]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const modelo = btn.dataset.modelo;
                if (btn.dataset.accion === 'usar') {
                    try {
                        await apiFetch('/coordinator/ia/modelo', { method: 'POST', body: { modelo } });
                        mostrarToast(`Modelo activo del chat: ${modelo}`);
                        loadIA();
                    } catch (e) { mostrarToast(`Error: ${e.message}`); }
                } else {
                    btn.disabled = true;
                    btn.textContent = 'Probando...';
                    try {
                        const r = await apiFetch('/coordinator/ia/probar', { method: 'POST', body: { modelo } });
                        abrirModal({
                            titulo: `Respuesta de ${modelo}`,
                            cuerpo: `<p>${escapeHtml(r.respuesta)}</p>`,
                            aceptarTexto: 'Cerrar',
                            onAceptar: () => {}
                        });
                    } catch (e) { mostrarToast(`Error: ${e.message}`); }
                    btn.disabled = false;
                    btn.textContent = 'Probar';
                }
            });
        });
    } catch (e) {
        lista.innerHTML = `<div class="item-glass"><span class="item-meta">Error: ${escapeHtml(e.message)}</span></div>`;
    }
}

async function iaPull() {
    const modelo = document.getElementById('iaPullNombre').value.trim();
    if (!modelo) {
        mostrarToast('Escribe el nombre del modelo a descargar');
        return;
    }
    const btn = document.getElementById('btnIaPull');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-ring"></span> Descargando...';
    try {
        mostrarToast(`Descargando ${modelo} (puede tardar varios minutos)...`);
        const r = await apiFetch('/coordinator/ia/pull', { method: 'POST', body: { modelo } });
        mostrarToast(`${r.modelo}: ${r.detalle}`);
        document.getElementById('iaPullNombre').value = '';
        loadIA();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-download"></i> Descargar';
    }
}

async function guardarIaParams() {
    try {
        await apiFetch('/coordinator/ia/params', {
            method: 'POST',
            body: {
                temperatura: parseFloat(document.getElementById('iaTemp').value),
                num_predict: parseInt(document.getElementById('iaPredict').value, 10),
                top_p: parseFloat(document.getElementById('iaTopP').value)
            }
        });
        mostrarToast('Parámetros guardados. Se aplican en el próximo mensaje del chat.');
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}

// ============================================
// SEGURIDAD / 2FA
// ============================================
async function loadMfa() {
    const estado = document.getElementById('mfaEstado');
    const acciones = document.getElementById('mfaActions');
    const disableBox = document.getElementById('mfaDisableBox');
    document.getElementById('mfaSetupBox').style.display = 'none';
    try {
        const me = await apiFetch('/auth/me');
        state.userData = me;
        if (me.mfa_enabled) {
            estado.innerHTML = '<i class="fas fa-circle-check"></i> El 2FA está <strong>activado</strong> en tu cuenta.';
            acciones.style.display = 'none';
            disableBox.style.display = 'block';
        } else {
            estado.innerHTML = '<i class="fas fa-triangle-exclamation"></i> El 2FA está <strong>desactivado</strong>.';
            acciones.style.display = 'block';
            disableBox.style.display = 'none';
        }
    } catch (e) {
        estado.textContent = `Error: ${e.message}`;
    }
}

async function mfaSetup() {
    try {
        const r = await apiFetch('/auth/mfa/setup', { method: 'POST' });
        document.getElementById('mfaQr').src = r.qr;
        document.getElementById('mfaSecret').textContent = r.secret;
        document.getElementById('mfaEnableCode').value = '';
        document.getElementById('mfaSetupBox').style.display = 'block';
        document.getElementById('mfaActions').style.display = 'none';
        document.getElementById('mfaDisableBox').style.display = 'none';
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}

async function mfaEnable() {
    const code = document.getElementById('mfaEnableCode').value.trim();
    if (!/^\d{6}$/.test(code)) { mostrarToast('Introduce el código de 6 dígitos'); return; }
    try {
        await apiFetch('/auth/mfa/enable', { method: 'POST', body: { code } });
        mostrarToast('2FA activado correctamente');
        loadMfa();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}

async function mfaDisable() {
    const code = document.getElementById('mfaDisableCode').value.trim();
    if (!/^\d{6}$/.test(code)) { mostrarToast('Introduce el código de 6 dígitos'); return; }
    try {
        await apiFetch('/auth/mfa/disable', { method: 'POST', body: { code } });
        mostrarToast('2FA desactivado');
        document.getElementById('mfaDisableCode').value = '';
        loadMfa();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}


// ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███    
//█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█   
// ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░  
//  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░ 
//████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░ 
// ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░ 
//  ░░░░  ░░░░░ ░░░░  ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░ 