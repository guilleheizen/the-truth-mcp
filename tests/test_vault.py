"""Tests for the_truth_mcp.vault — the safety-critical filesystem layer."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from the_truth_mcp import vault
from the_truth_mcp.schemas import (
    AddLink,
    CreatePage,
    DeletePage,
    RenamePage,
    UpdatePage,
)


# ──────────────────────────────────────────────────────────────────────────────
# slugify
# ──────────────────────────────────────────────────────────────────────────────


def test_slugify_basic_lowercases_and_dashes():
    assert vault.slugify("Hello World") == "hello-world"


def test_slugify_strips_accents_atencion():
    assert vault.slugify("Atención") == "atencion"


def test_slugify_strips_accents_nino():
    assert vault.slugify("Niño") == "nino"


def test_slugify_replaces_special_chars():
    assert vault.slugify("Foo!@# Bar") == "foo-bar"


def test_slugify_empty_returns_untitled():
    assert vault.slugify("") == "untitled"


def test_slugify_whitespace_returns_untitled():
    assert vault.slugify("   ") == "untitled"


def test_slugify_collapses_repeated_separators():
    assert vault.slugify("foo---bar") == "foo-bar"


def test_slugify_already_kebab_is_unchanged():
    assert vault.slugify("already-kebab") == "already-kebab"


# ──────────────────────────────────────────────────────────────────────────────
# _safe_path (path traversal protection)
# ──────────────────────────────────────────────────────────────────────────────


def test_safe_path_inside_vault_returns_path(vault_setup: Path):
    p = vault._safe_path("wiki/foo.md")
    assert p.is_relative_to(vault_setup.resolve())
    assert p.name == "foo.md"


def test_safe_path_parent_traversal_raises(vault_setup: Path):
    with pytest.raises(ValueError, match="fuera de la bóveda"):
        vault._safe_path("../etc/passwd")


def test_safe_path_nested_parent_traversal_raises(vault_setup: Path):
    with pytest.raises(ValueError, match="fuera de la bóveda"):
        vault._safe_path("wiki/../../etc/passwd")


def test_safe_path_absolute_path_raises(vault_setup: Path):
    with pytest.raises(ValueError, match="fuera de la bóveda"):
        vault._safe_path("/absolute/path")


# ──────────────────────────────────────────────────────────────────────────────
# vault_root
# ──────────────────────────────────────────────────────────────────────────────


def test_vault_root_unset_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.delenv("LLM_WIKI_PATH", raising=False)
    with pytest.raises(RuntimeError, match="no está seteado"):
        vault.vault_root()


def test_vault_root_uses_llm_wiki_path_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.setenv("LLM_WIKI_PATH", str(tmp_path))
    assert vault.vault_root() == tmp_path.resolve()


def test_vault_root_nonexistent_dir_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_WIKI_PATH", raising=False)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path / "does-not-exist"))
    with pytest.raises(RuntimeError, match="inexistente"):
        vault.vault_root()


def test_vault_root_resolves_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    real_dir = tmp_path / "real_vault"
    real_dir.mkdir()
    link = tmp_path / "link_vault"
    link.symlink_to(real_dir)
    monkeypatch.delenv("LLM_WIKI_PATH", raising=False)
    monkeypatch.setenv("VAULT_PATH", str(link))
    root = vault.vault_root()
    assert root == real_dir.resolve()


# ──────────────────────────────────────────────────────────────────────────────
# _resolve_slug
# ──────────────────────────────────────────────────────────────────────────────


def test_resolve_slug_single_match(vault_setup: Path):
    cat = vault_setup / "wiki" / "cat"
    cat.mkdir()
    target = cat / "foo.md"
    target.write_text("hi", encoding="utf-8")
    resolved = vault._resolve_slug("foo")
    assert resolved == target.resolve()


def test_resolve_slug_ambiguous_raises(vault_setup: Path):
    a = vault_setup / "wiki" / "cat_a"
    b = vault_setup / "wiki" / "cat_b"
    a.mkdir()
    b.mkdir()
    (a / "foo.md").write_text("a", encoding="utf-8")
    (b / "foo.md").write_text("b", encoding="utf-8")
    with pytest.raises(ValueError, match="ambiguo"):
        vault._resolve_slug("foo")


def test_resolve_slug_with_full_md_path(vault_setup: Path):
    cat = vault_setup / "wiki" / "cat"
    cat.mkdir()
    (cat / "foo.md").write_text("hi", encoding="utf-8")
    resolved = vault._resolve_slug("wiki/cat/foo.md")
    assert resolved == (cat / "foo.md").resolve()


def test_resolve_slug_md_without_wiki_prefix(vault_setup: Path):
    target = vault_setup / "wiki" / "foo.md"
    target.write_text("hi", encoding="utf-8")
    resolved = vault._resolve_slug("foo.md")
    assert resolved == target.resolve()


def test_resolve_slug_missing_raises(vault_setup: Path):
    with pytest.raises(FileNotFoundError, match="No existe"):
        vault._resolve_slug("nonexistent")


# ──────────────────────────────────────────────────────────────────────────────
# list_pages
# ──────────────────────────────────────────────────────────────────────────────


def test_list_pages_empty_vault_returns_empty(vault_setup: Path):
    assert vault.list_pages() == []


def test_list_pages_returns_sorted_relative_paths(vault_setup: Path):
    cat_a = vault_setup / "wiki" / "cat_a"
    cat_b = vault_setup / "wiki" / "cat_b"
    cat_a.mkdir()
    cat_b.mkdir()
    (cat_b / "z.md").write_text("z", encoding="utf-8")
    (cat_a / "a.md").write_text("a", encoding="utf-8")
    (cat_a / "m.md").write_text("m", encoding="utf-8")

    pages = vault.list_pages()
    assert pages == sorted(pages)
    assert "wiki/cat_a/a.md" in pages
    assert "wiki/cat_a/m.md" in pages
    assert "wiki/cat_b/z.md" in pages


def test_list_pages_excludes_index_md(vault_setup: Path):
    (vault_setup / "wiki" / "index.md").write_text("idx", encoding="utf-8")
    (vault_setup / "wiki" / "real.md").write_text("real", encoding="utf-8")
    pages = vault.list_pages()
    assert "wiki/index.md" not in pages
    assert "wiki/real.md" in pages


def test_list_pages_category_filter(vault_setup: Path):
    cat_a = vault_setup / "wiki" / "cat_a"
    cat_b = vault_setup / "wiki" / "cat_b"
    cat_a.mkdir()
    cat_b.mkdir()
    (cat_a / "a.md").write_text("a", encoding="utf-8")
    (cat_b / "b.md").write_text("b", encoding="utf-8")

    pages = vault.list_pages(category="cat_a")
    assert pages == ["wiki/cat_a/a.md"]


def test_list_pages_missing_category_returns_empty(vault_setup: Path):
    assert vault.list_pages(category="ghost") == []


# ──────────────────────────────────────────────────────────────────────────────
# read_log
# ──────────────────────────────────────────────────────────────────────────────


def _seed_log(vault_root: Path, content: str) -> None:
    (vault_root / "log.md").write_text(content, encoding="utf-8")


def test_read_log_n_zero_returns_full(vault_setup: Path):
    content = "# Log\n\n## [2024-01-01] ingest | a\nbody-a\n\n## [2024-01-02] ingest | b\nbody-b\n"
    _seed_log(vault_setup, content)
    assert vault.read_log(n=0) == content


def test_read_log_returns_last_n_entries(vault_setup: Path):
    content = (
        "# Log\n\n"
        "## [2024-01-01] ingest | a\nbody-a\n\n"
        "## [2024-01-02] ingest | b\nbody-b\n\n"
        "## [2024-01-03] ingest | c\nbody-c\n"
    )
    _seed_log(vault_setup, content)
    out = vault.read_log(n=2)
    assert "## [2024-01-01] ingest | a" not in out
    assert "## [2024-01-02] ingest | b" in out
    assert "## [2024-01-03] ingest | c" in out


def test_read_log_n_larger_than_entries_returns_all(vault_setup: Path):
    content = (
        "# Log\n\n"
        "## [2024-01-01] ingest | a\nbody-a\n\n"
        "## [2024-01-02] ingest | b\nbody-b\n"
    )
    _seed_log(vault_setup, content)
    out = vault.read_log(n=99)
    assert "## [2024-01-01] ingest | a" in out
    assert "## [2024-01-02] ingest | b" in out


def test_read_log_preserves_head(vault_setup: Path):
    content = (
        "# Log\nIntro paragraph.\n\n"
        "## [2024-01-01] ingest | a\nbody-a\n"
    )
    _seed_log(vault_setup, content)
    out = vault.read_log(n=1)
    assert out.startswith("# Log\nIntro paragraph.\n\n")
    assert "## [2024-01-01] ingest | a" in out


# ──────────────────────────────────────────────────────────────────────────────
# add_to_raw
# ──────────────────────────────────────────────────────────────────────────────


def test_add_to_raw_creates_file(vault_setup: Path):
    rel = vault.add_to_raw("hello", slug="foo")
    assert rel == "raw/foo.md"
    assert (vault_setup / "raw" / "foo.md").is_file()


def test_add_to_raw_adds_front_matter_when_missing(vault_setup: Path):
    vault.add_to_raw("body content here", slug="foo", title="Foo Title")
    text = (vault_setup / "raw" / "foo.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "fetched:" in text
    assert 'title: "Foo Title"' in text
    assert "body content here" in text


def test_add_to_raw_preserves_existing_front_matter(vault_setup: Path):
    custom = "---\nfoo: bar\n---\n\nbody"
    vault.add_to_raw(custom, slug="myslug")
    text = (vault_setup / "raw" / "myslug.md").read_text(encoding="utf-8")
    assert text == custom


def test_add_to_raw_slug_takes_precedence_over_title(vault_setup: Path):
    rel = vault.add_to_raw("x", slug="explicit-slug", title="Some Other Title")
    assert rel == "raw/explicit-slug.md"
    assert (vault_setup / "raw" / "explicit-slug.md").is_file()
    assert not (vault_setup / "raw" / "some-other-title.md").exists()


def test_add_to_raw_without_slug_or_title_raises(vault_setup: Path):
    with pytest.raises(ValueError, match="slug.*title"):
        vault.add_to_raw("content")


def test_add_to_raw_existing_slug_raises(vault_setup: Path):
    vault.add_to_raw("first", slug="dup")
    with pytest.raises(FileExistsError, match="ya existe"):
        vault.add_to_raw("second", slug="dup")


def test_add_to_raw_path_traversal_slug_is_sanitized(vault_setup: Path):
    """Un slug malicioso como '../etc/passwd' debe sanitizarse vía slugify y
    el archivo resultante debe quedar bajo raw/ (no en otro lado del vault).
    """
    rel_path = vault.add_to_raw("payload", slug="../etc/passwd")
    assert rel_path.startswith("raw/"), f"escape detectado: {rel_path}"
    # El slug se normaliza pero los caracteres alfanuméricos se preservan.
    assert (vault_setup / rel_path).is_file()
    # El archivo NO debe haberse creado fuera de raw/.
    assert not (vault_setup / "etc" / "passwd.md").exists()


def test_add_to_raw_slug_with_separators_is_flattened(vault_setup: Path):
    """Slugs con `/` se aplastan: raw/ es plano por design."""
    rel_path = vault.add_to_raw("body", slug="sub/dir/file")
    assert rel_path.startswith("raw/")
    assert "/" not in rel_path[len("raw/"):rel_path.rfind(".md")]


# ──────────────────────────────────────────────────────────────────────────────
# apply_operation
# ──────────────────────────────────────────────────────────────────────────────


def _create_page(path: str, content: str) -> CreatePage:
    return CreatePage(path=path, content=content, rationale="test")


def test_apply_create_page_writes_file(vault_setup: Path):
    op = _create_page("wiki/cat/new.md", "hello")
    msg = vault.apply_operation(op)
    assert "created" in msg
    assert (vault_setup / "wiki" / "cat" / "new.md").read_text(encoding="utf-8") == "hello"


def test_apply_create_page_outside_wiki_raises(vault_setup: Path):
    op = _create_page("raw/x.md", "evil")
    with pytest.raises(ValueError, match="Solo se puede escribir bajo wiki/"):
        vault.apply_operation(op)


def test_apply_update_page_missing_raises(vault_setup: Path):
    op = UpdatePage(path="wiki/missing.md", content="new", rationale="test")
    with pytest.raises(FileNotFoundError, match="No existe"):
        vault.apply_operation(op)


def test_apply_delete_page_missing_returns_skipped(vault_setup: Path):
    op = DeletePage(path="wiki/ghost.md", rationale="test")
    msg = vault.apply_operation(op)
    assert "skipped" in msg


def test_apply_rename_page_works(vault_setup: Path):
    src = vault_setup / "wiki" / "old.md"
    src.write_text("hi", encoding="utf-8")
    op = RenamePage(from_path="wiki/old.md", to_path="wiki/new.md", rationale="test")
    msg = vault.apply_operation(op)
    assert "renamed" in msg
    assert not src.exists()
    assert (vault_setup / "wiki" / "new.md").read_text(encoding="utf-8") == "hi"


def test_apply_add_link_creates_section_when_missing(vault_setup: Path):
    page = vault_setup / "wiki" / "host.md"
    page.write_text("# Host\n\nbody\n", encoding="utf-8")
    op = AddLink(in_path="wiki/host.md", target_slug="other", rationale="test")
    msg = vault.apply_operation(op)
    assert "added link" in msg
    text = page.read_text(encoding="utf-8")
    assert "## Ver también" in text
    assert "- [[other]]" in text


def test_apply_add_link_under_existing_section(vault_setup: Path):
    page = vault_setup / "wiki" / "host.md"
    page.write_text("# Host\n\nbody\n\n## Ver también\n- [[existing]]\n", encoding="utf-8")
    op = AddLink(in_path="wiki/host.md", target_slug="another", rationale="test")
    vault.apply_operation(op)
    text = page.read_text(encoding="utf-8")
    assert "- [[another]]" in text
    assert "- [[existing]]" in text


def test_apply_add_link_already_present_returns_skipped(vault_setup: Path):
    page = vault_setup / "wiki" / "host.md"
    page.write_text("# Host\n\n## Ver también\n- [[other]]\n", encoding="utf-8")
    op = AddLink(in_path="wiki/host.md", target_slug="other", rationale="test")
    msg = vault.apply_operation(op)
    assert "skipped" in msg


# ──────────────────────────────────────────────────────────────────────────────
# _wiki_sources_index and vault_status
# ──────────────────────────────────────────────────────────────────────────────


def test_wiki_sources_index_picks_up_referenced_raw(vault_setup: Path):
    page = vault_setup / "wiki" / "p.md"
    page.write_text(
        "---\n"
        "title: P\n"
        "sources:\n"
        "  - raw/foo.md\n"
        "  - raw/bar.md\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    refs = vault._wiki_sources_index()
    assert "raw/foo.md" in refs
    assert "raw/bar.md" in refs


def test_vault_status_distinguishes_pending_and_processed(vault_setup: Path):
    (vault_setup / "raw" / "processed.md").write_text("p", encoding="utf-8")
    (vault_setup / "raw" / "pending.md").write_text("q", encoding="utf-8")
    page = vault_setup / "wiki" / "p.md"
    page.write_text(
        "---\nsources:\n  - raw/processed.md\n---\n\nbody\n",
        encoding="utf-8",
    )

    status = vault.vault_status()
    assert status["raw_total"] == 2
    assert status["raw_processed"] == 1
    assert status["raw_pending"] == ["raw/pending.md"]
    assert status["wiki_pages"] == 1
    assert status["vault_root"] == str(vault_setup.resolve())


# ──────────────────────────────────────────────────────────────────────────────
# mark_groomed / last_groom_at
# ──────────────────────────────────────────────────────────────────────────────


def test_last_groom_at_is_none_when_never_groomed(vault_setup: Path):
    assert vault.last_groom_at() is None


def test_mark_groomed_creates_stamp(vault_setup: Path):
    vault.mark_groomed()
    assert (vault_setup / ".last_groom").is_file()


def test_last_groom_at_returns_recent_utc_after_mark(vault_setup: Path):
    from datetime import datetime, timezone, timedelta

    before = datetime.now(timezone.utc) - timedelta(seconds=2)
    vault.mark_groomed()
    after = datetime.now(timezone.utc) + timedelta(seconds=2)
    ts = vault.last_groom_at()
    assert ts is not None
    assert ts.tzinfo is not None
    assert before <= ts <= after


def test_vault_status_includes_last_groom_null_when_unset(vault_setup: Path):
    assert vault.vault_status()["last_groom"] is None


def test_vault_status_includes_last_groom_iso_after_mark(vault_setup: Path):
    vault.mark_groomed()
    last = vault.vault_status()["last_groom"]
    assert isinstance(last, str)
    # ISO-8601 con timezone UTC.
    assert last.endswith("+00:00") or last.endswith("Z")
