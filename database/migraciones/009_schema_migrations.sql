-- 009_schema_migrations.sql
-- Tabla de control de migraciones aplicadas (permite saber el estado del
-- esquema de forma determinista, en lugar de depender solo de idempotencia).
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Backfill de las migraciones ya existentes en instalaciones previas.
INSERT INTO schema_migrations (version) VALUES
    ('001_pgvector_1024'),
    ('002_eliminar_trigger_historial'),
    ('003_columnas_usuarios'),
    ('004_estado_archivado'),
    ('005_chat_global'),
    ('006_mfa'),
    ('007_chat_privado'),
    ('008_auth_hardening')
ON CONFLICT (version) DO NOTHING;
