"""Extraction: every link form resolves the way Obsidian resolves it."""

from __future__ import annotations

from pathlib import Path

import pytest
from kg_utils.specs import EdgeSpec, NodeSpec

from vaultkg.extractor import VaultExtractor
from vaultkg.parse import parse_note, relation_name

RETRIEVAL = "note:wiki/concepts/Retrieval.md"
SEARCH = "note:wiki/concepts/Search.md"
LOST = "note:wiki/sources/Lost in the Middle.md"


def _extract(
    vault: Path, **config
) -> tuple[dict[str, NodeSpec], dict[tuple[str, str, str], EdgeSpec]]:
    nodes: dict[str, NodeSpec] = {}
    edges: dict[tuple[str, str, str], EdgeSpec] = {}
    for item in VaultExtractor(vault, config).extract():
        if isinstance(item, NodeSpec):
            assert item.node_id not in nodes, f"duplicate node {item.node_id}"
            nodes[item.node_id] = item
        else:
            edges[(item.source_id, item.relation, item.target_id)] = item
    return nodes, edges


@pytest.fixture
def graph(vault: Path):
    return _extract(vault)


def test_notes_and_skipped_folders(graph) -> None:
    nodes, _ = graph
    notes = sorted(n for n, s in nodes.items() if s.kind == "note")
    assert RETRIEVAL in notes and "note:Orphan.md" in notes
    assert not any(".obsidian" in n for n in nodes)


def test_exclude_pattern(vault: Path) -> None:
    nodes, _ = _extract(vault, exclude=["templates"])
    assert "note:templates/concept.md" not in nodes


def test_heading_hierarchy(graph) -> None:
    _, edges = graph
    h1 = "heading:wiki/concepts/Retrieval.md#retrieval-augmented-generation"
    h2 = "heading:wiki/concepts/Retrieval.md#failure-modes"
    h3 = "heading:wiki/concepts/Retrieval.md#deep-section"
    assert (RETRIEVAL, "CONTAINS", h1) in edges
    assert (h1, "CONTAINS", h2) in edges
    assert (h2, "CONTAINS", h3) in edges


def test_heading_span_and_text(graph) -> None:
    nodes, _ = graph
    h2 = nodes["heading:wiki/concepts/Retrieval.md#failure-modes"]
    assert h2.lineno is not None and h2.end_lineno is not None
    assert h2.end_lineno > h2.lineno
    assert "Long contexts lose the middle" in h2.docstring
    assert h2.qualname.endswith("#Retrieval augmented generation > Failure modes")


def test_plain_link_with_alias_prefers_same_folder(graph) -> None:
    _, edges = graph
    e = edges[(RETRIEVAL, "LINKS_TO", SEARCH)]
    assert e.metadata["aliases"] == ["search engines"]
    assert e.metadata["ambiguous"] is True  # two notes are named Search


def test_typed_links_inline_and_frontmatter(graph) -> None:
    _, edges = graph
    assert (RETRIEVAL, "SUPPORTS", LOST) in edges  # (supports:: [[...]])
    assert (RETRIEVAL, "EXTENDS", SEARCH) in edges  # extends: "[[Search]]"
    # Unquoted [[X]] in YAML parses as a nested list; still a typed link.
    assert (LOST, "CONTRADICTS", "missing:long context replaces rag") in edges


def test_heading_anchor_targets_heading(graph) -> None:
    _, edges = graph
    assert (SEARCH, "LINKS_TO", "heading:wiki/concepts/Retrieval.md#failure-modes") in edges


def test_alias_resolution(graph) -> None:
    _, edges = graph
    assert (LOST, "LINKS_TO", RETRIEVAL) in edges  # [[RAG]] is an alias


def test_markdown_links_relative_and_folder(graph) -> None:
    _, edges = graph
    assert ("note:wiki/sources/Search.md", "LINKS_TO", RETRIEVAL) in edges
    assert ("note:projects/p1/README.md", "LINKS_TO", SEARCH) in edges
    assert ("note:index.md", "LINKS_TO", "note:projects/p1/README.md") in edges
    # A bare Markdown file name is a relative path, not a name search.
    e = edges[(LOST, "LINKS_TO", "note:wiki/sources/Search.md")]
    assert "ambiguous" not in e.metadata


def test_title_falls_back_to_h1(graph) -> None:
    nodes, _ = graph
    assert nodes["note:projects/p1/README.md"].metadata["title"] == "Project one"


def test_unresolved_and_attachment(graph) -> None:
    nodes, edges = graph
    assert nodes["missing:nowhere"].kind == "symbol"
    assert (RETRIEVAL, "EMBEDS", "attachment:assets/diagram.png") in edges
    assert nodes["attachment:assets/diagram.png"].kind == "attachment"


def test_code_and_comments_are_not_links(graph) -> None:
    nodes, _ = graph
    for fake in ("missing:fake", "missing:alsofake", "missing:hidden", "tag:nope"):
        assert fake not in nodes


def test_tags_frontmatter_inline_and_nested(graph) -> None:
    nodes, edges = graph
    assert {"tag:ml", "tag:ml/retrieval", "tag:core", "tag:deep-tag"} <= set(nodes)
    assert ("tag:ml", "CONTAINS", "tag:ml/retrieval") in edges
    assert (RETRIEVAL, "TAGGED", "tag:deep-tag") in edges


def test_temporal_metadata(graph) -> None:
    nodes, _ = graph
    assert nodes[LOST].metadata["occurred_start"] == "2023-07-06"
    assert nodes[RETRIEVAL].metadata["recorded_at"] == "2026-03-01"
    assert nodes[RETRIEVAL].metadata["aliases"] == ["RAG"]


def test_deterministic(vault: Path) -> None:
    a = list(VaultExtractor(vault).extract())
    b = list(VaultExtractor(vault).extract())
    assert a == b


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("see [[A|x\\|y]]", ("A", "", "x|y")),
        ("[[Page#Head|Alias]]", ("Page", "Head", "Alias")),
    ],
)
def test_link_splitting(line: str, expected: tuple[str, str, str]) -> None:
    (link,) = parse_note(line).links
    assert (link.target, link.anchor, link.alias) == expected


def test_field_only_at_line_start_or_bracketed() -> None:
    links = parse_note("- up:: [[Home]]\nratio a:: [[B]] mid-sentence\n").links
    assert [(lk.target, lk.relation) for lk in links] == [("Home", "UP"), ("B", "")]


def test_relation_name() -> None:
    assert relation_name("part-of") == "PART_OF"
    assert relation_name("See also") == "SEE_ALSO"


def test_bad_frontmatter_is_reported_not_fatal() -> None:
    note = parse_note("---\ntitle: [unclosed\n---\n# Body\n[[X]]\n")
    assert note.frontmatter == {} and note.frontmatter_error
    assert [lk.target for lk in note.links] == ["X"]


def test_unicode_decomposed_file_name(tmp_path: Path) -> None:
    import unicodedata  # noqa: PLC0415

    # macOS writes file names decomposed; the link is typed composed.
    nfd = unicodedata.normalize("NFD", "Café")
    (tmp_path / f"{nfd}.md").write_text("# Café\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("[[Café]]\n", encoding="utf-8")
    nodes, edges = _extract(tmp_path)
    assert ("note:a.md", "LINKS_TO", f"note:{nfd}.md") in edges
    assert not any(n.startswith("missing:") for n in nodes)


def test_heading_text_keeps_inner_hash() -> None:
    heads = parse_note("## C#\n### Closed ##\n").headings
    assert [h.text for h in heads] == ["C#", "Closed"]


def test_multiline_comment() -> None:
    text = "a [[One]] %% start\n[[Hidden]]\nend %% [[Two]] %%x%% [[Three]]\n"
    assert [lk.target for lk in parse_note(text).links] == ["One", "Two", "Three"]
