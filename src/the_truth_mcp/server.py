"""MCP server: the-truth-mcp.

Local-only, transport stdio. Configurable por env vars:
  - GEMINI_API_KEY   (obligatoria — el bibliotecario corre con cada save_info)
  - VAULT_PATH       (obligatoria — path absoluto a la bóveda; alias: LLM_WIKI_PATH)
  - GEMINI_MODEL     (opcional, default gemini-2.5-flash)

Diseño minimalista: el agente cliente (Claude Code, Cursor, ChatGPT, etc.)
solo puede hacer dos cosas — consultar y guardar. El "guardar" dispara
automáticamente al bibliotecario Gemini, que ordena la bóveda. La complejidad
queda dentro del MCP.

Tools (4):
  - vault_search       leer: grep en wiki/
  - vault_read_page    leer: contenido de una página
  - vault_list_pages   leer: catálogo
  - save_info          escribir: plonk en raw/ + Gemini reorganiza wiki/

Resources:
  - vault://index, vault://log, vault://agents
  - vault://page/{category}/{slug}
"""

from __future__ import annotations

from typing import Annotated

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# Carga .env desde varios lugares razonables (en orden de prioridad descendente).
# Si una variable ya está en el environment, no se pisa: el shell siempre gana.
# Orden:
#   1. cwd y ancestros           (proyecto local)
#   2. <vault>/.env              (config por bóveda)
#   3. ~/.config/the-truth-mcp/.env  (config global del usuario — donde install
#      escribe la API key para que la herramienta sea ready-to-work sin
#      depender de cómo se lance el cliente MCP)
load_dotenv()
_vault_path = os.environ.get("VAULT_PATH") or os.environ.get("LLM_WIKI_PATH")
if _vault_path:
    load_dotenv(Path(_vault_path).expanduser() / ".env", override=False)
load_dotenv(Path.home() / ".config" / "the-truth-mcp" / ".env", override=False)

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
    defer_groom: Annotated[
        bool,
        Field(
            description=(
                "Si True, NO dispara a Gemini — solo escribe el archivo crudo en raw/ y "
                "vuelve casi instantáneo (<100ms). El wiki/ NO se actualiza hasta que "
                "alguien llame `vault_groom`. Usalo cuando vas a guardar varios docs "
                "seguidos: groom una sola vez al final del batch es mucho más barato "
                "y eficiente que groom por cada save. Default: False (groom inmediato)."
            )
        ),
    ] = False,
) -> dict:
    """Guarda una fuente nueva en la bóveda.

    Por default hace dos cosas en una llamada:
      1. Plonk del contenido crudo en `raw/<slug>.md` (inmutable, append-only).
      2. Dispara a Gemini para que reorganice `wiki/` y absorba la nueva fuente.

    El paso 2 es lento (~10–30s). Si vas a guardar varias cosas seguidas, pasá
    `defer_groom=True` y llamá `vault_groom` al final — Gemini procesa todos
    los pendientes de una sola vez, ahorrando tiempo y cuota de API.

    Si Gemini falla (sin red, key vencida, 503), el archivo crudo igual queda
    guardado: `raw/` es la verdad, `wiki/` es una vista derivada que se puede
    regenerar cuando vuelvas a tener red corriendo `vault_groom`.

    Returns: dict con
      - `saved_at`: ruta relativa al archivo en raw/.
      - `gemini_summary` + `operations_applied`: si NO se deferreó.
      - `deferred`: True si se deferreó (sin tocar wiki/).
      - `gemini_error`: string si Gemini falló (la fuente igual quedó en raw/).
      - `error`: string si no se pudo adquirir el lock del vault en 60s.
    """
    try:
        with vault.vault_lock():
            raw_path = vault.add_to_raw(content, slug=slug, title=title, source=source)
            vault.append_log(
                "ingest",
                f"save_info {raw_path}",
                body=(
                    f"- archivo: {raw_path}\n"
                    f"- source: {source or '(no especificado)'}\n"
                    f"- defer_groom: {defer_groom}"
                ),
            )

            response: dict = {"saved_at": raw_path}

            if defer_groom:
                response["deferred"] = True
                response["hint"] = (
                    "wiki/ no se actualizó. Llamá `vault_groom` cuando termines el batch."
                )
                return response

            try:
                plan, result = gemini_agent.reorganize(dry_run=False)
                response["gemini_summary"] = plan.summary
                response["operations_applied"] = result.applied
                if result.errors:
                    response["gemini_errors"] = result.errors
            except Exception as e:
                response["gemini_error"] = (
                    f"El bibliotecario falló: {e}. La fuente quedó guardada en raw/, pero wiki/ no se actualizó. "
                    "Podés reintentar después corriendo `vault_groom` (ej. cuando vuelvas a tener red o renueves la API key)."
                )

            return response
    except TimeoutError as e:
        return {"error": str(e)}


@mcp.tool()
def vault_groom() -> dict:
    """Pide a Gemini que reorganice `wiki/` ahora.

    Cuándo usar esta tool:
      - Después de un batch de `save_info(defer_groom=True)`: Gemini absorbe
        todos los raws pendientes de una sola pasada (mucho más eficiente que
        groom por save).
      - Cuando editaste `AGENTS.md` y querés que Gemini relea las convenciones
        y aplique cambios estructurales al wiki/ existente.
      - Como tarea programada (cron / launchd / GitHub Action) corriendo
        `the-truth-mcp groom <vault>` cada N horas.

    Cuándo NO usar:
      - No hace falta llamarla después de un `save_info` con default
        (`defer_groom=False`) — ese ya hizo el groom.
      - Si `vault_status` muestra `raw_pending: []` y no editaste `AGENTS.md`,
        groomear de nuevo es desperdicio de tokens.

    Es lock-protegido: si otro `save_info` o `vault_groom` está corriendo,
    espera hasta 60s y después devuelve `error`.

    Returns: dict con
      - `summary`: resumen humano del plan que ejecutó Gemini.
      - `operations_applied`: lista de operaciones aplicadas (ej.
        `"created wiki/foo.md"`, `"merged [a,b] → c"`). Vacía si no hubo nada
        que hacer.
      - `errors`: errores no fatales por operación (si los hubo).
      - `error`: string si no se pudo adquirir el lock o Gemini falló.
    """
    try:
        with vault.vault_lock():
            try:
                plan, result = gemini_agent.reorganize(dry_run=False)
            except Exception as e:
                return {
                    "error": (
                        f"El bibliotecario falló: {e}. La bóveda no se modificó. "
                        "Reintentá cuando vuelvas a tener red o renueves la API key."
                    )
                }
            response: dict = {
                "summary": plan.summary,
                "operations_applied": result.applied,
            }
            if result.errors:
                response["errors"] = result.errors
            return response
    except TimeoutError as e:
        return {"error": str(e)}


@mcp.tool()
def vault_status() -> dict:
    """Snapshot del estado de la bóveda. Útil para decidir si correr `vault_groom`.

    Returns: dict con
      - `vault_root`: path absoluto de la bóveda.
      - `wiki_pages`: cantidad de páginas en wiki/ (excluye index.md).
      - `raw_total`: cantidad total de fuentes en raw/.
      - `raw_pending`: lista de paths de raws que TODAVÍA NO están referenciados
        en el campo `sources:` de ninguna página de wiki/. Si tiene elementos,
        hay material para procesar — llamá `vault_groom`.
      - `raw_processed`: cantidad de raws ya integrados al wiki/.
      - `last_groom`: timestamp ISO-8601 UTC del último groom exitoso, o `null`
        si nunca corrió (vault recién creado).
    """
    return vault.vault_status()


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


@mcp.resource("vault://agents")
def res_agents() -> str:
    """AGENTS.md — el schema vivo de la bóveda."""
    return vault.read_agents_md()


@mcp.resource("vault://page/{category}/{slug}")
def res_page(category: str, slug: str) -> str:
    """Una página específica de wiki/<category>/<slug>.md."""
    return vault.read_page(f"wiki/{category}/{slug}.md")


# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────


def run_server() -> None:
    """Arranca el server con stdio transport (modo local, lo levanta el cliente MCP)."""
    mcp.run(transport="stdio")


def main() -> None:
    """Entry point del package. Despacha a CLI (init) o al server (default)."""
    from .cli import main as cli_main

    raise SystemExit(cli_main())


if __name__ == "__main__":
    main()
