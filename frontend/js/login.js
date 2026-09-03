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

// Toggle password visibility
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
        showError('Please enter both email and password');
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
        
        if (response.ok) {
            // Login exitoso
            await handleSuccessfulLogin(data, remember);
        } else {
            // Error del backend
            showError(data.detail || 'Invalid credentials');
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Connection error. Please check if the server is running.');
    } finally {
        hideLoading();
        btnLogin.disabled = false;
    }
});

// Manejar login exitoso
async function handleSuccessfulLogin(data, remember) {
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
    showSuccessMessage('Login successful! Redirecting...');
    
    // Esperar un momento y redirigir
    setTimeout(() => {
        window.location.href = redirectUrl;
    }, 1000);
}

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
