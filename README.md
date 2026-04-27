# the-truth-mcp

> Una bóveda LLM Wiki estilo Karpathy, gestionada por un MCP local.
> **Claude consulta y guarda. Gemini ordena. El humano decide qué entra.**

Inspirado en [el patrón LLM Wiki de Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): en lugar de hacer RAG sobre chunks crudos en una vector DB, mantenés una bóveda markdown estructurada que **un agente reorganiza activamente**. El conocimiento *compounded* en lugar de re-descubrirse en cada query.

## Arquitectura

```
Claude (cliente) ──save_info──▶ MCP ──▶ raw/        (plonk crudo, inmutable)
                                  │
                                  └──Gemini API──▶ wiki/  (Gemini ordena, automático)

Claude (cliente) ──vault_search/read_page──▶ MCP ──▶ wiki/  (solo lectura)
```

**Reparto de responsabilidades estricto**:

- **Claude** (vos, vía Claude Code): solo **consulta** y **guarda info cruda**. Nunca escribe en `wiki/`.
- **MCP `the-truth`**: dueño del filesystem. Una sola tool de escritura (`save_info`).
- **Gemini** (dentro del MCP): dueño exclusivo de `wiki/`. En cada `save_info`, lee toda la bóveda y reorganiza — crea, actualiza, fusiona, divide páginas, mantiene cross-references. No interviene en consultas.

## Quickstart

Necesitás [`uv`](https://docs.astral.sh/uv/getting-started/installation/) y [Claude Code](https://claude.com/claude-code).

```bash
# 1. Clonar e instalar
git clone https://github.com/guilleheizen/the-truth-mcp.git
cd the-truth-mcp
uv sync

# 2. Crear una bóveda nueva en cualquier ruta
uv run the-truth-mcp init ~/Documents/my-vault

# 3. Sacar una API key de Gemini (free tier)
#    https://aistudio.google.com/apikey
export GEMINI_API_KEY=tu-key

# 4. Abrir la bóveda con Claude Code
cd ~/Documents/my-vault
claude
```

Claude Code detecta el `.mcp.json` y te pregunta si querés cargar el MCP `the-truth`. Decí que sí. Probalo:

```
/ingest https://karpathy.medium.com/software-2-0-a64152b37c35
/query qué dice Karpathy sobre Software 2.0
```

## Cómo es el flujo

### Guardar info nueva (`/ingest <fuente>`)

1. Claude fetchea la fuente (URL, PDF, texto).
2. Llama a la tool `save_info` del MCP.
3. El MCP guarda el contenido crudo en `raw/seed/<slug>.md` (inmutable).
4. El MCP dispara automáticamente al **bibliotecario Gemini**, que:
   - Lee `CLAUDE.md` (el schema), todas las fuentes en `raw/`, y el estado actual de `wiki/`.
   - Decide qué páginas crear, actualizar, fusionar, dividir, o linkear.
   - Aplica los cambios sobre `wiki/`.
5. El log en `log.md` queda con la entrada.

### Consultar (`/query <pregunta>`)

1. Claude busca con `vault_search` y lee páginas con `vault_read_page`.
2. Sintetiza una respuesta citando rutas de `wiki/...` y `raw/...`.
3. Gemini **no interviene** — la lectura es directa contra el filesystem.

## Tools y Resources que expone el MCP

**Tools**:

| Tool | Descripción |
|---|---|
| `vault_search(query, limit?)` | Grep en `wiki/`. Devuelve archivo + línea. |
| `vault_read_page(slug_or_path)` | Contenido completo de una página. |
| `vault_list_pages(category?)` | Lista por categoría (`conceptos`, `personas`, `papers`). |
| `save_info(content, title?, slug?, source?)` | Guarda crudo + dispara Gemini. |

**Resources** (lectura via `@`-mention en Claude Code):

- `vault://index` — el catálogo
- `vault://log` — la bitácora completa
- `vault://claude` — el `CLAUDE.md` (schema vivo)
- `vault://page/{category}/{slug}` — cualquier página

## Configuración (env vars)

| Variable | Obligatoria | Descripción |
|---|---|---|
| `LLM_WIKI_PATH` | sí | Path absoluto a la bóveda. El `init` lo deja preconfigurado en el `.mcp.json` del vault. |
| `GEMINI_API_KEY` | sí (para `save_info`) | API key de [Google AI Studio](https://aistudio.google.com/apikey). Tier gratis alcanza para uso personal. |
| `GEMINI_MODEL` | no | Default `gemini-2.5-flash`. Opciones: `gemini-2.5-pro` (más caro, mejor razonamiento). |

Las podés definir en tu shell (`export`), en un `.env` del repo del MCP, o directamente en el bloque `env` del `.mcp.json` del vault.

## Estructura del vault (lo que `init` te crea)

```
my-vault/
├── CLAUDE.md                    ← schema vivo (Claude + Gemini lo leen)
├── .mcp.json                    ← registra the-truth para esta bóveda
├── .claude/
│   ├── settings.json            ← permissions + hooks
│   ├── commands/{ingest,query}.md
│   └── skills/markdown-cleaner/SKILL.md
├── raw/
│   ├── seed/                    ← fuentes ingestadas (inmutables)
│   └── pending/                 ← fuentes a procesar manualmente
├── wiki/                        ← mantenido por Gemini
│   ├── index.md
│   ├── conceptos/
│   ├── personas/
│   └── papers/
└── log.md                       ← bitácora append-only
```

## Por qué Gemini y no Claude para reorganizar

- **Context de 1M tokens**: Gemini lee la bóveda completa en una sola request. Claude tendría que paginar.
- **Económico**: Gemini Flash es muy barato — el `save_info` se puede llamar seguido sin pánico de quemar tokens de Claude.
- **Separación de roles**: Claude es el lector que cita; Gemini es el bibliotecario que ordena. El humano arbitra.

Si más adelante querés cambiarlo (Claude haciendo todo, otro modelo, modelo local), está aislado en `gemini_agent.py`.

## Desarrollo

```bash
uv sync                           # instalar deps
uv run the-truth-mcp run          # arrancar el server (stdio)
uv run python -m the_truth_mcp.server  # equivalente
```

Estructura del paquete:

```
src/the_truth_mcp/
├── server.py            ← FastMCP: tools + resources
├── vault.py             ← I/O sobre el filesystem (sin LLM)
├── gemini_agent.py      ← bibliotecario Gemini (one-shot, JSON estructurado)
├── schemas.py           ← Pydantic: Plan + 7 tipos de Operation
├── cli.py               ← `init` y dispatch
└── vault_starter/       ← template del vault que usa `init`
```

## Limitaciones conocidas

- **Sin retry automático**: si Gemini falla durante `save_info`, el archivo crudo igual queda guardado en `raw/`. La fuente no se pierde, pero `wiki/` no se actualiza hasta que llamés `save_info` nuevamente con otra fuente (o agregues una tool de retry — PRs welcome).
- **One-shot, no agent loop**: Gemini emite un único Plan estructurado por invocación. No hace múltiples pasadas. Para bóvedas muy grandes esto puede ser limitante.
- **No hay merge inteligente del log**: `log.md` es append-only, nunca se compacta.

## License

MIT. Ver [LICENSE](LICENSE).
