// frontend/js/kanban-solucion.js — Modal de "solución" (Kanban).
// Compartido por los tableros de agente y coordinador (roles agente,
// coordinador y administrador). Debe cargarse ANTES del script del dashboard.
//
// API global:
//   KanbanSolucion.pedir(ticket) -> Promise<{solucion: string} | null>
//     null = cancelado (la tarjeta NO se mueve a "Completados").
//
// Flujo: al arrastrar una tarjeta a la columna "Completados" (estado 'cerrado'),
// se pide al agente/coordinador/administrador que describa cómo resolvió el
// incidente. El texto se guarda en solicitud.solucion y es visible para el
// solicitante desde su dashboard ("Ver solución").
//
// Estilos: reutiliza la cáscara común de styles/popups.css (modal-overlay,
// modal-content, modal-header...). No inyecta CSS propio.
(function () {
    'use strict';

    function pedir(ticket) {
        return new Promise(function (resolve) {
            var backdrop = document.createElement('div');
            backdrop.className = 'modal-overlay';

            var modal = document.createElement('div');
            modal.className = 'modal-content kanban-modal';
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');

            // Cabecera unificada: icono + título + cierre.
            var header = document.createElement('div');
            header.className = 'modal-header';

            var titulo = document.createElement('h3');
            var iconoWrap = document.createElement('span');
            iconoWrap.className = 'modal-icon';
            var icono = document.createElement('i');
            icono.className = 'fas fa-lightbulb';
            icono.setAttribute('aria-hidden', 'true');
            iconoWrap.appendChild(icono);
            var tituloTexto = document.createElement('span');
            tituloTexto.textContent = 'Completar ticket';
            titulo.appendChild(iconoWrap);
            titulo.appendChild(tituloTexto);

            var btnCerrar = document.createElement('button');
            btnCerrar.type = 'button';
            btnCerrar.className = 'modal-close';
            btnCerrar.setAttribute('aria-label', 'Cerrar');
            btnCerrar.innerHTML = '<i class="fas fa-xmark" aria-hidden="true"></i>';

            header.appendChild(titulo);
            header.appendChild(btnCerrar);
            modal.appendChild(header);

            // Cuerpo: referencia del ticket + explicación + textarea.
            var body = document.createElement('div');
            body.className = 'modal-body';

            var ref = document.createElement('div');
            ref.className = 'modal-ref';
            ref.textContent = '#' + ticket.id_solicitud + (ticket.asunto ? ' — ' + ticket.asunto : '');
            body.appendChild(ref);

            var texto = document.createElement('p');
            texto.textContent = 'Describe cómo resolviste el incidente. Esta solución será visible para el solicitante.';
            body.appendChild(texto);

            var area = document.createElement('textarea');
            area.className = 'modal-textarea';
            area.placeholder = 'Ej: se restableció la contraseña y se verificó el acceso desde el equipo del usuario...';
            area.maxLength = 2000;
            body.appendChild(area);

            modal.appendChild(body);

            var acciones = document.createElement('div');
            acciones.className = 'modal-footer';

            function cerrar(resultado) {
                document.removeEventListener('keydown', onKey);
                backdrop.remove();
                resolve(resultado);
            }

            function onKey(e) {
                if (e.key === 'Escape') cerrar(null);
            }

            var btnSec = document.createElement('button');
            btnSec.type = 'button';
            btnSec.className = 'btn-cancel';
            btnSec.textContent = 'Cancelar';
            btnSec.addEventListener('click', function () { cerrar(null); });
            acciones.appendChild(btnSec);

            var btnPri = document.createElement('button');
            btnPri.type = 'button';
            btnPri.className = 'btn-confirm';
            btnPri.textContent = 'Guardar y completar';
            btnPri.addEventListener('click', function () {
                // Sin comentario (o vacío) se trata como cancelación: el ticket
                // vuelve a su columna original.
                var valor = area.value.trim();
                cerrar(valor ? { solucion: valor } : null);
            });
            acciones.appendChild(btnPri);

            modal.appendChild(acciones);
            backdrop.appendChild(modal);
            document.body.appendChild(backdrop);

            btnCerrar.addEventListener('click', function () { cerrar(null); });
            backdrop.addEventListener('mousedown', function (e) {
                if (e.target === backdrop) cerrar(null);
            });
            document.addEventListener('keydown', onKey);
            requestAnimationFrame(function () {
                backdrop.classList.add('open');
                requestAnimationFrame(function () { area.focus(); });
            });
        });
    }

    window.KanbanSolucion = { pedir: pedir };
})();



// ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███
//█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█
// ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░
//  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░
//████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░
// ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░
//  ░░░░  ░░░░░ ░░░░  ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░
