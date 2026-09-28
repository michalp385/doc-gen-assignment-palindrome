"""Read a statement-image file into bytes for the vision call (T7/T18, DESIGN.md section
3.3). No `SourceDoc`: an image has no addressable paragraphs to quote-verify against --
P10 treats it as low-trust by design (`extract/image.py`), not as a text source.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageSource:
    path: Path
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def read_image(path: Path) -> ImageSource:
    return ImageSource(path=path, content=path.read_bytes())
