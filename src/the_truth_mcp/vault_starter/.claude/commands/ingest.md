---
description: Guardar info nueva en la bóveda — el MCP la guarda y Gemini ordena
argument-hint: <url-o-ruta-o-texto>
---

Guardás info nueva en la bóveda usando el MCP `the-truth`. Una sola tool, un
solo paso: el MCP guarda crudo en `raw/` y Gemini reorganiza `wiki/`
automáticamente — decide la estructura según el contenido.

Fuente: **$ARGUMENTS**

## Pasos

1. **Conseguí el contenido**:
   - URL → `WebFetch` → extraé el texto markdown.
   - Ruta a archivo → leelo.
   - Texto en bruto pasado como argumento → usalo directo.

2. **Sacá un título humano** del contenido. El slug se deriva automáticamente.

3. **Llamá `save_info`** del MCP `the-truth`:
   ```
   save_info(content=<markdown>, title=<título>, source=<url|path>)
   ```
   Esto:
   - Guarda en `raw/<slug>.md` (inmutable).
   - Dispara al bibliotecario Gemini, que reorganiza `wiki/` automáticamente.
   - Logea todo en `log.md`.

4. **Mostrá al usuario** lo que devolvió `save_info`:
   - `saved_at`: dónde quedó el crudo.
   - `gemini_summary`: qué hizo Gemini.
   - `operations_applied`: lista de cambios sobre `wiki/`.
   - Si hay `gemini_error`: avisalo — el crudo igual quedó guardado, podés reintentar.

## Reglas

- Vos no escribís en `wiki/`. Nunca. Es Gemini quien decide la estructura.
- Si el usuario quiere revisar antes de guardar, pedí feedback sobre el título
  o el contenido extraído **antes** de llamar `save_info` — una vez llamada,
  el archivo crudo es inmutable.
