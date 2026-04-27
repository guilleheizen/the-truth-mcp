# LLM Wiki — Schema

Este repo es una **bóveda de conocimiento** estilo Karpathy (LLM Wiki). Este archivo es el manual de operaciones de la bóveda — lo leen tanto Claude (cliente) como Gemini (bibliotecario, vía el MCP `the-truth`).

> Lectura obligada: este `CLAUDE.md` se carga en cada sesión. Tratalo como la fuente de verdad sobre cómo operar la bóveda. Si descubrís una convención mejor, proponela y actualizá este archivo — el schema co-evoluciona.

## Arquitectura del proyecto

La bóveda se gestiona vía un **MCP local**, `the-truth-mcp`. El reparto de responsabilidades es estricto y minimalista:

- **Claude (cliente del MCP)**: solo dos cosas — **consultar** y **guardar**. Para consultar usa `vault_search`, `vault_read_page`, `vault_list_pages`. Para guardar info nueva, una sola tool: `save_info`. **Nunca escribe en `wiki/`.**
- **MCP `the-truth`**: dueño del filesystem. Cuando llega info nueva (`save_info`), la guarda cruda en `raw/seed/` y dispara al bibliotecario Gemini automáticamente.
- **Gemini (dentro del MCP)**: dueño exclusivo de `wiki/`. En cada `save_info`, lee toda la bóveda y reorganiza — crea, actualiza, fusiona, divide páginas, mantiene cross-references. No interviene en consultas.

```
Claude ──save_info──▶ MCP ──▶ raw/        (plonk crudo)
                       │
                       └──Gemini API──▶ wiki/  (Gemini ordena, automático)

Claude ──vault_search/read_page──▶ MCP ──▶ wiki/  (solo lectura)
```

---

## 1. Las tres capas

```
raw/      ← fuentes inmutables. NUNCA editar.
wiki/     ← notas que Gemini genera y mantiene.
log.md    ← bitácora append-only en la raíz.
```

- **`raw/`**: PDFs, .md crudos, transcripciones, recortes web. Es el *input*. Solo se lee.
- **`wiki/`**: el *output*. Resúmenes, páginas de concepto, páginas de persona, comparaciones. Gemini es el dueño.
- **`log.md`**: cada operación queda registrada cronológicamente.

## 2. Estructura de `wiki/`

```
wiki/
├── index.md            ← catálogo de la bóveda. Gemini lo actualiza en cada save_info.
├── conceptos/          ← una página por concepto técnico
├── personas/           ← una página por persona
└── papers/             ← una página por paper o artículo fuente
```

### 2.1 Adaptar las categorías a tu dominio

Las categorías por defecto (`conceptos`, `personas`, `papers`) están pensadas para investigación técnica/académica al estilo Karpathy. **Son completamente personalizables** — el sistema no las hardcodea, son una convención que vive en este `CLAUDE.md`.

Para adaptar la bóveda a otro dominio:

1. **Editá esta sección** describiendo tus propias categorías y qué va en cada una.
2. **Renombrá / creá las carpetas** correspondientes en `wiki/`.
3. **Actualizá los valores válidos de `type` en el front-matter** (sección 3).
4. La próxima vez que se llame `save_info`, Gemini va a leer este archivo actualizado y respetar las nuevas categorías.

Ejemplos de configuración por dominio:

- **Investigación / IA** (default): `conceptos/`, `personas/`, `papers/`.
- **Producto / Equipo**: `features/`, `decisiones/`, `usuarios/`, `incidentes/`.
- **Consultoría**: `clientes/`, `proyectos/`, `propuestas/`, `lecciones-aprendidas/`.
- **Aprendizaje personal**: `temas/`, `recursos/`, `dudas/`, `proyectos/`.
- **Cocina**: `recetas/`, `tecnicas/`, `ingredientes/`.

Lo único que **no** debés cambiar es la separación `raw/` (inmutable) vs `wiki/` (Gemini ordena) vs `log.md` — esa es la arquitectura del MCP.

## 3. Convenciones de archivos

- **Nombres**: `kebab-case.md`. Sin tildes, sin mayúsculas, sin espacios.
- **Front-matter** obligatorio en cada página de `wiki/`:

  ```yaml
  ---
  title: Título Humano
  type: concepto            # uno de los tipos definidos en sección 2 / 2.1
  created: 2026-04-27
  updated: 2026-04-27
  sources:                  # rutas relativas a raw/, o URLs
    - raw/seed/foo.md
  related:                  # wikilinks a otras páginas
    - "[[otra-pagina]]"
  ---
  ```

- **Cuerpo**: empieza con un párrafo de 2-4 líneas que sirva como TL;DR. Después secciones (`## ...`).
- **Cross-references**: usar wikilinks `[[pagina-destino]]`. Si la destino no existe, crearla como stub.
- **Citas**: cuando se afirme algo que viene de una fuente, citar la ruta `raw/...` o URL al final del párrafo entre paréntesis: `(raw/seed/foo.md)`.

## 4. `index.md`

Catálogo organizado por categoría:

```markdown
# Index

## Conceptos
- [[concepto-1]] — descripción de una línea
...

## Personas
- [[persona-1]] — descripción de una línea
...

## Papers
- [[paper-1]] — descripción de una línea
...
```

## 5. `log.md`

Append-only. Cada entrada empieza con un heading parseable:

```markdown
## [2026-04-27] ingest | Título de la fuente
- archivo: raw/seed/foo.md
- source: <url>

## [2026-04-27] reorganize | resumen del cambio
- modelo: gemini-2.5-flash
- operaciones propuestas: 3
- aplicadas: 3
```

Tipos válidos: `init`, `ingest`, `reorganize`, `query`, `lint`, `refactor`.

## 6. Workflows

### 6.1. Guardar info (`/ingest`)

1. Conseguí el contenido (WebFetch / Read / texto directo).
2. Sacá un título humano.
3. Llamá `save_info(content, title, source)` del MCP. Eso:
   - Guarda crudo en `raw/seed/<slug>.md`.
   - Dispara a Gemini, que reorganiza `wiki/` automáticamente.
   - Logea en `log.md`.
4. Mostrá al usuario qué hizo Gemini (campo `gemini_summary` y `operations_applied`).

### 6.2. Consultar (`/query`)

1. `vault_search(query=keywords)` — buscá páginas relevantes.
2. `vault_read_page(slug)` para 2-5 páginas top.
3. Sintetizá la respuesta citando rutas: `(wiki/conceptos/foo.md)`.
4. Si la pregunta toca algo que no está, sugerí `/ingest <fuente>`.

## 7. Reglas de oro

1. **`raw/` es sagrado.** Nadie edita raw, ni Claude ni Gemini. Solo `save_info` agrega archivos nuevos.
2. **No inventar citas.** Si una afirmación no viene de una fuente, marcarla como `> Inferencia del agente.`
3. **Cross-references siempre.** Una página sin wikilinks es probablemente una huérfana mal nacida.
4. **Stubs antes que nada.** Mejor 10 stubs interconectados que 1 página perfecta aislada.
5. **El log es testigo.** Toda mutación a `wiki/` deja entrada en `log.md`.
