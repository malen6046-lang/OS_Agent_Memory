"""Architecture gates for the backend-first integration stage."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from app.core.config import ConfigManager
from app.dependencies import build_service_container
from app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_API_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/events/ingest"),
    ("POST", "/api/v1/memory/search"),
    ("POST", "/api/v1/forget/preview"),
    ("POST", "/api/v1/forget/execute"),
    ("POST", "/api/v1/evaluations/run"),
}


def _static_import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                roots.add(node.module.partition(".")[0])
            else:
                roots.update(alias.name.partition(".")[0] for alias in node.names)
    return roots


def _violations(paths: list[Path], forbidden: set[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in paths:
        imports = sorted(_static_import_roots(path) & forbidden)
        if imports:
            found[path.relative_to(PROJECT_ROOT).as_posix()] = imports
    return found


def test_backend_stage_keeps_the_six_frozen_api_routes() -> None:
    paths = app.openapi()["paths"]
    registered = {
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api/v1/")
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert registered == EXPECTED_API_ROUTES


def test_api_layer_does_not_import_repositories_or_algorithm_modules() -> None:
    api_files = sorted((PROJECT_ROOT / "app" / "api").rglob("*.py"))
    api_files.append(PROJECT_ROOT / "app" / "dependencies" / "api_service.py")

    assert _violations(api_files, {"repositories", "modules"}) == {}


@pytest.mark.parametrize("profile", ["default", "development"])
def test_default_and_development_assembly_stay_algorithm_free(
    profile: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency_files = sorted(
        (PROJECT_ROOT / "app" / "dependencies").rglob("*.py")
    )
    composition_files = [PROJECT_ROOT / "app" / "main.py", *dependency_files]
    assert _violations(composition_files, {"modules"}) == {}

    for name in list(os.environ):
        if name.upper().startswith("OS_AGENT_"):
            monkeypatch.delenv(name)

    container = build_service_container(ConfigManager().load(profile))
    assembled_components = {
        "preference_service": container.preference_service,
        "safety_service": container.safety_service,
        "forget_service": container.forget_service,
        "knowledge_service": container.knowledge_service,
        "retriever": container.retriever,
        "embedding_provider": container.embedding_provider,
        "vector_store": container.vector_store,
    }
    algorithm_components = {
        name: type(component).__module__
        for name, component in assembled_components.items()
        if type(component).__module__.partition(".")[0] == "modules"
    }
    assert algorithm_components == {}
