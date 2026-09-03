// Configuración
const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000/api';

// Elementos del DOM
const registerForm = document.getElementById('registerForm');
const nombresInput = document.getElementById('nombres');
const apellidosInput = document.getElementById('apellidos');
const emailInput = document.getElementById('email');
const areaSelect = document.getElementById('area');
const passwordInput = document.getElementById('password');
const password2Input = document.getElementById('password2');
const togglePasswordBtn = document.getElementById('togglePassword');
const togglePassword2Btn = document.getElementById('togglePassword2');
const errorMessage = document.getElementById('errorMessage');
const errorText = document.getElementById('errorText');
const successMessage = document.getElementById('successMessage');
const successText = document.getElementById('successText');
const loadingMessage = document.getElementById('loadingMessage');
const btnRegister = document.getElementById('btnRegister');

// Toggle password visibility
togglePasswordBtn.addEventListener('click', () => {
    const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
    passwordInput.setAttribute('type', type);
    
    const icon = togglePasswordBtn.querySelector('i');
    icon.classList.toggle('fa-eye');
    icon.classList.toggle('fa-eye-slash');
});

togglePassword2Btn.addEventListener('click', () => {
    const type = password2Input.getAttribute('type') === 'password' ? 'text' : 'password';
    password2Input.setAttribute('type', type);
    
    const icon = togglePassword2Btn.querySelector('i');
    icon.classList.toggle('fa-eye');
    icon.classList.toggle('fa-eye-slash');
});

// Manejar submit del formulario
registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // Limpiar mensajes previos
    hideError();
    hideSuccess();
    
    // Obtener valores
    const nombres = nombresInput.value.trim();
    const apellidos = apellidosInput.value.trim();
    const email = emailInput.value.trim();
    const area = areaSelect.value;
    const password = passwordInput.value;
    const password2 = password2Input.value;
    
    // Validaciones
    if (!nombres || !apellidos || !email || !area || !password || !password2) {
        showError('Por favor completa todos los campos');
        return;
    }
    
    if (password !== password2) {
        showError('Las contraseñas no coinciden');
        return;
    }
    
    if (password.length < 6) {
        showError('La contraseña debe tener al menos 6 caracteres');
        return;
    }
    
    // Validar formato de email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        showError('Por favor ingresa un correo válido');
        return;
    }
    
    // Mostrar loading
    showLoading();
    btnRegister.disabled = true;
    
    try {
        // Llamar al backend
        const response = await fetch(`${API_BASE_URL}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                nombres: nombres,
                apellidos: apellidos,
                email: email,
                area: area,
                password: password,
            }),
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Registro exitoso
            showSuccess('¡Registro exitoso! Ahora puedes iniciar sesión.');
            
            btnRegister.disabled = true;
            document.querySelectorAll('.input-group input, .input-group select').forEach(el => el.disabled = true);
            
            // Redirigir al login después de 2 segundos
            setTimeout(() => {
                window.location.href = 'login.html';
            }, 2000);
        } else {
            // Error del backend
            showError(data.detail || 'Error al registrar usuario');
        }
    } catch (error) {
        console.error('Register error:', error);
        showError('Error de conexión. Verifica que el servidor esté corriendo.');
    } finally {
        hideLoading();
        btnRegister.disabled = false;
    }
});

// Mostrar error
function showError(message) {
    errorText.textContent = message;
    errorMessage.style.display = 'flex';
}

// Ocultar error
function hideError() {
    errorMessage.style.display = 'none';
}

// Mostrar éxito
function showSuccess(message) {
    successText.textContent = message;
    successMessage.style.display = 'flex';
}

// Ocultar éxito
function hideSuccess() {
    successMessage.style.display = 'none';
}

// Mostrar loading
function showLoading() {
    loadingMessage.style.display = 'flex';
}

// Ocultar loading
function hideLoading() {
    loadingMessage.style.display = 'none';
}
