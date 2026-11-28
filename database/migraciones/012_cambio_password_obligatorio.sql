-- ============================================================================
-- MIGRACIÓN 012 — Cambio obligatorio de contraseña tras un restablecimiento
-- ============================================================================
-- MOTIVO: cuando el administrador restablece una contraseña (temporal o
-- manual), el usuario debe cambiarla obligatoriamente en su siguiente inicio
-- de sesión. Mientras `debe_cambiar_password` sea TRUE:
--   * el login no emite un token de acceso normal, sino un ticket restringido
--     de cambio de contraseña;
--   * `usuario_actual()` rechaza cualquier token de acceso normal.
--
-- `intentos_cambio_password` limita a 3 los intentos de confirmar la
-- contraseña temporal. Se reinicia solo cuando el administrador vuelve a
-- restablecer la contraseña.
--
-- IDEMPOTENTE: ADD COLUMN IF NOT EXISTS.
-- ============================================================================

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS intentos_cambio_password INT NOT NULL DEFAULT 0;

-- ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███    
--█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█   
-- ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░  
--  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░ 
--████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░ 
-- ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░ 
--  ░░░░ ░░░░░ ░░░░ ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░ 
