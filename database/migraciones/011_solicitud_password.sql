-- ============================================================================
-- MIGRACIÓN 011 — Solicitudes de restablecimiento de contraseña
-- ============================================================================
-- MOTIVO: el restablecimiento de contraseña no puede depender de correo/SMS
-- (el 2FA por móvil aún no está implantado). El usuario registra una solicitud
-- y el ADMINISTRADOR valida su identidad EN PERSONA antes de asignar una
-- contraseña temporal.
--
-- Estados:
--   pendiente          -> creada por el usuario, esperando validación presencial
--   identidad_validada -> el admin confirmó la identidad en persona
--   resuelta           -> el admin asignó la nueva contraseña
--   rechazada          -> el admin no pudo validar la identidad
--   cancelada          -> reservado (p. ej. cancelación manual futura)
--
-- IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS.
-- ============================================================================

CREATE TABLE IF NOT EXISTS solicitud_password (
    id_solicitud_password SERIAL PRIMARY KEY,
    -- Referencia viva al usuario; si se elimina, la solicitud conserva los
    -- datos snapshot (email/nombre/rol) para auditoría.
    id_usuario INTEGER REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    nombre VARCHAR(255),
    rol_solicitante VARCHAR(20),
    motivo TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'identidad_validada', 'resuelta', 'rechazada', 'cancelada')),
    origen_ip VARCHAR(45),
    id_admin_valida INTEGER REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
    fecha_identidad TIMESTAMPTZ,
    nota_validacion TEXT,
    id_admin_resuelve INTEGER REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
    fecha_resolucion TIMESTAMPTZ,
    nota_resolucion TEXT,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Listado del panel: abiertas primero por estado y fecha.
CREATE INDEX IF NOT EXISTS idx_solicitud_password_estado
    ON solicitud_password (estado, fecha_creacion DESC);

-- Una sola solicitud abierta por usuario: evita spam y validaciones duplicadas.
CREATE UNIQUE INDEX IF NOT EXISTS ux_solicitud_password_abierta
    ON solicitud_password (id_usuario)
    WHERE estado IN ('pendiente', 'identidad_validada');

-- ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███    
--█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█   
-- ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░  
--  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░ 
--████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░ 
-- ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░ 
--  ░░░░ ░░░░░ ░░░░ ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░ 
