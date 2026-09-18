-- ============================================================================
-- MIGRACIÓN 010 — Comentario de solución en solicitud
-- ============================================================================
-- MOTIVO: al cerrar un ticket (arrastrarlo a "Completados" en el Kanban), el
-- agente/coordinador/administrador debe registrar cómo resolvió el incidente.
-- El solicitante consulta esa solución desde su dashboard ("Ver solución").
--
-- IDEMPOTENTE: añade la columna solo si no existe.
-- ============================================================================

ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS solucion TEXT;
