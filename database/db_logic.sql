-- ============================================================================
-- SISTEMA HELPDESK - SENA
-- Base de datos: helpdesk_db
-- PostgreSQL 16 + pgvector
-- Versión FINAL corregida y alineada con frontend/backend
-- ============================================================================
-- REPLICAR EN OTRO EQUIPO (orden recomendado):
--   1) Esquema completo : psql -U postgres -d helpdesk_db -f db_logic.sql
--   2) Migraciones      : psql -U postgres -d helpdesk_db -f migraciones/00X_*.sql
--                         (idempotentes; alinean BDs creadas con esquemas previos)
--   3) Datos de ejemplo : psql -U postgres -d helpdesk_db -f seed_usuarios.sql
--                         psql -U postgres -d helpdesk_db -f mock_tickets_resueltos.sql
--   Con Docker, Iniciar.ps1 / iniciar.sh aplican 1-3 y crean el rol helpdesk_app.
-- ============================================================================

-- ============================================================================
-- 1. EXTENSIONES Y CONFIGURACIÓN INICIAL
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 2. TABLAS DE USUARIOS (Jerarquía - Single Table Inheritance)
-- ============================================================================
CREATE TABLE usuarios (
    id_usuario SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    contraseña VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('solicitante', 'agente', 'coordinador', 'administrador')),
    area VARCHAR(100),
    estado VARCHAR(20) DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo')),
    fecha_registro TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_ultimo_acceso TIMESTAMPTZ,
    -- Atributos específicos de AgenteSoporte
    especialidad VARCHAR(100),
    carga_trabajo INT DEFAULT 0,
    -- Atributos específicos de CoordinadorSoporte
    nivel_jerarquia INT,
    permisos_supervision BOOLEAN DEFAULT FALSE,
    -- Atributos específicos de Administrador
    nivel_acceso INT,
    permisos_especiales BOOLEAN DEFAULT FALSE,
    -- Promoción temporal a administrador (login degrada al vencer)
    rol_anterior VARCHAR(20),
    admin_temporal_hasta TIMESTAMPTZ,
    -- Segundo factor de autenticación (TOTP): secreto y bandera de activación
    mfa_secret VARCHAR(64),
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    -- Endurecimiento de autenticación: bloqueo por intentos y revocación de JWT
    intentos_fallidos INT NOT NULL DEFAULT 0,
    bloqueado_hasta TIMESTAMPTZ,
    token_version INT NOT NULL DEFAULT 0
);

CREATE INDEX idx_usuarios_email ON usuarios(email);
CREATE INDEX idx_usuarios_rol ON usuarios(rol);
CREATE INDEX idx_usuarios_estado ON usuarios(estado);

-- ============================================================================
-- 3. TABLAS DE SOPORTE (Core del Sistema)
-- ============================================================================

-- Tabla: Categoria
CREATE TABLE categoria (
    id_categoria SERIAL PRIMARY KEY,
    nombre VARCHAR(50) UNIQUE NOT NULL,
    descripcion TEXT,
    icono VARCHAR(50)
);

-- Tabla: Prioridad
CREATE TABLE prioridad (
    id_prioridad SERIAL PRIMARY KEY,
    nivel VARCHAR(20) UNIQUE NOT NULL CHECK (nivel IN ('crítica', 'alta', 'media', 'baja')),
    color VARCHAR(7),
    tiempo_respuesta_min INT,
    tiempo_solucion_min INT
);

-- Tabla: Solicitud (Ticket) - CORREGIDA: eliminadas columnas redundantes
CREATE TABLE solicitud (
    id_solicitud SERIAL PRIMARY KEY,
    asunto VARCHAR(200) NOT NULL,
    descripcion TEXT NOT NULL,
    estado VARCHAR(20) DEFAULT 'nuevo' CHECK (estado IN ('nuevo', 'asignado', 'en_proceso', 'resuelto', 'cerrado', 'escalado', 'archivado')),
    fecha_creacion TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    categoria VARCHAR(50),
    prioridad VARCHAR(20),
    -- Claves foráneas
    id_solicitante INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_agente_asignado INT REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
    id_categoria INT REFERENCES categoria(id_categoria) ON DELETE SET NULL,
    id_prioridad INT REFERENCES prioridad(id_prioridad) ON DELETE SET NULL
);

-- Tabla: Adjunto
CREATE TABLE adjunto (
    id_adjunto SERIAL PRIMARY KEY,
    nombre_archivo VARCHAR(255) NOT NULL,
    ruta VARCHAR(500) NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    tamaño INT NOT NULL,
    fecha_subida TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    id_solicitud INT NOT NULL REFERENCES solicitud(id_solicitud) ON DELETE CASCADE
);

-- Tabla: Comentario
CREATE TABLE comentario (
    id_comentario SERIAL PRIMARY KEY,
    contenido TEXT NOT NULL,
    fecha TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    autor VARCHAR(100) NOT NULL,
    es_interno BOOLEAN DEFAULT FALSE,
    id_solicitud INT NOT NULL REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
    id_usuario INT REFERENCES usuarios(id_usuario) ON DELETE SET NULL
);

-- Tabla: Historial
CREATE TABLE historial (
    id_historial SERIAL PRIMARY KEY,
    estado_anterior VARCHAR(20),
    estado_nuevo VARCHAR(20) NOT NULL,
    comentario TEXT,
    fecha TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    id_solicitud INT NOT NULL REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
    id_usuario INT REFERENCES usuarios(id_usuario) ON DELETE SET NULL
);

-- Tabla: SLA
CREATE TABLE sla (
    id_sla SERIAL PRIMARY KEY,
    tiempo_resp_max INTERVAL,
    tiempo_sol_max INTERVAL,
    id_prioridad INT REFERENCES prioridad(id_prioridad) ON DELETE CASCADE,
    activo BOOLEAN DEFAULT TRUE,
    fecha_creacion TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Tabla: Log (Auditoría)
CREATE TABLE log (
    id_log SERIAL PRIMARY KEY,
    accion VARCHAR(100) NOT NULL,
    detalles TEXT,
    fecha TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ip VARCHAR(45),
    navegador VARCHAR(100),
    id_usuario INT REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
    id_solicitud INT REFERENCES solicitud(id_solicitud) ON DELETE SET NULL
);

-- ============================================================================
-- 4. TABLAS DE INTELIGENCIA ARTIFICIAL (Módulo IA) - CORREGIDAS
-- ============================================================================

-- Tabla: ClasificacionIA - AGREGADAS columnas faltantes
CREATE TABLE clasificacion_ia (
    id_clasificacion SERIAL PRIMARY KEY,
    prioridad_ia VARCHAR(20),
    categoria_ia VARCHAR(50),
    confianza FLOAT CHECK (confianza >= 0 AND confianza <= 1),
    modelo_ia VARCHAR(50),
    tiempo_ejecucion_ms INT,
    tokens_usados INT,
    fecha_clasificacion TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    id_solicitud INT NOT NULL REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
    revisado_por INT REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
    revision_manual BOOLEAN DEFAULT FALSE,
    comentario_revision TEXT
);

-- Tabla: EmbeddingVector (para RAG - pgvector)
-- El backend usa bge-m3 (1024 dimensiones) vía Ollama. La columna DEBE ser
-- vector(1024); antes estaba en vector(768) y toda indexación RAG fallaba.
CREATE TABLE embedding_vector (
    id_embedding SERIAL PRIMARY KEY,
    id_solicitud INT NOT NULL REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
    embedding vector(1024),
    modelo_embedding VARCHAR(50) DEFAULT 'bge-m3',
    fecha_creacion TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_embedding_vector_hnsw
ON embedding_vector
USING hnsw (embedding vector_cosine_ops);

-- Tabla: SugerenciaRAG
CREATE TABLE sugerencia_rag (
    id_sugerencia SERIAL PRIMARY KEY,
    sugerencia TEXT NOT NULL,
    similitud FLOAT,
    utilizado BOOLEAN DEFAULT FALSE,
    calificacion_utilidad INT CHECK (calificacion_utilidad >= 1 AND calificacion_utilidad <= 5),
    fecha_generacion TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    id_solicitud_actual INT NOT NULL REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
    id_solicitud_fuente INT REFERENCES solicitud(id_solicitud) ON DELETE SET NULL,
    id_agente INT REFERENCES usuarios(id_usuario) ON DELETE SET NULL
);

-- Tabla: LogIA
CREATE TABLE log_ia (
    id_logia SERIAL PRIMARY KEY,
    accion VARCHAR(50) NOT NULL,
    prompt TEXT NOT NULL,
    respuesta_ia TEXT NOT NULL,
    tokens_usados INT,
    tiempo_ejecucion_ms INT,
    fecha TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    id_solicitud INT REFERENCES solicitud(id_solicitud) ON DELETE SET NULL,
    id_usuario INT REFERENCES usuarios(id_usuario) ON DELETE SET NULL
);

-- Tabla: ConfiguracionIA
CREATE TABLE configuracion_ia (
    id_config SERIAL PRIMARY KEY,
    clave VARCHAR(100) UNIQUE NOT NULL,
    valor TEXT NOT NULL,
    descripcion TEXT,
    fecha_actualizacion TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Tabla: control de migraciones aplicadas (versionado de esquema)
CREATE TABLE schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 4.1 TABLAS DE CHAT
-- ----------------------------------------------------------------------------
-- Canal global: todos los roles autenticados (incluido solicitante).
CREATE TABLE mensaje_chat_global (
    id_mensaje SERIAL PRIMARY KEY,
    id_usuario INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    mensaje VARCHAR(1000) NOT NULL,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Chat privado 1 a 1 (solo personal interno: agente, coordinador, administrador).
-- Cada fila es un mensaje dirigido; `leido` marca si el receptor ya lo abrió.
CREATE TABLE mensaje_chat_privado (
    id_mensaje SERIAL PRIMARY KEY,
    id_emisor INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_receptor INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    mensaje VARCHAR(1000) NOT NULL,
    leido BOOLEAN NOT NULL DEFAULT FALSE,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 5. ÍNDICES ADICIONALES PARA RENDIMIENTO - CORREGIDOS
-- ============================================================================
CREATE INDEX idx_solicitud_estado ON solicitud(estado);
CREATE INDEX idx_solicitud_fecha_creacion ON solicitud(fecha_creacion);
CREATE INDEX idx_solicitud_solicitante ON solicitud(id_solicitante);
CREATE INDEX idx_solicitud_agente_asignado ON solicitud(id_agente_asignado);
CREATE INDEX idx_solicitud_categoria ON solicitud(id_categoria);
CREATE INDEX idx_solicitud_prioridad ON solicitud(id_prioridad);

CREATE INDEX idx_comentario_solicitud ON comentario(id_solicitud);
CREATE INDEX idx_comentario_fecha ON comentario(fecha);

CREATE INDEX idx_historial_solicitud ON historial(id_solicitud);
CREATE INDEX idx_historial_fecha ON historial(fecha);

CREATE INDEX idx_adjunto_solicitud ON adjunto(id_solicitud);

CREATE INDEX idx_clasificacion_ia_solicitud ON clasificacion_ia(id_solicitud);
CREATE INDEX idx_clasificacion_ia_confianza ON clasificacion_ia(confianza);

CREATE INDEX idx_sugerencia_rag_solicitud ON sugerencia_rag(id_solicitud_actual);
CREATE INDEX idx_sugerencia_rag_similitud ON sugerencia_rag(similitud);

CREATE INDEX idx_log_ia_fecha ON log_ia(fecha);
CREATE INDEX idx_log_ia_accion ON log_ia(accion);

-- Chat: recorte inicial/polling del global y recuperación de conversaciones.
CREATE INDEX idx_chat_global_fecha ON mensaje_chat_global (fecha DESC);
CREATE INDEX idx_chat_privado_conv ON mensaje_chat_privado (id_emisor, id_receptor, id_mensaje);
CREATE INDEX idx_chat_privado_no_leidos ON mensaje_chat_privado (id_receptor, leido);

-- ============================================================================
-- 6. DATOS INICIALES (SEED DATA) - ALINEADOS CON FRONTEND
-- ============================================================================

-- Insertar Categorías (exactamente como están en el frontend)
INSERT INTO categoria (id_categoria, nombre, descripcion, icono) VALUES
(1, 'Hardware', 'Problemas con equipos físicos, periféricos', 'fas fa-microchip'),
(2, 'Software', 'Errores de aplicaciones, sistemas operativos', 'fas fa-laptop-code'),
(3, 'Red/Internet', 'Conectividad, WiFi, VPN, acceso a internet', 'fas fa-wifi'),
(4, 'Cuentas/Accesos', 'Reset de contraseñas, creación de usuarios', 'fas fa-user-lock'),
(5, 'Otros', 'Solicitudes generales o no categorizadas', 'fas fa-ellipsis-h')
ON CONFLICT (id_categoria) DO NOTHING;

-- Insertar Prioridades (exactamente como están en el frontend)
INSERT INTO prioridad (id_prioridad, nivel, color, tiempo_respuesta_min, tiempo_solucion_min) VALUES
(1, 'crítica', '#FF0000', 15, 60),
(2, 'alta', '#FFA500', 30, 240),
(3, 'media', '#FFFF00', 60, 480),
(4, 'baja', '#00FF00', 120, 1440)
ON CONFLICT (id_prioridad) DO NOTHING;

-- Insertar SLAs por prioridad
INSERT INTO sla (tiempo_resp_max, tiempo_sol_max, id_prioridad, activo)
SELECT
    (tiempo_respuesta_min || ' minutes')::INTERVAL,
    (tiempo_solucion_min || ' minutes')::INTERVAL,
    id_prioridad,
    TRUE
FROM prioridad
ON CONFLICT DO NOTHING;

-- Insertar Configuración IA por defecto
INSERT INTO configuracion_ia (clave, valor, descripcion) VALUES
('modelo_ia_clasificacion', 'qwen2.5:0.5b', 'Modelo de IA para clasificación automática de tickets'),
('modelo_ia_embeddings', 'bge-m3', 'Modelo para generar embeddings vectoriales (bge-m3, 1024 dims)'),
('umbral_confianza_clasificacion', '0.70', 'Confianza mínima para auto-asignar categoría (0.0 - 1.0)'),
('limite_tickets_similares_rag', '5', 'Cantidad de tickets similares a buscar en RAG'),
('temperatura_ia', '0.3', 'Temperatura del modelo IA (0.0 = determinista, 1.0 = creativo)'),
('max_tokens_ia', '1000', 'Máximo de tokens para respuestas de IA')
ON CONFLICT (clave) DO NOTHING;

-- ============================================================================
-- 7. VISTAS ÚTILES - CORREGIDAS
-- ============================================================================

-- Vista: Tickets por estado y prioridad (corregida sin columnas redundantes)
CREATE OR REPLACE VIEW vista_tickets_resumen AS
SELECT
    s.id_solicitud,
    s.asunto,
    s.estado,
    s.fecha_creacion,
    s.fecha_actualizacion,
    u.nombre AS solicitante,
    u.email AS solicitante_email,
    a.nombre AS agente_asignado,
    c.nombre AS categoria_nombre,
    c.icono AS categoria_icono,
    p.nivel AS prioridad_nivel,
    p.color AS prioridad_color
FROM solicitud s
LEFT JOIN usuarios u ON s.id_solicitante = u.id_usuario
LEFT JOIN usuarios a ON s.id_agente_asignado = a.id_usuario
LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad;

-- Vista: Estadísticas de agentes
CREATE OR REPLACE VIEW vista_estadisticas_agentes AS
SELECT
    u.id_usuario,
    u.nombre,
    u.especialidad,
    COUNT(s.id_solicitud) AS total_tickets,
    COUNT(CASE WHEN s.estado IN ('resuelto', 'archivado') THEN 1 END) AS tickets_resueltos,
    COUNT(CASE WHEN s.estado = 'en_proceso' THEN 1 END) AS tickets_en_proceso,
    COUNT(CASE WHEN s.estado = 'asignado' THEN 1 END) AS tickets_pendientes,
    AVG(EXTRACT(EPOCH FROM (s.fecha_actualizacion - s.fecha_creacion))) AS tiempo_promedio_resolucion_seg
FROM usuarios u
LEFT JOIN solicitud s ON u.id_usuario = s.id_agente_asignado
WHERE u.rol IN ('agente', 'coordinador', 'administrador')
GROUP BY u.id_usuario, u.nombre, u.especialidad;

-- ============================================================================
-- 8. FUNCIONES Y TRIGGERS
-- ============================================================================

-- Función: Actualizar fecha_actualizacion automáticamente
CREATE OR REPLACE FUNCTION actualizar_fecha_modificacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_actualizar_fecha_solicitud
BEFORE UPDATE ON solicitud
FOR EACH ROW
EXECUTE FUNCTION actualizar_fecha_modificacion();

-- Función: Registrar cambio en historial automáticamente
-- NOTA (auditoría): este trigger SE ELIMINÓ. Duplicaba cada transición de
-- estado (el backend ya inserta en historial con usuario y comentario reales,
-- por lo que se registraban 2 filas por cambio y la segunda con estado_anterior
-- incorrecto). El registro en historial lo controla SOLO la aplicación.
-- (Si se desea un respaldo a nivel de BD, reintroducirlo con cuidado.)

-- Función: Actualizar carga de trabajo del agente
CREATE OR REPLACE FUNCTION actualizar_carga_trabajo()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.id_agente_asignado IS NOT NULL THEN
        UPDATE usuarios
        SET carga_trabajo = carga_trabajo + 1
        WHERE id_usuario = NEW.id_agente_asignado;
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF OLD.id_agente_asignado IS DISTINCT FROM NEW.id_agente_asignado THEN
            IF OLD.id_agente_asignado IS NOT NULL THEN
                UPDATE usuarios
                SET carga_trabajo = GREATEST(carga_trabajo - 1, 0)
                WHERE id_usuario = OLD.id_agente_asignado;
            END IF;
            IF NEW.id_agente_asignado IS NOT NULL THEN
                UPDATE usuarios
                SET carga_trabajo = carga_trabajo + 1
                WHERE id_usuario = NEW.id_agente_asignado;
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_actualizar_carga_trabajo
AFTER INSERT OR UPDATE ON solicitud
FOR EACH ROW
EXECUTE FUNCTION actualizar_carga_trabajo();

-- ============================================================================
-- 9. CONSULTAS DE VERIFICACIÓN
-- ============================================================================

-- Verificar que todas las tablas se crearon correctamente
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Verificar extensión pgvector
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Verificar datos iniciales
SELECT 'Categorías' AS tabla, COUNT(*) AS total FROM categoria
UNION ALL
SELECT 'Prioridades', COUNT(*) FROM prioridad
UNION ALL
SELECT 'SLAs', COUNT(*) FROM sla
UNION ALL
SELECT 'Config IA', COUNT(*) FROM configuracion_ia;

-- ============================================================================
-- FIN DEL SCRIPT
-- ============================================================================