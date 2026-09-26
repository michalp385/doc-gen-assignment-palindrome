"""Print every source file for a client as text, for investigation.

Usage: uv run python scripts/dump_client.py <client>

Images are listed, not read: open them with your image viewer (or the Read tool) and
compare their figures against the JSON and the meeting note.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from document_formatter.loading import read_file  # noqa: E402  (path set up above)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    client_dir = Path("data") / sys.argv[1]
    if not client_dir.is_dir():
        print(f"No such client folder: {client_dir}")
        return 2
    for path in sorted(client_dir.iterdir()):
        print(f"\n########## {path.name} ##########")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            print(f"[image: open {path} to read it]")
        else:
            print(read_file(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
