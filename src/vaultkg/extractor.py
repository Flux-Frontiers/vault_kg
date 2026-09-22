"""extractor.py -- turn an Obsidian vault into NodeSpec / EdgeSpec records.

Nodes
-----
``note``        one Markdown file (``note:<path>``)
``heading``     one section of a note (``heading:<path>#<slug>``)
``tag``         one tag, nested tags chained by CONTAINS (``tag:<tag>``)
``attachment``  a non-Markdown file a note embeds or links (``attachment:<path>``)
``symbol``      a link target no file answers to (``missing:<target>``); the SDK
                keeps ``symbol`` nodes out of search results and out of
                ``meaningful_nodes``, which is right for a page that does not exist

Edges
-----
``CONTAINS``    note -> top heading, heading -> subheading, tag -> nested tag
``LINKS_TO``    a plain ``[[wikilink]]`` or ``[text](note.md)``
``EMBEDS``      ``![[note]]`` / ``![[image.png]]``
``TAGGED``      note -> tag
typed           ``supports:: [[X]]`` or ``supports: ["[[X]]"]`` in frontmatter
                becomes ``SUPPORTS``; any key works, normalised by
                :func:`~vaultkg.parse.relation_name`

Wikilinks resolve the way Obsidian resolves them: an exact vault path first,
then a path relative to the linking note, then the file name anywhere in the
vault (same folder preferred, then the shortest path), then a frontmatter
alias. A Markdown link is a path (relative to the note, else to the vault
root) and never resolves by name, so it is never ambiguous. A
``#Heading`` anchor that matches a heading in the target points the edge at
that heading. Repeated links between the same two nodes with the same
relation collapse into one edge whose weight is the count.
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from kg_utils.extractor import KGExtractor
from kg_utils.specs import EdgeSpec, NodeSpec
from kg_utils.temporal import parse_temporal, temporal_metadata

from vaultkg.parse import Heading, Link, ParsedNote, parse_note

NODE_KINDS = ["note", "heading", "tag", "attachment", "symbol"]
STRUCTURAL_RELS = ["CONTAINS", "LINKS_TO", "EMBEDS", "TAGGED"]

#: Directories never walked: tool state, not notes. Any dot-directory is also
#: skipped (``.obsidian``, ``.git``, ``.trash``, ``.vaultkg``...).
DEFAULT_EXCLUDE = ("node_modules", "__pycache__")

#: Embedded text caps. The default embedding model reads ~256 tokens, so more
#: than this only costs time.
NOTE_TEXT_CHARS = 1500
SECTION_TEXT_CHARS = 1000
#: Per-edge evidence caps (line numbers and alias texts kept on an edge).
EVIDENCE_CAP = 10


@dataclass
class _Note:
    """A note as the extractor sees it: path plus parsed parts."""

    path: str  # vault-relative POSIX path, with extension
    parsed: ParsedNote
    heading_ids: list[str]

    @property
    def stem(self) -> str:
        return posixpath.splitext(posixpath.basename(self.path))[0]

    @property
    def key(self) -> str:
        """Lower-cased path without extension, the resolution key."""
        return _fold(posixpath.splitext(self.path)[0])


def _fold(text: str) -> str:
    """Case- and Unicode-fold a name for matching.

    macOS stores file names decomposed (NFD) while typed text is composed
    (NFC), so ``[[Café]]`` only finds ``Café.md`` once both are normalised.
    Only lookup keys are folded; node ids and paths keep the real file name.
    """
    return unicodedata.normalize("NFC", text).lower()


def slug(text: str) -> str:
    """Anchor slug for a heading: lower-case words joined by ``-``.

    :param text: Heading text.
    :return: Slug; ``section`` when the text has no word characters.
    """
    s = re.sub(r"[^\w\s-]", "", _fold(text))
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "section"


def _anchor_key(text: str) -> str:
    """Normalise a heading or anchor for matching (case, spacing, punctuation)."""
    return re.sub(r"[^\w]+", " ", _fold(text)).strip()


def _snip(text: str, cap: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    return text if len(text) <= cap else text[:cap].rsplit(" ", 1)[0] + " ..."


class VaultExtractor(KGExtractor):
    """Extractor for an Obsidian-style Markdown vault.

    :param repo_path: Vault root.
    :param config: Optional ``{"exclude": [...]}``: directory names or glob
        patterns (matched against vault-relative POSIX paths) to skip, in
        addition to :data:`DEFAULT_EXCLUDE` and every dot-directory.
    """

    def __init__(self, repo_path: Path, config: dict[str, Any] | None = None) -> None:
        super().__init__(repo_path, config)
        self.exclude: tuple[str, ...] = DEFAULT_EXCLUDE + tuple(self.config.get("exclude") or ())
        self._typed_rels: set[str] = set()

    # ------------------------------------------------------------ contract
    def node_kinds(self) -> list[str]:
        return list(NODE_KINDS)

    def edge_kinds(self) -> list[str]:
        return STRUCTURAL_RELS + sorted(self._typed_rels)

    def meaningful_node_kinds(self) -> list[str]:
        # Only nodes that carry prose are embedded; tags, attachments and
        # missing pages are reached by graph expansion from them.
        return ["note", "heading"]

    # ------------------------------------------------------------ walking
    def _excluded(self, rel: str, name: str) -> bool:
        if name.startswith("."):
            return True
        return any(
            name == pat or fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
            for pat in self.exclude
        )

    def _walk(self) -> tuple[list[str], list[str]]:
        """Vault-relative POSIX paths of notes and of other files, sorted."""
        notes: list[str] = []
        others: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.repo_path):
            rel_dir = Path(dirpath).relative_to(self.repo_path).as_posix()
            rel_dir = "" if rel_dir == "." else rel_dir
            dirnames[:] = sorted(
                d for d in dirnames if not self._excluded(posixpath.join(rel_dir, d), d)
            )
            for name in sorted(filenames):
                rel = posixpath.join(rel_dir, name)
                if self._excluded(rel, name):
                    continue
                (notes if name.lower().endswith(".md") else others).append(rel)
        return sorted(notes), sorted(others)

    # ------------------------------------------------------------ extract
    def extract(self) -> Iterator[NodeSpec | EdgeSpec]:
        note_paths, other_paths = self._walk()
        notes: list[_Note] = []
        for path in note_paths:
            text = (self.repo_path / path).read_text(encoding="utf-8", errors="replace")
            notes.append(_Note(path, parse_note(text), []))

        resolver = _Resolver(notes, other_paths)
        tag_ids: set[str] = set()
        missing: dict[str, str] = {}  # node id -> display target
        attachments: set[str] = set()
        edges: dict[tuple[str, str, str], dict[str, Any]] = {}

        def add_edge(src: str, dst: str, rel: str, **evidence: Any) -> None:
            e = edges.setdefault((src, dst, rel), {"count": 0, "lines": [], "aliases": []})
            e["count"] += 1
            line = evidence.get("line")
            if line and len(e["lines"]) < EVIDENCE_CAP:
                e["lines"].append(line)
            alias = evidence.get("alias")
            if alias and alias not in e["aliases"] and len(e["aliases"]) < EVIDENCE_CAP:
                e["aliases"].append(alias)
            if evidence.get("ambiguous"):
                e["ambiguous"] = True

        for note in notes:
            yield self._note_spec(note)
            yield from self._heading_specs(note, add_edge)

        for note in notes:
            src = f"note:{note.path}"
            for tag in note.parsed.tags:
                parts = tag.split("/")
                for depth in range(1, len(parts) + 1):
                    tid = "tag:" + _fold("/".join(parts[:depth]))
                    if depth > 1:
                        parent = "tag:" + _fold("/".join(parts[: depth - 1]))
                        edges.setdefault((parent, tid, "CONTAINS"), {"count": 1})
                    tag_ids.add(tid)
                add_edge(src, "tag:" + _fold(tag), "TAGGED")

            for link in note.parsed.links:
                rel = link.relation or ("EMBEDS" if link.embed else "LINKS_TO")
                if link.relation:
                    self._typed_rels.add(link.relation)
                dst, ambiguous = resolver.resolve(note, link)
                if dst is None:
                    continue  # a self-link to the note as a whole
                if dst.startswith("missing:"):
                    missing[dst] = link.target
                elif dst.startswith("attachment:"):
                    attachments.add(dst)
                add_edge(src, dst, rel, line=link.line, alias=link.alias, ambiguous=ambiguous)

        for tid in sorted(tag_ids):
            name = tid.removeprefix("tag:")
            yield NodeSpec(
                node_id=tid,
                kind="tag",
                name="#" + name,
                qualname=name,
                source_path="",
                docstring=f"Tag {name.replace('/', ' ')}",
            )
        for aid in sorted(attachments):
            path = aid.removeprefix("attachment:")
            yield NodeSpec(
                node_id=aid,
                kind="attachment",
                name=posixpath.basename(path),
                qualname=path,
                source_path="",
                metadata={"path": path},
            )
        for mid in sorted(missing):
            yield NodeSpec(
                node_id=mid,
                kind="symbol",
                name=missing[mid],
                qualname=missing[mid],
                source_path="",
                metadata={"unresolved": True},
            )
        for (src, dst, rel), e in sorted(edges.items()):
            # The store keeps only the evidence JSON, not EdgeSpec.weight, so
            # the link count is recorded there too.
            meta: dict[str, Any] = {"count": e["count"]} if e["count"] > 1 else {}
            if e.get("lines"):
                meta["lines"] = e["lines"]
            if e.get("aliases"):
                meta["aliases"] = e["aliases"]
            if e.get("ambiguous"):
                meta["ambiguous"] = True
            yield EdgeSpec(src, dst, rel, weight=float(e["count"]), metadata=meta)

    # ------------------------------------------------------------ specs
    def _note_spec(self, note: _Note) -> NodeSpec:
        fm = note.parsed.frontmatter
        title = fm.get("title") if isinstance(fm.get("title"), str) else ""
        h1 = next((h.text for h in note.parsed.headings if h.level == 1), "")
        title = title or h1
        aliases = _as_strings(fm.get("aliases", fm.get("alias")))
        summary = next(
            (fm[k] for k in ("description", "summary") if isinstance(fm.get(k), str)), ""
        )
        head = [title or note.stem]
        if aliases:
            head.append("Also known as: " + ", ".join(aliases))
        if summary:
            head.append(summary)
        body = note.parsed.body
        meta: dict[str, Any] = {
            "title": title or note.stem,
            "words": len(body.split()),
        }
        if isinstance(fm.get("type"), str):
            meta["type"] = fm["type"]
        if aliases:
            meta["aliases"] = aliases
        if note.parsed.tags:
            meta["tags"] = note.parsed.tags
        if note.parsed.frontmatter_error:
            meta["frontmatter_error"] = note.parsed.frontmatter_error
        meta.update(_note_dates(fm))
        return NodeSpec(
            node_id=f"note:{note.path}",
            kind="note",
            name=note.stem,
            qualname=posixpath.splitext(note.path)[0],
            source_path=note.path,
            lineno=1,
            end_lineno=max(1, len(note.parsed.lines)),
            docstring=_snip("\n".join(head) + "\n\n" + body, NOTE_TEXT_CHARS),
            metadata=meta,
        )

    def _heading_specs(self, note: _Note, add_edge: Any) -> Iterator[NodeSpec]:
        stack: list[tuple[Heading, str, str]] = []  # (heading, id, trail)
        used: dict[str, int] = {}
        lines = note.parsed.lines
        for h in note.parsed.headings:
            while stack and stack[-1][0].level >= h.level:
                stack.pop()
            trail = " > ".join([s[0].text for s in stack] + [h.text])
            base = slug(h.text)
            used[base] = used.get(base, 0) + 1
            hid = f"heading:{note.path}#{base}" + (f"~{used[base]}" if used[base] > 1 else "")
            note.heading_ids.append(hid)
            parent = stack[-1][1] if stack else f"note:{note.path}"
            add_edge(parent, hid, "CONTAINS")
            section = "\n".join(lines[h.line : h.end_line])
            yield NodeSpec(
                node_id=hid,
                kind="heading",
                name=h.text,
                qualname=f"{posixpath.splitext(note.path)[0]}#{trail}",
                source_path=note.path,
                lineno=h.line,
                end_lineno=h.end_line,
                docstring=_snip(f"{trail}\n\n{section}", SECTION_TEXT_CHARS),
                metadata={"level": h.level, "note": note.path},
            )
            stack.append((h, hid, trail))


class _Resolver:
    """Obsidian-style link resolution over one vault."""

    def __init__(self, notes: list[_Note], other_paths: list[str]) -> None:
        self.by_key: dict[str, _Note] = {n.key: n for n in notes}
        self.by_stem: dict[str, list[_Note]] = {}
        self.by_alias: dict[str, list[_Note]] = {}
        for n in notes:
            self.by_stem.setdefault(_fold(n.stem), []).append(n)
            for a in _as_strings(n.parsed.frontmatter.get("aliases")):
                self.by_alias.setdefault(_fold(a), []).append(n)
        self.files: dict[str, str] = {_fold(p): p for p in other_paths}
        self.file_names: dict[str, list[str]] = {}
        for p in other_paths:
            self.file_names.setdefault(_fold(posixpath.basename(p)), []).append(p)

    def resolve(self, src: _Note, link: Link) -> tuple[str | None, bool]:
        """Node id a link points at, and whether it was one of several candidates.

        :return: ``(node_id, ambiguous)``. ``node_id`` is ``None`` for a link to
            the linking note itself with no anchor.
        """
        target = (unquote(link.target) if link.markdown else link.target).strip().lstrip("/")
        if not target:
            # [[#Heading]]: a link within the same note.
            return self._heading(src, link.anchor), False
        ext = posixpath.splitext(target)[1].lower()
        if ext != ".md":
            # A real file wins over a note of the same name, as in Obsidian:
            # [[diagram.png]] is the image even if "diagram.png.md" existed.
            path, ambiguous = self._file(src, target)
            if path is not None:
                return "attachment:" + path, ambiguous
        if target.endswith("/"):
            # A folder link, as GitHub renders it: the folder's README/index.
            for page in ("README", "index"):
                note, _ = self._note(src, target + page, exact=True)
                if note is not None:
                    return f"note:{note.path}", False
            return "missing:" + _fold(target), False
        # A Markdown link is a path, relative to the note or to the vault root,
        # never a name to search for; only a wikilink resolves by name.
        note, ambiguous = self._note(
            src, target[:-3] if ext == ".md" else target, exact=link.markdown
        )
        if note is None:
            return "missing:" + _fold(target), False
        if note is src and not link.anchor:
            return None, False
        hid = self._heading(note, link.anchor) if link.anchor else None
        return hid or f"note:{note.path}", ambiguous

    def _note(self, src: _Note, target: str, *, exact: bool = False) -> tuple[_Note | None, bool]:
        key = _fold(target)
        if "/" in key or exact:
            rel = _fold(posixpath.normpath(posixpath.join(posixpath.dirname(src.path), key)))
            for cand in (rel, key) if exact else (key, rel):
                if cand in self.by_key:
                    return self.by_key[cand], False
        if exact:
            return None, False
        candidates = self.by_stem.get(posixpath.basename(key), [])
        if "/" in key:
            candidates = [c for c in candidates if c.key.endswith(key)]
        if not candidates:
            candidates = self.by_alias.get(key, [])
        if not candidates:
            return None, False
        src_dir = posixpath.dirname(src.path)
        best = sorted(
            candidates,
            key=lambda c: (posixpath.dirname(c.path) != src_dir, c.path.count("/"), c.path),
        )[0]
        return best, len(candidates) > 1

    def _file(self, src: _Note, target: str) -> tuple[str | None, bool]:
        key = _fold(target)
        rel = _fold(posixpath.normpath(posixpath.join(posixpath.dirname(src.path), key)))
        for cand in (key, rel):
            if cand in self.files:
                return self.files[cand], False
        candidates = self.file_names.get(posixpath.basename(key), [])
        if not candidates:
            return None, False
        return sorted(candidates, key=lambda p: (p.count("/"), p))[0], len(candidates) > 1

    @staticmethod
    def _heading(note: _Note, anchor: str) -> str | None:
        if not anchor or anchor.startswith("^"):
            return None
        want = _anchor_key(anchor.split("#")[-1])
        for h, hid in zip(note.parsed.headings, note.heading_ids, strict=False):
            if _anchor_key(h.text) == want or slug(h.text) == slug(anchor):
                return hid
        return None


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return []


def _note_dates(fm: dict[str, Any]) -> dict[str, str]:
    """Fleet temporal keys from frontmatter.

    ``date`` is when the note's subject happened (a meeting, a journal day);
    ``created`` is when the note was written. File modification times are not
    used: they change on every clone and would make the build nondeterministic.
    """

    def ok(v: Any) -> Any:
        try:
            return v if parse_temporal(v) else None
        except (ValueError, TypeError):
            return None

    return temporal_metadata(occurred_start=ok(fm.get("date")), recorded_at=ok(fm.get("created")))
