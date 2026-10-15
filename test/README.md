# test/ — Informe de calidad de SHelpDesk (sistemahelpdesk.online)

Mediciones de **arquitectura, escalabilidad, seguridad y rendimiento** sobre el
sistema original (frontend en Vercel + API en el backend Docker tunelado por
Cloudflare). Todo se ejecutó contra el sistema real pero con pruebas **no
destructivas y de solo lectura** (ver *Metodología y límites*).

## Índice

| Documento | Contenido |
| --- | --- |
| [reportes/seguridad.md](reportes/seguridad.md) | Hallazgos con severidad, controles conformes, recomendaciones |
| [reportes/rendimiento.md](reportes/rendimiento.md) | Latencias (p50/p95/TTFB), descomposición, caché, comparativa túnel vs local |
| [reportes/escalabilidad.md](reportes/escalabilidad.md) | Pruebas de concurrencia, saturación, recursos, cuellos de botella |
| [reportes/arquitectura.md](reportes/arquitectura.md) | Mapa de servicios, flujos, métricas de código, deuda técnica |

Datos crudos en [`datos/`](datos/), gráficos en [`graficos/`](graficos/) y
scripts reproducibles en [`scripts/`](scripts/).

## Resumen ejecutivo

| Dimensión | Resultado | Veredicto |
| --- | --- | --- |
| Seguridad | 9 hallazgos (2 medios, 4 bajos, 3 informativos); 17 comprobaciones conformes | **Buena, con ajustes puntuales** |
| Rendimiento | API vía túnel p50 **416 ms**; local **21 ms**; frontend p50 **2,0–2,9 s** (RTT) | **API correcta; frontend depende de la distancia de red** |
| Escalabilidad | 31 req/s sostenidos (túnel, c=20) y 55 req/s (local, c=10) con **0 fallos** | **Suficiente para el tamaño actual; limitada a 1 worker** |
| Arquitectura | 7 contenedores, 47 rutas / 56 operaciones, ~58 k LOC, CI con ruff | **Modular y bien segmentada; sin tests automáticos** |

### Hallazgos que conviene atender primero

1. **[Seguridad-Medio] Documentación de la API pública**: `/docs`, `/redoc` y
   `/openapi.json` responden 200 sin autenticación (34 KB de especificación).
2. **[Seguridad-Medio] El backend escucha en todas las interfaces**: `:8000`
   responde 200 desde la LAN (`192.168.1.10`) y desde Tailscale
   (`100.120.32.64`), es decir, **sin pasar por Cloudflare**. El resto de
   servicios sí están en `127.0.0.1`.
3. **[Seguridad-Medio] `uvicorn --reload` en producción** (Dockerfile CMD):
   recarga ante cada escritura de fichero y añade superficie innecesaria.
4. **[Seguridad-Bajo] Enumeración de adjuntos**: la autenticación se aplica
   *después* de consultar la BD (`adjuntos.py:234-243`), así que con un token
   inválido un nombre existente devuelve 401 y uno inexistente 404.
5. **[Rendimiento] `logohelpdesk.png` pesa 667 KB** y es el asset más lento
   (p95 10,5 s en la prueba).
6. **[Escalabilidad] Un único worker uvicorn + límites de tasa en memoria**:
   el techo observado fue ~31 req/s por el túnel y la latencia sube de 366 →
   659 ms (p50) al duplicar la concurrencia (10 → 20).

## Cómo reproucirlo

```powershell
python test/scripts/recon.py            # seguridad / exposición / CORS / rate-limit
python test/scripts/tls.py              # TLS y certificados
python test/scripts/rendimiento.py 15   # latencias (15 muestras por objetivo)
python test/scripts/carga.py            # concurrencia (5 escenarios)
python test/scripts/metricas_codigo.py  # métricas de código + endpoints
python test/scripts/graficos.py         # regenera test/graficos/*.png
```

> `metricas_codigo.py` es local; `recon.py` envía ~120 peticiones (incluye
> 6 intentos de login fallidos que disparan el 429). `carga.py` usa
> `GET /api/health` y un HTML estático (sin escrituras).

## Metodología y límites

- **Fecha de las pruebas**: 2026-10-15 (UTC-5 en el host).
- **Punto de medición**: una sola máquina Windows sobre Wi-Fi
  (`192.168.1.10`) con salida hacia un PoP de Cloudflare en **Miami** y
  Vercel en **iad1** (Washington). No hay mediciones multi-región: los
  tiempos del frontend dependen mucho de la distancia a estos PoPs.
- **No se probaron**: fuerza bruta real de credenciales, fuzzing extenso,
  DoS, ni endpoints autenticados (no se usaron credenciales de usuario real).
  El límite de tasa por cuenta se verificó con 6 intentos fallidos de un
  email inexistente (se cortó en el primer 429).
- **Escrituras**: ninguna. Todas las operaciones de la auditoría son GET u
  OPCiones, salvo `POST /api/auth/login` con credenciales inválidas (para
  validar rate-limit y validación de esquema).
- **Los resultados de latencia son de un único vantage point** en una ventana
  corta; úsalos para comparar objetivos entre sí, no como SLA.
