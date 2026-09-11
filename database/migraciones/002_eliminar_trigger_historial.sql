-- ============================================================================
-- MIGRACIÓN 002 — Eliminar trigger duplicador de historial
-- ============================================================================
-- MOTIVO (auditoría): el trigger trg_registrar_cambio_estado insertaba una fila
-- en historial en cada UPDATE de solicitud.estado, ADEMÁS de la que ya inserta
-- la aplicación (update_ticket / asignar_ticket). Resultado: cada transición se
-- registraba DOS veces (rompiendo el conteo de "asignados_hoy" y el cupo diario
-- de asignación) y la fila manual quedaba con estado_anterior == estado_nuevo.
--
-- El registro en historial lo controla ahora SOLO la aplicación (con usuario y
-- estados correctos). Este script elimina la función y el trigger asociados.
-- Es idempotente: si ya no existen, no hace nada.
-- ============================================================================

DROP TRIGGER IF EXISTS trg_registrar_cambio_estado ON solicitud;

DROP FUNCTION IF EXISTS registrar_cambio_estado();
