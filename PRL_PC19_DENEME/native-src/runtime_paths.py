"""Keep writable configuration beside the Windows executable, including frozen builds."""
from pathlib import Path
import sys


def application_root(source_file):
    return Path(sys.executable if getattr(sys, 'frozen', False) else source_file).resolve().parent
