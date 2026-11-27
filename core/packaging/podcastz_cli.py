"""Entry point for the frozen CLI (PyInstaller) that the desktop app bundles as its sidecar."""
import sys

from podcastz.cli import main

if __name__ == '__main__':
    sys.exit(main())
