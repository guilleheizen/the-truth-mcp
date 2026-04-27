# Convenciones de mi dominio — Aprendizaje personal

> Pegá esto dentro de la sección "Convenciones de mi dominio" del `CLAUDE.md` de tu vault.

## Categorías de wiki/

- **`wiki/temas/`** — un tema = un dominio amplio que estás aprendiendo (ej. `rust`, `negociacion`, `linealgebra`).
- **`wiki/recursos/`** — libros, cursos, papers, videos que consumiste. Una página por recurso.
- **`wiki/dudas/`** — preguntas abiertas que tenés. Idealmente cerrarlas con respuesta, conectándolas a páginas de `temas/`.
- **`wiki/proyectos/`** — proyectos prácticos donde aplicás lo que aprendés.

## Front-matter

Agregá estos campos a los obligatorios:

```yaml
type: tema | recurso | duda | proyecto
status:                          # solo para recursos
  - to-read | reading | done | abandoned
status:                          # solo para dudas
  - abierta | resuelta
status:                          # solo para proyectos
  - idea | en-progreso | terminado | abandonado
rating: 1 | 2 | 3 | 4 | 5        # solo para recursos consumidos
```

## Reglas extra

- Cada `recurso` consumido tiene una sección `## Takeaways` con bullets.
- Cada `duda` arranca con la pregunta, y cuando la cerrás, agregás `## Respuesta` con cita de qué la resolvió.
- En cada `tema/<slug>.md` mantené un `## Mapa` con wikilinks a los recursos, dudas, y proyectos relacionados.
- Si una `duda` aparece en >2 lugares, promovela a página propia en `wiki/dudas/`.
