import ast
from pathlib import Path


def test_frontend_does_not_import_backend_or_database_implementations():
    frontend_root = Path(__file__).resolve().parents[1]
    forbidden_roots = {
        "adapters",
        "app",
        "contracts",
        "modules",
        "repositories",
        "sqlalchemy",
        "sqlite3",
    }

    imported_roots: set[str] = set()
    for source_path in frontend_root.rglob("*.py"):
        if "tests" in source_path.parts:
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(forbidden_roots)
