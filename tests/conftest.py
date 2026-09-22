"""Shared fixtures: a small vault exercising every link form, and a stub embedder."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import pytest
from kg_utils.embedder import Embedder

NOTES = {
    "wiki/concepts/Retrieval.md": """---
title: Retrieval augmented generation
type: concept
created: 2026-03-01
aliases: [RAG]
tags: [ml/retrieval, core]
extends: "[[Search]]"
---

# Retrieval augmented generation

Retrieval feeds documents to a model at query time. See [[Search|search engines]].

## Failure modes

Long contexts lose the middle (supports:: [[Lost in the Middle]]).
A link to [[Nowhere]] and an embed ![[diagram.png]].

### Deep section

Nested under failure modes. #deep-tag
""",
    "wiki/concepts/Search.md": """# Search

Plain search. Back to [[Retrieval#Failure modes]].

```python
# not a link: [[Fake]] and not a tag: #nope
```

Inline `[[AlsoFake]]` code. %% hidden [[Hidden]] %%
""",
    "wiki/sources/Lost in the Middle.md": """---
date: 2023-07-06
contradicts: [[Long context replaces RAG]]
---
# Lost in the Middle

Models ignore the middle of long contexts. Cites [[RAG]] and [the local one](Search.md).
""",
    "wiki/sources/Search.md": """# Search (source)

A second note named Search, for ambiguity. [Relative](../concepts/Retrieval.md)
""",
    "Orphan.md": "Nobody links here and it links nowhere.\n",
    "projects/p1/README.md": "# Project one\n\n[wiki](../../wiki/concepts/Search.md)\n",
    "index.md": "# Index\n\n[projects](projects/p1/) and [[Retrieval]].\n",
    ".obsidian/workspace.md": "[[Retrieval]] should never be read.\n",
    "templates/concept.md": "# {{title}}\n",
}
FILES = {"assets/diagram.png": b"\x89PNG"}


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    for rel, text in NOTES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for rel, data in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


class HashEmbedder(Embedder):
    """Deterministic bag-of-words hashing embedder: no model download."""

    dim = 64

    def embed_texts(self, texts: list[str], encode_batch_size: int = 32) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dim
            for tok in re.findall(r"[a-z]+", text.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out
