# Convenciones de mi dominio — Cocina

> Pegá esto dentro de la sección "Convenciones de mi dominio" del `AGENTS.md` de tu vault.

## Categorías de wiki/

- **`wiki/recetas/`** — una página por receta.
- **`wiki/tecnicas/`** — técnicas o conceptos transversales (`fermentacion`, `mise-en-place`, `temperar-chocolate`).
- **`wiki/ingredientes/`** — páginas por ingrediente cuando hay info que vale destacar (origen, sustituciones, conservación).

## Front-matter

Agregá estos campos a los obligatorios:

```yaml
type: receta | tecnica | ingrediente
porciones: 4                       # solo para recetas
tiempo_total_min: 45               # solo para recetas
dificultad: facil | media | dificil
dietas:                            # solo para recetas
  - vegetariana
  - sin-gluten
restricciones:                     # solo para ingredientes
  - alergeno: gluten
```

## Reglas extra

- Cada `receta` debe tener: `## Ingredientes` (con wikilinks a `wiki/ingredientes/<slug>` cuando aplique), `## Pasos`, `## Notas` (variaciones, sustituciones).
- Las `tecnicas` se linkean desde cualquier `receta` que las use.
- Si un `ingrediente` aparece en >3 recetas, agregá su página en `wiki/ingredientes/`.

## Cuándo NO usar este perfil

Si solo querés guardar un par de recetas sueltas, no hace falta este nivel de estructura — dejá que Gemini decida sin guías.
