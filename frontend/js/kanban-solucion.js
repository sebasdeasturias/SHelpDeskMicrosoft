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
(function () {
    'use strict';

    var STYLE_ID = 'kanban-solucion-styles';

    function inyectarEstilos() {
        if (document.getElementById(STYLE_ID)) return;
        var css = [
            '.ks-backdrop{position:fixed;inset:0;background:rgba(15,18,30,.55);backdrop-filter:blur(3px);',
            'display:flex;align-items:center;justify-content:center;z-index:10001;animation:ks-fade .15s ease;}',
            '.ks-modal{width:min(500px,calc(100vw - 40px));background:#ffffff;color:#1f2430;border-radius:14px;',
            'box-shadow:0 20px 60px rgba(0,0,0,.35);padding:22px 24px 18px;',
            "font-family:'Segoe UI',system-ui,-apple-system,sans-serif;animation:ks-pop .18s ease;}",
            '.ks-night .ks-modal{background:#232634;color:#e8eaf2;box-shadow:0 20px 60px rgba(0,0,0,.6);}',
            '.ks-cabecera{display:flex;align-items:center;gap:12px;margin-bottom:12px;}',
            '.ks-icono{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;',
            'font-size:21px;background:rgba(16,185,129,.16);flex:none;}',
            '.ks-titulo{font-size:17px;font-weight:700;margin:0;}',
            '.ks-ref{font-size:13px;font-weight:600;color:#047857;background:rgba(16,185,129,.08);',
            'border:1px solid rgba(16,185,129,.25);padding:7px 10px;border-radius:8px;margin:0 0 10px;word-break:break-word;}',
            '.ks-texto{font-size:13.5px;line-height:1.6;margin:0 0 12px;}',
            '.ks-night .ks-texto{color:#aeb4c4;}',
            '.ks-area{width:100%;min-height:96px;resize:vertical;box-sizing:border-box;',
            'padding:11px 13px;border-radius:10px;font-family:inherit;font-size:14px;line-height:1.55;',
            'background:#f7f9fc;color:#1f2430;border:1.5px solid #d7dce4;outline:none;transition:border-color .15s ease, box-shadow .15s ease;}',
            '.ks-area:focus{border-color:#10b981;box-shadow:0 0 0 3px rgba(16,185,129,.18);}',
            '.ks-area.ks-error{border-color:#ef4444;box-shadow:0 0 0 3px rgba(239,68,68,.15);}',
            '.ks-night .ks-area{background:#2d3140;color:#e8eaf2;border-color:#3a3f52;}',
            '.ks-error-msg{display:none;font-size:12.5px;color:#ef4444;margin:6px 2px 0;}',
            '.ks-error-msg.ks-visible{display:block;}',
            '.ks-acciones{display:flex;justify-content:flex-end;gap:10px;margin-top:14px;}',
            '.ks-btn{padding:9px 16px;border-radius:9px;font-size:13.5px;font-weight:600;border:1px solid transparent;',
            'cursor:pointer;transition:filter .15s ease;font-family:inherit;}',
            '.ks-btn:hover{filter:brightness(1.06);}',
            '.ks-btn-sec{background:#f1f3f7;color:#444c5c;border-color:#dfe3ea;}',
            '.ks-night .ks-btn-sec{background:#2d3140;color:#cdd2de;border-color:#3a3f52;}',
            '.ks-btn-primary{background:#10b981;color:#ffffff;}',
            '@keyframes ks-fade{from{opacity:0}to{opacity:1}}',
            '@keyframes ks-pop{from{transform:scale(.96);opacity:0}to{transform:scale(1);opacity:1}}'
        ].join('');
        var s = document.createElement('style');
        s.id = STYLE_ID;
        s.textContent = css;
        document.head.appendChild(s);
    }

    function pedir(ticket) {
        inyectarEstilos();
        return new Promise(function (resolve) {
            var backdrop = document.createElement('div');
            backdrop.className = 'ks-backdrop' + (document.body.classList.contains('night-mode') ? ' ks-night' : '');

            var modal = document.createElement('div');
            modal.className = 'ks-modal';
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');

            var cab = document.createElement('div');
            cab.className = 'ks-cabecera';
            var icono = document.createElement('div');
            icono.className = 'ks-icono';
            icono.textContent = '💡';
            var titulo = document.createElement('h3');
            titulo.className = 'ks-titulo';
            titulo.textContent = 'Completar ticket';
            cab.appendChild(icono);
            cab.appendChild(titulo);
            modal.appendChild(cab);

            var ref = document.createElement('div');
            ref.className = 'ks-ref';
            ref.textContent = '#' + ticket.id_solicitud + (ticket.asunto ? ' — ' + ticket.asunto : '');
            modal.appendChild(ref);

            var texto = document.createElement('p');
            texto.className = 'ks-texto';
            texto.textContent = 'Describe cómo resolviste el incidente. Esta solución será visible para el solicitante.';
            modal.appendChild(texto);

            var area = document.createElement('textarea');
            area.className = 'ks-area';
            area.placeholder = 'Ej: se restableció la contraseña y se verificó el acceso desde el equipo del usuario...';
            area.maxLength = 2000;
            modal.appendChild(area);

            var acciones = document.createElement('div');
            acciones.className = 'ks-acciones';

            function cerrar(resultado) {
                document.removeEventListener('keydown', onKey);
                backdrop.remove();
                resolve(resultado);
            }

            function onKey(e) {
                if (e.key === 'Escape') cerrar(null);
            }

            var btnSec = document.createElement('button');
            btnSec.className = 'ks-btn ks-btn-sec';
            btnSec.textContent = 'Cancelar';
            btnSec.addEventListener('click', function () { cerrar(null); });
            acciones.appendChild(btnSec);

            var btnPri = document.createElement('button');
            btnPri.className = 'ks-btn ks-btn-primary';
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

            backdrop.addEventListener('mousedown', function (e) {
                if (e.target === backdrop) cerrar(null);
            });
            document.addEventListener('keydown', onKey);
            area.focus();
        });
    }

    window.KanbanSolucion = { pedir: pedir };
})();
