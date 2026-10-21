"""Entry point for ``python -m orchestration`` (run from the backend/ directory)."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
