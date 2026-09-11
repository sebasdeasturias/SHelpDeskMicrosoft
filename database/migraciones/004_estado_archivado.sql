-- ============================================================================
-- MIGRACIÓN 004 — Estado terminal 'archivado' en solicitud
-- ============================================================================
-- MOTIVO: el tablero Kanban (agente/coordinador/admin) acumulaba tickets en
-- la columna "Completados". Se añade el estado terminal 'archivado' para
-- limpiar el tablero: un ticket resuelto/cerrado puede archivarse (con
-- confirmación) y desaparece del tablero. Los datos e historial se conservan.
--
-- REGLAS DEL FLUJO:
--   * Solo se puede archivar desde 'resuelto' o 'cerrado' (lo valida el
--     backend en tickets.py; la BD solo autoriza el valor en el CHECK).
--   * Un ticket 'archivado' NO vuelve al tablero (estado terminal).
--
-- IDEMPOTENTE Y SEGURA DE REPETIR:
--   * Re-crea el CHECK de solicitud.estado solo si aún no incluye 'archivado'.
--   * Actualiza vista_estadisticas_agentes: un ticket ARCHIVADO sigue
--     contando como resuelto (archivar es limpieza del tablero, no borra
--     el trabajo del agente).
-- ============================================================================

-- 1) CHECK de solicitud.estado: permitir 'archivado'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'solicitud_estado_check'
          AND pg_get_constraintdef(oid) LIKE '%archivado%'
    ) THEN
        ALTER TABLE solicitud DROP CONSTRAINT IF EXISTS solicitud_estado_check;
        ALTER TABLE solicitud ADD CONSTRAINT solicitud_estado_check
            CHECK (estado IN ('nuevo', 'asignado', 'en_proceso', 'resuelto',
                              'cerrado', 'escalado', 'archivado'));
    END IF;
END
$$;

-- 2) Estadísticas de agentes: lo archivado sigue contando como resuelto
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
