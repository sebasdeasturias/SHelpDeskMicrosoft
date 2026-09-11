-- 008_auth_hardening.sql
-- Endurecimiento de autenticación (idempotente).
--   * intentos_fallidos / bloqueado_hasta: bloqueo temporal de cuenta ante
--     fuerza bruta, persistido en BD (no solo el limitador en memoria).
--   * token_version: permite revocar los JWT vigentes al cambiar la contraseña
--     (el login y la revalidación comparan el claim `tv`).
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS intentos_fallidos INT NOT NULL DEFAULT 0;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado_hasta TIMESTAMPTZ;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS token_version INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_usuarios_bloqueado_hasta ON usuarios (bloqueado_hasta);
