---
name: markdown-cleaner
description: Usar cuando se acaba de escribir o editar un .md en wiki/ y hay que normalizar formato. Limpia front-matter, normaliza headings, valida wikilinks, asegura newline final. NO uses en raw/.
---

Limpiador de markdown para la bóveda LLM Wiki. Ejecutá estos pasos en orden sobre el archivo objetivo:

## 1. Front-matter

- Debe estar entre `---` al principio del archivo, exactamente.
- Campos obligatorios para `wiki/**`: `title`, `type`, `created`, `updated`, `sources`, `related`.
- Si falta `updated`, ponelo a la fecha de hoy.
- `type` debe ser uno de: `concepto`, `persona`, `paper`. Si dice algo distinto, marcalo como warning (no lo cambies sin confirmación).

## 2. Headings

- Un solo `# H1` por archivo, debe coincidir con `title` del front-matter.
- No saltar niveles (no pasar de `##` a `####`).
- Sin trailing punctuation en headings.

## 3. Wikilinks

- Formato `[[slug-en-kebab-case]]`. Sin espacios, sin tildes, ASCII.
- Si encontrás `[[Slug Con Espacios]]`, normalizalo a `[[slug-con-espacios]]`.

## 4. Trailing whitespace y newlines

- Eliminá whitespace al final de cada línea.
- Asegurá que el archivo termine con exactamente UN newline.
- No más de 1 línea en blanco consecutiva (excepto separadores `---`).

## 5. Citas

- Citas a `raw/` deben ir entre paréntesis al final del párrafo: `(raw/seed/foo.md)`.
- Si encontrás una cita malformada (ej: `[ref: foo]`), proponé conversión.

## Salida

- Si hay cambios, aplicalos con `Edit`.
- Si encontrás warnings que requieren decisión del usuario, listalos sin tocar nada.

## NO hacer

- No tocar archivos en `raw/` bajo ninguna circunstancia.
- No reescribir el contenido. Solo formato.
