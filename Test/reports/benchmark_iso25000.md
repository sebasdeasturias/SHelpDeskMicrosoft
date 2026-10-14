# Informe de benchmark de calidad — Familia ISO/IEC 25000

**Sistema:** SHelpDesk Microsoft  
**Fecha (UTC):** 2026-10-14T22:38:48Z  
**Usuarios mock:** 23  
**Principio:** Benchmark de runtime con usuarios mock sobre los contenedores montados con iniciar.sh. Sin auto-declaraciones: todas las métricas se miden.

## 1. Umbrales de evaluación (ISO/IEC 25023, declarados a priori)

- Lectura API: P95 ≤ **300 ms** (bien) / ≤ 800 ms (aceptable)
- Escritura API: P95 ≤ **500 ms** (bien) / ≤ 1500 ms (aceptable)
- Disponibilidad objetivo: **99.5%**
- Tasa de error objetivo: **≤ 1.0%**

## 2. Veredicto por norma de la familia

| Norma | Score | Veredicto |
|---|---:|---|
| ISO/IEC 25000:2014 (SQuaRE — guía de la familia) | 93.7 | CUMPLE |
| ISO/IEC 25010:2023 (modelo de calidad de producto) | 91.8 | CUMPLE |
| ISO/IEC 25012:2008 (calidad de datos) | 100.0 | CUMPLE |
| ISO/IEC 25023:2016 (métricas de calidad del producto) | 93.7 | CUMPLE |
| ISO/IEC 25040:2011 (proceso de evaluación) | 100.0 | CUMPLE |

## 3. Score por módulo del sistema

| Módulo | Score ISO/IEC 25010 | Veredicto |
|---|---:|---|
| seguridad | 100.0 | CUMPLE |
| auditoria | 100.0 | CUMPLE |
| ia_externa | 100.0 | CUMPLE |
| infraestructura | 92.5 | CUMPLE |
| auth | 92.5 | CUMPLE |
| tickets | 92.5 | CUMPLE |
| adjuntos | 92.5 | CUMPLE |
| chat_global | 92.5 | CUMPLE |
| chat_privado | 92.5 | CUMPLE |
| coordinador | 92.5 | CUMPLE |
| streamlit | 91.2 | CUMPLE |
| chat_ia | 86.2 | CUMPLE |

## 4. Características ISO/IEC 25010:2023 (medias de todos los módulos)

| Característica ISO/IEC 25010:2023 | Score medio |
|---|---:|
| idoneidad funcional | 100.0 |
| eficiencia desempeno | 94.4 |
| confiabilidad | 100.0 |
| seguridad | 86.5 |
| mantenibilidad | 90.0 |
| compatibilidad | 88.9 |
| usabilidad | 75.0 |
| flexibilidad | 100.0 |

## 5. Mediciones por módulo (ISO/IEC 25023)

### 5.1 Módulo `adjuntos` — score 92.5 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| subir_png_128kb | POST | 5 | 1 | 100% | 4.17 | 6.33 | 6.67 | 213.71 | — |
| listar_adjuntos | GET | 20 | 4 | 100% | 4.84 | 9.73 | 10.4 | 653.52 | — |

### 5.2 Módulo `auditoria` — score 100.0 (CUMPLE)

### 5.3 Módulo `auth` — score 92.5 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| whoami_me | GET | 40 | 6 | 100% | 4.71 | 30.27 | 42.34 | 567.35 | — |
| me_solicitante | GET | 30 | 6 | 100% | 4.25 | 8.08 | 15.69 | 1109.09 | — |
| login_mock_rotando | POST | 24 | 1 | 100% | 185.14 | 188.09 | 190.11 | 0 | — |

### 5.4 Módulo `chat_global` — score 92.5 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| historial | GET | 40 | 8 | 100% | 11.4 | 38.02 | 42.72 | 540.1 | — |
| enviar_mensaje | POST | 24 | 4 | 100% | 6.04 | 8.32 | 9.68 | 609.12 | — |

### 5.5 Módulo `chat_ia` — score 86.2 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| health_n8n | GET | 8 | 2 | 100% | 12.5 | 16.41 | 16.53 | 150.73 | — |
| mensaje_ia | POST | 6 | 1 | 100% | 19016.03 | 34860.86 | 38592.8 | 0 | — |

### 5.6 Módulo `chat_privado` — score 92.5 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| contactos | GET | 30 | 6 | 100% | 6.37 | 10.53 | 20.47 | 762.2 | — |
| no_leidos | GET | 30 | 6 | 100% | 6.09 | 7.83 | 17.66 | 853.02 | — |

### 5.7 Módulo `coordinador` — score 92.5 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| estadisticas | GET | 12 | 4 | 100% | 8.8 | 14.37 | 15.07 | 379.17 | — |
| reportes | GET | 12 | 4 | 100% | 7.93 | 11.4 | 12.63 | 417.38 | — |
| agentes | GET | 12 | 4 | 100% | 4.6 | 5.52 | 5.82 | 744.25 | — |
| asignacion | GET | 12 | 4 | 100% | 7.57 | 9.51 | 10.1 | 468.47 | — |
| sla | GET | 12 | 4 | 100% | 4.01 | 5.58 | 5.63 | 852.84 | — |
| usuarios | GET | 12 | 4 | 100% | 5.73 | 7.32 | 7.44 | 583.6 | — |
| bd_tablas | GET | 12 | 4 | 100% | 3.91 | 6.52 | 6.71 | 757.16 | — |
| ia_config | GET | 12 | 4 | 100% | 27.44 | 30.92 | 31.1 | 140.33 | — |
| n8n_workflows | GET | 12 | 4 | 100% | 44.31 | 68.68 | 69.21 | 76.36 | — |
| asignar_ticket | POST | 3 | 1 | 100% | 4.58 | 6.63 | 6.81 | 0 | — |

### 5.8 Módulo `ia_externa` — score 100.0 (CUMPLE)

> Dependencias externas del módulo IA (Ollama/n8n); su caída degrada el chat IA pero no el servicio core.

### 5.9 Módulo `infraestructura` — score 92.5 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| health_backend | GET | 12 | 4 | 100% | 52.7 | 70.07 | 72.82 | 74.74 | — |
| raiz_api | GET | 10 | 4 | 100% | 2.29 | 2.8 | 2.91 | 1585.47 | — |

### 5.10 Módulo `seguridad` — score 100.0 (CUMPLE)

- **seguridad**: 100.0 — 6/6 controles de seguridad validados en runtime

> Módulo transversal: su puntuación son los controles ejecutados en runtime (JWT, RBAC, rate-limit, lockout).

### 5.11 Módulo `streamlit` — score 91.2 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| panel_admin | GET | 10 | 3 | 100% | 1.78 | 3.82 | 3.87 | 1127.74 | — |

### 5.12 Módulo `tickets` — score 92.5 (CUMPLE)

| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| listado_coordinador | GET | 40 | 8 | 100% | 24.53 | 67.62 | 73.54 | 256.74 | — |
| listado_solicitante | GET | 40 | 8 | 100% | 8.31 | 23.34 | 29.83 | 747.61 | — |
| listado_agente | GET | 30 | 6 | 100% | 5.78 | 8.02 | 19.05 | 834.24 | — |
| crear_ticket_solicitante | POST | 18 | 1 | 100% | 9.14 | 13.75 | 14.76 | 0 | — |

## 6. Calidad de datos (ISO/IEC 25012)

**Veredicto:** CUMPLE (score 100.0)

- ✅ `exactitud_huerfanos_historial`
- ✅ `exactitud_estados_historial`
- ✅ `exactitud_estados_solicitud`
- ✅ `consistencia_fechas`
- ✅ `credibilidad_passwords`
- ✅ `trazabilidad_auditoria`
- ✅ `integridad_referencial`
- ✅ `restricciones_dominio`

## 7. Proceso de evaluación (ISO/IEC 25040)

**Veredicto:** CUMPLE (score 100.0) — 528 muestras.

## 8. Controles de seguridad ejecutados en runtime

- `jwt_invalido_401`: True
- `sin_token_rechazado`: True
- `rbac_solicitante_bloqueado`: True
- `rbac_chat_ia_solo_staff`: True
- `login_malo_status`: 401, 401, 401, 429, 429, 429
- `lockout_tras_5_fallos`: True
- `tickets_sin_token_401`: True

## 9. Infraestructura medida

- `helpdesk-backend`: Up 3 minutes (healthy)
- `helpdesk-streamlit`: Up 4 minutes
- `helpdesk-socket-proxy`: Up 51 minutes
- `n8n`: Up 18 minutes
- `helpdesk-db`: Up 54 minutes (healthy)
- `ollama`: Up 54 minutes
- `/api/health`: `healthy` — checks: `{'database': 'ok', 'ollama': 'ok', 'n8n': 'ok'}`

## 10. Dependencias IA externas

- `ollama`: {'status_code': 200, 'latencia_ms': 1.48, 'disponible': True}
- `n8n`: {'status_code': 200, 'latencia_ms': 1.12, 'disponible': True}
- `backend_chat_health`: {'status_code': 200, 'latencia_ms': 7.07, 'disponible': True}

## 11. Frontend (métricas de activos)

- Archivos: 29 — peso total: 564.5 KB — páginas HTML: 8 — handlers inline: 0

---

*Generado por `Test/run_benchmark.py` (suite ISO/IEC 25000 del repositorio).*
