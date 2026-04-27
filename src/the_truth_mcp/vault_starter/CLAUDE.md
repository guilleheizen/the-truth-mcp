# LLM Wiki — Schema

Esta es una **bóveda de conocimiento** estilo [Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Este archivo es el manual de operaciones — lo leen tanto Claude (cliente) como Gemini (bibliotecario, vía el MCP `the-truth`).

> Editá este archivo libremente. A medida que tu bóveda crezca y descubras convenciones que te sirven, agregalas acá. Gemini lo relee en cada operación de escritura — el schema co-evoluciona con vos.

---

## Arquitectura

```
Claude ──save_info──▶ MCP ──▶ raw/        (plonk crudo, inmutable)
                       │
                       └──Gemini API──▶ wiki/  (Gemini ordena, automático)

Claude ──vault_search/read_page──▶ MCP ──▶ wiki/  (solo lectura)
```

**Reparto de roles**:
- **Claude (vos, cliente del MCP)**: solo dos cosas — **consultar** la bóveda y **guardar** info nueva. Nunca escribe en `wiki/`.
- **MCP `the-truth`**: I/O sobre el filesystem. Cuando llega info nueva (`save_info`), la guarda cruda en `raw/` y dispara al bibliotecario Gemini automáticamente.
- **Gemini (dentro del MCP)**: dueño exclusivo de `wiki/`. Lee toda la bóveda y la reorganiza — crea, actualiza, fusiona, divide páginas, mantiene cross-references. **Decide la estructura**.

---

## Las tres capas

```
raw/      ← fuentes inmutables. NUNCA editar.
wiki/     ← notas que Gemini genera y mantiene.
log.md    ← bitácora append-only.
```

- **`raw/`**: PDFs, .md crudos, transcripciones, recortes web. Es el *input*. Solo se lee. La única forma de agregar archivos acá es vía la tool `save_info`.
- **`wiki/`**: el *output*. Gemini decide la estructura interna. Puede crear subcarpetas, mover archivos, fusionar. Vos no tocás esto a mano.
- **`log.md`**: cada operación queda registrada cronológicamente. Sirve de auditoría.

---

## Estructura de `wiki/` — Gemini decide

Esta bóveda **no impone categorías**. Gemini observa el contenido que entra y decide cómo organizarlo. Puede que tu bóveda termine con `wiki/conceptos/`, `wiki/papers/`, `wiki/personas/`, o con `wiki/recetas/`, `wiki/clientes/`, `wiki/proyectos/`, o lo que sea — depende de qué guardes.

**Si querés guiar la organización**, agregá una sección "Convenciones de mi dominio" más abajo en este archivo (ejemplo al final). Gemini va a respetar esas convenciones en cada `save_info`.

Lo único que sí asume el sistema:
- **Una página = un archivo `.md`** dentro de `wiki/` (en cualquier subcarpeta).
- **Wikilinks** entre páginas con sintaxis `[[slug-de-la-pagina]]`.

---

## Convenciones mínimas

- **Nombres de archivo**: `kebab-case.md`. Sin tildes, sin mayúsculas, sin espacios.
- **Front-matter** sugerido (Gemini lo agrega automáticamente):

  ```yaml
  ---
  title: Título Humano
  created: YYYY-MM-DD
  updated: YYYY-MM-DD
  sources:
    - raw/foo.md
  related:
    - "[[otra-pagina]]"
  ---
  ```

- **Citas**: cuando una afirmación viene de una fuente, citá la ruta entre paréntesis al final: `(raw/foo.md)`.
- **Wikilinks**: si referenciás una página que no existe todavía, Gemini la crea como stub y la conecta.

---

## `index.md`

Catálogo de la bóveda. Gemini lo regenera en cada `save_info`. Estructura: una sección por categoría (las que Gemini haya decidido usar), y dentro una entrada por página: `- [[slug]] — descripción de una línea`.

## `log.md`

Append-only. Cada entrada empieza con un heading parseable:

```
## [YYYY-MM-DD] tipo | título corto
- detalles...
```

Tipos: `init`, `ingest`, `reorganize`, `query`, `lint`, `refactor`.

---

## Flujos

### Guardar info nueva (`/ingest <fuente>`)

1. Conseguís el contenido (URL, archivo, texto).
2. Llamás `save_info(content, title, source)` del MCP.
3. El MCP guarda crudo en `raw/<slug>.md`, dispara a Gemini, registra en `log.md`.
4. Gemini reorganiza `wiki/`: crea/actualiza páginas, mantiene cross-references.

### Consultar (`/query <pregunta>`)

1. `vault_search(keywords)` — buscás páginas relevantes.
2. `vault_read_page(slug)` para leer las que parezcan top.
3. Sintetizás citando rutas: `(wiki/foo.md)`. Si no encontrás algo, sugerís `/ingest`.

---

## Reglas duras

1. **`raw/` es sagrado**. Nadie edita raw, solo `save_info` agrega archivos nuevos.
2. **No inventar citas**. Si una afirmación no viene de una fuente, marcala como `> Inferencia.`
3. **Cross-references siempre**. Una página sin wikilinks pierde valor.
4. **El log es testigo**. Toda mutación a `wiki/` deja entrada en `log.md`.

---

## Convenciones de mi dominio

> _Esta sección arranca vacía. Agregala vos a medida que descubras qué te sirve. Ejemplos:_
>
> - _"Cada página tiene que tener un campo `confidence: low|medium|high` indicando qué tan seguro estoy del contenido."_
> - _"Las páginas de tipo `incidente` viven en `wiki/incidents/` y siempre incluyen una sección `## Postmortem`."_
> - _"Los wikilinks a personas usan el formato `[[@nombre]]`."_
>
> _Cualquier cosa que escribas acá, Gemini la va a respetar en futuros `save_info`._
