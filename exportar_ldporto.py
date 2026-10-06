"""Compatibility wrapper. Canonical implementation: scripts/export/exportar_ldporto.py."""
from scripts.export import exportar_ldporto as _implementation


globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith('__')})


if __name__ == '__main__':
    raise SystemExit(_implementation.main())