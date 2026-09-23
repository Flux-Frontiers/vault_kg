"""theme.py -- colours shared by the 2-D link graph and the 3-D folder tree.

Kept apart from ``viz.py`` and ``scene.py`` so each can import it without
pulling the other's render stack: this module needs nothing beyond the
standard library.

The categorical palette is Okabe-Ito, which stays distinguishable under the
common forms of colour-vision deficiency. Shape carries node kind in the 2-D
view as a second cue, so no view depends on colour alone.
"""

from __future__ import annotations

from typing import Final

#: Okabe-Ito, minus black. Categories beyond the first seven fold into
#: :data:`OTHER_COLOR`, so a vault with forty folders does not cycle colours
#: and make two unrelated folders look alike.
CATEGORY_PALETTE: Final[tuple[str, ...]] = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
)
OTHER_COLOR: Final[str] = "#999999"

#: Legend label for notes at the vault root, which belong to no folder.
ROOT_LABEL: Final[str] = "(vault root)"

#: Backlink-count buckets, pale to dark, and their upper bounds (inclusive).
#: A note nothing links to is the palest; a hub is the darkest.
LINK_BUCKETS: Final[tuple[tuple[int, str], ...]] = (
    (0, "#DEEBF7"),
    (1, "#9ECAE1"),
    (3, "#6BAED6"),
    (7, "#3182BD"),
    (10**9, "#08519C"),
)

#: Node colour per kind in the 2-D view. A missing note (``symbol``) is grey:
#: it is a gap in the vault, not a note.
KIND_COLOR: Final[dict[str, str]] = {
    "note": "#56B4E9",
    "heading": "#9ECAE1",
    "tag": "#009E73",
    "attachment": "#E69F00",
    "symbol": "#8C8C8C",
}

#: Edge colour per relation. Structure within a note stays muted; links
#: between notes are the loud ones. Typed relations not listed here take
#: :data:`TYPED_REL_COLOR`, except the two that carry an argument's shape.
REL_COLOR: Final[dict[str, str]] = {
    "LINKS_TO": "#7A9CC6",
    "EMBEDS": "#B07AA1",
    "CONTAINS": "#4A5568",
    "TAGGED": "#3F7F6A",
    "SUPPORTS": "#2CA02C",
    "CONTRADICTS": "#D62728",
}
TYPED_REL_COLOR: Final[str] = "#E69F00"


def category_colors(categories: list[str]) -> dict[str, str]:
    """Assign palette colours to categories, largest first.

    :param categories: Category names ordered by importance (for example by
        note count, descending). Order decides who gets a real colour.
    :return: Category to hex colour; everything past the palette is
        :data:`OTHER_COLOR`.
    """
    return {
        c: CATEGORY_PALETTE[i] if i < len(CATEGORY_PALETTE) else OTHER_COLOR
        for i, c in enumerate(categories)
    }


def top_folder(path: str) -> str:
    """A note's top-level folder, or :data:`ROOT_LABEL` for a note at the root.

    :param path: Vault-relative note path, ``wiki/concepts/X.md``.
    :return: ``wiki``, or ``(vault root)``.
    """
    return path.split("/")[0] if "/" in path else ROOT_LABEL


def link_bucket(backlinks: int) -> int:
    """Index into :data:`LINK_BUCKETS` for a backlink count.

    :param backlinks: Distinct notes linking in.
    :return: Bucket index, 0 (none) to ``len(LINK_BUCKETS) - 1`` (hub).
    """
    for i, (upper, _) in enumerate(LINK_BUCKETS):
        if backlinks <= upper:
            return i
    return len(LINK_BUCKETS) - 1
