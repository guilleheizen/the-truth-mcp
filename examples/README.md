# Examples — convenciones por dominio

Cada subcarpeta tiene un fragmento que podés pegar en la sección **"Convenciones de mi dominio"** del `CLAUDE.md` de tu vault. Gemini lo lee en cada `save_info` y respeta esas reglas al organizar `wiki/`.

| Dominio | Categorías propuestas |
|---|---|
| [`investigacion/`](investigacion/CLAUDE-fragment.md) | `conceptos/`, `personas/`, `papers/` |
| [`producto/`](producto/CLAUDE-fragment.md) | `features/`, `decisiones/`, `incidentes/`, `usuarios/` |
| [`consultoria/`](consultoria/CLAUDE-fragment.md) | `clientes/`, `proyectos/`, `propuestas/`, `lecciones-aprendidas/` |
| [`aprendizaje/`](aprendizaje/CLAUDE-fragment.md) | `temas/`, `recursos/`, `dudas/`, `proyectos/` |
| [`cocina/`](cocina/CLAUDE-fragment.md) | `recetas/`, `tecnicas/`, `ingredientes/` |

## Cómo usar uno

1. Abrí el `CLAUDE.md` de tu vault.
2. Copiá el fragmento del dominio que te sirve (o mezclá varios).
3. Pegalo dentro de la sección **"Convenciones de mi dominio"**.
4. Tu próximo `save_info` ya respeta esas reglas — Gemini relee `CLAUDE.md` cada vez.

No hace falta tocar código ni reiniciar el MCP.

## Aportar un dominio nuevo

¿Tu caso de uso no encaja con ninguno? Abrí un PR con un nuevo subdirectorio `examples/<tu-dominio>/CLAUDE-fragment.md`. Lineamientos:

- 50–150 líneas, no más.
- Categorías concretas (las carpetas de `wiki/`).
- Si el dominio pide un campo extra en el front-matter (ej. `severity`, `client_id`), declaralo.
- Una sección "Cuándo NO usar este perfil" si aplica.
