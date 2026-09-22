"""VaultKG -- Obsidian-style Markdown vaults as fleet knowledge graphs.

The graph comes from what the notes already say: wikilinks, embeds, headings,
tags and typed links. Nothing is extracted by a language model.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vault-kg")
except PackageNotFoundError:  # running from a source tree
    __version__ = "unknown"

from vaultkg.extractor import VaultExtractor  # noqa: E402
from vaultkg.module import VaultKG  # noqa: E402

__all__ = ["VaultExtractor", "VaultKG", "__version__"]
