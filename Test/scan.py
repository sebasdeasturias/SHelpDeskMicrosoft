import ast
import re
from collections import defaultdict
from pathlib import Path

from config import ROOT, SKIP_DIRS, SOURCE_SUFFIXES, BACKEND, DATABASE


def iter_files(*suffixes):
    wanted = set(suffixes) if suffixes else SOURCE_SUFFIXES
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in wanted:
            yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def corpus(*suffixes) -> str:
    chunks = []
    for path in iter_files(*suffixes):
        chunks.append(read_text(path))
    return "\n".join(chunks)


def file_map(*suffixes) -> dict[str, str]:
    out = {}
    for path in iter_files(*suffixes):
        out[rel(path)] = read_text(path)
    return out


def count_matches(text: str, pattern: str, flags=0) -> int:
    return len(re.findall(pattern, text, flags))


def has_all(text: str, patterns) -> bool:
    return all(p in text for p in patterns)


def has_any(text: str, patterns) -> bool:
    return any(p in text for p in patterns)


def evidence_level(text: str, patterns) -> str:
    if not patterns:
        return "ninguna"
    hits = sum(1 for p in patterns if p in text)
    if hits == len(patterns):
        return "completa"
    if hits > 0:
        return "parcial"
    return "ninguna"


def _complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.Assert, ast.With, ast.AsyncWith)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(len(child.values) - 1, 0)
        elif isinstance(child, ast.comprehension):
            score += 1
        elif isinstance(child, ast.IfExp):
            score += 1
    return score


def python_metrics() -> dict:
    functions = []
    try_blocks = 0
    http_exc = 0
    routers = 0
    sql_text = 0
    sql_fstring = 0
    loc = 0
    comments = 0
    total_lines = 0
    imports = defaultdict(int)

    for path in iter_files(".py"):
        src = read_text(path)
        total_lines += src.count("\n") + 1
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                comments += 1
            else:
                loc += 1
        http_exc += src.count("HTTPException")
        routers += src.count("APIRouter(")
        sql_text += count_matches(src, r"text\s*\(")
        sql_fstring += count_matches(src, r"text\s*\(\s*f[\"']")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                try_blocks += 1
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "file": rel(path),
                    "name": node.name,
                    "cc": _complexity(node),
                    "lineno": node.lineno,
                })
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.name.split(".")[0]] += 1
            if isinstance(node, ast.ImportFrom) and node.module:
                imports[node.module.split(".")[0]] += 1

    ccs = [f["cc"] for f in functions]
    return {
        "py_files": len(list(iter_files(".py"))),
        "loc": loc,
        "total_lines": total_lines,
        "comment_lines": comments,
        "comment_density": round(comments / loc, 4) if loc else 0,
        "functions": len(functions),
        "avg_cc": round(sum(ccs) / len(ccs), 2) if ccs else 0,
        "max_cc": max(ccs) if ccs else 0,
        "cc_gt_10": sum(1 for c in ccs if c > 10),
        "cc_gt_20": sum(1 for c in ccs if c > 20),
        "try_blocks": try_blocks,
        "http_exceptions": http_exc,
        "routers": routers,
        "sql_text_calls": sql_text,
        "sql_fstring_calls": sql_fstring,
        "sql_param_ratio": round((sql_text - sql_fstring) / sql_text, 4) if sql_text else 1.0,
        "top_complex": sorted(functions, key=lambda f: f["cc"], reverse=True)[:8],
        "imports": dict(sorted(imports.items(), key=lambda kv: -kv[1])[:20]),
    }


def schema_metrics() -> dict:
    sql_files = list(DATABASE.rglob("*.sql")) if DATABASE.exists() else []
    sql = "\n".join(read_text(p) for p in sql_files)
    tables = re.findall(r"CREATE TABLE\s+(\w+)", sql, re.I)
    checks = count_matches(sql, r"\bCHECK\s*\(", re.I)
    fks = count_matches(sql, r"\bREFERENCES\s+\w+", re.I)
    pks = count_matches(sql, r"\bPRIMARY KEY\b", re.I)
    uniques = count_matches(sql, r"\bUNIQUE\b", re.I)
    not_null = count_matches(sql, r"\bNOT NULL\b", re.I)
    indexes = count_matches(sql, r"\bCREATE INDEX\b", re.I)
    triggers = count_matches(sql, r"\bCREATE TRIGGER\b", re.I)
    views = count_matches(sql, r"\bCREATE OR REPLACE VIEW\b", re.I)
    return {
        "sql_files": len(sql_files),
        "tables": sorted(set(tables)),
        "table_count": len(set(tables)),
        "checks": checks,
        "foreign_keys": fks,
        "primary_keys": pks,
        "uniques": uniques,
        "not_null": not_null,
        "indexes": indexes,
        "triggers": triggers,
        "views": views,
        "has_historial": "CREATE TABLE historial" in sql,
        "has_sla": "CREATE TABLE sla" in sql,
        "has_log": "CREATE TABLE log" in sql,
        "has_embedding": "CREATE TABLE embedding_vector" in sql,
        "has_pgvector": "CREATE EXTENSION IF NOT EXISTS vector" in sql,
    }


def endpoint_metrics() -> dict:
    src = corpus(".py")
    decorated = re.findall(
        r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"']",
        src,
        re.I,
    )
    health = "/api/health" in src or 'async def health_check' in src
    login = "/login" in src
    return {
        "count": len(decorated),
        "by_method": {
            method: sum(1 for m, _ in decorated if m.lower() == method)
            for method in ("get", "post", "put", "patch", "delete")
        },
        "paths": [f"{m.upper()} {p}" for m, p in decorated],
        "health": health,
        "login": login,
    }


def auth_metrics() -> dict:
    py = corpus(".py")
    js = corpus(".js")
    html = corpus(".html")
    yml = corpus(".yml", ".yaml")
    all_src = py + js + html + yml
    return {
        "jwt": "jwt.encode" in py and "jwt.decode" in py,
        "bcrypt": "bcrypt" in py,
        "oauth2": "OAuth2PasswordBearer" in py,
        "rate_limit": "SlidingWindowLimiter" in py or "login_limiter" in py,
        "cors": "CORSMiddleware" in py,
        "env_jwt": "JWT_SECRET_KEY" in py,
        "env_db": "DATABASE_URL" in py,
        "fail_closed_ai": "AI_CALLBACK_KEY" in py and "Fail-closed" in py,
        "magic_bytes": "PNG_FIRMA" in py or "magic bytes" in py.lower(),
        "uuid_uploads": "uuid" in py and "UPLOAD_DIR" in py,
        "password_min_8": "al menos 8" in py or "mín. 8" in html,
        "trust_proxy": "TRUST_PROXY" in py,
        "docker_sock": "/var/run/docker.sock" in yml,
        "cors_default_star": 'CORS_ORIGINS", "*"' in py or "CORS_ORIGINS:-*" in yml,
        "jwt_24h": "60 * 24" in py,
        "hardcoded_password": "password123" in py,
        "no_password_in_ticket": "NUNCA la contraseña" in py,
        "gitignore_env": (ROOT / ".gitignore").exists() and ".env" in read_text(ROOT / ".gitignore"),
        "bind_params": py.count("text(") > 0,
        "roles": all(r in all_src for r in ("solicitante", "agente", "coordinador", "administrador")),
    }


def product_size() -> dict:
    files = list(iter_files())
    loc = 0
    by_ext = defaultdict(lambda: {"files": 0, "loc": 0})
    for path in files:
        src = read_text(path)
        lines = sum(1 for line in src.splitlines() if line.strip())
        loc += lines
        by_ext[path.suffix or "(none)"]["files"] += 1
        by_ext[path.suffix or "(none)"]["loc"] += lines
    return {
        "files": len(files),
        "loc": loc,
        "by_ext": dict(by_ext),
        "has_backend": BACKEND.exists(),
        "has_frontend": (ROOT / "frontend").exists(),
        "has_docker": (ROOT / "docker").exists(),
        "has_streamlit": (ROOT / "streamlit_app").exists(),
        "has_ai": (ROOT / "AIEngine").exists(),
    }


def collect_all() -> dict:
    return {
        "size": product_size(),
        "python": python_metrics(),
        "schema": schema_metrics(),
        "endpoints": endpoint_metrics(),
        "auth": auth_metrics(),
        "corpus_py": corpus(".py"),
        "corpus_all": corpus(".py", ".js", ".html", ".sql", ".yml", ".yaml"),
    }
