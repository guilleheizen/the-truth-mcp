"""MCP server: the-truth-mcp.

Local-only, transport stdio. Configurable por env vars:
  - GEMINI_API_KEY   (obligatoria — el bibliotecario corre con cada save_info)
  - LLM_WIKI_PATH    (obligatoria — path absoluto a la bóveda)
  - GEMINI_MODEL     (opcional, default gemini-2.5-flash)

Diseño minimalista: el cliente (Claude) solo puede hacer dos cosas — consultar
y guardar. El "guardar" dispara automáticamente al bibliotecario Gemini, que
ordena la bóveda. La complejidad queda dentro del MCP.

Tools (4):
  - vault_search       leer: grep en wiki/
  - vault_read_page    leer: contenido de una página
  - vault_list_pages   leer: catálogo
  - save_info          escribir: plonk en raw/ + Gemini reorganiza wiki/

Resources:
  - vault://index, vault://log, vault://claude
  - vault://page/{category}/{slug}
"""

from __future__ import annotations

from typing import Annotated

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# Carga .env del cwd o ancestros antes de tocar env vars.
load_dotenv()

from . import gemini_agent, vault  # noqa: E402  (después de load_dotenv)


mcp = FastMCP("the-truth-mcp")


# ──────────────────────────────────────────────────────────────────────────────
# Tools — lectura
# ──────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def vault_search(
    query: Annotated[str, Field(description="Texto a buscar (case-insensitive) en wiki/")],
    limit: Annotated[int, Field(description="Máximo de matches a devolver", ge=1, le=200)] = 50,
) -> list[dict]:
    """Busca en wiki/ y devuelve matches con archivo y número de línea."""
    return vault.search(query, limit=limit)


@mcp.tool()
def vault_read_page(
    slug_or_path: Annotated[
        str,
        Field(description="Slug ('attention') o ruta ('wiki/conceptos/attention.md')"),
    ],
) -> str:
    """Lee el contenido completo de una página de wiki/."""
    return vault.read_page(slug_or_path)


@mcp.tool()
def vault_list_pages(
    category: Annotated[
        str | None,
        Field(description="Filtrar por categoría: 'conceptos', 'personas', 'papers', o None"),
    ] = None,
) -> list[str]:
    """Lista las páginas de wiki/ (paths relativos a la bóveda)."""
    return vault.list_pages(category=category)


# ──────────────────────────────────────────────────────────────────────────────
# Tools — escritura
# ──────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def save_info(
    content: Annotated[str, Field(description="Contenido completo de la fuente (markdown crudo)")],
    title: Annotated[
        str | None,
        Field(description="Título humano de la fuente. Se usa para generar el slug si no se provee uno."),
    ] = None,
    slug: Annotated[
        str | None,
        Field(description="Slug explícito en kebab-case. Si no se provee, se deriva del título."),
    ] = None,
    source: Annotated[
        str | None,
        Field(description="URL o referencia de origen. Va al front-matter."),
    ] = None,
) -> dict:
    """Guarda info nueva en la bóveda.

    Flujo automático:
      1. Plonk del contenido crudo en `raw/seed/<slug>.md` (inmutable).
      2. Dispara al bibliotecario Gemini, que reorganiza `wiki/` para reflejar
         la nueva fuente: crea/actualiza páginas, mantiene cross-references.

    Si Gemini falla (sin red, sin API key), el archivo crudo igual queda
    guardado — raw es la verdad, wiki es una vista derivada.
    """
    raw_path = vault.add_to_raw(content, slug=slug, title=title, source=source)
    vault.append_log(
        "ingest",
        f"save_info {raw_path}",
        body=f"- archivo: {raw_path}\n- source: {source or '(no especificado)'}",
    )

    response: dict = {"saved_at": raw_path}

    try:
        plan, result = gemini_agent.reorganize(dry_run=False)
        response["gemini_summary"] = plan.summary
        response["operations_applied"] = result.applied
        if result.errors:
            response["gemini_errors"] = result.errors
    except Exception as e:
        response["gemini_error"] = (
            f"El bibliotecario falló: {e}. La fuente quedó guardada en raw/, pero wiki/ no se actualizó. "
            "Podés reintentar después corrigiendo el problema (ej. API key)."
        )

    return response


# ──────────────────────────────────────────────────────────────────────────────
# Resources
# ──────────────────────────────────────────────────────────────────────────────


@mcp.resource("vault://index")
def res_index() -> str:
    """wiki/index.md — el catálogo de la bóveda."""
    return vault.read_index()


@mcp.resource("vault://log")
def res_log() -> str:
    """log.md — bitácora completa."""
    return vault.read_log(n=0)


@mcp.resource("vault://claude")
def res_claude() -> str:
    """CLAUDE.md — el schema vivo."""
    return vault.read_claude_md()


@mcp.resource("vault://page/{category}/{slug}")
def res_page(category: str, slug: str) -> str:
    """Una página específica de wiki/<category>/<slug>.md."""
    return vault.read_page(f"wiki/{category}/{slug}.md")


# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────


def run_server() -> None:
    """Arranca el server con stdio transport (modo local, para Claude Code)."""
    mcp.run(transport="stdio")


def main() -> None:
    """Entry point del package. Despacha a CLI (init) o al server (default)."""
    from .cli import main as cli_main

    raise SystemExit(cli_main())


if __name__ == "__main__":
    main()
