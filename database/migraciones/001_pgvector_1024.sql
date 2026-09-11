-- ============================================================================
-- MIGRACIÓN 001 — pgvector: 768 → 1024 dimensiones (modelo bge-m3)
-- ============================================================================
-- MOTIVO (auditoría): el backend genera embeddings con bge-m3 (1024 dims) pero
-- la columna embedding_vector.embedding podía estar definida como vector(768),
-- haciendo fallar toda indexación RAG.
--
-- IDEMPOTENTE Y SEGURA DE REPETIR:
--   * Solo actúa cuando el contenido NO está ya en 1024 dimensiones.
--   * Si ya hay embeddings de 1024 (migrada antes), no toca nada.
--   * Si hay embeddings de otra dimensión (p.ej. 768) los BORRA (no se pueden
--     convertir); vuelve a generarlos desde Coordinador → RAG → "Indexar".
--   * Si la tabla está vacía, simplemente deja la columna en vector(1024).
--
-- Ejecutar como superusuario (POSTGRES_USER), NO como helpdesk_app.
-- ============================================================================

DO $$
DECLARE
    dims_max INT;
BEGIN
    SELECT COALESCE(MAX(vector_dims(embedding)), 0) INTO dims_max FROM embedding_vector;

    IF dims_max = 1024 THEN
        RAISE NOTICE 'embedding_vector ya está en 1024 dims; no se modifica';
    ELSE
        RAISE NOTICE 'Migrando embedding_vector a vector(1024) (dims actuales: %)', dims_max;
        EXECUTE 'DROP INDEX IF EXISTS idx_embedding_vector_hnsw';
        -- Drop/ADD de columna: evita el cast de vector(768) a vector(1024), que
        -- pgvector rechaza. Se pierden los embeddings (se regeneran con RAG).
        EXECUTE 'ALTER TABLE embedding_vector DROP COLUMN IF EXISTS embedding';
        EXECUTE 'ALTER TABLE embedding_vector ADD COLUMN embedding vector(1024)';
        EXECUTE 'CREATE INDEX idx_embedding_vector_hnsw
                 ON embedding_vector USING hnsw (embedding vector_cosine_ops)';
    END IF;
END
$$;

-- Alinear el modelo por defecto de la tabla con el usado por el backend.
ALTER TABLE embedding_vector
    ALTER COLUMN modelo_embedding SET DEFAULT 'bge-m3';

-- Actualizar la configuracion_ia (si existe la fila de semilla).
UPDATE configuracion_ia
SET valor = 'bge-m3', fecha_actualizacion = now()
WHERE clave = 'modelo_ia_embeddings';
