"""Absolute-path entry point for Windows login startup."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.button_launcher import main

if __name__ == '__main__':
    main()
