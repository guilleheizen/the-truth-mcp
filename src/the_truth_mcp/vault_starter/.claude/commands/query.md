---
description: Consultar la bóveda vía MCP — Claude responde citando archivos
argument-hint: <pregunta>
---

Consultás la bóveda usando las tools de lectura del MCP `the-truth`.
Gemini no se mete en queries — solo ordena cuando guardás info nueva.

Pregunta: **$ARGUMENTS**

## Pasos

1. **Buscar páginas relevantes** con `vault_search(query=<keywords>)`.
   Extraé 1-3 keywords clave de la pregunta.

2. **Leer las páginas más prometedoras** con `vault_read_page(slug)`.
   Típicamente 2-5 páginas alcanzan.

3. **Sintetizá la respuesta** citando cada afirmación con la ruta del archivo:
   `(wiki/foo.md)` o `(wiki/<subcarpeta>/foo.md)`. Si una afirmación viene de
   la fuente cruda, citá la ruta de `raw/`.

4. **Si la pregunta toca algo que no está en la bóveda**, decilo explícito.
   No inventes. Sugerí `/ingest <fuente>` para cubrirlo.

## Reglas

- Citá siempre. Ninguna afirmación sin ruta entre paréntesis.
- No leas todo el wiki — buscá primero, leé selectivo.
- Si encontrás contradicciones entre páginas, marcalas — la próxima vez que
  alguien guarde info, Gemini va a tener oportunidad de resolverlas.
