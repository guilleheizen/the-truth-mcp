# the-truth-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-compatible-7B68EE.svg)](https://modelcontextprotocol.io/)
[![uvx](https://img.shields.io/badge/uvx-friendly-EF6C00.svg)](https://docs.astral.sh/uv/)

> **Tu segundo cerebro como repo.** Tirás info al MCP. Gemini la organiza. Tu cliente MCP la consulta y la cita.

Un MCP local que convierte una carpeta de markdown en una **bóveda de conocimiento que se ordena sola**, basada en el [patrón LLM Wiki de Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). En lugar de RAG sobre chunks crudos en una vector DB, mantenés un grafo de archivos `.md` interconectados que un agente reorganiza activamente.

El MCP es **agnóstico al cliente**: corre con cualquier herramienta MCP-compatible (Claude Code, Codex CLI, Gemini CLI, Cursor, Claude Desktop, ChatGPT, …). Lo único interno al server es Gemini — el bibliotecario que reorganiza la bóveda.

---

## Quickstart (un solo comando)

Necesitás [`uv`](https://docs.astral.sh/uv/getting-started/installation/), un cliente MCP, y una [API key de Gemini](https://aistudio.google.com/apikey) (tier gratis alcanza).

Elegí el comando según el cliente que uses:

```bash
# Claude Code (Anthropic)
uvx --from git+https://github.com/guilleheizen/the-truth-mcp \
    the-truth-mcp install-claude \
      --vault ~/Documents/my-vault \
      --key AIza...your-gemini-key...

# Codex CLI (OpenAI) — registra en ~/.codex/config.toml
uvx --from git+https://github.com/guilleheizen/the-truth-mcp \
    the-truth-mcp install-codex --vault ~/Documents/my-vault --key AIza...

# Gemini CLI (Google) — registra en ~/.gemini/settings.json
uvx --from git+https://github.com/guilleheizen/the-truth-mcp \
    the-truth-mcp install-gemini --vault ~/Documents/my-vault --key AIza...
```

Cada `install*` hace lo mismo:
1. Crea la bóveda en el path indicado si no existe.
2. Registra el MCP en el archivo de config nativo del cliente correspondiente.
3. Guarda la API key y el modelo en `~/.config/the-truth-mcp/.env` con permisos `600` — **nunca** en el archivo de config del cliente. El secreto vive en un solo lugar y se comparte entre todos los clientes.

### Lo que tenés que ver

```text
→ Bóveda existente detectada en /Users/.../my-vault
→ Usando API key de tu shell ($GEMINI_APIKEY). Modelo guardado en ~/.config/the-truth-mcp/.env.
→ Registrando MCP `the-truth` en Claude Code (scope user)

✓ MCP `the-truth` instalado en claude-code.
  vault:  /Users/.../my-vault
  modelo: gemini-2.5-flash
  scope:  user
  config: ~/.config/the-truth-mcp/.env (key + modelo del bibliotecario)
```

Si ves un `✗` en cualquier paso, corré `the-truth-mcp doctor /Users/.../my-vault` para diagnosticar.

> **Si ya tenés `GEMINI_API_KEY` exportada en tu shell** (zshrc/bashrc), podés omitir `--key`. El server lee primero del entorno y solo cae al `.env` global si no encuentra nada — el shell siempre gana.

Después abrís el cliente apuntando al vault y usás las tools del MCP (`save_info`, `vault_search`, `vault_read_page`, `vault_list_pages`).

---

## Cómo funciona

```
Tu cliente MCP
       │
       ├── save_info(...)         ──▶ MCP ──▶ raw/<slug>.md  (plonk crudo, inmutable)
       │                                │
       │                                └── Gemini API ──▶ wiki/  (Gemini decide la estructura)
       │
       └── vault_search / vault_read_page ──▶ MCP ──▶ wiki/  (solo lectura)
```

**Tres roles, sin solapamiento**:

| Rol | Quién | Qué hace |
|---|---|---|
| Cliente | Cualquier herramienta MCP (vos) | **Consulta** y **guarda info cruda**. Nunca escribe en `wiki/`. |
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

El server resuelve las variables en este orden (la primera que tenga valor gana):

1. **Entorno del proceso** — exports de tu shell (`~/.zshrc`, `~/.bashrc`).
2. **`.env` del cwd** — útil para correr el server desde un repo.
3. **`<vault>/.env`** — config por bóveda.
4. **`~/.config/the-truth-mcp/.env`** — config global del usuario (lo que escribe `install`).

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `VAULT_PATH` | sí | — | Path absoluto a la bóveda. Cada `install*` lo registra en el config del cliente. Alias: `LLM_WIKI_PATH`. |
| `GEMINI_API_KEY` | sí (para `save_info`) | — | API key de [Google AI Studio](https://aistudio.google.com/apikey). |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Modelo del bibliotecario. `gemini-2.5-pro` para más calidad. |

Aliases aceptados para la key: `GOOGLE_API_KEY`, `GEMINI_APIKEY`, `GOOGLE_GENAI_API_KEY`.

### Free tier de Gemini — qué esperar

El [tier gratis de Google AI Studio](https://aistudio.google.com/apikey) tiene rate limits modestos (alrededor de 15 requests por minuto en `gemini-2.5-flash`, con cuota diaria). Para uso normal — guardar 1–2 docs por minuto — alcanza sobrado. Si hacés ráfagas de `save_info` muy seguidas vas a recibir 429s; el server reintenta automáticamente con backoff (2s, 8s, 30s) y cae a `gemini-2.5-pro` como fallback. Si hacés ingestas grandes con frecuencia, considerá pagar el tier de Google AI Studio o cambiar a Vertex AI.

### Por qué la key vive en `~/.config/the-truth-mcp/.env` y no en el config del cliente

Los archivos de config de los clientes MCP (`~/.claude.json`, `~/.codex/config.toml`, `~/.gemini/settings.json`) son archivos que: a) los abren apps GUI sin pasar por tu shell, b) la gente comparte o sube a repos por error, c) no tienen permisos restrictivos. Guardar la API key ahí en texto plano es un footgun. La config global del MCP vive en su propio archivo con `chmod 600`, es cargada solo por el server, y se comparte entre todos los clientes — instalá en tres herramientas distintas y la key sigue en un único lugar.

---

## CLI

```bash
the-truth-mcp                              # arranca el server MCP (stdio) — esto lo invoca el cliente
the-truth-mcp init <path>                  # crea una bóveda nueva (sin registrar)
the-truth-mcp install-claude --vault <p>   # registra en Claude Code (~/.claude.json)
the-truth-mcp install-codex  --vault <p>   # registra en Codex CLI (~/.codex/config.toml)
the-truth-mcp install-gemini --vault <p>   # registra en Gemini CLI (~/.gemini/settings.json)
the-truth-mcp doctor [<path>]              # verifica setup (env vars, key, vault, salud de Gemini)
the-truth-mcp --version
```

Las flags compartidas por los tres `install-*` son: `--vault`, `--key` (opcional si la key ya está en tu shell), `--model`, `--name`, `--local`. El comando `install-claude` acepta además `--scope {user,local,project}` para elegir dónde registrar el MCP en Claude Code.

Podés correr varios `install*` contra la misma bóveda — cada cliente tiene su propio archivo de config y la key se comparte vía `~/.config/the-truth-mcp/.env`.

---

## Por qué Gemini para reorganizar

- **Context de 1M tokens**: lee la bóveda completa en una sola request. Otros modelos tendrían que paginar.
- **Económico**: Gemini Flash es muy barato — `save_info` se puede llamar seguido sin pánico.
- **Separación de roles**: el cliente MCP lee y cita; Gemini es el bibliotecario que ordena. El humano arbitra.

Si querés cambiarlo (otro modelo, modelo local), está aislado en `src/the_truth_mcp/gemini_agent.py`.

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
├── server.py         ← FastMCP: tools + resources
├── vault.py          ← I/O sobre el filesystem (sin LLM, testeable)
├── gemini_agent.py   ← bibliotecario Gemini (one-shot, JSON estructurado)
├── schemas.py        ← Pydantic: Plan + 7 tipos de Operation
├── cli.py            ← init, doctor, run, install*
├── vault_starter/    ← template client-agnostic que copia `init`
└── client_extras/    ← archivos que cada `install-<cliente>` agrega al vault
    └── claude-code/  ← .claude/ (slash commands, permisos, hooks)
```

---

## Limitaciones conocidas

- **Retry limitado**: el server reintenta errores transitorios de Gemini (429/5xx) con backoff (2s, 8s, 30s) y cae a `gemini-2.5-pro` como fallback. Si igual falla — sin red, key vencida — el crudo queda en `raw/` y `wiki/` no se actualiza hasta el próximo `save_info`. La info no se pierde.
- **One-shot, no agent loop**: Gemini emite un único Plan por invocación. Para bóvedas muy grandes (>500k tokens de contenido) puede ser limitante.
- **`log.md` no se compacta**: append-only, crece indefinido.

PRs bienvenidos para cualquiera de estos.

---

## Troubleshooting

### `Gemini responde 503` o `429`

Rate limit o sobrecarga upstream. El server reintenta automáticamente con backoff. Re-corré `save_info` en un minuto. Si persiste, probá `GEMINI_MODEL=gemini-2.5-pro` para pegarle a un modelo menos cargado.

### `No encuentro la API key de Gemini`

El server chequeó los cuatro alias de entorno (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_APIKEY`, `GOOGLE_GENAI_API_KEY`) y no encontró ninguno, y `~/.config/the-truth-mcp/.env` está vacío o no existe. Fix: re-corré `the-truth-mcp install-claude --vault <path> --key <key>`, o `export GEMINI_API_KEY=...` en tu shell rc.

### `El path de la bóveda apunta a un directorio inexistente`

`VAULT_PATH` apunta a una carpeta que no existe. O arreglás el registro (re-corré `install-*`) o `mkdir -p` el path a mano. Corré `the-truth-mcp doctor <path>` para diagnosticar.

### `AGENTS.md no encontrado en <path>`

A la bóveda le falta su archivo de schema. O apuntás `VAULT_PATH` a una carpeta creada con `the-truth-mcp init`, o copiás un template de `AGENTS.md` a mano (ver `src/the_truth_mcp/vault_starter/AGENTS.md`).

### El MCP aparece pero las tools no responden

El server arrancó pero algo en su startup falló silenciosamente (típico: env vars mal cargadas cuando lanzaste el cliente desde Spotlight/Dock en macOS). Cerrá el cliente y arrancalo desde la terminal donde tu shell rc se cargó. Alternativamente, asegurate de tener la key en `~/.config/the-truth-mcp/.env` — el server la carga sin depender del entorno del cliente.

---

## License

MIT. Ver [LICENSE](LICENSE).
