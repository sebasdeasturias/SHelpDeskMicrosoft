-- ============================================================================
-- USUARIOS DE PRUEBA - SISTEMA HELPDESK
-- 4 usuarios: 1 Solicitante, 1 Agente, 1 Coordinador, 1 Admin
-- Contraseña para todos: password123
-- Hash bcrypt generado con: bcrypt.hashpw('password123'.encode('utf-8'), bcrypt.gensalt())
--
-- IDEMPOTENTE: con ON CONFLICT (email) DO NOTHING, re-ejecutar el seed NO
-- duplica usuarios y NUNCA pisa cambios hechos desde el panel (contraseñas,
-- roles, estados). Solo crea los que falten en una BD nueva.
-- ============================================================================

-- Insertar Usuarios de Prueba
INSERT INTO usuarios (nombre, email, contraseña, rol, area, estado, especialidad, carga_trabajo, nivel_jerarquia, permisos_supervision, nivel_acceso, permisos_especiales) VALUES
-- 1. SOLICITANTE (Usuario final que reporta incidentes)
(
    'Sebastian Solicitante',
    'sebastian-solicitante@empresa.com',
    '$2b$12$iYqdmnOYc.sFE6TYLkdfIe80LhwpKH/VMRCbBtKBg6wcw7h/t/vvG', 
    'solicitante',
    'Ventas',
    'activo',
    NULL,  -- especialidad
    0,     -- carga_trabajo
    NULL,  -- nivel_jerarquia
    FALSE, -- permisos_supervision
    NULL,  -- nivel_acceso
    NULL   -- permisos_especiales
),

-- 2. AGENTE DE SOPORTE (Técnico que atiende tickets)
(
    'Sebastian Agente',
    'sebastian-agente@empresa.com',
    '$2b$12$iYqdmnOYc.sFE6TYLkdfIe80LhwpKH/VMRCbBtKBg6wcw7h/t/vvG', 
    'agente',
    'Soporte TI',
    'activo',
    'Hardware y Redes',  -- especialidad
    0,                   -- carga_trabajo
    NULL,                -- nivel_jerarquia
    FALSE,               -- permisos_supervision
    NULL,                -- nivel_acceso
    NULL                 -- permisos_especiales
),

-- 3. COORDINADOR DE SOPORTE (Supervisor)
(
    'Sebastian Coordinador',
    'sebastian-coordinador@empresa.com',
    '$2b$12$iYqdmnOYc.sFE6TYLkdfIe80LhwpKH/VMRCbBtKBg6wcw7h/t/vvG', 
    'coordinador',
    'Soporte TI',
    'activo',
    'Gestión de Equipos',  -- especialidad
    0,                    -- carga_trabajo
    2,                    -- nivel_jerarquia
    TRUE,                 -- permisos_supervision
    NULL,                 -- nivel_acceso
    NULL                  -- permisos_especiales
),

-- 4. ADMINISTRADOR DEL SISTEMA (Máximos privilegios)
(
    'Sebastian Administrador',
    'sebastian-admin@empresa.com',
    '$2b$12$iYqdmnOYc.sFE6TYLkdfIe80LhwpKH/VMRCbBtKBg6wcw7h/t/vvG',  
    'administrador',
    'TI',
    'activo',
    'Administración de Sistemas',  -- especialidad
    0,                             -- carga_trabajo
    3,                    -- nivel_jerarquia
    TRUE,                          -- permisos_supervision
    NULL,                  -- nivel_acceso
    TRUE                           -- permisos_especiales
)
ON CONFLICT (email) DO NOTHING;

-- Verificar usuarios creados
SELECT id_usuario, nombre, email, rol, area, estado 
FROM usuarios 
ORDER BY 
    CASE rol 
        WHEN 'administrador' THEN 1 
        WHEN 'coordinador' THEN 2 
        WHEN 'agente' THEN 3 
        WHEN 'solicitante' THEN 4 
    END;
