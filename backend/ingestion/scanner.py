from pathlib import Path
from typing import List

_COBOL_EXTENSIONS = {".cbl", ".cob", ".cpy"}

_SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache"}


def scan(root: Path) -> List[Path]:
    """Return sorted list of all COBOL source files found recursively under root."""
    results: List[Path] = []
    _walk(root, results)
    return sorted(results)


def _walk(directory: Path, results: List[Path]) -> None:
    for entry in directory.iterdir():
        if entry.is_dir():
            if entry.name not in _SKIP_DIRS:
                _walk(entry, results)
        elif entry.suffix.lower() in _COBOL_EXTENSIONS:
            results.append(entry)
