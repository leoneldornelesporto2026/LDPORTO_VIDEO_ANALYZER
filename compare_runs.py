"""Compatibility wrapper. Canonical implementation: scripts/dev/compare_runs.py."""
from scripts.dev import compare_runs as _implementation


globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith('__')})


if __name__ == '__main__':
    raise SystemExit(_implementation.main())