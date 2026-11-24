// frontend/js/kanban-archive.js — Modal de confirmación de archivo (Kanban).
// Compartido por los tableros de agente y coordinador (roles agente,
// coordinador y administrador). Debe cargarse ANTES del script del dashboard.
//
// API global:
//   KanbanArchivo.confirmar(ticket)   -> Promise<boolean>  (true = archivar)
//   KanbanArchivo.avisoNoArchivable(estado) -> Promise<void> (solo informativo)
//
// Flujo acordado: arrastrar una tarjeta resuelta/cerrada a la columna
// "Archivado" pide confirmación; al confirmar, el ticket se archiva (estado
// terminal) y desaparece del tablero. Los datos e historial se conservan.
//
// Estilos: reutiliza la cáscara común de styles/popups.css (modal-overlay,
// modal-content, modal-header...). No inyecta CSS propio.
(function () {
    'use strict';

    function abrirModal(opts) {
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
            icono.className = 'fas ' + (opts.icono || 'fa-circle-question');
            icono.setAttribute('aria-hidden', 'true');
            iconoWrap.appendChild(icono);
            var tituloTexto = document.createElement('span');
            tituloTexto.textContent = opts.titulo;
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

            // Cuerpo: referencia, texto y nota opcional.
            var body = document.createElement('div');
            body.className = 'modal-body';

            if (opts.ref) {
                var ref = document.createElement('div');
                ref.className = 'modal-ref';
                ref.textContent = opts.ref; // textContent: nunca HTML del usuario
                body.appendChild(ref);
            }

            var texto = document.createElement('p');
            texto.innerHTML = opts.textoHtml; // solo texto controlado del propio módulo
            body.appendChild(texto);

            if (opts.notaHtml) {
                var nota = document.createElement('p');
                nota.className = 'modal-note';
                nota.innerHTML = opts.notaHtml;
                body.appendChild(nota);
            }

            modal.appendChild(body);

            var acciones = document.createElement('div');
            acciones.className = 'modal-footer';

            function cerrar(resultado) {
                document.removeEventListener('keydown', onKey);
                backdrop.remove();
                resolve(resultado);
            }

            function onKey(e) {
                if (e.key === 'Escape') cerrar(false);
                if (e.key === 'Enter' && !opts.ocultarSecundario) cerrar(true);
            }

            if (!opts.ocultarSecundario) {
                var btnSec = document.createElement('button');
                btnSec.type = 'button';
                btnSec.className = 'btn-cancel';
                btnSec.textContent = opts.secundario || 'Cancelar';
                btnSec.addEventListener('click', function () { cerrar(false); });
                acciones.appendChild(btnSec);
            }

            var btnPri = document.createElement('button');
            btnPri.type = 'button';
            btnPri.className = 'btn-confirm' + (opts.peligroso ? ' warning' : '');
            btnPri.textContent = opts.primario;
            btnPri.addEventListener('click', function () { cerrar(true); });
            acciones.appendChild(btnPri);

            modal.appendChild(acciones);
            backdrop.appendChild(modal);
            document.body.appendChild(backdrop);

            btnCerrar.addEventListener('click', function () { cerrar(false); });
            backdrop.addEventListener('mousedown', function (e) {
                if (e.target === backdrop) cerrar(false);
            });
            document.addEventListener('keydown', onKey);
            requestAnimationFrame(function () {
                backdrop.classList.add('open');
                requestAnimationFrame(function () { btnPri.focus(); });
            });
        });
    }

    window.KanbanArchivo = {
        // Confirmación de archivo: true = archivar, false/cancelado = nada.
        confirmar: function (ticket) {
            var ref = '#' + ticket.id_solicitud;
            if (ticket.asunto) ref += ' — ' + ticket.asunto;
            return abrirModal({
                titulo: 'Archivar ticket',
                icono: 'fa-box-archive',
                peligroso: true,
                ref: ref,
                textoHtml: '¿Estás seguro de que deseas <b>archivar</b> este ticket?',
                notaHtml: 'El ticket se retirará del tablero y <b>no volverá a aparecer en el Kanban</b>. ' +
                          'Sus datos e historial se conservan en la base de datos; esta acción no se ' +
                          'puede deshacer desde el tablero.',
                primario: 'Archivar ticket',
                secundario: 'Cancelar'
            });
        },

        // Aviso: solo tickets resueltos/cerrados son archivables.
        avisoNoArchivable: function (estado) {
            return abrirModal({
                titulo: 'No se puede archivar',
                icono: 'fa-triangle-exclamation',
                ref: null,
                textoHtml: 'Solo se pueden archivar tickets en estado <b>resuelto</b> o <b>cerrado</b>. ' +
                           'Este ticket está en estado <b>' + String(estado || 'desconocido').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</b>.',
                notaHtml: 'Muévelo a un estado completado y luego arrástralo aquí para archivarlo.',
                primario: 'Entendido',
                ocultarSecundario: true
            });
        }
    };
})();



// ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███
//█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█
// ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░
//  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░
//████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░
// ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░
//  ░░░░  ░░░░░ ░░░░  ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░
