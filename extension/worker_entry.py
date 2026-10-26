"""Fixed launcher for Blender's bundled standalone Python (-I)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine.workflow import main

if __name__ == "__main__":
    main()
