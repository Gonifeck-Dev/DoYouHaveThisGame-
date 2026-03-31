"""Entry point for the Steam API Helper GUI (used by PyInstaller and direct execution)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the src/ package is on the path whether running from source or bundled.
_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from gui import main  # noqa: E402

if __name__ == "__main__":
    main()
