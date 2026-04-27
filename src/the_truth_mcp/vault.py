"""Capa de I/O sobre la bóveda llm-wiki/. Sin LLM, sin MCP — puro filesystem.

Diseñado para ser testeable y reutilizable. Tanto las MCP tools como el
agente Gemini llaman a estas funciones; nadie escribe directo al disco.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import date
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
    """El schema vivo. Útil para inyectarlo al prompt de Gemini.

    Busca primero AGENTS.md (nombre canónico, agent-agnostic). Si no existe,
    cae a CLAUDE.md por compatibilidad con vaults viejos.
    """
    root = vault_root()
    for name in ("AGENTS.md", "CLAUDE.md"):
        candidate = root / name
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Ni AGENTS.md ni CLAUDE.md encontrados en {root}")


# Alias deprecado para back-compat. Se removerá en una versión futura.
read_claude_md = read_agents_md


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
    return {
        "vault_root": str(root),
        "wiki_pages": len(pages),
        "raw_total": len(raw_files),
        "raw_pending": pending,
        "raw_processed": len(raw_files) - len(pending),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Escritura
# ──────────────────────────────────────────────────────────────────────────────


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


def add_to_raw(
    content: str,
    *,
    slug: str | None = None,
    title: str | None = None,
    source: str | None = None,
) -> str:
    """Guarda contenido nuevo en raw/<slug>.md.

    Es la única vía por la que entra info nueva a la bóveda. No procesa, no
    analiza. Si ya existe el archivo, falla — no sobrescribe (raw es sagrado).
    """
    if not slug and not title:
        raise ValueError("Necesito al menos `slug` o `title` para nombrar el archivo")
    final_slug = slug or slugify(title or "")
    target = _safe_path(f"raw/{final_slug}.md")
    if target.exists():
        raise FileExistsError(f"raw/{final_slug}.md ya existe — raw es inmutable")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Si no hay front-matter, lo agregamos
    if not content.lstrip().startswith("---"):
        today = date.today().isoformat()
        fm_lines = ["---", f"fetched: {today}"]
        if title:
            fm_lines.append(f'title: "{title}"')
        if source:
            fm_lines.append(f"source: {source}")
        fm_lines.append("---")
        content = "\n".join(fm_lines) + "\n\n" + content

    target.write_text(content, encoding="utf-8")
    return str(target.relative_to(vault_root()))


# ──────────────────────────────────────────────────────────────────────────────
# Operaciones del plan Gemini
# ──────────────────────────────────────────────────────────────────────────────


def _ensure_under_wiki(rel_path: str) -> Path:
    """Permite escribir solo dentro de wiki/. Bloquea raw/, .claude/, etc."""
    if not rel_path.startswith("wiki/"):
        raise ValueError(f"Solo se puede escribir bajo wiki/: {rel_path}")
    return _safe_path(rel_path)


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
        target.write_text(op.content, encoding="utf-8")
        return f"updated {op.path}"

    if isinstance(op, DeletePage):
        target = _ensure_under_wiki(op.path)
        if not target.exists():
            return f"skipped delete (no existe): {op.path}"
        target.unlink()
        return f"deleted {op.path}"

    if isinstance(op, RenamePage):
        src = _ensure_under_wiki(op.from_path)
        dst = _ensure_under_wiki(op.to_path)
        if not src.exists():
            raise FileNotFoundError(f"No existe: {op.from_path}")
        if dst.exists():
            raise FileExistsError(f"Destino ya existe: {op.to_path}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"renamed {op.from_path} → {op.to_path}"

    if isinstance(op, MergePages):
        into = _ensure_under_wiki(op.into_path)
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
