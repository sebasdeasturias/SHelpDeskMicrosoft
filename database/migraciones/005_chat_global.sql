-- 005_chat_global.sql
-- Tabla del chat global: todos los roles autenticados (solicitante, agente,
-- coordinador, administrador) pueden conversar. Sin borrado de historial por
-- ahora; el DELETE en cascada solo aplica si se elimina el usuario.
--
-- Solo DDL (idempotente). NO se concede aquí permisos al rol de la app:
--   * La migración se aplica ANTES de que iniciar.sh cree el rol helpdesk_app
--     (GRANT a un rol inexistente fallaría en una instalación limpia).
--   * Los GRANT se centralizan en iniciar.sh, bloque "Usuario de BD de la
--     aplicación", que añade 'mensaje_chat_global' a su lista de tablas y
--     otorga USAGE/SELECT sobre las secuencias (idempotente en cada arranque).
CREATE TABLE IF NOT EXISTS mensaje_chat_global (
    id_mensaje SERIAL PRIMARY KEY,
    id_usuario INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    mensaje VARCHAR(1000) NOT NULL,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- El listado siempre se ordena por fecha/ids crecientes; este índice ayuda
-- al recorte inicial (últimos N mensajes) del polling del frontend.
CREATE INDEX IF NOT EXISTS idx_chat_global_fecha ON mensaje_chat_global (fecha DESC);
