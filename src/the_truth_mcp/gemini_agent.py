"""El bibliotecario Gemini.

Entrada: el estado actual de la bóveda (AGENTS.md + raw/* + wiki/**).
Salida: un Plan estructurado con operaciones a aplicar sobre wiki/.

Diseño deliberado de un solo turno (no agent loop): cargamos todo el contexto
en un prompt, Gemini responde con JSON validado contra Pydantic, el server
del MCP aplica el plan vía vault.py.

Por qué Gemini para esta tarea:
- Context de 1M tokens permite mandar la bóveda entera en una sola request.
- Flash es muy barato — el reorganize se puede correr seguido sin pánico.
- Separación de responsabilidades: el cliente MCP solo consulta y guarda crudo;
  Gemini, dentro del server, es el único que escribe en wiki/.
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
from pydantic import BaseModel, ValidationError

from . import vault
from .schemas import Answer, ApplyResult, FindResults, Plan


SYSTEM_INSTRUCTION = """\
Sos el "bibliotecario" de una bóveda LLM Wiki estilo Karpathy. Tu trabajo es
mantener la carpeta `wiki/` ordenada, consistente y bien interconectada, contra
las fuentes en `raw/`.

Recibís en cada request:
1. El schema vivo de la bóveda (`AGENTS.md`) — fuente de verdad sobre las
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
- Si el `AGENTS.md` define convenciones específicas (sección "Convenciones de mi
  dominio" u otras), respetalas.
- Si el `AGENTS.md` está vacío en ese aspecto, aplicá tu mejor criterio: leé qué
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
  el dominio lo pide o si el `AGENTS.md` los define.
- Si un raw está pendiente, prioridad #1: crear las páginas que reflejen su contenido.
- Si encontrás info duplicada o contradictoria entre páginas, proponé `merge_pages`.
- Sé conservador: mejor 5 operaciones bien justificadas que 30 ruidosas.
- Páginas con `pinned: true` en su front-matter están protegidas: no proponer
  operaciones `update_page`, `delete_page`, `rename_page`, `merge_pages` ni
  `split_page` sobre ellas. Solo `add_link` está permitido.

Tu output debe ser JSON válido conforme al schema Plan que te proveen.
"""


ANSWER_SYSTEM_INSTRUCTION = """\
Sos un asistente que responde preguntas sobre el contenido de una bóveda
LLM Wiki. Respondé con citas. Si no hay información suficiente en la bóveda,
decilo explícitamente y sugerí qué guardar (qué fuente faltaría) en lugar de
inventar.

Citas: cada cita debe ser un path relativo (ej. `wiki/conceptos/foo.md`).
Confianza: `high` si la respuesta sale literal de las páginas; `medium` si
tuviste que inferir desde varias páginas; `low` si la bóveda no cubre bien la
pregunta.
"""


FIND_SYSTEM_INSTRUCTION = """\
Sos un buscador semántico sobre una bóveda LLM Wiki. Dado un query, devolvé
las top-K páginas más relevantes con un puntaje 0..1 y una breve explicación
de por qué son relevantes. Trabajás solo con metadata (path, title, summary)
de las páginas — no tenés el contenido completo, así que basate en eso.
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

    parts.append("# AGENTS.md (schema vivo)\n")
    try:
        parts.append("```markdown\n" + vault.read_agents_md() + "\n```\n")
    except FileNotFoundError:
        parts.append("_(AGENTS.md no encontrado — operá con convenciones por defecto)_\n")

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
            "Sacá una key gratis en https://aistudio.google.com/apikey y dejala "
            "disponible de alguna de estas formas:\n"
            "  • exportala en tu shell rc (`export GEMINI_API_KEY=...`)\n"
            "  • corré `the-truth-mcp install --vault <path> --key ...` para "
            "guardarla en ~/.config/the-truth-mcp/.env\n"
            "  • agregala a un .env en la raíz de tu vault"
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


def _generate_with_fallback(
    client: genai.Client,
    prompt: str,
    *,
    system_instruction: str = SYSTEM_INSTRUCTION,
    response_schema: type[BaseModel] = Plan,
    temperature: float = 0.2,
) -> tuple[str, str]:
    """Intenta generate_content con cada modelo y reintentos. Devuelve (modelo_que_funcionó, texto).

    Estrategia: por cada modelo, hasta 3 intentos con backoff (2s, 8s, 30s).
    Si los 3 fallan con error transitorio, pasa al siguiente modelo.
    Si fallan TODOS los modelos, levanta la última excepción.
    """
    config = genai_types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
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


# ──────────────────────────────────────────────────────────────────────────────
# Q&A: vault_answer
# ──────────────────────────────────────────────────────────────────────────────


def _build_answer_prompt(question: str) -> str:
    """Empaqueta la pregunta + el wiki entero + listado de raws (sin contenido).

    Los raws van por path solamente: para responder, lo importante es saber qué
    fuentes existen (por si hace falta sugerir leer una en particular). Mandar
    todo el contenido de raws explotaría el prompt sin aportar mucho.
    """
    parts: list[str] = []
    parts.append(f"# Pregunta\n\n{question}\n\n")

    parts.append("# wiki/ — contenido completo\n")
    root = vault.vault_root()
    pages = vault.list_pages()
    if not pages:
        parts.append("_(vacío)_\n")
    for rel in pages:
        try:
            content = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        parts.append(f"\n## `{rel}`\n\n```markdown\n{content}\n```\n")

    parts.append("\n# raw/ — fuentes disponibles (solo paths)\n")
    raw_files = vault.list_raw()
    if not raw_files:
        parts.append("_(vacío)_\n")
    else:
        for rel in raw_files:
            parts.append(f"- {rel}\n")

    parts.append(
        "\n---\n\nRespondé la pregunta con el schema Answer. Citá los paths de "
        "las páginas que usaste. Si la bóveda no tiene info suficiente, "
        "decilo y sugerí qué guardar.\n"
    )
    return "".join(parts)


def answer_question(question: str) -> tuple[str, Answer]:
    """Pregunta sobre la bóveda. Devuelve (modelo_usado, Answer)."""
    client = _client()
    prompt = _build_answer_prompt(question)
    model_used, text = _generate_with_fallback(
        client,
        prompt,
        system_instruction=ANSWER_SYSTEM_INSTRUCTION,
        response_schema=Answer,
        temperature=0.3,
    )
    return model_used, Answer.model_validate_json(text)


# ──────────────────────────────────────────────────────────────────────────────
# Búsqueda semántica: vault_find
# ──────────────────────────────────────────────────────────────────────────────


def _build_find_prompt(query: str, k: int) -> str:
    """Listado de páginas (path/title/summary) + query. Sin contenido completo."""
    parts: list[str] = []
    parts.append(f"# Query\n\n{query}\n\n")
    parts.append(f"# Top-K solicitado\n\n{k}\n\n")
    parts.append("# Páginas disponibles\n\n")
    detailed = vault.list_pages_detailed()
    if not detailed:
        parts.append("_(la bóveda no tiene páginas)_\n")
    for d in detailed:
        title = d.get("title") or "(sin título)"
        summary = d.get("summary") or "(sin resumen)"
        parts.append(f"- path: `{d['path']}` | title: {title} | summary: {summary}\n")
    parts.append(
        f"\n---\n\nDevolvé las top {k} páginas más relevantes para el query. "
        "Cada resultado: slug (sin extensión), path, why_relevant (1 frase), "
        "score 0..1.\n"
    )
    return "".join(parts)


def find_pages(query: str, k: int = 5) -> tuple[str, FindResults]:
    """Búsqueda semántica via Gemini. Devuelve (modelo_usado, FindResults)."""
    client = _client()
    prompt = _build_find_prompt(query, k)
    model_used, text = _generate_with_fallback(
        client,
        prompt,
        system_instruction=FIND_SYSTEM_INSTRUCTION,
        response_schema=FindResults,
        temperature=0.2,
    )
    results = FindResults.model_validate_json(text)
    # Truncar al k pedido por si el modelo se pasó.
    results.results = results.results[:k]
    return model_used, results


# ──────────────────────────────────────────────────────────────────────────────
# Clasificación de errores estructurada
# ──────────────────────────────────────────────────────────────────────────────


def _classify_error(exc: BaseException) -> dict:
    """Clasifica una excepción de Gemini/Pydantic a un dict estructurado.

    Devuelve `{type, message, retry_after}`. `type` es uno de:
    `rate_limit`, `auth`, `transient`, `schema`, `unknown`. `retry_after` es
    segundos sugeridos antes de reintentar (o None si no aplica).
    """
    if isinstance(exc, genai_errors.APIError):
        code = exc.code
        msg = str(exc)
        if code == 429:
            return {"type": "rate_limit", "message": msg, "retry_after": 60}
        if code in (401, 403):
            return {"type": "auth", "message": msg, "retry_after": None}
        if code in (500, 502, 503, 504):
            return {"type": "transient", "message": msg, "retry_after": 30}
        return {"type": "unknown", "message": msg, "retry_after": None}
    if isinstance(exc, ValidationError):
        return {"type": "schema", "message": str(exc), "retry_after": None}
    return {"type": "unknown", "message": str(exc), "retry_after": None}


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

    # Stamp del último groom — usado por vault_status() para que el cliente
    # decida si conviene volver a groomear.
    if not dry_run:
        vault.mark_groomed()

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
