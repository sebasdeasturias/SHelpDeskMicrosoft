-- 006_mfa.sql — Segundo factor (TOTP) por usuario.
-- Idempotente: se puede aplicar varias veces sin efectos secundarios.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(64);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE;
