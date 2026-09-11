-- ============================================================================
-- MIGRACIÓN 003 — Columnas faltantes en usuarios (rol_anterior / admin_temporal_hasta)
-- ============================================================================
-- MOTIVO (hallado en prueba de integración): el backend y el panel admin usan
-- usuarios.rol_anterior y usuarios.admin_temporal_hasta (promoción temporal a
-- administrador y degradación automática en el login), pero db_logic.sql no las
-- definía. En una instalación limpia, el login fallaba con
-- "column rol_anterior does not exist".
--
-- Idempotente: si las columnas ya existen, no hace nada.
-- Ejecutar como superusuario (POSTGRES_USER), no como helpdesk_app.
-- ============================================================================

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS rol_anterior VARCHAR(20);

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS admin_temporal_hasta TIMESTAMPTZ;
