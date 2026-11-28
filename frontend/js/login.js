// Configuración
const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000/api';

// Elementos del DOM
const loginForm = document.getElementById('loginForm');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const togglePasswordBtn = document.getElementById('togglePassword');
const errorMessage = document.getElementById('errorMessage');
const errorText = document.getElementById('errorText');
const loadingMessage = document.getElementById('loadingMessage');
const btnLogin = document.getElementById('btnLogin');
const mfaSection = document.getElementById('mfaSection');
const mfaCode = document.getElementById('mfaCode');
const btnMfaVerify = document.getElementById('btnMfaVerify');
const groupEmail = document.getElementById('groupEmail');
const groupPassword = document.getElementById('groupPassword');
let mfaToken = null;

// Modal obligatorio de cambio de contraseña temporal
const pwdChangeOverlay = document.getElementById('pwdChangeOverlay');
const pwdChangeForm = document.getElementById('pwdChangeForm');
const pwdTemporal = document.getElementById('pwdTemporal');
const pwdNueva = document.getElementById('pwdNueva');
const pwdNueva2 = document.getElementById('pwdNueva2');
const btnPwdChange = document.getElementById('btnPwdChange');
const pwdChangeError = document.getElementById('pwdChangeError');
const pwdChangeErrorText = document.getElementById('pwdChangeErrorText');
const pwdChangeLoading = document.getElementById('pwdChangeLoading');
const pwdChangeAttempts = document.getElementById('pwdChangeAttempts');
const pwdChangeBlocked = document.getElementById('pwdChangeBlocked');
const pwdChangeBlockedText = document.getElementById('pwdChangeBlockedText');

// Activar o desactivar visibilidad de la contraseña
togglePasswordBtn.addEventListener('click', () => {
    const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
    passwordInput.setAttribute('type', type);
    
    const icon = togglePasswordBtn.querySelector('i');
    icon.classList.toggle('fa-eye');
    icon.classList.toggle('fa-eye-slash');
});

// Manejar submit del formulario
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // Limpiar mensajes previos
    hideError();
    
    // Obtener valores
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    const remember = document.getElementById('remember').checked;
    
    // Validar
    if (!email || !password) {
        showError('Por favor, completa todos los campos.');
        return;
    }
    
    // Mostrar loading
    showLoading();
    btnLogin.disabled = true;
    
    try {
        // Llamar al backend
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                email: email,
                password: password,
            }),
        });
        
        const data = await response.json();
        
        if (response.ok && data.mfa_required) {
            // Credenciales correctas pero el usuario tiene 2FA: pedir el código.
            mfaToken = data.mfa_token;
            showMfaStep();
        } else if (response.ok) {
            // Login exitoso
            await handleSuccessfulLogin(data, remember);
        } else {
            // Error del backend
            showError(data.detail || 'Credenciales inválidas. Por favor, verifica tu email y contraseña.');
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Error de conexión. Por favor, verifica si el servidor está en funcionamiento.');
    } finally {
        hideLoading();
        btnLogin.disabled = false;
    }
});

// Mostrar el paso de segundo factor (2FA) ocultando usuario/contraseña
function showMfaStep() {
    hideError();
    groupEmail.style.display = 'none';
    groupPassword.style.display = 'none';
    btnLogin.style.display = 'none';
    mfaSection.style.display = 'block';
    mfaCode.value = '';
    mfaCode.focus();
}

// Verificar el código TOTP y completar el login
btnMfaVerify.addEventListener('click', async () => {
    hideError();
    const code = mfaCode.value.trim();
    if (!/^\d{6}$/.test(code)) {
        showError('Introduce el código de 6 dígitos.');
        return;
    }
    showLoading();
    btnMfaVerify.disabled = true;
    try {
        const response = await fetch(`${API_BASE_URL}/auth/mfa/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mfa_token: mfaToken, code: code }),
        });
        const data = await response.json();
        if (response.ok) {
            const remember = document.getElementById('remember').checked;
            await handleSuccessfulLogin(data, remember);
        } else {
            showError(data.detail || 'Código 2FA incorrecto.');
        }
    } catch (error) {
        console.error('MFA error:', error);
        showError('Error de conexión. Por favor, verifica si el servidor está en funcionamiento.');
    } finally {
        hideLoading();
        btnMfaVerify.disabled = false;
    }
});

// Permite enviar el código con Enter
mfaCode.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); btnMfaVerify.click(); }
});

// Manejar login exitoso
async function handleSuccessfulLogin(data, remember) {
    // El administrador restableció la contraseña: el backend no entrega un
    // token de acceso, solo un ticket restringido para cambiarla.
    if (data.password_change_required && data.pwd_change_token) {
        showForcedPasswordChange(data);
        return;
    }

    // Guardar token si es necesario
    if (data.access_token) {
        if (remember) {
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('user', JSON.stringify(data.user));
        } else {
            sessionStorage.setItem('token', data.access_token);
            sessionStorage.setItem('user', JSON.stringify(data.user));
        }
    }
    
    // Redirigir según el rol
    const userRole = data.user.rol || data.user.role;
    const redirectUrl = getRedirectUrl(userRole);
    
    // Mostrar mensaje de éxito
    showSuccessMessage('Inicio exitoso, redirigiendo...');
    
    // Esperar un momento y redirigir
    setTimeout(() => {
        window.location.href = redirectUrl;
    }, 1000);
}

// ============================================
// CAMBIO OBLIGATORIO DE CONTRASEÑA TEMPORAL
// ============================================
function showForcedPasswordChange(data) {
    // Un reset invalida cualquier sesión previa: se eliminan los tokens de
    // acceso y solo queda el ticket restringido.
    localStorage.removeItem('token');
    sessionStorage.removeItem('token');
    localStorage.removeItem('user');
    sessionStorage.removeItem('user');
    sessionStorage.setItem('pwd_change_token', data.pwd_change_token);

    const nombre = (data.user && (data.user.nombre || data.user.email))
        || sessionStorage.getItem('pwd_change_user')
        || 'Tu cuenta';
    sessionStorage.setItem('pwd_change_user', nombre);
    document.getElementById('pwdChangeUser').textContent = nombre;

    const restantes = (data.intentos_restantes != null)
        ? Number(data.intentos_restantes)
        : Number(sessionStorage.getItem('pwd_change_remaining') || 3);
    sessionStorage.setItem('pwd_change_remaining', String(restantes));

    // Restaurar el formulario de cambio (por si venía del estado bloqueado)
    pwdChangeForm.style.display = 'block';
    pwdChangeBlocked.style.display = 'none';
    pwdChangeAttempts.style.display = 'block';
    pwdChangeAttempts.textContent =
        `Intentos restantes: ${restantes}. Si se agotan, deberás solicitar un nuevo ` +
        'restablecimiento al administrador.';
    hidePwdChangeError();
    pwdTemporal.value = '';
    pwdNueva.value = '';
    pwdNueva2.value = '';

    pwdChangeOverlay.classList.add('open');
    document.body.classList.add('pwd-change-lock');
    pwdChangeOverlay.setAttribute('aria-hidden', 'false');
    setTimeout(() => pwdTemporal.focus(), 60);
}

function showPwdChangeError(msg) {
    pwdChangeErrorText.textContent = msg;
    pwdChangeError.style.display = 'flex';
}

function hidePwdChangeError() {
    pwdChangeError.style.display = 'none';
}

function setPwdChangeLoading(on) {
    pwdChangeLoading.style.display = on ? 'flex' : 'none';
    btnPwdChange.disabled = on;
}

function showPwdChangeBlocked(msg) {
    pwdChangeForm.style.display = 'none';
    pwdChangeAttempts.style.display = 'none';
    hidePwdChangeError();
    pwdChangeBlockedText.textContent = msg;
    pwdChangeBlocked.style.display = 'block';
}

function cerrarPwdChange() {
    sessionStorage.removeItem('pwd_change_token');
    sessionStorage.removeItem('pwd_change_user');
    sessionStorage.removeItem('pwd_change_remaining');
    pwdChangeOverlay.classList.remove('open');
    document.body.classList.remove('pwd-change-lock');
    pwdChangeOverlay.setAttribute('aria-hidden', 'true');
}

pwdChangeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hidePwdChangeError();

    const temporal = pwdTemporal.value;
    const nueva = pwdNueva.value;
    const nueva2 = pwdNueva2.value;

    if (!temporal || !nueva || !nueva2) {
        showPwdChangeError('Completa los tres campos para continuar.');
        return;
    }
    if (nueva.length < 8) {
        showPwdChangeError('La nueva contraseña debe tener al menos 8 caracteres.');
        return;
    }
    if (nueva !== nueva2) {
        showPwdChangeError('Las contraseñas nuevas no coinciden. Verifica que ambas sean iguales.');
        return;
    }
    if (nueva === temporal) {
        showPwdChangeError('La nueva contraseña debe ser distinta de la temporal.');
        return;
    }

    const changeToken = sessionStorage.getItem('pwd_change_token');
    if (!changeToken) {
        showPwdChangeError('Tu ticket de cambio expiró. Inicia sesión de nuevo con la contraseña temporal.');
        return;
    }

    setPwdChangeLoading(true);
    try {
        const response = await fetch(`${API_BASE_URL}/auth/password-change`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${changeToken}`,
            },
            body: JSON.stringify({
                password_temporal: temporal,
                password_nueva: nueva,
                password_nueva2: nueva2,
            }),
        });

        let data = {};
        try { data = await response.json(); } catch (_) { /* sin JSON */ }

        if (response.ok) {
            cerrarPwdChange();
            const remember = document.getElementById('remember').checked;
            await handleSuccessfulLogin(data, remember);
            return;
        }

        const detail = data.detail;
        if (detail && typeof detail === 'object') {
            if (detail.bloqueado || response.status === 403) {
                // Se agotaron los intentos: se invalida el ticket, pero el modal
                // permanece abierto mostrando el bloqueo (no se puede saltar).
                sessionStorage.removeItem('pwd_change_token');
                sessionStorage.setItem('pwd_change_remaining', '0');
                showPwdChangeBlocked(detail.mensaje ||
                    'Has agotado los 3 intentos. Solicita un nuevo restablecimiento al administrador.');
                return;
            }
            if (detail.intentos_restantes != null) {
                sessionStorage.setItem('pwd_change_remaining', String(detail.intentos_restantes));
                pwdChangeAttempts.textContent =
                    `Intentos restantes: ${detail.intentos_restantes}. Si se agotan, ` +
                    'deberás solicitar un nuevo restablecimiento al administrador.';
            }
            showPwdChangeError(detail.mensaje || 'No se pudo cambiar la contraseña.');
            pwdTemporal.value = '';
            pwdTemporal.focus();
            return;
        }

        if (response.status === 401) {
            // Ticket expirado o revocado: hay que iniciar sesión otra vez.
            cerrarPwdChange();
            showError(typeof detail === 'string' ? detail :
                'Tu sesión de cambio expiró. Inicia sesión de nuevo con la contraseña temporal.');
            return;
        }

        showPwdChangeError(typeof detail === 'string' ? detail : 'No se pudo cambiar la contraseña.');
    } catch (error) {
        console.error('Password change error:', error);
        showPwdChangeError('Error de conexión. Verifica si el servidor está en funcionamiento.');
    } finally {
        setPwdChangeLoading(false);
    }
});

document.getElementById('btnPwdChangeBack').addEventListener('click', () => {
    cerrarPwdChange();
    mfaSection.style.display = 'none';
    groupEmail.style.display = 'flex';
    groupPassword.style.display = 'flex';
    btnLogin.style.display = 'block';
    showError('Has agotado los 3 intentos. Solicita un nuevo restablecimiento al administrador.');
});

// Obtener URL de redirección según el rol
function getRedirectUrl(role) {
    const roleUrls = {
        'solicitante': 'dashboard-solicitante.html',
        'agente': 'dashboard-agente.html',
        'coordinador': 'dashboard-coordinador.html',
        'administrador': 'dashboard-admin.html',
    };
    
    return roleUrls[role] || 'login.html';
}

// Mostrar error
function showError(message) {
    errorText.textContent = message;
    errorMessage.style.display = 'flex';
}

// Ocultar error
function hideError() {
    errorMessage.style.display = 'none';
}

// Mostrar loading
function showLoading() {
    loadingMessage.style.display = 'flex';
}

// Ocultar loading
function hideLoading() {
    loadingMessage.style.display = 'none';
}

// Mostrar mensaje de éxito
function showSuccessMessage(message) {
    errorText.textContent = message;
    errorMessage.style.display = 'flex';
    errorMessage.style.background = 'rgba(16, 185, 129, 0.1)';
    errorMessage.style.borderColor = 'var(--secondary-color)';
    errorMessage.style.color = 'var(--secondary-color)';
}

// Verificar si hay token guardado al cargar la página
window.addEventListener('load', async () => {
    // Prioridad absoluta: si hay un cambio de contraseña pendiente, no se
    // permite entrar al sistema hasta completarlo (ni siquiera recargando).
    const pendingChange = sessionStorage.getItem('pwd_change_token');
    if (pendingChange) {
        showForcedPasswordChange({
            pwd_change_token: pendingChange,
            intentos_restantes: sessionStorage.getItem('pwd_change_remaining'),
        });
        return;
    }

    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    if (token) {
        try {
            // Verificar que el token sea válido antes de redirigir
            const response = await fetch(`${API_BASE_URL}/auth/me`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                const user = await response.json();
                // Guardar usuario actualizado en el mismo almacén que el token
                const storage = localStorage.getItem('token') ? localStorage : sessionStorage;
                storage.setItem('user', JSON.stringify(user));
                
                // Redirigir según rol (el endpoint /auth/me devuelve el campo 'role')
                const redirectUrl = getRedirectUrl(user.role);
                window.location.href = redirectUrl;
            } else {
                // Token inválido, limpiar
                localStorage.removeItem('token');
                sessionStorage.removeItem('token');
                localStorage.removeItem('user');
                sessionStorage.removeItem('user');
            }
        } catch (error) {
            console.warn('Error verificando token:', error);
            // Si hay error, limpiar y quedarse en login
            localStorage.removeItem('token');
            sessionStorage.removeItem('token');
            localStorage.removeItem('user');
            sessionStorage.removeItem('user');
        }
    }
    
    // Auto-completar email si está guardado
    const savedEmail = localStorage.getItem('remembered_email');
    if (savedEmail) {
        emailInput.value = savedEmail;
        document.getElementById('remember').checked = true;
    }
});

// Guardar email si se marca "Remember me"
emailInput.addEventListener('blur', () => {
    const remember = document.getElementById('remember').checked;
    if (remember && emailInput.value) {
        localStorage.setItem('remembered_email', emailInput.value);
    }
});



// ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███    
//█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█   
// ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░  
//  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░ 
//████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░ 
// ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░ 
//  ░░░░  ░░░░░ ░░░░  ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░ 