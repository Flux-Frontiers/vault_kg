"""add.py -- place source documents into a vault as derived notes.

``vaultkg add`` converts each source file with the SDK's converters
(:mod:`kg_utils.ingest`: PDF via ``pymupdf4llm``, office formats via
``anydoc``, LaTeX and HTML via ``pandoc``, Markdown and text as they are) and
writes it to ``<vault>/<raw_dir>/<kind>/<slug>.md`` with provenance
frontmatter (:func:`kg_utils.ingest.write_derived`). The original is copied
to ``<raw_dir>/<kind>/files/`` unless ``copy=False``.

Nothing here reads or writes the graph, and nothing calls a model: placing a
source is deterministic, and turning it into wiki pages is the agent's job.

Collisions are decided by content, not by name. If the slug is taken by a
note whose ``source_sha256`` matches the new file, the file is skipped as
already added; any other occupant is an error, resolved with ``prefix``.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from kg_utils.ingest import (
    ConversionError,
    default_converters,
    resolve_converter,
    sha256_file,
    write_derived,
)

Status = Literal["added", "identical", "unsupported", "collision", "failed"]

#: Statuses that make ``vaultkg add`` exit non-zero.
FAILURES: frozenset[str] = frozenset({"collision", "failed"})

_KIND_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_H1_RE = re.compile(r"^# +(.+?) *#*$", re.M)


@dataclass(frozen=True)
class AddResult:
    """What happened to one source file.

    :param source: The source file.
    :param status: ``added``, ``identical``, ``unsupported``, ``collision`` or
        ``failed``.
    :param note: Vault-relative path of the derived note (empty when none).
    :param reason: Why it was skipped or failed (empty when added).
    """

    source: Path
    status: Status
    note: str = ""
    reason: str = ""


def slugify(name: str) -> str:
    """Lowercase, hyphen-joined ASCII form of *name*.

    :param name: A file stem, possibly with spaces, accents or punctuation.
    :return: The slug; ``"untitled"`` when nothing usable remains.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "untitled"


def _frontmatter_sha(note: Path) -> str:
    """Return the ``source_sha256`` recorded in *note*, or ``""``."""
    text = note.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return ""
    head = text.split("\n---", 1)[0][3:]
    try:
        data = yaml.safe_load(head) or {}
    except yaml.YAMLError:
        return ""
    return str(data.get("source_sha256", "")) if isinstance(data, dict) else ""


def _iter_sources(paths: list[Path]) -> list[tuple[Path, Path]]:
    """Expand files and folders into ``(source, source_root)`` pairs.

    A named file's root is its own folder, so only its name is recorded; a
    folder's files are recorded relative to that folder. Dotfiles and
    dot-folders are skipped.
    """
    found: list[tuple[Path, Path]] = []
    for raw in paths:
        p = raw.expanduser().resolve()
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                rel = f.relative_to(p).parts
                if f.is_file() and not any(part.startswith(".") for part in rel):
                    found.append((f, p))
        else:
            found.append((p, p.parent))
    return found


def add_sources(
    vault: Path,
    paths: list[Path],
    *,
    kind: str,
    raw_dir: str = "RAW",
    prefix: str = "",
    copy: bool = True,
) -> list[AddResult]:
    """Convert and place each source under ``<vault>/<raw_dir>/<kind>/``.

    :param vault: Vault root.
    :param paths: Files and/or folders (folders are walked recursively).
    :param kind: Sub-folder of *raw_dir*, a lowercase hyphenated slug.
    :param raw_dir: Vault-relative folder for sources (from config).
    :param prefix: Prepended to every slug, to separate same-named files.
    :param copy: Copy each original to ``<kind>/files/``.
    :return: One :class:`AddResult` per source file, in order.
    :raises ValueError: If *kind* is not a slug.
    :raises FileNotFoundError: If a named path does not exist.
    """
    if not _KIND_RE.match(kind):
        raise ValueError(f"kind must be a lowercase hyphenated slug, got {kind!r}")
    for p in paths:
        if not p.expanduser().exists():
            raise FileNotFoundError(f"no such file or folder: {p}")

    target = Path(vault).resolve() / raw_dir / kind
    converters = default_converters()
    results: list[AddResult] = []
    for source, root in _iter_sources(paths):
        converter = resolve_converter(source, converters)
        if converter is None:
            results.append(
                AddResult(
                    source, "unsupported", reason=f"unsupported format: {source.suffix or '(none)'}"
                )
            )
            continue

        slug = slugify(prefix + source.stem)
        note = target / f"{slug}.md"
        copy_dest = target / "files" / f"{slug}{source.suffix.lower()}"
        rel_note = note.relative_to(Path(vault).resolve()).as_posix()
        digest = sha256_file(source)
        if note.exists():
            recorded = _frontmatter_sha(note)
            if recorded == digest or (
                not recorded and copy_dest.exists() and sha256_file(copy_dest) == digest
            ):
                results.append(
                    AddResult(source, "identical", rel_note, "already added (same content)")
                )
            else:
                results.append(
                    AddResult(
                        source,
                        "collision",
                        rel_note,
                        f"{rel_note} holds a different source; rerun with --prefix",
                    )
                )
            continue

        if copy and copy_dest.exists() and sha256_file(copy_dest) != digest:
            rel_copy = copy_dest.relative_to(Path(vault).resolve()).as_posix()
            results.append(
                AddResult(
                    source,
                    "collision",
                    rel_note,
                    f"{rel_copy} holds a different original; rerun with --prefix",
                )
            )
            continue

        try:
            result = converter.convert(source)
        except ConversionError as exc:
            results.append(AddResult(source, "failed", reason=str(exc)))
            continue

        h1 = _H1_RE.search("\n".join(result.markdown.splitlines()[:40]))
        title = result.metadata.get("title") or (h1.group(1) if h1 else source.stem)
        extra = {"kind": kind, "title": title, "words": str(len(result.markdown.split()))}
        if copy:
            extra["original"] = copy_dest.relative_to(Path(vault).resolve()).as_posix()
        write_derived(result, source, note, source_root=root, extra=extra)
        if copy:
            copy_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, copy_dest)
        results.append(AddResult(source, "added", rel_note))
    return results
