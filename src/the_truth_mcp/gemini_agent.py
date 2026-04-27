"""El bibliotecario Gemini.

Entrada: el estado actual de la bóveda (CLAUDE.md + raw/* + wiki/**).
Salida: un Plan estructurado con operaciones a aplicar sobre wiki/.

Diseño deliberado de un solo turno (no agent loop): cargamos todo el contexto
en un prompt, Gemini responde con JSON validado contra Pydantic, el server
del MCP aplica el plan vía vault.py.

Por qué Gemini y no Claude:
- Context de 1M tokens permite mandar la bóveda entera en una sola request.
- Flash es muy barato — el reorganize se puede correr seguido sin pánico.
- Separación de responsabilidades narrativa: Claude lee, Gemini ordena.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from . import vault
from .schemas import ApplyResult, Plan


SYSTEM_INSTRUCTION = """\
Sos el "bibliotecario" de una bóveda LLM Wiki estilo Karpathy. Tu trabajo es
mantener la carpeta `wiki/` ordenada, consistente y bien interconectada, contra
las fuentes en `raw/`.

Recibís en cada request:
1. El schema vivo de la bóveda (`CLAUDE.md`) — fuente de verdad sobre las
   convenciones que el usuario quiere para SU dominio.
2. El listado completo de páginas en `wiki/` con su contenido.
3. El listado de fuentes en `raw/` con su contenido.
4. El listado de fuentes "pendientes" — están en raw/ pero ningún archivo de wiki/
   las menciona en su front-matter `sources:`. Son tu prioridad.

Devolvés un Plan JSON estructurado con operaciones discretas. Cada operación
incluye un `rationale` explicando por qué la proponés.

VOS DECIDÍS LA ESTRUCTURA. La bóveda no impone categorías. Observá el contenido
de las fuentes y decidí cómo organizar `wiki/`:
- Podés usar subcarpetas (`wiki/concepto-x/`, `wiki/persona-y/`) o no.
- Podés crear el `type` que tenga sentido para el dominio, o no usar `type`.
- Si el `CLAUDE.md` define convenciones específicas (sección "Convenciones de mi
  dominio" u otras), respetalas.
- Si el `CLAUDE.md` está vacío en ese aspecto, aplicá tu mejor criterio: leé qué
  tipo de info entró y proponé una taxonomía que escale.

Reglas duras (estas no se negocian):
- NUNCA proponer operaciones sobre `raw/`. Solo `wiki/`.
- NUNCA inventar slugs o paths. Si referenciás una página, tiene que existir
  o estar siendo creada en el mismo plan.
- Wikilinks `[[slug-en-kebab-case]]`. Sin tildes, sin espacios.
- Nombres de archivo: kebab-case ASCII, terminan en `.md`.
- Citas a `raw/` al final del párrafo factual: `(raw/foo.md)`.
- Al menos 1 wikilink por página (excepto si la bóveda tiene 1 sola página).
- Front-matter mínimo en cada `create_page` o `update_page`: `title`, `created`
  (YYYY-MM-DD), `updated`, `sources`, `related`. Podés agregar más campos si
  el dominio lo pide o si el `CLAUDE.md` los define.
- Si un raw está pendiente, prioridad #1: crear las páginas que reflejen su contenido.
- Si encontrás info duplicada o contradictoria entre páginas, proponé `merge_pages`.
- Sé conservador: mejor 5 operaciones bien justificadas que 30 ruidosas.

Tu output debe ser JSON válido conforme al schema Plan que te proveen.
"""


def _build_user_prompt() -> str:
    """Empaqueta el estado completo de la bóveda como un solo string.

    Esto cabe holgado en el context de Gemini 2.5 Flash (1M tokens).
    """
    parts: list[str] = []

    parts.append(f"# Fecha de hoy\n\n{date.today().isoformat()}\n\n")
    parts.append(
        "Usá esta fecha para los campos `created` y `updated` del front-matter "
        "de páginas que crees ahora. NO inventes fechas.\n"
    )

    parts.append("# CLAUDE.md (schema vivo)\n")
    try:
        parts.append("```markdown\n" + vault.read_claude_md() + "\n```\n")
    except FileNotFoundError:
        parts.append("_(CLAUDE.md no encontrado — operá con convenciones por defecto)_\n")

    status = vault.vault_status()
    parts.append(f"\n# Estado actual\n```json\n{json.dumps(status, indent=2, ensure_ascii=False)}\n```\n")

    # raw/
    parts.append("\n# raw/ — fuentes inmutables\n")
    root = vault.vault_root()
    raw_files = vault.list_raw()
    if not raw_files:
        parts.append("_(vacío)_\n")
    for rel in raw_files:
        content = (root / rel).read_text(encoding="utf-8")
        is_pending = rel in status["raw_pending"]  # type: ignore[operator]
        flag = " ⚠ PENDIENTE" if is_pending else ""
        parts.append(f"\n## `{rel}`{flag}\n\n```markdown\n{content}\n```\n")

    # wiki/
    parts.append("\n# wiki/ — estado actual de las páginas\n")
    pages = vault.list_pages()
    if not pages:
        parts.append("_(vacío — bóveda nueva)_\n")
    for rel in pages:
        content = (root / rel).read_text(encoding="utf-8")
        parts.append(f"\n## `{rel}`\n\n```markdown\n{content}\n```\n")

    # index.md (lo trato aparte)
    try:
        idx = vault.read_index()
        parts.append(f"\n## `wiki/index.md`\n\n```markdown\n{idx}\n```\n")
    except FileNotFoundError:
        pass

    parts.append(
        "\n---\n\n"
        "Devolvé el Plan. Si la bóveda está perfecta, devolvé un plan con "
        "`operations: []` y un `summary` explicando por qué no hay nada que hacer.\n"
    )

    return "".join(parts)


_API_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_APIKEY", "GOOGLE_GENAI_API_KEY")


def _client() -> genai.Client:
    api_key = next((os.environ[v] for v in _API_KEY_VARS if os.environ.get(v)), None)
    if not api_key:
        raise RuntimeError(
            "No encuentro la API key de Gemini. Definí una de estas variables "
            f"de entorno: {', '.join(_API_KEY_VARS)}.\n"
            "Sacá una key gratis en https://aistudio.google.com/apikey "
            "y exportala (`export GEMINI_API_KEY=...`) o agregala a un .env "
            "en la raíz de tu vault o del proyecto MCP."
        )
    return genai.Client(api_key=api_key)


def _models() -> list[str]:
    """Lista priorizada de modelos a intentar — primero el configurado, después fallbacks.

    El usuario puede pasar `GEMINI_MODEL=foo,bar` para fijar fallbacks explícitos.
    Si pasa solo un modelo, agregamos los fallbacks razonables (dedupeando).
    """
    configured = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    primary = [m.strip() for m in configured.split(",") if m.strip()]
    fallbacks = ["gemini-2.5-flash", "gemini-2.5-pro"]
    out: list[str] = []
    for m in primary + fallbacks:
        if m not in out:
            out.append(m)
    return out


# Errores transitorios que justifican reintento (sobrecarga, rate limit, server hiccup).
_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return exc.code in _TRANSIENT_STATUSES
    return False


def _generate_with_fallback(client: genai.Client, prompt: str) -> tuple[str, str]:
    """Intenta generate_content con cada modelo y reintentos. Devuelve (modelo_que_funcionó, texto).

    Estrategia: por cada modelo, hasta 3 intentos con backoff (2s, 8s, 30s).
    Si los 3 fallan con error transitorio, pasa al siguiente modelo.
    Si fallan TODOS los modelos, levanta la última excepción.
    """
    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=Plan,
        temperature=0.2,
    )
    backoffs = [2, 8, 30]
    last_exc: BaseException | None = None

    for model in _models():
        for delay in backoffs:
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt, config=config
                )
                return model, response.text or ""
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not _is_transient(exc):
                    # Error no transitorio → fallar inmediato, no tiene sentido reintentar.
                    raise
                time.sleep(delay)
        # Todos los retries de este modelo fallaron — pasar al siguiente.

    assert last_exc is not None
    raise last_exc


def propose_plan() -> tuple[str, Plan]:
    """Llama a Gemini y devuelve (modelo_usado, Plan). No aplica nada."""
    client = _client()
    user_prompt = _build_user_prompt()
    model_used, text = _generate_with_fallback(client, user_prompt)
    return model_used, Plan.model_validate_json(text)


def reorganize(*, dry_run: bool = False) -> tuple[Plan, ApplyResult]:
    """Pide un plan a Gemini y lo aplica salvo dry_run.

    Logea siempre la operación al log.md, sea dry_run o no.
    """
    model_used, plan = propose_plan()
    result = ApplyResult(dry_run=dry_run)

    if dry_run:
        for op in plan.operations:
            result.applied.append(f"[DRY] {op.type}: {_op_summary(op)}")
    else:
        for op in plan.operations:
            try:
                msg = vault.apply_operation(op)
                result.applied.append(msg)
            except (FileExistsError, FileNotFoundError, ValueError) as e:
                result.errors.append(f"{op.type}: {e}")

    title = plan.summary.split("\n")[0][:80] if plan.summary else "reorganize"
    body_lines = [
        f"- modelo: {model_used}",
        f"- dry_run: {dry_run}",
        f"- operaciones propuestas: {len(plan.operations)}",
        f"- aplicadas: {len(result.applied)}",
        f"- errores: {len(result.errors)}",
    ]
    vault.append_log("reorganize", title, body="\n".join(body_lines))

    return plan, result


def _op_summary(op) -> str:
    """Una línea descriptiva por operación, para mostrar en dry-run."""
    t = op.type
    if t in ("create_page", "update_page", "delete_page"):
        return f"{op.path}"
    if t == "rename_page":
        return f"{op.from_path} → {op.to_path}"
    if t == "merge_pages":
        return f"{op.from_paths} → {op.into_path}"
    if t == "split_page":
        return f"{op.from_path} → {[p.path for p in op.new_pages]}"
    if t == "add_link":
        return f"{op.in_path} ← [[{op.target_slug}]]"
    return repr(op)
