from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import oauth2_scheme, SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
import os
import re
import uuid

router = APIRouter(prefix="/tickets", tags=["Adjuntos"])

# Carpeta donde viven los archivos subidos (persistida como volumen en Docker).
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads/adjuntos")

# Reglas de negocio del adjunto (también se comunican en el frontend).
MAX_TAMANO_ARCHIVO = 20 * 1024 * 1024  # 20 MB por archivo
MAX_ADJUNTOS_POR_TICKET = 5
EXTENSIONES_PERMITIDAS = {".png", ".jpg", ".jpeg"}

# Rutas públicas (servidas con nombres UUID no adivinables).
URL_BASE_ADJUNTOS = "/api/adjuntos-archivos"

PNG_FIRMA = b"\x89PNG\r\n\x1a\n"


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


async def _usuario_actual(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


@router.post("/{ticket_id}/adjuntos", status_code=status.HTTP_201_CREATED)
async def subir_adjuntos(
    ticket_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    payload = await _usuario_actual(token)
    user_id = payload.get("user_id")
    role = payload.get("role")

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se recibieron archivos")

    fila = await db.execute(
        text("SELECT id_solicitante FROM solicitud WHERE id_solicitud = :id"), {"id": ticket_id})
    ticket = fila.fetchone()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    # El dueño del ticket puede adjuntar; el staff también (evidencias del agente).
    if role == "solicitante" and ticket[0] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes adjuntar a un ticket ajeno")

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
        data = await file.read()

        if len(data) > MAX_TAMANO_ARCHIVO:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"'{file.filename}' supera el máximo de 20 MB"
            )
        if len(data) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{file.filename}' está vacío")

        ext_real = _extension_real(data)
        if ext_real is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"'{file.filename}' no es una imagen PNG o JPG válida"
            )

        nombre_limpio = _nombre_seguro(file.filename)
        _, ext_original = os.path.splitext(nombre_limpio)
        if ext_original.lower() not in EXTENSIONES_PERMITIDAS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"'{nombre_limpio}': solo se aceptan archivos PNG o JPG"
            )

        nombre_disco = f"{uuid.uuid4().hex}{ext_real}"
        ruta_absoluta = os.path.join(UPLOAD_DIR, nombre_disco)
        with open(ruta_absoluta, "wb") as destino:
            destino.write(data)

        fila = await db.execute(text("""
            INSERT INTO adjunto (nombre_archivo, ruta, tipo, tamaño, fecha_subida, id_solicitud)
            VALUES (:nombre, :ruta, :tipo, :tamano, NOW(), :id_solicitud)
            RETURNING id_adjunto, fecha_subida
        """), {
            "nombre": nombre_limpio,
            "ruta": f"{URL_BASE_ADJUNTOS}/{nombre_disco}",
            "tipo": "image/png" if ext_real == ".png" else "image/jpeg",
            "tamano": len(data),
            "id_solicitud": ticket_id,
        })
        id_adjunto, fecha = fila.fetchone()

        guardados.append({
            "id_adjunto": id_adjunto,
            "nombre_archivo": nombre_limpio,
            "ruta": f"{URL_BASE_ADJUNTOS}/{nombre_disco}",
            "tipo": "image/png" if ext_real == ".png" else "image/jpeg",
            "tamaño": len(data),
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
    payload = await _usuario_actual(token)
    user_id = payload.get("user_id")
    role = payload.get("role")

    fila = await db.execute(text("""
        SELECT s.id_solicitante FROM solicitud s WHERE s.id_solicitud = :id
    """), {"id": ticket_id})
    ticket = fila.fetchone()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    # El solicitante solo ve los adjuntos de sus propios tickets.
    if role == "solicitante" and ticket[0] != user_id:
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
