# Convenciones de mi dominio — Producto / equipo

> Pegá esto dentro de la sección "Convenciones de mi dominio" del `CLAUDE.md` de tu vault.

## Categorías de wiki/

- **`wiki/features/`** — una página por feature del producto (shipped, in progress, o backlog).
- **`wiki/decisiones/`** — una página por decisión arquitectónica o de producto (formato ADR).
- **`wiki/incidentes/`** — postmortems. Una página por incidente.
- **`wiki/usuarios/`** — segmentos, personas (en sentido UX), o customers concretos si vendés B2B.

## Front-matter

Agregá estos campos a los obligatorios:

```yaml
type: feature | decision | incident | user
status: shipped | in-progress | backlog | deprecated
severity: low | medium | high | critical    # solo para incidents
date_resolved: 2026-04-27                   # solo para incidents
owner: "@nombre"
```

## Reglas extra

- Cada `decision` debe terminar en una sección `## Trade-offs` y otra `## Alternativas consideradas`.
- Cada `incident` debe tener `## Timeline`, `## Causa raíz`, `## Acciones de seguimiento`.
- Si una `feature` resuelve a una `decision`, linkearlas mutuamente.
- Si una `feature` causó un `incident`, linkearlas mutuamente.
- Las páginas de `usuarios` se linkean desde las features que los afectan.
