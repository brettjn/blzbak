"""gitignore-style exclusion pattern handling for blzbak.

Patterns are stored in a .blzbak-ignore file (one per line, same syntax as
.gitignore).  At backup-set creation time the current patterns are copied
into the set's YAML so that future changes to the global ignore file do not
affect existing sets.
"""

from pathlib import Path
from typing import Union

import pathspec


def load_spec(patterns: list[str]) -> pathspec.PathSpec:
    """Build a PathSpec from a list of gitignore-style pattern strings."""
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def load_spec_from_file(path: Union[str, Path]) -> pathspec.PathSpec:
    """Load a PathSpec from a .blzbak-ignore file."""
    path = Path(path)
    if not path.exists():
        return pathspec.PathSpec.from_lines("gitwildmatch", [])
    with open(path) as f:
        lines = [line.rstrip("\n") for line in f]
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def patterns_to_rsync_excludes(patterns: list[str]) -> list[str]:
    """Convert ignore patterns to rsync --exclude=... argument strings."""
    result = []
    for p in patterns:
        p = p.strip()
        if p and not p.startswith("#"):
            result.append(f"--exclude={p}")
    return result
