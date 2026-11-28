// recuperar-password.js — Solicitud de restablecimiento con validación presencial.
const API_BASE = window.API_BASE_URL || 'http://localhost:8000/api';

const recoverForm = document.getElementById('recoverForm');
const recoverEmail = document.getElementById('recoverEmail');
const recoverMotivo = document.getElementById('recoverMotivo');
const btnRecover = document.getElementById('btnRecover');
const recoverError = document.getElementById('recoverError');
const recoverErrorText = document.getElementById('recoverErrorText');
const recoverLoading = document.getElementById('recoverLoading');
const recoverSuccess = document.getElementById('recoverSuccess');
const recoverSuccessText = document.getElementById('recoverSuccessText');

function showError(msg) {
    recoverErrorText.textContent = msg;
    recoverError.style.display = 'flex';
}

function hideError() {
    recoverError.style.display = 'none';
}

function setLoading(on) {
    recoverLoading.style.display = on ? 'flex' : 'none';
    btnRecover.disabled = on;
}

recoverForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideError();

    const email = recoverEmail.value.trim().toLowerCase();
    if (!email) {
        showError('Escribe el correo con el que estás registrado.');
        return;
    }

    setLoading(true);
    try {
        const res = await fetch(`${API_BASE}/auth/password-reset-request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email,
                motivo: recoverMotivo.value.trim() || null,
            }),
        });

        let data = {};
        try { data = await res.json(); } catch (_) { /* respuesta sin JSON */ }

        if (!res.ok) {
            // 429 = límite anti-abuso; el resto se muestra genérico.
            throw new Error(data.detail || 'No se pudo registrar la solicitud. Inténtalo de nuevo.');
        }

        // Respuesta genérica: no confirma si el correo existe.
        recoverForm.style.display = 'none';
        recoverSuccessText.textContent = data.mensaje ||
            'Si el correo pertenece a una cuenta activa, la solicitud quedó registrada.';
        recoverSuccess.style.display = 'block';
    } catch (err) {
        showError(err.message || 'Error de conexión. Verifica que el servicio esté disponible.');
    } finally {
        setLoading(false);
    }
});
