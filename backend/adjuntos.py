from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import oauth2_scheme, usuario_actual
from jose import jwt, JWTError
import os
import re
import uuid

router = APIRouter(prefix="/tickets", tags=["Adjuntos"])
# Router sin prefijo para servir el archivo del adjunto (con autenticación).
router_archivos = APIRouter(tags=["Adjuntos"])

# Carpeta donde viven los archivos subidos (persistida como volumen en Docker).
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads/adjuntos")

# Reglas de negocio del adjunto (también se comunican en el frontend).
MAX_TAMANO_ARCHIVO = 20 * 1024 * 1024  # 20 MB por archivo
MAX_ADJUNTOS_POR_TICKET = 5
EXTENSIONES_PERMITIDAS = {".png", ".jpg", ".jpeg"}

# Ruta base de descarga de adjuntos. Requiere autenticación y control de acceso
# (ya NO se sirve como estático público). El nombre en disco es un UUID.
URL_BASE_ADJUNTOS = "/api/adjuntos-archivos"

PNG_FIRMA = b"\x89PNG\r\n\x1a\n"

# Tamaño de cada trozo al leer el upload por streaming (evita cargar en memoria
# un archivo arbitrariamente grande antes de validar el límite).
CHUNK_SIZE = 1024 * 1024


def _extension_real(data: bytes):
    """Valida la firma binaria (magic bytes) del archivo: no confiamos ni en
    la extensión ni en el Content-Type que declara el navegador."""
    if data.startswith(PNG_FIRMA):
        return ".png"
    if len(data) >= 3 and data[0] == 0xFF and data[1] == 0xD8 and data[2] == 0xFF:
        return ".jpg"
    return None


def _nombre_seguro(nombre: str) -> str:
    """Limpia el nombre original para mostrarlo (sin rutas ni caracteres raros)."""
    nombre = os.path.basename(nombre or "archivo")
    nombre = re.sub(r"[^\w\-. ()]", "_", nombre).strip()
    return nombre[:255] or "archivo"


async def _usuario_actual(db, token: str):
    # Revalidado contra la BD (usuario existente y activo).
    return await usuario_actual(db, token)


async def _guardar_archivo(file: UploadFile) -> tuple[str, int, str, str]:
    """Guarda el UploadFile por TROZOS (streaming) sin cargarlo entero en memoria.

    Valida magic bytes y tamaño mientras escribe. Devuelve
    (nombre_disco, tamaño, tipo_mime, nombre_limpio). Limpia el fichero parcial
    si algo falla."""
    primero = await file.read(8192)
    if not primero:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"'{file.filename}' está vacío")

    ext_real = _extension_real(primero)
    if ext_real is None:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"'{file.filename}' no es una imagen PNG o JPG válida")

    nombre_limpio = _nombre_seguro(file.filename)
    _, ext_original = os.path.splitext(nombre_limpio)
    if ext_original.lower() not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"'{nombre_limpio}': solo se aceptan archivos PNG o JPG")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    nombre_disco = f"{uuid.uuid4().hex}{ext_real}"
    ruta_absoluta = os.path.join(UPLOAD_DIR, nombre_disco)
    tipo = "image/png" if ext_real == ".png" else "image/jpeg"
    total = 0
    try:
        with open(ruta_absoluta, "wb") as destino:
            trozo = primero
            while trozo:
                total += len(trozo)
                if total > MAX_TAMANO_ARCHIVO:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"'{file.filename}' supera el máximo de 20 MB")
                destino.write(trozo)
                trozo = await file.read(CHUNK_SIZE)
    except HTTPException:
        try:
            os.remove(ruta_absoluta)
        except OSError:
            pass
        raise

    return nombre_disco, total, tipo, nombre_limpio


@router.post("/{ticket_id}/adjuntos", status_code=status.HTTP_201_CREATED)
async def subir_adjuntos(
    ticket_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    payload = await _usuario_actual(db, token)
    user_id = payload.get("user_id")
    role = payload.get("role")

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se recibieron archivos")

    fila = await db.execute(
        text("SELECT id_solicitante, id_agente_asignado FROM solicitud WHERE id_solicitud = :id"), {"id": ticket_id})
    ticket = fila.fetchone()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    # El dueño del ticket puede adjuntar; el staff también (evidencias del agente).
    if role == "solicitante" and ticket[0] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes adjuntar a un ticket ajeno")
    if role == "agente" and ticket[1] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes adjuntar en tickets que tengas asignados")

    conteo = await db.execute(
        text("SELECT COUNT(*) FROM adjunto WHERE id_solicitud = :id"), {"id": ticket_id})
    ya_subidos = conteo.scalar() or 0
    if ya_subidos + len(files) > MAX_ADJUNTOS_POR_TICKET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Máximo {MAX_ADJUNTOS_POR_TICKET} adjuntos por ticket (ya tiene {ya_subidos})"
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    guardados = []

    for file in files:
        # Streaming: se escribe por trozos y se corta al superar 20 MB (sin
        # cargar el archivo completo en memoria antes de validar el tamaño).
        nombre_disco, tamano, tipo, nombre_limpio = await _guardar_archivo(file)
        ruta_publica = f"{URL_BASE_ADJUNTOS}/{nombre_disco}"

        fila = await db.execute(text("""
            INSERT INTO adjunto (nombre_archivo, ruta, tipo, tamaño, fecha_subida, id_solicitud)
            VALUES (:nombre, :ruta, :tipo, :tamano, NOW(), :id_solicitud)
            RETURNING id_adjunto, fecha_subida
        """), {
            "nombre": nombre_limpio,
            "ruta": ruta_publica,
            "tipo": tipo,
            "tamano": tamano,
            "id_solicitud": ticket_id,
        })
        id_adjunto, fecha = fila.fetchone()

        guardados.append({
            "id_adjunto": id_adjunto,
            "nombre_archivo": nombre_limpio,
            "ruta": ruta_publica,
            "tipo": tipo,
            "tamaño": tamano,
            "fecha_subida": fecha.isoformat() if fecha else None,
        })

    await db.commit()
    return {"status": "created", "adjuntos": guardados}


@router.get("/{ticket_id}/adjuntos")
async def listar_adjuntos(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    payload = await _usuario_actual(db, token)
    user_id = payload.get("user_id")
    role = payload.get("role")

    fila = await db.execute(text("""
        SELECT s.id_solicitante, s.id_agente_asignado FROM solicitud s WHERE s.id_solicitud = :id
    """), {"id": ticket_id})
    ticket = fila.fetchone()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    # El solicitante solo ve los adjuntos de sus propios tickets; el agente, los suyos asignados.
    if role == "solicitante" and ticket[0] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a este ticket")
    if role == "agente" and ticket[1] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a este ticket")

    result = await db.execute(text("""
        SELECT id_adjunto, nombre_archivo, ruta, tipo, tamaño, fecha_subida
        FROM adjunto WHERE id_solicitud = :id ORDER BY fecha_subida ASC
    """), {"id": ticket_id})

    return [
        {
            "id_adjunto": r[0],
            "nombre_archivo": r[1],
            "ruta": r[2],
            "tipo": r[3],
            "tamaño": r[4],
            "fecha_subida": r[5].isoformat() if r[5] else None,
        }
        for r in result.fetchall()
    ]


_NOMBRE_ARCHIVO_RE = re.compile(r"[0-9a-f]{32}\.(png|jpg|jpeg)")


@router_archivos.get("/adjuntos-archivos/{archivo}")
async def descargar_archivo(
    archivo: str,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Sirve el binario del adjunto SOLO a usuarios con acceso al ticket.

    Sustituye al StaticFiles público (A1): el nombre en disco es un UUID y ahora
    se exige sesión válida y pertenencia (solicitante dueño, agente asignado,
    coordinador o administrador)."""
    nombre = os.path.basename(archivo)
    if nombre != archivo or not _NOMBRE_ARCHIVO_RE.fullmatch(nombre):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    fila = await db.execute(text("""
        SELECT s.id_solicitante, s.id_agente_asignado
        FROM adjunto a JOIN solicitud s ON s.id_solicitud = a.id_solicitud
        WHERE a.ruta = :r
    """), {"r": f"{URL_BASE_ADJUNTOS}/{nombre}"})
    row = fila.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    payload = await _usuario_actual(db, token)
    role = payload.get("role")
    uid = payload.get("user_id")
    if role == "solicitante" and row[0] != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a este adjunto")
    if role == "agente" and row[1] != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a este adjunto")

    ruta_fs = os.path.join(UPLOAD_DIR, nombre)
    if not os.path.isfile(ruta_fs):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    media = "image/png" if nombre.endswith(".png") else "image/jpeg"
    return FileResponse(
        ruta_fs,
        media_type=media,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )
