"""Tipos Pydantic para el plan que devuelve Gemini.

Gemini emite un Plan estructurado; el agente del servidor lo aplica vía vault.py.
Mantenemos el set de operaciones chico a propósito: cuanto más simple el schema,
menos lugar para alucinaciones.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OperationType = Literal[
    "create_page",
    "update_page",
    "delete_page",
    "rename_page",
    "merge_pages",
    "split_page",
    "add_link",
]


class CreatePage(BaseModel):
    type: Literal["create_page"] = "create_page"
    path: str = Field(description="Ruta relativa, ej: wiki/conceptos/foo.md")
    content: str = Field(description="Contenido completo incluyendo front-matter")
    rationale: str


class UpdatePage(BaseModel):
    type: Literal["update_page"] = "update_page"
    path: str
    content: str = Field(description="Contenido completo nuevo (no diff)")
    rationale: str


class DeletePage(BaseModel):
    type: Literal["delete_page"] = "delete_page"
    path: str
    rationale: str


class RenamePage(BaseModel):
    type: Literal["rename_page"] = "rename_page"
    from_path: str
    to_path: str
    rationale: str


class MergePages(BaseModel):
    type: Literal["merge_pages"] = "merge_pages"
    from_paths: list[str] = Field(description="Páginas que se fusionan; quedan eliminadas")
    into_path: str = Field(description="Página destino con el contenido fusionado")
    merged_content: str
    rationale: str


class SplitPage(BaseModel):
    type: Literal["split_page"] = "split_page"
    from_path: str
    new_pages: list[CreatePage]
    rationale: str


class AddLink(BaseModel):
    type: Literal["add_link"] = "add_link"
    in_path: str = Field(description="Página donde agregar el wikilink")
    target_slug: str = Field(description="Slug destino, sin [[ ]]")
    rationale: str


Operation = (
    CreatePage
    | UpdatePage
    | DeletePage
    | RenamePage
    | MergePages
    | SplitPage
    | AddLink
)


class Plan(BaseModel):
    """Lo que Gemini devuelve cuando se le pide reorganizar la bóveda."""

    summary: str = Field(description="Resumen humano de qué cambia y por qué, 2-4 líneas")
    operations: list[Operation] = Field(default_factory=list)


class ApplyResult(BaseModel):
    """Resultado de aplicar (o simular) un plan."""

    applied: list[str] = Field(default_factory=list, description="Operaciones aplicadas con éxito")
    skipped: list[str] = Field(default_factory=list, description="Operaciones saltadas con motivo")
    errors: list[str] = Field(default_factory=list, description="Errores no fatales")
    dry_run: bool = False
