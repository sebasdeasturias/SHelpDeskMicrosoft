// markdown-ligero.js
// Renderizador Markdown MÍNIMO y SEGURO para las respuestas de la IA (chat y
// análisis RAG). La respuesta del modelo es contenido NO confiable, así que la
// estrategia es: 1) escapar TODO el HTML primero, 2) sobre ese texto ya
// escapado aplicar un subconjunto reducido de Markdown. Como <, > y & ya son
// entidades (&lt; &gt; &amp;) antes de tocar los asteriscos, es imposible que
// se inyecten etiquetas: nunca se construye HTML a partir de datos sin escapar.
// Respeta la CSP estricta (no usa eval, no inyecta <script>).
//
// Subconjunto soportado:
//   **texto**  o  __texto__   -> <strong>
//   *texto*    o  _texto_     -> <em>
//   `texto`                   -> <code>
//   saltos de línea \n        -> <br>
(function () {
    'use strict';

    function escaparHtml(v) {
        return String(v == null ? '' : v)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function mdLigero(texto) {
        // 1) Escapar: a partir de aquí no hay HTML del servidor sin neutralizar.
        var s = escaparHtml(texto);

        // 2) Código en línea primero, para que su contenido no se reinterprete
        //    como negrita/cursiva. El texto interno ya está escapado.
        s = s.replace(/`([^`\n]+?)`/g, function (_m, code) {
            return '<code>' + code + '</code>';
        });

        // 3) Negrita: **texto** o __texto__ (no vacío, sin cruzar saltos).
        s = s.replace(/\*\*([^\s*][^*\n]*?)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/__([^\s_][^_\n]*?)__/g, '<strong>$1</strong>');

        // 4) Cursiva: *texto* o _texto_. Se aplica después de la negrita para
        //    no capturar los asteriscos dobles ya convertidos.
        s = s.replace(/(^|[^*])\*([^\s*][^*\n]*?)\*(?!\*)/g, '$1<em>$2</em>');
        s = s.replace(/(^|[^_])_([^\s_][^_\n]*?)_(?!_)/g, '$1<em>$2</em>');

        // 5) Saltos de línea.
        s = s.replace(/\n/g, '<br>');

        return s;
    }

    // Expuesto en window para que lo usen los dashboards (chat IA y RAG).
    window.mdLigero = mdLigero;
    window.escaparHtml = window.escaparHtml || escaparHtml;
})();
