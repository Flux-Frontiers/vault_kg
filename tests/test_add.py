"""vaultkg add: place sources as derived notes, decide collisions by content."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from vaultkg.add import add_sources, slugify
from vaultkg.cli import cli
from vaultkg.module import CONFIG_FILE, load_config


def _fm(note: Path) -> dict:
    return yaml.safe_load(note.read_text(encoding="utf-8").split("\n---", 1)[0][3:])


@pytest.fixture
def src(tmp_path: Path) -> Path:
    d = tmp_path / "incoming"
    d.mkdir()
    (d / "Field Notes.md").write_text("# Field Notes: Day One\n\nSaw a heron.\n", encoding="utf-8")
    (d / "plain.txt").write_text("No heading here.\n", encoding="utf-8")
    (d / "photo.jpeg").write_bytes(b"\xff\xd8\xff")
    (d / ".hidden.md").write_text("# secret\n", encoding="utf-8")
    return d


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


def test_slugify() -> None:
    assert slugify("Field Notes: Day One") == "field-notes-day-one"
    assert slugify("Café Été") == "cafe-ete"
    assert slugify("!!!") == "untitled"


def test_add_a_folder(vault: Path, src: Path) -> None:
    results = add_sources(vault, [src], kind="articles")
    by_name = {r.source.name: r for r in results}
    assert ".hidden.md" not in by_name
    assert by_name["photo.jpeg"].status == "unsupported"
    note = vault / "RAW" / "articles" / "field-notes.md"
    assert by_name["Field Notes.md"].status == "added"
    assert by_name["Field Notes.md"].note == "RAW/articles/field-notes.md"
    fm = _fm(note)
    assert fm["source_path"] == "Field Notes.md"  # relative to the folder added
    assert fm["title"] == "Field Notes: Day One"  # from the H1, YAML-safe
    assert fm["kind"] == "articles" and fm["converter"] == "passthrough"
    assert fm["original"] == "RAW/articles/files/field-notes.md"
    assert len(fm["source_sha256"]) == 64 and fm["ingested_at"]
    assert (vault / "RAW" / "articles" / "files" / "field-notes.md").exists()
    assert "Saw a heron." in note.read_text(encoding="utf-8")
    assert not (vault / ".vaultkg" / "graph.sqlite").exists()  # never touches the graph


def test_readding_the_same_file_is_identical(vault: Path, src: Path) -> None:
    add_sources(vault, [src / "plain.txt"], kind="documents")
    before = (vault / "RAW" / "documents" / "plain.md").read_bytes()
    (result,) = add_sources(vault, [src / "plain.txt"], kind="documents")
    assert result.status == "identical"
    assert (vault / "RAW" / "documents" / "plain.md").read_bytes() == before


def test_a_different_file_under_a_taken_name_collides(
    vault: Path, src: Path, tmp_path: Path
) -> None:
    add_sources(vault, [src / "plain.txt"], kind="documents")
    other = tmp_path / "other"
    other.mkdir()
    (other / "plain.txt").write_text("Different content.\n", encoding="utf-8")
    (result,) = add_sources(vault, [other / "plain.txt"], kind="documents")
    assert result.status == "collision" and "--prefix" in result.reason
    (prefixed,) = add_sources(vault, [other / "plain.txt"], kind="documents", prefix="other-")
    assert prefixed.status == "added" and prefixed.note == "RAW/documents/other-plain.md"


def test_a_legacy_note_without_a_hash_matches_by_its_copy(vault: Path, src: Path) -> None:
    """Notes from before vaultkg add carry no source_sha256; the copy decides."""
    d = vault / "RAW" / "documents"
    (d / "files").mkdir(parents=True)
    (d / "plain.md").write_text("---\ntitle: plain\n---\nold\n", encoding="utf-8")
    (d / "files" / "plain.txt").write_bytes((src / "plain.txt").read_bytes())
    (result,) = add_sources(vault, [src / "plain.txt"], kind="documents")
    assert result.status == "identical"


def test_a_differing_original_copy_collides(vault: Path, src: Path) -> None:
    files = vault / "RAW" / "documents" / "files"
    files.mkdir(parents=True)
    (files / "plain.txt").write_text("someone else's file\n", encoding="utf-8")
    (result,) = add_sources(vault, [src / "plain.txt"], kind="documents")
    assert result.status == "collision"
    assert not (vault / "RAW" / "documents" / "plain.md").exists()


def test_no_copy(vault: Path, src: Path) -> None:
    add_sources(vault, [src / "plain.txt"], kind="documents", copy=False)
    assert not (vault / "RAW" / "documents" / "files").exists()
    assert "original" not in _fm(vault / "RAW" / "documents" / "plain.md")


def test_bad_kind_and_missing_path(vault: Path, src: Path) -> None:
    with pytest.raises(ValueError, match="slug"):
        add_sources(vault, [src], kind="Articles")
    with pytest.raises(FileNotFoundError):
        add_sources(vault, [src / "nope.pdf"], kind="articles")


def test_cli_uses_raw_dir_from_config_and_exits_1_on_collision(
    vault: Path, src: Path, tmp_path: Path
) -> None:
    (vault / ".vaultkg").mkdir()
    (vault / CONFIG_FILE).write_text("raw_dir: sources\n", encoding="utf-8")
    runner = CliRunner()
    ok = runner.invoke(
        cli, ["add", "--vault", str(vault), "--kind", "documents", str(src / "plain.txt")]
    )
    assert ok.exit_code == 0, ok.output
    assert (vault / "sources" / "documents" / "plain.md").exists()
    assert "1 added" in ok.output

    other = tmp_path / "o"
    other.mkdir()
    (other / "plain.txt").write_text("changed\n", encoding="utf-8")
    bad = runner.invoke(
        cli, ["add", "--vault", str(vault), "--kind", "documents", str(other / "plain.txt")]
    )
    assert bad.exit_code == 1 and "collision" in bad.output


def test_config_rejects_a_raw_dir_outside_the_vault(vault: Path) -> None:
    (vault / ".vaultkg").mkdir()
    (vault / CONFIG_FILE).write_text("raw_dir: ../elsewhere\n", encoding="utf-8")
    with pytest.raises(ValueError, match="raw_dir"):
        load_config(vault)


def test_add_a_pdf(vault: Path, tmp_path: Path) -> None:
    pymupdf = pytest.importorskip("pymupdf", reason="needs the ingest extra (pymupdf4llm)")
    pytest.importorskip("pymupdf4llm", reason="needs the ingest extra (pymupdf4llm)")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Disulfide bonds stabilize proteins.", fontsize=12)
    pdf = tmp_path / "Paper.pdf"
    doc.save(str(pdf))
    doc.close()
    (result,) = add_sources(vault, [pdf], kind="documents")
    assert result.status == "added"
    fm = _fm(vault / "RAW" / "documents" / "paper.md")
    assert fm["converter"] == "pymupdf4llm" and fm["source_format"] == "pdf" and fm["pages"] == "1"
    assert (vault / "RAW" / "documents" / "files" / "paper.pdf").exists()

    blank = pymupdf.open()
    blank.new_page()
    scan = tmp_path / "scan.pdf"
    blank.save(str(scan))
    blank.close()
    (failed,) = add_sources(vault, [scan], kind="documents")
    assert failed.status == "failed" and "OCR" in failed.reason
    assert not (vault / "RAW" / "documents" / "scan.md").exists()
