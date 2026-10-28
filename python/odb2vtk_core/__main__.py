"""Execute a complete export request with ``python -m odb2vtk_core``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
