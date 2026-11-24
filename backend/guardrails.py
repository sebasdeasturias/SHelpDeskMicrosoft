# backend/guardrails.py
"""Guardrail de prompt injection para el chat IA.

Filtra, ANTES de enviar el mensaje a n8n/Ollama, combinaciones de palabras
asociadas a inyección de prompts: anular instrucciones, revelar el system
prompt, crear/ejecutar scripts, exfiltrar datos de usuarios, jailbreaks, etc.

Diseño:
  * Se normaliza el texto (minúsculas, sin acentos, sin caracteres de ancho
    cero y con espacios colapsados) para evitar evasiones triviales.
  * Cada patrón se asocia a una categoría legible que se registra en auditoría.
  * El contexto del ticket (dato no confiable aportado por el solicitante) se
    evalúa aparte: si está marcado, se omite del payload que va a n8n.
  * Interruptor `GUARDRAIL_CHAT_ENABLED` para desactivarlo sin tocar código.

Este filtro es defensa en profundidad: NO sustituye a los guardrails de
salida ni al aislamiento del system prompt (ver docs/SEGURIDAD-IA.md).
"""
import os
import re
import unicodedata
from typing import Optional, Tuple

# Interruptor general (por defecto activado).
GUARDRAIL_CHAT_ENABLED = os.getenv(
    "GUARDRAIL_CHAT_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "on")

# Verbos de petición, incluidas formas con pronombre ("muéstrame", "dámelos").
# El texto se normaliza sin acentos, por eso "enséñame" se escribe "ensename".
_VERBO_SOLICITAR = (
    r"\b(dame|damel[oa]s?|muestra(me|r|mos)?|ensen[a|e]a?(me|r|mos)?|"
    r"revela(me|r|mos)?|lista(me|r|mos)?|pasa(me|r|mos)?|"
    r"give|show|reveal|list|exporta?|leak|get|obten(me)?|dump|filtra(me|r)?)\b"
)

# (patrón, categoría). Los patrones se comparan sobre el texto normalizado.
_PATRONES = [
    # --- 1) Anular / revelar instrucciones o system prompt ---
    (r"\b(ignora|ignore|olvida|forget|disregard|override|anula|salta|skip)\b"
     r".{0,40}\b(instrucciones?|instructions?|reglas?|rules?|restricciones?|"
     r"restrictions?|prompt|sistema|system)\b", "anular_instrucciones"),
    (r"\bsystem\s*prompt\b|\bprompt\s*(del|de)\s*sistema\b|"
     r"\bsystem\s*instructions?\b", "revelar_system_prompt"),
    (r"\b(revela|reveal|muestra|show|imprime|print|repite|repeat|filtra|leak|"
     r"dime|tell)\b.{0,30}\b(prompt|instrucciones|instructions|system|sistema)\b",
     "revelar_system_prompt"),
    (r"\b(jailbreak|dan\s*mode|developer\s*mode|modo\s*desarrollador|"
     r"modo\s*dios|god\s*mode|do\s*anything\s*now|sin\s*restricciones|"
     r"no\s*restrictions)\b", "jailbreak"),

    # --- 2) Crear / ejecutar scripts y comandos ---
    (r"\b(crea|crear|create|write|escribe|genera|generate|haz|make|run|"
     r"ejecuta|execute|construye|build)\b.{0,40}\b(script|scripts|comando|"
     r"comandos|command|commands|codigo|code|shell|bash|powershell|batch|"
     r"payload|malware|virus|ransomware)\b", "crear_ejecutar_codigo"),
    (r"\b(curl|wget)\b.{0,80}(\||>|http://|https://)", "ejecutar_comando"),
    (r"\b(rm\s+-rf|mkfs(\.[a-z0-9]+)?|dd\s+if=|chmod\s+777|nc\s+-e|/bin/sh|"
     r"powershell\s+-enc)\b", "comando_peligroso"),

    # --- 3) Exfiltrar datos de usuarios / credenciales ---
    (_VERBO_SOLICITAR + r".{0,40}\b(contrase[nñ]as?|passwords?|"
     r"credenciales?|credentials?|api[\s_-]?keys?|secretos?|secrets?|tokens?)\b",
     "exfiltrar_credenciales"),
    (_VERBO_SOLICITAR + r".{0,40}\b(datos|data|informacion|"
     r"information)\b.{0,25}\b(de\s+)?(los\s+|las\s+|the\s+)?"
     r"(usuarios?|users?|clientes?|customers?|personales?|personal)\b",
     "exfiltrar_datos"),
    (_VERBO_SOLICITAR + r".{0,40}\b(usuarios?|users?|clientes?|customers?)\b"
     r".{0,25}\b(datos|data|informacion|information|emails?|correos?|telefonos?|"
     r"phones?)\b", "exfiltrar_datos"),
    (r"\b(base\s+de\s+datos|database|dump|volcado)\b.{0,30}\b(usuarios|users|"
     r"completa|complete|entera|full)\b", "exfiltrar_datos"),

    # --- 4) Cambio de identidad / roleplay malicioso ---
    (r"\b(actua\s+como|act\s+as|you\s+are\s+now|ahora\s+eres|finge\s+ser|"
     r"pretend\s+to\s+be|roleplay|role\s*play)\b", "cambio_identidad"),

    # --- 5) Tokens de plantilla que rompen el formato del chat ---
    (r"<\|[^|>]{1,30}\|>|<<\s*SYS\s*>>|\[/?INST\]", "token_plantilla"),
]

_COMPILADOS = [
    (re.compile(patron, re.IGNORECASE | re.DOTALL), categoria)
    for patron, categoria in _PATRONES
]


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos, sin caracteres invisibles y espacios simples."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def evaluar_prompt(texto: str) -> Tuple[bool, str]:
    """Devuelve (bloqueado, categoría). `categoría` es '' si no hay riesgo."""
    if not GUARDRAIL_CHAT_ENABLED:
        return False, ""
    t = normalizar(texto)
    if not t:
        return False, ""
    for regex, categoria in _COMPILADOS:
        if regex.search(t):
            return True, categoria
    return False, ""


def mensaje_rechazo() -> str:
    """Respuesta fija y segura que se muestra cuando se bloquea un mensaje."""
    return (
        "No puedo procesar esa solicitud: contiene instrucciones que intentan "
        "modificar el comportamiento del asistente o extraer información "
        "sensible. Reformula tu consulta técnica sobre el ticket."
    )


def texto_ticket_seguro(texto: str) -> Optional[str]:
    """Devuelve el texto si es seguro, o None si parece una inyección.

    Se usa para el contexto del ticket (dato no confiable): si está marcado se
    omite del payload en lugar de enviarlo al modelo.
    """
    bloqueado, _ = evaluar_prompt(texto)
    return None if bloqueado else texto
