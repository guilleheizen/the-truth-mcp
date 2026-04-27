# Convenciones de mi dominio — Investigación técnica / IA

> Pegá esto dentro de la sección "Convenciones de mi dominio" del `CLAUDE.md` de tu vault.

## Categorías de wiki/

- **`wiki/conceptos/`** — una página por concepto técnico abstracto (ej. `attention`, `rag`, `embeddings`).
- **`wiki/personas/`** — investigadores, autores, founders. Una página por persona.
- **`wiki/papers/`** — papers académicos o posts canónicos. Una página por paper.

## Front-matter

Agregá estos campos a los obligatorios:

```yaml
type: concepto | persona | paper
year: 2017                # solo para papers
authors:                  # solo para papers
  - "Nombre 1"
  - "Nombre 2"
affiliation: "OpenAI"     # solo para personas (afiliación principal)
```

## Reglas extra

- Si un paper menciona conceptos nuevos, creá stubs en `wiki/conceptos/` y linkealos desde la página del paper.
- Si una persona aparece como autor de un paper, creá stub en `wiki/personas/` y linkealo desde la página del paper.
- En la página de cada concepto, mantené una sección `## Papers relevantes` con wikilinks a los papers que lo discuten.
