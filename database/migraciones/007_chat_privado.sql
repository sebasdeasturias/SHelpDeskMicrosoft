-- 007_chat_privado.sql
-- Tabla del chat privado 1 a 1 entre personal interno (agente, coordinador,
-- administrador). Cada fila es un mensaje dirigido de un emisor a un receptor.
-- Solo DDL idempotente; los GRANT se centralizan en los scripts de arranque
-- (Iniciar.ps1 / iniciar.sh), que incluyen 'mensaje_chat_privado' en su lista
-- de tablas y otorgan USAGE/SELECT sobre las secuencias.
CREATE TABLE IF NOT EXISTS mensaje_chat_privado (
    id_mensaje SERIAL PRIMARY KEY,
    id_emisor INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_receptor INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    mensaje VARCHAR(1000) NOT NULL,
    leido BOOLEAN NOT NULL DEFAULT FALSE,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Recuperar una conversación: filtra por la pareja (emisor, receptor) y ordena
-- por id creciente para el polling incremental del frontend.
CREATE INDEX IF NOT EXISTS idx_chat_privado_conv
    ON mensaje_chat_privado (id_emisor, id_receptor, id_mensaje);

-- Conteo de no leídos por receptor (badge de contactos y total del FAB).
CREATE INDEX IF NOT EXISTS idx_chat_privado_no_leidos
    ON mensaje_chat_privado (id_receptor, leido);
