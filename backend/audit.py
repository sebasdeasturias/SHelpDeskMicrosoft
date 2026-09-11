# backend/audit.py
# Auditoría de acciones relevantes en la tabla `log` (append-only).
# Usa una sesión propia y confirma de inmediato: así el registro sobrevive
# aunque la transacción del endpoint falle o se revierta (p. ej. un login fallido).
from sqlalchemy import text
from database import AsyncSessionLocal


async def registrar_log(accion, detalles=None, id_usuario=None, id_solicitud=None,
                        ip=None, navegador=None):
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO log (accion, detalles, ip, navegador, id_usuario, id_solicitud)
                VALUES (:accion, :detalles, :ip, :navegador, :id_usuario, :id_solicitud)
            """), {
                "accion": (accion or "")[:100],
                "detalles": (detalles or None) and str(detalles)[:1000],
                "ip": (ip or None) and str(ip)[:45],
                "navegador": (navegador or None) and str(navegador)[:100],
                "id_usuario": id_usuario,
                "id_solicitud": id_solicitud,
            })
            await db.commit()
    except Exception as e:
        print(f"[audit] no se pudo registrar '{accion}': {e}")
