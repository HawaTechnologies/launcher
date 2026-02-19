import os
import glob
from pathlib import Path, PurePosixPath, PurePath
from typing import Iterable, Iterator, Optional, Set, List, Tuple


def _iter_yes_roots(reference_dir: Path, yes_pattern: str) -> Iterator[Path]:
    """
    Resolve YES glob relative to reference_dir.
    Silently ignore anything escaping reference_dir.
    """

    reference_dir = reference_dir.resolve()
    rel_glob = yes_pattern.lstrip("/")
    abs_glob = (reference_dir / rel_glob).as_posix()

    print("abs_glob:", abs_glob)
    for s in glob.iglob(abs_glob, recursive=True):
        print("s (1):", s)
        try:
            p = Path(s).resolve(strict=True)
        except FileNotFoundError:
            continue

        print("s (2):", s)
        # 🔒 Containment check
        try:
            p.relative_to(reference_dir)
        except ValueError:
            # Escapes reference_dir → ignore silently
            continue

        yield p


def _walk_tree_including_self(root: Path) -> Iterator[Path]:
    """
    Yield root, then all descendants (dirs + files).
    """
    yield root
    if root.is_dir():
        # os.walk is fast and includes all descendants.
        for dirpath, dirnames, filenames in os.walk(root):
            dp = Path(dirpath)
            # subdirs
            for d in dirnames:
                yield dp / d
            # files
            for f in filenames:
                yield dp / f


def _posix_relpath_under(base: Path, p: Path) -> Optional[PurePosixPath]:
    """
    Return p relative to base as a PurePosixPath, or None if p is not under base.
    """
    try:
        rel = p.resolve().relative_to(base.resolve())
    except Exception:
        return None
    # Force POSIX path semantics for matching patterns with "/"
    return PurePosixPath(rel.as_posix())


def _matches_any_but(reference_dir: Path, candidate: Path, but_patterns: Iterable[str]) -> bool:
    """
    Evaluate BUT patterns with glob-style matching against the candidate path,
    expressed as a path relative to reference_dir.
    """

    rel = _posix_relpath_under(reference_dir, candidate)
    if rel is None:
        return False

    # Our stored patterns are normalized like "/some/thing/**".
    # PurePosixPath.match expects patterns without a leading "/".
    for but_pat in but_patterns:
        pat = but_pat.lstrip("/")
        pat2 = but_pat.strip("/") + "/**"
        if PurePath(rel).full_match(pat) or PurePath(rel).full_match(pat2):
            return True
    return False


def enumerate(
    clauses: List[Tuple[str, List[str]]],
    reference_dir: str | Path
) -> Iterator[Path]:
    """
    Main generator:
    - Parses Yes/But clauses from a save-filters structure.
    - Enumerates the resulting files and directories in the `yes`
      patterns and not in the respectively contained `but` patterns.
    - Yields the paths (absolute) under reference_dir, de-duplicated.
    """

    reference_dir = Path(reference_dir).resolve()
    print("Reference dir:", reference_dir)

    seen: Set[Path] = set()
    for clause in clauses:
        yes, but = clause
        print("Yes:", yes)
        for but_ in but:
            print("But:", but_)

        # 1. Each YES clause is traversed and enumerated.
        for yes_root in _iter_yes_roots(reference_dir, yes):
            # It will match a file or a directory. In this case,
            # the elements in the directory are matched recursively.

            for candidate in _walk_tree_including_self(yes_root):
                # If the file does not exist, then it's ignored.

                if not candidate.exists():
                    continue

                # If candidate matches ANY BUT clause, exclude it.
                if _matches_any_but(reference_dir, candidate, but):
                    continue

                # De-dupe across multiple YES clauses
                cand_resolved = candidate.resolve()
                if cand_resolved in seen:
                    continue
                seen.add(cand_resolved)

                yield cand_resolved
