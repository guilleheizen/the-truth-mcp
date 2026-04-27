# the-truth-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-compatible-7B68EE.svg)](https://modelcontextprotocol.io/)
[![uvx](https://img.shields.io/badge/uvx-friendly-EF6C00.svg)](https://docs.astral.sh/uv/)

> **Tu segundo cerebro como repo.** Tirás info al MCP. Gemini la organiza. Claude la consulta y la cita.

Un MCP local que convierte una carpeta de markdown en una **bóveda de conocimiento que se ordena sola**, basada en el [patrón LLM Wiki de Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). En lugar de RAG sobre chunks crudos en una vector DB, mantenés un grafo de archivos `.md` interconectados que un agente reorganiza activamente.

---

## Quickstart (un solo comando)

Necesitás [`uv`](https://docs.astral.sh/uv/getting-started/installation/), [Claude Code](https://claude.com/claude-code), y una [API key de Gemini](https://aistudio.google.com/apikey) (tier gratis alcanza).

```bash
uvx --from git+https://github.com/guilleheizen/the-truth-mcp \
    the-truth-mcp install \
      --vault ~/Documents/my-vault \
      --key AIza...your-gemini-key... \
      --model gemini-2.5-flash
```

Eso solo:
1. Crea la bóveda en `~/Documents/my-vault` si no existe (con todos los archivos del template).
2. Registra el MCP en Claude Code a nivel **usuario** (disponible en cualquier proyecto).
3. Pasa la API key y el modelo como env vars del MCP.

Después abrís Claude Code en cualquier folder:

```bash
claude
```

```
/ingest https://karpathy.medium.com/software-2-0-a64152b37c35
/query qué es Software 2.0
```

---

## Cómo funciona

```
Vos (Claude Code)
       │
       ├── /ingest <fuente>  ──save_info──▶  MCP  ──▶  raw/<slug>.md   (plonk crudo, inmutable)
       │                                       │
       │                                       └──Gemini API──▶  wiki/   (Gemini decide la estructura)
       │
       └── /query <pregunta> ──vault_search/read_page──▶  MCP  ──▶  wiki/   (solo lectura)
```

**Tres roles, sin solapamiento**:

| Rol | Quién | Qué hace |
|---|---|---|
| Cliente | Claude (vos) | **Consulta** y **guarda info cruda**. Nunca escribe en `wiki/`. |
| Servidor | MCP `the-truth` | I/O sobre el filesystem. Una sola tool de escritura: `save_info`. |
| Bibliotecario | Gemini (dentro del MCP) | Dueño exclusivo de `wiki/`. Lee toda la bóveda y reorganiza. |

---

## Qué obtenés

Una carpeta así, **mantenida automáticamente** a medida que tirás fuentes:

```
my-vault/
├── AGENTS.md         ← reglas del juego (vos las editás, Gemini las lee)
├── raw/              ← inmutable: cada fuente que entró
│   ├── software-2-0.md
│   ├── attention-paper.md
│   └── …
├── wiki/             ← Gemini lo organiza solo
│   ├── index.md
│   ├── conceptos/    ← (o papers/, o personas/, o lo que Gemini decida)
│   │   ├── software-2-0.md
│   │   └── attention.md
│   └── …
└── log.md            ← bitácora append-only de cada operación
```

**Las páginas de `wiki/` se referencian entre sí** con `[[wikilinks]]` — funciona out-of-the-box con [Obsidian](https://obsidian.md), Logseq, o cualquier editor que entienda el formato.

---

## Arranca limpio, se adapta a tu dominio

La bóveda **no impone categorías**. Gemini observa qué guardás y decide la organización. Si querés guiar la estructura, escribís convenciones en el `AGENTS.md` del vault (hay una sección reservada).

Algunos ejemplos de configuración (ver [`examples/`](examples/) en el repo):

- **Investigación técnica** (default fit): `conceptos/`, `personas/`, `papers/`
- **Producto / equipo**: `features/`, `decisiones/`, `incidentes/`, con `severity` en front-matter
- **Consultoría**: `clientes/`, `proyectos/`, `lecciones-aprendidas/`
- **Aprendizaje personal**: `temas/`, `recursos/`, `dudas/`
- **Cocina**: `recetas/`, `tecnicas/`, `ingredientes/`

Editás el `AGENTS.md`, guardás algo nuevo, y Gemini empieza a respetar la convención. Sin tocar código.

---

## Tools y Resources del MCP

**Tools** (4):

| Tool | Descripción |
|---|---|
| `vault_search(query, limit?)` | Grep en `wiki/`. Devuelve archivo + línea. |
| `vault_read_page(slug_or_path)` | Contenido completo de una página. |
| `vault_list_pages(category?)` | Lista páginas. `category` es subcarpeta de `wiki/` (libre). |
| `save_info(content, title?, slug?, source?)` | Guarda crudo en `raw/` + dispara Gemini. |

**Resources** (lectura via `@`-mention):

- `vault://index` — el catálogo
- `vault://log` — la bitácora completa
- `vault://agents` — el `AGENTS.md` (schema vivo)
- `vault://page/{category}/{slug}` — cualquier página

---

## Configuración

Variables de entorno (cualquiera de estas formas funciona: shell, `.env` del vault, `env` del `.mcp.json`):

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `VAULT_PATH` | sí | — | Path absoluto a la bóveda. `init` ya lo deja en `.mcp.json`. Alias: `LLM_WIKI_PATH`. |
| `GEMINI_API_KEY` | sí (para `save_info`) | — | API key de [Google AI Studio](https://aistudio.google.com/apikey). |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Modelo del bibliotecario. `gemini-2.5-pro` para más calidad. |

Aliases aceptados para la key: `GOOGLE_API_KEY`, `GEMINI_APIKEY`, `GOOGLE_GENAI_API_KEY`.

---

## CLI

```bash
the-truth-mcp                       # arranca el server MCP (stdio) — esto usa Claude Code
the-truth-mcp install --vault <p> --key <k> [--model <m>]
                                    # all-in-one: vault + registro en Claude Code
the-truth-mcp init <path>           # crea una bóveda nueva (sin registrar)
the-truth-mcp doctor [<path>]       # verifica setup (env vars, key, vault, salud de Gemini)
the-truth-mcp --version
```

`install` por defecto usa `--scope user`. Si querés instalarlo solo en un proyecto, pasá `--scope project` (genera `.mcp.json` en cwd) o `--scope local` (solo tu copia local del proyecto).

---

## Por qué Gemini y no Claude para reorganizar

- **Context de 1M tokens**: lee la bóveda completa en una sola request. Claude tendría que paginar.
- **Económico**: Gemini Flash es muy barato — `save_info` se puede llamar seguido sin pánico.
- **Separación de roles**: Claude lee y cita; Gemini es el bibliotecario que ordena. El humano arbitra.

Si querés cambiarlo (Claude haciendo todo, otro modelo, modelo local), está aislado en `src/the_truth_mcp/gemini_agent.py`.

---

## Desarrollo

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para el flujo completo. Quick tour:

```bash
git clone https://github.com/guilleheizen/the-truth-mcp.git
cd the-truth-mcp
uv sync
uv run the-truth-mcp run            # corre el server localmente
```

Estructura:

```
src/the_truth_mcp/
├── server.py        ← FastMCP: tools + resources
├── vault.py         ← I/O sobre el filesystem (sin LLM, testeable)
├── gemini_agent.py  ← bibliotecario Gemini (one-shot, JSON estructurado)
├── schemas.py       ← Pydantic: Plan + 7 tipos de Operation
├── cli.py           ← init, doctor, run
└── vault_starter/   ← template que copia `init`
```

---

## Limitaciones conocidas

- **Sin retry automático**: si Gemini falla durante `save_info`, el crudo queda en `raw/` pero `wiki/` no se actualiza hasta el próximo `save_info`. La info no se pierde.
- **One-shot, no agent loop**: Gemini emite un único Plan por invocación. Para bóvedas muy grandes (>500k tokens de contenido) puede ser limitante.
- **`log.md` no se compacta**: append-only, crece indefinido.

PRs bienvenidos para cualquiera de estos.

---

## License

MIT. Ver [LICENSE](LICENSE).
