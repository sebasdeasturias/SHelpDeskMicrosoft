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
(function () {
    'use strict';

    var STYLE_ID = 'kanban-archive-styles';

    function inyectarEstilos() {
        if (document.getElementById(STYLE_ID)) return;
        var css = [
            '.ka-backdrop{position:fixed;inset:0;background:rgba(15,18,30,.55);backdrop-filter:blur(3px);',
            'display:flex;align-items:center;justify-content:center;z-index:10000;animation:ka-fade .15s ease;}',
            '.ka-modal{width:min(470px,calc(100vw - 40px));background:#ffffff;color:#1f2430;border-radius:14px;',
            'box-shadow:0 20px 60px rgba(0,0,0,.35);padding:22px 24px 18px;',
            "font-family:'Segoe UI',system-ui,-apple-system,sans-serif;animation:ka-pop .18s ease;}",
            '.ka-night .ka-modal{background:#232634;color:#e8eaf2;box-shadow:0 20px 60px rgba(0,0,0,.6);}',
            '.ka-cabecera{display:flex;align-items:center;gap:12px;margin-bottom:12px;}',
            '.ka-icono{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;',
            'font-size:21px;background:rgba(180,83,9,.14);flex:none;}',
            '.ka-titulo{font-size:17px;font-weight:700;margin:0;}',
            '.ka-ref{font-size:13px;font-weight:600;color:#b45309;background:rgba(180,83,9,.08);',
            'border:1px solid rgba(180,83,9,.25);padding:7px 10px;border-radius:8px;margin:0 0 10px;word-break:break-word;}',
            '.ka-texto{font-size:13.5px;line-height:1.6;margin:0 0 6px;}',
            '.ka-nota{font-size:12.5px;line-height:1.55;color:#6b7280;margin:0 0 16px;}',
            '.ka-night .ka-texto,.ka-night .ka-nota{color:#aeb4c4;}',
            '.ka-nota b{color:inherit;}',
            '.ka-acciones{display:flex;justify-content:flex-end;gap:10px;margin-top:16px;}',
            '.ka-btn{padding:9px 16px;border-radius:9px;font-size:13.5px;font-weight:600;border:1px solid transparent;',
            'cursor:pointer;transition:filter .15s ease;font-family:inherit;}',
            '.ka-btn:hover{filter:brightness(1.06);}',
            '.ka-btn-sec{background:#f1f3f7;color:#444c5c;border-color:#dfe3ea;}',
            '.ka-night .ka-btn-sec{background:#2d3140;color:#cdd2de;border-color:#3a3f52;}',
            '.ka-btn-primary{background:#b45309;color:#ffffff;}',
            '@keyframes ka-fade{from{opacity:0}to{opacity:1}}',
            '@keyframes ka-pop{from{transform:scale(.96);opacity:0}to{transform:scale(1);opacity:1}}'
        ].join('');
        var s = document.createElement('style');
        s.id = STYLE_ID;
        s.textContent = css;
        document.head.appendChild(s);
    }

    function abrirModal(opts) {
        inyectarEstilos();
        return new Promise(function (resolve) {
            var backdrop = document.createElement('div');
            backdrop.className = 'ka-backdrop' + (document.body.classList.contains('night-mode') ? ' ka-night' : '');

            var modal = document.createElement('div');
            modal.className = 'ka-modal';
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');

            var cab = document.createElement('div');
            cab.className = 'ka-cabecera';
            var icono = document.createElement('div');
            icono.className = 'ka-icono';
            icono.textContent = '🗂️';
            var titulo = document.createElement('h3');
            titulo.className = 'ka-titulo';
            titulo.textContent = opts.titulo;
            cab.appendChild(icono);
            cab.appendChild(titulo);
            modal.appendChild(cab);

            if (opts.ref) {
                var ref = document.createElement('div');
                ref.className = 'ka-ref';
                ref.textContent = opts.ref; // textContent: nunca HTML del usuario
                modal.appendChild(ref);
            }

            var texto = document.createElement('p');
            texto.className = 'ka-texto';
            texto.innerHTML = opts.textoHtml; // solo texto controlado del propio módulo
            modal.appendChild(texto);

            if (opts.notaHtml) {
                var nota = document.createElement('p');
                nota.className = 'ka-nota';
                nota.innerHTML = opts.notaHtml;
                modal.appendChild(nota);
            }

            var acciones = document.createElement('div');
            acciones.className = 'ka-acciones';

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
                btnSec.className = 'ka-btn ka-btn-sec';
                btnSec.textContent = opts.secundario || 'Cancelar';
                btnSec.addEventListener('click', function () { cerrar(false); });
                acciones.appendChild(btnSec);
            }

            var btnPri = document.createElement('button');
            btnPri.className = 'ka-btn ka-btn-primary';
            btnPri.textContent = opts.primario;
            btnPri.addEventListener('click', function () { cerrar(true); });
            acciones.appendChild(btnPri);

            modal.appendChild(acciones);
            backdrop.appendChild(modal);
            document.body.appendChild(backdrop);

            backdrop.addEventListener('mousedown', function (e) {
                if (e.target === backdrop) cerrar(false);
            });
            document.addEventListener('keydown', onKey);
            btnPri.focus();
        });
    }

    window.KanbanArchivo = {
        // Confirmación de archivo: true = archivar, false/cancelado = nada.
        confirmar: function (ticket) {
            var ref = '#' + ticket.id_solicitud;
            if (ticket.asunto) ref += ' — ' + ticket.asunto;
            return abrirModal({
                titulo: 'Archivar ticket',
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
                ref: null,
                textoHtml: 'Solo se pueden archivar tickets en estado <b>resuelto</b> o <b>cerrado</b>. ' +
                           'Este ticket está en estado <b>' + String(estado || 'desconocido').replace(/</g, '&lt;') + '</b>.',
                notaHtml: 'Muévelo a un estado completado y luego arrástralo aquí para archivarlo.',
                primario: 'Entendido',
                ocultarSecundario: true
            });
        }
    };
})();
