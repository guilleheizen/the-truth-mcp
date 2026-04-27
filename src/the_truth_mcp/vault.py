"""Capa de I/O sobre la bóveda llm-wiki/. Sin LLM, sin MCP — puro filesystem.

Diseñado para ser testeable y reutilizable. Tanto las MCP tools como el
agente Gemini llaman a estas funciones; nadie escribe directo al disco.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import shutil
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from .schemas import (
    AddLink,
    CreatePage,
    DeletePage,
    MergePages,
    Operation,
    RenamePage,
    SplitPage,
    UpdatePage,
)


VAULT_PATH_VARS = ("VAULT_PATH", "LLM_WIKI_PATH")


def vault_root() -> Path:
    """Path absoluto a la bóveda. Lee VAULT_PATH (o LLM_WIKI_PATH como alias)."""
    p = next((os.environ[v] for v in VAULT_PATH_VARS if os.environ.get(v)), None)
    if not p:
        raise RuntimeError(
            "El path de la bóveda no está seteado. Definí una de estas variables: "
            f"{', '.join(VAULT_PATH_VARS)}.\n"
            "Ejemplo: `export VAULT_PATH=~/Documents/my-vault`."
        )
    root = Path(p).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"El path de la bóveda apunta a un directorio inexistente: {root}")
    return root


def _safe_path(rel_path: str) -> Path:
    """Resuelve una ruta relativa contra vault_root y verifica que no escape.

    Bloquea path traversal: el path resuelto tiene que estar bajo vault_root.
    """
    root = vault_root()
    p = (root / rel_path).resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise ValueError(f"Path fuera de la bóveda: {rel_path}") from e
    return p


def _resolve_slug(slug_or_path: str) -> Path:
    """Acepta 'attention', 'wiki/conceptos/attention.md', o 'attention.md'.

    Retorna el path absoluto al archivo si existe; si no, lanza FileNotFoundError.
    """
    root = vault_root()

    # Caso 1: ruta relativa que ya incluye el .md
    if slug_or_path.endswith(".md"):
        candidate = _safe_path(slug_or_path)
        if candidate.is_file():
            return candidate
        # quizá venía sin "wiki/"
        candidate = _safe_path(f"wiki/{slug_or_path}")
        if candidate.is_file():
            return candidate

    # Caso 2: solo el slug — buscar en wiki/**/<slug>.md
    matches = list(root.glob(f"wiki/**/{slug_or_path}.md"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        rels = [str(m.relative_to(root)) for m in matches]
        raise ValueError(f"Slug ambiguo '{slug_or_path}', matchea: {rels}")

    raise FileNotFoundError(f"No existe página para '{slug_or_path}'")


_LOCK_FILENAME = ".lock"
_LOCK_TIMEOUT_SECONDS = 60


@contextmanager
def vault_lock(timeout: float = _LOCK_TIMEOUT_SECONDS):
    """Lock exclusivo a nivel del filesystem para serializar escrituras al vault.

    Usa fcntl.flock sobre `<vault>/.lock`. Si no se puede adquirir en `timeout`
    segundos, levanta TimeoutError. POSIX-only.
    """
    lock_path = vault_root() / _LOCK_FILENAME
    lock_path.touch(exist_ok=True)
    fh = lock_path.open("w")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Otro proceso tiene el lock del vault ({lock_path}). "
                        f"Esperé {timeout}s. Reintentá en un momento."
                    )
                time.sleep(0.2)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# ──────────────────────────────────────────────────────────────────────────────
# Lectura
# ──────────────────────────────────────────────────────────────────────────────


def list_pages(category: str | None = None) -> list[str]:
    """Lista páginas de wiki/. Si category está dado, filtra a esa subcarpeta.

    category ∈ {'conceptos', 'personas', 'papers'} o None para todas.
    Retorna paths relativos a vault_root.
    """
    root = vault_root()
    base = root / "wiki"
    if category:
        base = base / category
    if not base.is_dir():
        return []
    pages = sorted(p.relative_to(root) for p in base.rglob("*.md") if p.name != "index.md")
    return [str(p) for p in pages]


# ──────────────────────────────────────────────────────────────────────────────
# Front-matter: parser propio (sin PyYAML para no sumar deps).
# Soporta: strings escalares (con o sin comillas), booleanos, números, y
# listas YAML del estilo `key:\n  - item\n  - item`. Suficiente para nuestro
# front-matter — no es un parser YAML general.
# ──────────────────────────────────────────────────────────────────────────────


_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


def _coerce_scalar(raw: str) -> object:
    """Convierte un escalar de YAML simple. Quita comillas, parsea bools/ints/floats."""
    s = raw.strip()
    if not s:
        return ""
    # Quitar comillas si están balanceadas
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~"):
        return None
    # int / float
    try:
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"-?\d+\.\d+", s):
            return float(s)
    except ValueError:  # pragma: no cover (regex ya filtra)
        pass
    return s


def parse_front_matter(content: str) -> dict:
    """Parsea el bloque YAML entre `---` y `---` al inicio del contenido.

    Soporta escalares, booleanos, números y listas con `- item`. Si no hay
    front-matter, devuelve `{}`. No usa PyYAML — diseñado para nuestro
    front-matter, no como parser general.
    """
    m = _FRONT_MATTER_RE.match(content)
    if not m:
        return {}
    body = m.group(1)
    out: dict[str, object] = {}
    current_key: str | None = None
    current_list: list[object] | None = None

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        # Item de lista (indentado con espacios o tab y empezando con `-`)
        list_match = re.match(r"^[ \t]+-\s+(.*)$", line)
        if list_match and current_list is not None:
            current_list.append(_coerce_scalar(list_match.group(1)))
            continue
        # Item de lista en el primer nivel también (soportamos `- foo` después de `key:`)
        first_dash = re.match(r"^-\s+(.*)$", line)
        if first_dash and current_list is not None:
            current_list.append(_coerce_scalar(first_dash.group(1)))
            continue
        # Línea `key:` o `key: value`
        kv = re.match(r"^([A-Za-z_][A-Za-z0-9_\-]*):\s*(.*)$", line)
        if not kv:
            continue
        key = kv.group(1).strip()
        value = kv.group(2)
        if value.strip() == "":
            # Empieza una lista (o un dict — para nuestro caso, asumimos lista).
            current_list = []
            out[key] = current_list
            current_key = key
        else:
            out[key] = _coerce_scalar(value)
            current_list = None
            current_key = key
    # silenciar lint
    _ = current_key
    return out


def _strip_front_matter(content: str) -> str:
    """Devuelve el cuerpo después del bloque de front-matter inicial.

    Si no hay front-matter, devuelve el contenido sin tocar.
    """
    m = _FRONT_MATTER_RE.match(content)
    if not m:
        return content
    return content[m.end():]


def _content_hash(content: str) -> str:
    """SHA-256 hex del cuerpo (sin front-matter), normalizado (strip)."""
    body = _strip_front_matter(content).strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def list_pages_detailed(category: str | None = None) -> list[dict]:
    """Igual que `list_pages` pero devuelve metadata parseada del front-matter.

    Cada entrada: `{path, title, summary, tags, sources, related}`. Los campos
    que no estén en el front-matter quedan como `None` (escalares) o `[]`
    (listas).
    """
    root = vault_root()
    out: list[dict] = []
    for rel in list_pages(category=category):
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        fm = parse_front_matter(text)
        out.append({
            "path": rel,
            "title": fm.get("title"),
            "summary": fm.get("summary"),
            "tags": fm.get("tags") or [],
            "sources": fm.get("sources") or [],
            "related": fm.get("related") or [],
        })
    return out


def is_pinned(path_or_resolved: Path | str) -> bool:
    """True si el archivo tiene `pinned: true` en su front-matter.

    Acepta `Path` absoluto o ruta relativa al vault. Si el archivo no existe
    o no tiene front-matter, devuelve False.
    """
    if isinstance(path_or_resolved, str):
        try:
            target = _safe_path(path_or_resolved)
        except ValueError:
            return False
    else:
        target = path_or_resolved
    if not target.is_file():
        return False
    try:
        text = target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    fm = parse_front_matter(text)
    return bool(fm.get("pinned") is True)


def read_page(slug_or_path: str) -> str:
    """Lee el contenido completo de una página."""
    return _resolve_slug(slug_or_path).read_text(encoding="utf-8")


def read_file(rel_path: str) -> str:
    """Lee un archivo arbitrario dentro de la bóveda (con check de seguridad)."""
    return _safe_path(rel_path).read_text(encoding="utf-8")


def read_index() -> str:
    return (vault_root() / "wiki" / "index.md").read_text(encoding="utf-8")


def read_log(n: int = 20) -> str:
    """Devuelve las últimas N entradas del log (delimitadas por '## [')."""
    full = (vault_root() / "log.md").read_text(encoding="utf-8")
    if n <= 0:
        return full
    parts = re.split(r"(?m)^(?=## \[)", full)
    head = parts[0] if parts else ""
    entries = parts[1:] if len(parts) > 1 else []
    return head + "".join(entries[-n:])


def read_agents_md() -> str:
    """El schema vivo. Útil para inyectarlo al prompt de Gemini."""
    root = vault_root()
    candidate = root / "AGENTS.md"
    if not candidate.is_file():
        raise FileNotFoundError(f"AGENTS.md no encontrado en {root}")
    return candidate.read_text(encoding="utf-8")


def search(query: str, limit: int = 50) -> list[dict[str, object]]:
    """Grep simple sobre wiki/. Retorna lista de matches: {path, line, text}."""
    root = vault_root()
    out: list[dict[str, object]] = []
    needle = query.lower()
    for p in (root / "wiki").rglob("*.md"):
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if needle in line.lower():
                    out.append({
                        "path": str(p.relative_to(root)),
                        "line": i,
                        "text": line.strip(),
                    })
                    if len(out) >= limit:
                        return out
        except UnicodeDecodeError:
            continue
    return out


def list_raw() -> list[str]:
    """Archivos en raw/. Estructura plana — Gemini decide la organización del wiki."""
    root = vault_root()
    base = root / "raw"
    if not base.is_dir():
        return []
    return sorted(str(p.relative_to(root)) for p in base.rglob("*.md"))


_SOURCES_RE = re.compile(r"(?ms)^sources:\s*\n((?:[ \t]*-\s+.+\n?)*)")
_SOURCE_LINE_RE = re.compile(r"^[ \t]*-\s+(.+?)\s*$", re.MULTILINE)


def _wiki_sources_index() -> set[str]:
    """Set de todas las rutas mencionadas en `sources:` de cualquier wiki/**.md."""
    root = vault_root()
    found: set[str] = set()
    for p in (root / "wiki").rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        m = _SOURCES_RE.search(text)
        if not m:
            continue
        for src in _SOURCE_LINE_RE.findall(m.group(1)):
            found.add(src.strip().strip('"').strip("'"))
    return found


_LAST_GROOM_STAMP = ".last_groom"


def mark_groomed() -> None:
    """Toca el stamp `.last_groom` en la raíz del vault.

    Lo llama `gemini_agent.reorganize` después de aplicar el plan exitosamente.
    El mtime del archivo es el timestamp del último groom — barato y compatible
    con cualquier OS sin tracking adicional.
    """
    (vault_root() / _LAST_GROOM_STAMP).touch()


def last_groom_at() -> datetime | None:
    """Timestamp UTC del último groom exitoso, o None si nunca corrió."""
    stamp = vault_root() / _LAST_GROOM_STAMP
    if not stamp.is_file():
        return None
    return datetime.fromtimestamp(stamp.stat().st_mtime, tz=timezone.utc)


def vault_status() -> dict[str, object]:
    """Snapshot del estado: cuántas páginas, cuántas fuentes, qué está pendiente.

    Una fuente en `raw/` se considera "pendiente" si no aparece referenciada
    en el campo `sources:` de ninguna página de wiki/.
    """
    root = vault_root()
    referenced = _wiki_sources_index()
    raw_files = list_raw()
    pending = [p for p in raw_files if p not in referenced]
    pages = list_pages()
    last_groom = last_groom_at()
    return {
        "vault_root": str(root),
        "wiki_pages": len(pages),
        "raw_total": len(raw_files),
        "raw_pending": pending,
        "raw_processed": len(raw_files) - len(pending),
        "last_groom": last_groom.isoformat() if last_groom else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Escritura
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Parser del log (recientes)
# ──────────────────────────────────────────────────────────────────────────────


_LOG_HEADING_RE = re.compile(
    r"^##\s+\[(?P<date>\d{4}-\d{2}-\d{2})\]\s+(?P<type>\S+)\s*\|\s*(?P<title>.+?)\s*$",
    re.MULTILINE,
)


def parse_log_entries(text: str) -> list[dict]:
    """Parsea entradas del log. Cada entrada empieza con `## [YYYY-MM-DD] tipo | titulo`.

    Devuelve una lista de `{date, type, title, body}` en el orden en que aparecen.
    `body` es el texto entre el heading y el siguiente (sin incluir headings).
    """
    headings = list(_LOG_HEADING_RE.finditer(text))
    entries: list[dict] = []
    for i, h in enumerate(headings):
        body_start = h.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end].strip("\n")
        entries.append({
            "date": h.group("date"),
            "type": h.group("type"),
            "title": h.group("title").strip(),
            "body": body,
        })
    return entries


def recent_entries(since: str | None = None, limit: int = 20) -> list[dict]:
    """Devuelve las últimas entradas del log, opcionalmente filtradas por fecha.

    `since` es ISO `YYYY-MM-DD` (inclusive). `limit` recorta el resultado al
    final del orden descendente por fecha.
    """
    log_path = vault_root() / "log.md"
    if not log_path.is_file():
        return []
    text = log_path.read_text(encoding="utf-8")
    entries = parse_log_entries(text)
    if since:
        entries = [e for e in entries if e["date"] >= since]
    # Orden descendente por fecha (estable: si empatan fechas, conserva orden de
    # aparición — los más recientes en el archivo quedan primero).
    entries.sort(key=lambda e: e["date"], reverse=True)
    if limit > 0:
        entries = entries[:limit]
    return entries


def append_log(event_type: str, title: str, body: str | None = None) -> str:
    """Apendea entrada al log. Retorna la línea de heading que escribió."""
    valid = {"ingest", "query", "lint", "refactor", "init", "reorganize"}
    if event_type not in valid:
        raise ValueError(f"event_type inválido: {event_type}. Válidos: {valid}")
    today = date.today().isoformat()
    heading = f"## [{today}] {event_type} | {title}"
    block = f"\n\n{heading}\n"
    if body:
        block += body if body.endswith("\n") else body + "\n"
    log_path = vault_root() / "log.md"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(block)
    return heading


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    base = title.lower().strip()
    # quitar acentos básicos
    accents = str.maketrans("áéíóúüñ", "aeiouun")
    base = base.translate(accents)
    base = _SLUG_RE.sub("-", base).strip("-")
    return base or "untitled"


_CONTENT_HASH_RE = re.compile(r"(?m)^content_hash:\s*([0-9a-f]{64})\s*$")


def _find_raw_by_hash(hash_hex: str) -> str | None:
    """Busca un raw cuyo front-matter declare `content_hash: <hash_hex>`.

    No relee el cuerpo de cada raw — solo escanea el front-matter. Esto
    mantiene el dedup barato. Raws viejos sin `content_hash` no se detectan
    como duplicados (es OK, no rompemos nada).
    """
    root = vault_root()
    raw_dir = root / "raw"
    if not raw_dir.is_dir():
        return None
    for p in sorted(raw_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        m = _FRONT_MATTER_RE.match(text)
        if not m:
            continue
        hm = _CONTENT_HASH_RE.search(m.group(1))
        if hm and hm.group(1) == hash_hex:
            return str(p.relative_to(root))
    return None


def _build_raw_front_matter(
    *,
    title: str | None,
    source: str | None,
    content_hash: str,
) -> str:
    """Construye un bloque de front-matter para raws nuevos."""
    today = date.today().isoformat()
    lines = ["---", f"fetched: {today}"]
    if title:
        lines.append(f'title: "{title}"')
    if source:
        lines.append(f"source: {source}")
    lines.append(f"content_hash: {content_hash}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def add_to_raw(
    content: str,
    *,
    slug: str | None = None,
    title: str | None = None,
    source: str | None = None,
) -> dict:
    """Guarda contenido nuevo en raw/<slug>.md, con dedup por hash de contenido.

    Es la única vía por la que entra info nueva a la bóveda. No procesa, no
    analiza. Si ya existe un raw con el mismo hash de contenido, NO escribe
    nada y devuelve el path existente (flag `deduplicated: True`).

    Returns: dict con
      - `path`: ruta relativa al raw (recién creado o duplicado preexistente).
      - `deduplicated`: True si se detectó un duplicado y no se escribió nada.
    """
    if not slug and not title:
        raise ValueError("Necesito al menos `slug` o `title` para nombrar el archivo")

    # Dedup por hash del cuerpo (ignorando front-matter, normalizado).
    hash_hex = _content_hash(content)
    existing = _find_raw_by_hash(hash_hex)
    if existing is not None:
        return {"path": existing, "deduplicated": True}

    # Siempre normalizamos el slug — incluso si lo pasó el usuario. Esto
    # neutraliza separadores de ruta (`../`, `/`) que de otro modo permitirían
    # que un slug malicioso escape de `raw/` aún quedando dentro del vault.
    final_slug = slugify(slug or title or "")
    target = _safe_path(f"raw/{final_slug}.md")
    # Defensa en profundidad: aunque _safe_path ya impide escapar el vault,
    # exigimos explícitamente que el archivo termine bajo raw/.
    raw_root = (vault_root() / "raw").resolve()
    try:
        target.relative_to(raw_root)
    except ValueError as e:
        raise ValueError(f"El slug derivado escapa de raw/: {final_slug!r}") from e
    if target.exists():
        raise FileExistsError(f"raw/{final_slug}.md ya existe — raw es inmutable")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Si no hay front-matter, lo agregamos (con content_hash incluido).
    # Si lo hay, lo respetamos pero igual queremos `content_hash` para que el
    # próximo dedup nos detecte. Inyectamos la línea dentro del bloque existente.
    if not content.lstrip().startswith("---"):
        content = _build_raw_front_matter(
            title=title, source=source, content_hash=hash_hex
        ) + content
    else:
        m = _FRONT_MATTER_RE.match(content)
        if m and "content_hash:" not in m.group(1):
            inner = m.group(1).rstrip() + f"\ncontent_hash: {hash_hex}\n"
            body = content[m.end():]
            # Aseguramos al menos una línea en blanco entre el front-matter y
            # el cuerpo (si la había en el original, igual queda una sola
            # — no nos ponemos paranoicos con el formato exacto).
            content = f"---\n{inner}---\n\n" + body.lstrip("\n")

    target.write_text(content, encoding="utf-8")
    return {
        "path": str(target.relative_to(vault_root())),
        "deduplicated": False,
    }


def replace_raw(
    slug: str,
    new_content: str,
    *,
    source: str | None = None,
) -> dict:
    """Versiona el raw existente y escribe el nuevo en `raw/<slug>.md`.

    El raw debe existir; si no, levanta `FileNotFoundError`. Mueve el actual a
    `raw/<slug>-vN.md` (donde N es el primer número libre desde 2) y escribe
    el nuevo contenido en `raw/<slug>.md`. Devuelve `{current, archived}`.
    """
    final_slug = slugify(slug)
    current = _safe_path(f"raw/{final_slug}.md")
    if not current.exists():
        raise FileNotFoundError(f"No existe raw/{final_slug}.md para reemplazar")

    # Encontrar el siguiente número libre: -v2, -v3, ...
    n = 2
    while True:
        archived = _safe_path(f"raw/{final_slug}-v{n}.md")
        if not archived.exists():
            break
        n += 1

    shutil.move(str(current), str(archived))

    # Escribir el nuevo contenido reusando la lógica de add_to_raw para el
    # front-matter (incluye content_hash).
    hash_hex = _content_hash(new_content)
    if not new_content.lstrip().startswith("---"):
        new_content = _build_raw_front_matter(
            title=None, source=source, content_hash=hash_hex
        ) + new_content
    else:
        m = _FRONT_MATTER_RE.match(new_content)
        if m and "content_hash:" not in m.group(1):
            inner = m.group(1).rstrip() + f"\ncontent_hash: {hash_hex}\n"
            body = new_content[m.end():]
            new_content = f"---\n{inner}---\n\n" + body.lstrip("\n")

    current.write_text(new_content, encoding="utf-8")
    root = vault_root()
    return {
        "current": str(current.relative_to(root)),
        "archived": str(archived.relative_to(root)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Operaciones del plan Gemini
# ──────────────────────────────────────────────────────────────────────────────


def _ensure_under_wiki(rel_path: str) -> Path:
    """Permite escribir solo dentro de wiki/. Bloquea raw/ y cualquier otra cosa fuera de wiki/."""
    if not rel_path.startswith("wiki/"):
        raise ValueError(f"Solo se puede escribir bajo wiki/: {rel_path}")
    return _safe_path(rel_path)


def _check_not_pinned(rel_path: str, op_type: str) -> None:
    """Levanta ValueError si la página está pineada.

    Usado por las operaciones destructivas (update, delete, rename, merge,
    split). `add_link` no llama esto porque está permitida sobre páginas
    pineadas.
    """
    target = _safe_path(rel_path)
    if is_pinned(target):
        raise ValueError(
            f"Página pineada, operación {op_type} bloqueada: {rel_path}"
        )


def apply_operation(op: Operation) -> str:
    """Aplica una operación del plan de Gemini. Retorna mensaje de resultado.

    Solo toca wiki/. Nunca raw/.
    """
    if isinstance(op, CreatePage):
        target = _ensure_under_wiki(op.path)
        if target.exists():
            raise FileExistsError(f"Ya existe: {op.path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(op.content, encoding="utf-8")
        return f"created {op.path}"

    if isinstance(op, UpdatePage):
        target = _ensure_under_wiki(op.path)
        if not target.exists():
            raise FileNotFoundError(f"No existe: {op.path}")
        _check_not_pinned(op.path, "update_page")
        target.write_text(op.content, encoding="utf-8")
        return f"updated {op.path}"

    if isinstance(op, DeletePage):
        target = _ensure_under_wiki(op.path)
        if not target.exists():
            return f"skipped delete (no existe): {op.path}"
        _check_not_pinned(op.path, "delete_page")
        target.unlink()
        return f"deleted {op.path}"

    if isinstance(op, RenamePage):
        src = _ensure_under_wiki(op.from_path)
        dst = _ensure_under_wiki(op.to_path)
        if not src.exists():
            raise FileNotFoundError(f"No existe: {op.from_path}")
        if dst.exists():
            raise FileExistsError(f"Destino ya existe: {op.to_path}")
        _check_not_pinned(op.from_path, "rename_page")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"renamed {op.from_path} → {op.to_path}"

    if isinstance(op, MergePages):
        into = _ensure_under_wiki(op.into_path)
        # Si la destino existe y está pineada, no podemos sobrescribirla.
        if into.exists():
            _check_not_pinned(op.into_path, "merge_pages")
        # Ninguno de los origenes puede estar pineado.
        for src_path in op.from_paths:
            if src_path == op.into_path:
                continue
            src_check = _ensure_under_wiki(src_path)
            if src_check.exists():
                _check_not_pinned(src_path, "merge_pages")
        into.parent.mkdir(parents=True, exist_ok=True)
        into.write_text(op.merged_content, encoding="utf-8")
        deleted = []
        for src_path in op.from_paths:
            if src_path == op.into_path:
                continue
            src = _ensure_under_wiki(src_path)
            if src.exists():
                src.unlink()
                deleted.append(src_path)
        return f"merged {deleted} → {op.into_path}"

    if isinstance(op, SplitPage):
        src = _ensure_under_wiki(op.from_path)
        if not src.exists():
            raise FileNotFoundError(f"No existe: {op.from_path}")
        _check_not_pinned(op.from_path, "split_page")
        created = []
        for new_page in op.new_pages:
            target = _ensure_under_wiki(new_page.path)
            if target.exists():
                raise FileExistsError(f"Ya existe: {new_page.path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_page.content, encoding="utf-8")
            created.append(new_page.path)
        src.unlink()
        return f"split {op.from_path} → {created}"

    if isinstance(op, AddLink):
        target = _ensure_under_wiki(op.in_path)
        if not target.exists():
            raise FileNotFoundError(f"No existe: {op.in_path}")
        text = target.read_text(encoding="utf-8")
        link = f"[[{op.target_slug}]]"
        if link in text:
            return f"skipped add_link (ya está): {op.in_path} → {link}"
        # Append como bullet en una sección "Ver también" al final
        if "## Ver también" in text:
            text = re.sub(
                r"(## Ver también\n)",
                rf"\1- {link}\n",
                text,
                count=1,
            )
        else:
            sep = "" if text.endswith("\n") else "\n"
            text += f"{sep}\n## Ver también\n\n- {link}\n"
        target.write_text(text, encoding="utf-8")
        return f"added link in {op.in_path} → {link}"

    raise ValueError(f"Operación desconocida: {type(op).__name__}")
