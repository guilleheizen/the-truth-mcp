# Changelog

Todas las versiones notables del proyecto se documentan acá. Formato basado en [Keep a Changelog](https://keepachangelog.com/), versionado [SemVer](https://semver.org/lang/es/).

## [Unreleased]

## [0.1.0] — 2026-04-27

Primera release pública.

### Added
- MCP server con 4 tools (`vault_search`, `vault_read_page`, `vault_list_pages`, `save_info`) y 4 resources (`vault://{index, log, claude, page/{cat}/{slug}}`).
- Bibliotecario Gemini que reorganiza `wiki/` automáticamente con cada `save_info`. Modelo configurable (default `gemini-2.5-flash`).
- CLI con subcomandos `init`, `run`, `doctor`, `--version`.
- Comando `init <path>` que crea una bóveda nueva desde el template empaquetado.
- Comando `doctor [<path>]` que verifica setup completo (env vars, API key, vault, llamada de salud a Gemini).
- Template del vault minimalista: arranca limpio, sin categorías predefinidas. Gemini decide la estructura.
- Aliases para la API key: `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_APIKEY`, `GOOGLE_GENAI_API_KEY`.
- Carga automática de `.env` desde cwd y desde `VAULT_PATH/.env` (alias `LLM_WIKI_PATH`).
- Schema de la bóveda en `AGENTS.md` (agent-agnostic). `CLAUDE.md` aceptado como fallback para back-compat.
- Resource MCP `vault://agents` (alias `vault://claude` deprecated).
- Fallback automático entre modelos Gemini si el primario devuelve errores transitorios (429/5xx). Retry con backoff (2s, 8s, 30s).
- Inyección de la fecha de hoy en el prompt de Gemini para evitar fechas alucinadas en `front-matter`.
- Tolerancia a fallas: si Gemini falla durante `save_info`, el crudo queda guardado igual.

### Notes
- Inspirado en el [LLM Wiki gist de Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
