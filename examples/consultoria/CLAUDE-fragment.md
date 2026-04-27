# Convenciones de mi dominio — Consultoría

> Pegá esto dentro de la sección "Convenciones de mi dominio" del `CLAUDE.md` de tu vault.

## Categorías de wiki/

- **`wiki/clientes/`** — una página por cliente activo o histórico.
- **`wiki/proyectos/`** — engagements concretos. Pueden vincularse a un cliente.
- **`wiki/propuestas/`** — propuestas comerciales (enviadas, aceptadas, rechazadas).
- **`wiki/lecciones-aprendidas/`** — patterns que extraés cross-proyectos. Acá compounded el verdadero valor a largo plazo.

## Front-matter

Agregá estos campos a los obligatorios:

```yaml
type: cliente | proyecto | propuesta | leccion
client: "[[acme-corp]]"        # solo para proyectos y propuestas
status: activo | cerrado | en-pausa
fecha_inicio: 2026-01-15
fecha_cierre: 2026-04-27       # opcional
confidential: true             # si la página tiene info sensible
```

## Reglas extra

- Cada `proyecto` cerrado debe terminar en una sección `## Lecciones`. Ese contenido se promueve a una página separada en `wiki/lecciones-aprendidas/` si el aprendizaje aplica más allá de ese cliente.
- Las páginas marcadas `confidential: true` no se incluyen en ningún resumen público que generes desde la bóveda.
- Mantené `wiki/clientes/<slug>.md` con timeline cronológico de proyectos (wikilinks).

## Cuándo NO usar este perfil

Si trabajás in-house en un solo producto, usá el perfil `producto` en lugar de este.
