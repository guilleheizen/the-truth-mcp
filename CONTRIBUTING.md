# Contributing

Gracias por interesarte en contribuir. El proyecto es chico a propósito — el objetivo es que cualquiera pueda leer todo el código en una sentada y entenderlo.

## Setup

```bash
git clone https://github.com/guilleheizen/the-truth-mcp.git
cd the-truth-mcp
uv sync
```

Para probar tus cambios localmente sin tocar el repo público:

```bash
# Arrancar el server con stdio (modo MCP)
uv run the-truth-mcp run

# O probar el CLI
uv run the-truth-mcp init /tmp/test-vault
uv run the-truth-mcp doctor /tmp/test-vault
```

Si querés probar tu fork con Claude Code antes de pushearlo, apuntá el `.mcp.json` del vault al directorio local:

```json
{
  "mcpServers": {
    "the-truth": {
      "command": "uv",
      "args": ["--directory", "/path/to/your/the-truth-mcp", "run", "the-truth-mcp"],
      "env": { "...": "..." }
    }
  }
}
```

## Flujo

1. Issue primero si el cambio no es trivial — así alineamos antes de que escribas código.
2. Branch desde `main`.
3. Commits chicos y descriptivos.
4. PR con descripción clara: qué cambia, por qué, cómo se prueba.

## Áreas con buen ROI para PRs

- **Tests**: el repo no tiene suite. Cualquier `pytest` que cubra `vault.py` (las funciones puras) es bienvenido.
- **Modelos alternativos**: hoy solo Gemini. Un adapter para Claude o un modelo local en `gemini_agent.py` (renombrar `agent.py` quizás).
- **Retry/queue para `save_info`**: si Gemini falla, hoy no hay reintento automático.
- **Compactación de `log.md`**: rotación o resumen periódico.
- **Mejor handling de PDFs/imágenes** en `add_to_raw`: hoy se asume markdown.

## Estilo

- Python 3.11+, type hints donde aporten.
- Docstrings en español cortos. Comentar el "porqué", no el "qué".
- Nada de dependencias adicionales si se puede evitar — el value prop es que el server es chico.

## Comportamiento

Sé respetuoso, asumí buena fe, y revisá el código no a la persona. Si algo de la base de código te parece mal, abrí un issue para discutirlo — todas las decisiones de diseño son negociables.
