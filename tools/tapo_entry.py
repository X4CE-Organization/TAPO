"""Entry point for standalone TAPO executables."""

import sys

from tapo.cli import main


if __name__ == "__main__":
    sys.exit(main())
