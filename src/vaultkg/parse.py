"""parse.py -- read one Obsidian note into its structural parts.

Everything here is syntax, not interpretation: frontmatter is YAML, a heading
is an ATX ``#`` line, a link is ``[[...]]`` or ``[...](x.md)``, a typed link is
a Dataview inline field (``key:: [[X]]``) or a frontmatter key whose value holds
wikilinks. Nothing is inferred from prose, so the same file always yields the
same parts.

Code is not markup: wikilinks, tags and fields inside fenced blocks, inline
code spans and ``%%`` comments are masked out before any of them are matched.
Masking replaces characters with spaces, so match positions still line up with
the original text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

# ``[[target]]``, ``[[target|alias]]``, ``![[embed]]``. ``\|`` is how a pipe is
# written inside a Markdown table cell, so it is unescaped before splitting.
WIKILINK = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
# ``[text](target)`` with an optional quoted title; the target has no spaces
# unless it is wrapped in angle brackets.
MDLINK = re.compile(r"(!?)\[([^\]\n]*)\]\((<[^>\n]+>|[^)\s]+)(?:\s+\"[^\"\n]*\")?\)")
# The closing ``#`` run only counts after a space: ``## C#`` is the heading "C#".
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
COMMENT = re.compile(r"%%.*?%%")
# An Obsidian tag: ``#`` not preceded by a word character, slash, ``#`` or
# ``&`` (which would make it a URL fragment, a heading marker or an entity),
# and at least one non-digit (``#123`` is not a tag in Obsidian).
TAG = re.compile(r"(?<![\w/#&])#([\w/-]*[^\W\d][\w/-]*)")
FIELD_KEY = re.compile(r"([A-Za-z][\w-]*)::")

#: Frontmatter keys that describe the note itself rather than relate it to
#: another note, so a wikilink in one of them is not a typed link.
RESERVED_KEYS = frozenset(
    {"aliases", "alias", "tags", "tag", "title", "type", "cssclasses", "cssclass", "publish"}
)


@dataclass(frozen=True)
class Link:
    """One link occurrence in a note.

    :param target: Page part of the target, as written (no ``#anchor``).
    :param anchor: Heading or ``^block`` after ``#``; empty when absent.
    :param alias: Display text after ``|``; empty when absent.
    :param line: 1-based line the link sits on (0 for frontmatter links).
    :param embed: True for ``![[...]]`` and ``![...](...)``.
    :param relation: Typed-link key (``supports``) or empty for a plain link.
    :param markdown: True for a ``[...](path)`` link rather than a wikilink.
    """

    target: str
    anchor: str
    alias: str
    line: int
    embed: bool = False
    relation: str = ""
    markdown: bool = False


@dataclass(frozen=True)
class Heading:
    """One ATX heading and the section it opens.

    :param level: 1-6.
    :param text: Heading text with trailing ``#`` stripped.
    :param line: 1-based line of the heading.
    :param end_line: Last line of its section (before the next heading of the
        same or a higher level, or the end of the file).
    """

    level: int
    text: str
    line: int
    end_line: int


@dataclass
class ParsedNote:
    """Structural parts of one note.

    :param frontmatter: Parsed YAML mapping; empty when absent or invalid.
    :param frontmatter_error: YAML error message, or empty.
    :param body_start: 1-based line where the body begins (after frontmatter).
    :param lines: All lines of the file, without newlines.
    :param headings: Headings in file order.
    :param links: Links in file order; frontmatter links first.
    :param tags: Distinct tags, frontmatter first, without ``#``.
    """

    frontmatter: dict[str, Any]
    frontmatter_error: str
    body_start: int
    lines: list[str]
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        """The note text after the frontmatter."""
        return "\n".join(self.lines[self.body_start - 1 :])


def relation_name(key: str) -> str:
    """Normalise a typed-link key to an edge relation: ``part-of`` -> ``PART_OF``.

    :param key: Frontmatter key or inline-field key.
    :return: Upper-case relation name.
    """
    return re.sub(r"[^A-Za-z0-9]+", "_", key.strip()).strip("_").upper()


def split_target(raw: str) -> tuple[str, str, str]:
    """Split a wikilink body into ``(target, anchor, alias)``.

    :param raw: Text between ``[[`` and ``]]``.
    :return: Page target, anchor after ``#`` and alias after ``|``, each stripped.
    """
    raw = raw.replace("\\|", "|")
    target, _, alias = raw.partition("|")
    page, _, anchor = target.partition("#")
    return page.strip(), anchor.strip(), alias.strip()


def _read_frontmatter(lines: list[str]) -> tuple[dict[str, Any], str, int]:
    """Parse a leading ``---`` YAML block.

    :param lines: File lines.
    :return: ``(mapping, error, body_start)``.
    """
    if not lines or lines[0].strip() != "---":
        return {}, "", 1
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            block = "\n".join(lines[1:i])
            try:
                data = yaml.safe_load(block) if block.strip() else {}
            except yaml.YAMLError as exc:
                return {}, str(exc).splitlines()[0], i + 2
            if not isinstance(data, dict):
                return {}, "frontmatter is not a mapping", i + 2
            return {str(k): v for k, v in data.items()}, "", i + 2
    # An unterminated block is body text in Obsidian, not frontmatter.
    return {}, "", 1


def _mask(lines: list[str], body_start: int) -> list[str]:
    """Blank out code, comments and frontmatter, keeping line lengths.

    :param lines: File lines.
    :param body_start: First body line (1-based); earlier lines are blanked.
    :return: Masked copy of ``lines``.
    """
    out: list[str] = []
    fence: str | None = None
    in_comment = False
    for idx, line in enumerate(lines, start=1):
        if idx < body_start:
            out.append(" " * len(line))
            continue
        m = FENCE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append(" " * len(line))
            continue
        if m and not in_comment:
            fence = m.group(1)
            out.append(" " * len(line))
            continue
        masked = INLINE_CODE.sub(lambda mm: " " * len(mm.group(0)), line)
        # Close a comment left open by an earlier line before pairing new ones.
        if in_comment:
            close = masked.find("%%")
            if close < 0:
                out.append(" " * len(line))
                continue
            masked = " " * (close + 2) + masked[close + 2 :]
            in_comment = False
        masked = COMMENT.sub(lambda mm: " " * len(mm.group(0)), masked)
        # A ``%%`` left unpaired opens a comment that runs onto later lines.
        opened = masked.find("%%")
        if opened >= 0:
            masked = masked[:opened] + " " * (len(masked) - opened)
            in_comment = True
        out.append(masked)
    return out


def _field_spans(line: str) -> list[tuple[int, int, str]]:
    """Locate Dataview inline fields on a masked line.

    A field is ``key:: value``. Bracketed as ``(key:: value)`` or
    ``[key:: value]`` its value ends at the matching close bracket; otherwise it
    runs to the end of the line.

    :param line: One masked line.
    :return: ``(value_start, value_end, relation)`` spans.
    """
    spans: list[tuple[int, int, str]] = []
    for m in FIELD_KEY.finditer(line):
        before = line[: m.start()].rstrip()
        opener = before[-1:] if before else ""
        start = m.end()
        if opener in "([" and opener:
            close = {"(": ")", "[": "]"}[opener]
            depth, end = 0, len(line)
            for j in range(start, len(line)):
                ch = line[j]
                if ch == opener:
                    depth += 1
                elif ch == close:
                    if depth == 0:
                        end = j
                        break
                    depth -= 1
            spans.append((start, end, relation_name(m.group(1))))
        elif not before or before.endswith(("-", "*", "+", ">")):
            # Only a field that starts the line (or a list item / quote) is
            # unbracketed; ``a:: b`` mid-sentence is not a Dataview field.
            spans.append((start, len(line), relation_name(m.group(1))))
    return spans


def _headings(masked: list[str], body_start: int) -> list[Heading]:
    """Find ATX headings and close each section.

    :param masked: Masked lines.
    :param body_start: First body line.
    :return: Headings with section end lines filled in.
    """
    found: list[tuple[int, str, int]] = []
    for idx in range(body_start, len(masked) + 1):
        m = HEADING.match(masked[idx - 1])
        if m:
            found.append((len(m.group(1)), m.group(2).strip(), idx))
    out: list[Heading] = []
    for i, (level, text, line) in enumerate(found):
        end = len(masked)
        for level2, _, line2 in found[i + 1 :]:
            if level2 <= level:
                end = line2 - 1
                break
        out.append(Heading(level, text, line, end))
    return out


def _frontmatter_links(frontmatter: dict[str, Any]) -> list[Link]:
    """Typed links from frontmatter keys whose values hold wikilinks.

    :param frontmatter: Parsed frontmatter.
    :return: One :class:`Link` per wikilink, relation set from the key.
    """
    links: list[Link] = []
    for key in sorted(frontmatter):
        if key.lower() in RESERVED_KEYS:
            continue
        rel = relation_name(key)
        if not rel:
            continue
        stack: list[Any] = [frontmatter[key]]
        values: list[str] = []
        while stack:
            v = stack.pop(0)
            if isinstance(v, str):
                values.append(v)
            elif isinstance(v, list):
                stack[0:0] = v
            # YAML reads an unquoted ``[[X]]`` as a nested list ``[["X"]]``.
            # Flattening it above yields the bare ``X``, which is caught below.
        raw_value = frontmatter[key]
        bare_nested = _bare_nested_links(raw_value)
        for text in values:
            for m in WIKILINK.finditer(text):
                page, anchor, alias = split_target(m.group(2))
                if page or anchor:
                    links.append(Link(page, anchor, alias, 0, bool(m.group(1)), rel))
        for page in bare_nested:
            p, anchor, alias = split_target(page)
            if p:
                links.append(Link(p, anchor, alias, 0, False, rel))
    return links


def _bare_nested_links(value: Any) -> list[str]:
    """Targets written as unquoted ``[[X]]`` in YAML, which parses as ``[["X"]]``.

    :param value: A frontmatter value.
    :return: The link bodies found this way.
    """
    out: list[str] = []
    items = value if isinstance(value, list) else [value]
    # ``key: [[X]]`` -> [["X"]]; ``key: [[[X]], [[Y]]]`` -> [[["X"]], [["Y"]]].
    for item in items:
        while isinstance(item, list) and len(item) == 1 and isinstance(item[0], list):
            item = item[0]
        if (
            isinstance(item, list)
            and len(item) == 1
            and isinstance(item[0], str)
            and isinstance(value, list)
        ):
            out.append(item[0])
    return out


def _frontmatter_tags(frontmatter: dict[str, Any]) -> list[str]:
    """Tags from ``tags:`` / ``tag:``, as a list or a comma/space separated string.

    :param frontmatter: Parsed frontmatter.
    :return: Tags without a leading ``#``.
    """
    out: list[str] = []
    for key in ("tags", "tag"):
        raw = frontmatter.get(key)
        items: list[Any]
        if isinstance(raw, str):
            items = re.split(r"[,\s]+", raw)
        elif isinstance(raw, list):
            items = raw
        else:
            continue
        for item in items:
            if item is None:
                continue
            t = str(item).strip().lstrip("#").strip()
            if t:
                out.append(t)
    return out


def parse_note(text: str) -> ParsedNote:
    """Parse one note's text.

    :param text: Full file contents.
    :return: The note's frontmatter, headings, links and tags.
    """
    lines = text.splitlines()
    frontmatter, fm_error, body_start = _read_frontmatter(lines)
    masked = _mask(lines, body_start)
    note = ParsedNote(frontmatter, fm_error, body_start, lines)
    note.headings = _headings(masked, body_start)
    note.links.extend(_frontmatter_links(frontmatter))

    tags = _frontmatter_tags(frontmatter)
    for idx, line in enumerate(masked, start=1):
        if not line.strip():
            continue
        fields = _field_spans(line)

        def _rel(pos: int, fields: list[tuple[int, int, str]] = fields) -> str:
            for start, end, rel in fields:
                if start <= pos < end:
                    return rel
            return ""

        link_spans: list[tuple[int, int]] = []
        for m in WIKILINK.finditer(line):
            link_spans.append(m.span())
            page, anchor, alias = split_target(m.group(2))
            if not page and not anchor:
                continue
            note.links.append(Link(page, anchor, alias, idx, bool(m.group(1)), _rel(m.start())))
        for m in MDLINK.finditer(line):
            link_spans.append(m.span())
            target = m.group(3).strip("<>")
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue  # http:, mailto:, obsidian: ...
            page, _, anchor = target.partition("#")
            if not page and not anchor:
                continue
            note.links.append(
                Link(page, anchor, m.group(2).strip(), idx, bool(m.group(1)), _rel(m.start()), True)
            )

        # Tags: never inside a link (``[[#Heading]]``, ``(#anchor)``) and never
        # the heading marker itself (``# Title`` has a space, so TAG skips it).
        scan = list(line)
        for a, b in link_spans:
            scan[a:b] = " " * (b - a)
        for m in TAG.finditer("".join(scan)):
            tags.append(m.group(1).rstrip("/"))

    seen: set[str] = set()
    for t in tags:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            note.tags.append(t)
    return note
