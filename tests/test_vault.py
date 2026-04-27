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
    res = vault.add_to_raw("hello", slug="foo")
    assert res == {"path": "raw/foo.md", "deduplicated": False}
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
    # El front-matter original se preserva; agregamos `content_hash:` adentro.
    assert "foo: bar" in text
    assert "content_hash:" in text
    assert "\n\nbody" in text


def test_add_to_raw_slug_takes_precedence_over_title(vault_setup: Path):
    res = vault.add_to_raw("x", slug="explicit-slug", title="Some Other Title")
    assert res["path"] == "raw/explicit-slug.md"
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
    res = vault.add_to_raw("payload", slug="../etc/passwd")
    rel_path = res["path"]
    assert rel_path.startswith("raw/"), f"escape detectado: {rel_path}"
    # El slug se normaliza pero los caracteres alfanuméricos se preservan.
    assert (vault_setup / rel_path).is_file()
    # El archivo NO debe haberse creado fuera de raw/.
    assert not (vault_setup / "etc" / "passwd.md").exists()


def test_add_to_raw_slug_with_separators_is_flattened(vault_setup: Path):
    """Slugs con `/` se aplastan: raw/ es plano por design."""
    res = vault.add_to_raw("body", slug="sub/dir/file")
    rel_path = res["path"]
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


# ──────────────────────────────────────────────────────────────────────────────
# parse_front_matter / list_pages_detailed (#1)
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_front_matter_empty_when_missing():
    assert vault.parse_front_matter("# just markdown\n\nbody") == {}


def test_parse_front_matter_scalars_and_quoted_strings():
    fm = vault.parse_front_matter('---\ntitle: "Foo"\npinned: true\n---\n\nbody')
    assert fm == {"title": "Foo", "pinned": True}


def test_parse_front_matter_lists():
    text = "---\ntags:\n  - alpha\n  - beta\nsources:\n  - raw/x.md\n---\n\nbody"
    fm = vault.parse_front_matter(text)
    assert fm["tags"] == ["alpha", "beta"]
    assert fm["sources"] == ["raw/x.md"]


def test_list_pages_detailed_returns_metadata(vault_setup: Path):
    page = vault_setup / "wiki" / "p.md"
    page.write_text(
        '---\ntitle: "P"\nsummary: a short one\ntags:\n  - x\n---\n\nbody\n',
        encoding="utf-8",
    )
    detailed = vault.list_pages_detailed()
    assert detailed == [{
        "path": "wiki/p.md",
        "title": "P",
        "summary": "a short one",
        "tags": ["x"],
        "sources": [],
        "related": [],
    }]


def test_list_pages_detailed_handles_pages_without_front_matter(vault_setup: Path):
    (vault_setup / "wiki" / "raw.md").write_text("# Just a heading\n", encoding="utf-8")
    detailed = vault.list_pages_detailed()
    assert detailed[0]["title"] is None


# ──────────────────────────────────────────────────────────────────────────────
# is_pinned + bloqueos en apply_operation (#4)
# ──────────────────────────────────────────────────────────────────────────────


def _write_pinned(vault_root: Path, rel: str, *, pinned: bool = True) -> None:
    target = vault_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    fm_pinned = "true" if pinned else "false"
    target.write_text(f"---\ntitle: P\npinned: {fm_pinned}\n---\n\nbody\n", encoding="utf-8")


def test_is_pinned_true_when_front_matter_pinned(vault_setup: Path):
    _write_pinned(vault_setup, "wiki/p.md", pinned=True)
    assert vault.is_pinned("wiki/p.md") is True


def test_is_pinned_false_when_no_front_matter(vault_setup: Path):
    (vault_setup / "wiki" / "p.md").write_text("body\n", encoding="utf-8")
    assert vault.is_pinned("wiki/p.md") is False


def test_apply_update_page_blocked_on_pinned(vault_setup: Path):
    _write_pinned(vault_setup, "wiki/p.md", pinned=True)
    op = UpdatePage(path="wiki/p.md", content="new", rationale="t")
    with pytest.raises(ValueError, match="pineada"):
        vault.apply_operation(op)


def test_apply_delete_page_blocked_on_pinned(vault_setup: Path):
    _write_pinned(vault_setup, "wiki/p.md", pinned=True)
    op = DeletePage(path="wiki/p.md", rationale="t")
    with pytest.raises(ValueError, match="pineada"):
        vault.apply_operation(op)


def test_apply_add_link_allowed_on_pinned(vault_setup: Path):
    _write_pinned(vault_setup, "wiki/p.md", pinned=True)
    op = AddLink(in_path="wiki/p.md", target_slug="other", rationale="t")
    msg = vault.apply_operation(op)
    assert "added link" in msg


# ──────────────────────────────────────────────────────────────────────────────
# replace_raw (#6)
# ──────────────────────────────────────────────────────────────────────────────


def test_replace_raw_versions_existing(vault_setup: Path):
    vault.add_to_raw("first content", slug="foo")
    res = vault.replace_raw("foo", "second content")
    assert res == {"current": "raw/foo.md", "archived": "raw/foo-v2.md"}
    assert (vault_setup / "raw" / "foo-v2.md").read_text(encoding="utf-8").endswith("first content")


def test_replace_raw_missing_raises(vault_setup: Path):
    with pytest.raises(FileNotFoundError, match="No existe raw"):
        vault.replace_raw("ghost", "x")


def test_replace_raw_cycles_v2_v3(vault_setup: Path):
    vault.add_to_raw("v1", slug="foo")
    vault.replace_raw("foo", "v2")
    res = vault.replace_raw("foo", "v3")
    assert res["archived"] == "raw/foo-v3.md"


def test_replace_raw_writes_new_content(vault_setup: Path):
    vault.add_to_raw("old body", slug="foo")
    vault.replace_raw("foo", "brand new body", source="https://x")
    text = (vault_setup / "raw" / "foo.md").read_text(encoding="utf-8")
    assert "brand new body" in text


# ──────────────────────────────────────────────────────────────────────────────
# Hash dedup en add_to_raw (#7)
# ──────────────────────────────────────────────────────────────────────────────


def test_content_hash_strips_front_matter():
    a = vault._content_hash("---\nfoo: 1\n---\n\nbody text\n")
    b = vault._content_hash("body text")
    assert a == b


def test_add_to_raw_dedup_returns_existing_path(vault_setup: Path):
    first = vault.add_to_raw("body content", slug="foo")
    dup = vault.add_to_raw("body content", slug="bar")
    assert dup == {"path": first["path"], "deduplicated": True}


def test_add_to_raw_writes_content_hash_in_front_matter(vault_setup: Path):
    res = vault.add_to_raw("hello world body", slug="foo")
    text = (vault_setup / res["path"]).read_text(encoding="utf-8")
    assert "content_hash:" in text


def test_add_to_raw_does_not_dedup_legacy_raws_without_hash(vault_setup: Path):
    # Raw "viejo" sin content_hash en su front-matter.
    legacy = vault_setup / "raw" / "legacy.md"
    legacy.write_text("---\nfetched: 2024-01-01\n---\n\nshared body\n", encoding="utf-8")
    res = vault.add_to_raw("shared body\n", slug="newone")
    assert res["deduplicated"] is False


# ──────────────────────────────────────────────────────────────────────────────
# parse_log_entries / recent_entries (#9)
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_log_entries_extracts_basic_fields():
    text = "# Log\n\n## [2024-01-01] ingest | titulo\nbody-line\n"
    entries = vault.parse_log_entries(text)
    assert entries == [{"date": "2024-01-01", "type": "ingest", "title": "titulo", "body": "body-line"}]


def test_parse_log_entries_handles_multiple():
    text = (
        "# Log\n\n## [2024-01-01] ingest | a\nbody-a\n\n"
        "## [2024-01-02] reorganize | b\nbody-b\n"
    )
    entries = vault.parse_log_entries(text)
    assert [e["date"] for e in entries] == ["2024-01-01", "2024-01-02"]


def test_recent_entries_orders_desc_and_limits(vault_setup: Path):
    (vault_setup / "log.md").write_text(
        "# Log\n\n## [2024-01-01] ingest | a\nbody-a\n\n"
        "## [2024-01-02] ingest | b\nbody-b\n\n"
        "## [2024-01-03] ingest | c\nbody-c\n",
        encoding="utf-8",
    )
    out = vault.recent_entries(limit=2)
    assert [e["date"] for e in out] == ["2024-01-03", "2024-01-02"]


def test_recent_entries_filters_by_since(vault_setup: Path):
    (vault_setup / "log.md").write_text(
        "# Log\n\n## [2024-01-01] ingest | a\nbody-a\n\n"
        "## [2024-01-05] ingest | b\nbody-b\n",
        encoding="utf-8",
    )
    out = vault.recent_entries(since="2024-01-03", limit=10)
    assert [e["date"] for e in out] == ["2024-01-05"]
