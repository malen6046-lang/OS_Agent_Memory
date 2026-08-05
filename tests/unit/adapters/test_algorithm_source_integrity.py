"""Protect the byte-exact Algorithm V1.1 donor snapshots."""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

DONOR_BLOB_SHA1 = {
    "modules/knowledge_retrieval/algorithm_v1_1/bm25.py": (
        "10c6f2cca905372ea2f87e1793c6b9aa6f644d98"
    ),
    "modules/knowledge_retrieval/algorithm_v1_1/conflict_classifier.py": (
        "feb69160f50fbc06dcb813ef742bab0de4af3dd5"
    ),
    "modules/knowledge_retrieval/algorithm_v1_1/hybrid_retriever.py": (
        "ebe63eb90628cab874159a4cda56d11c1865f228"
    ),
    "modules/knowledge_retrieval/algorithm_v1_1/knowledge_service.py": (
        "7c35363468a5d63589eb14bb9ee648ce83b33920"
    ),
    "modules/knowledge_retrieval/algorithm_v1_1/memory_tier.py": (
        "97591da03d40341f5f830ab99193b1786c6ce357"
    ),
    "modules/preference_safety/algorithm_v1_1/preference_service.py": (
        "5b8e332de6940b79a73bd4f9bd3a4365a3242d11"
    ),
    "modules/preference_safety/algorithm_v1_1/safety_service.py": (
        "1aebf2ff4a8b2058f0a96da5221f437d39ccd1f5"
    ),
    "modules/preference_safety/algorithm_v1_1/forget_service.py": (
        "cbbf2666d3335028e711e3ed0f8821e8f099b93a"
    ),
}

CORE_ENTRY_POINTS = (
    (
        "modules.knowledge_retrieval.algorithm_v1_1",
        "bm25",
        "BM25Retriever",
    ),
    (
        "modules.knowledge_retrieval.algorithm_v1_1",
        "conflict_classifier",
        "ConflictClassifier",
    ),
    (
        "modules.knowledge_retrieval.algorithm_v1_1",
        "hybrid_retriever",
        "HybridRetriever",
    ),
    (
        "modules.knowledge_retrieval.algorithm_v1_1",
        "knowledge_service",
        "KnowledgeService",
    ),
    (
        "modules.knowledge_retrieval.algorithm_v1_1",
        "memory_tier",
        "MemoryTierStore",
    ),
    (
        "modules.preference_safety.algorithm_v1_1",
        "preference_service",
        "PreferenceService",
    ),
    (
        "modules.preference_safety.algorithm_v1_1",
        "safety_service",
        "SafetyService",
    ),
    (
        "modules.preference_safety.algorithm_v1_1",
        "forget_service",
        "ForgetService",
    ),
)


def _git_blob_sha1(path: Path) -> str:
    """Return Git's SHA-1 for a blob without invoking the Git executable."""
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


@pytest.mark.parametrize(
    ("relative_path", "expected_sha1"),
    DONOR_BLOB_SHA1.items(),
)
def test_algorithm_donor_git_blob_is_unchanged(
    relative_path: str,
    expected_sha1: str,
) -> None:
    donor_path = REPOSITORY_ROOT / relative_path

    assert donor_path.is_file(), f"missing donor source: {relative_path}"
    assert _git_blob_sha1(donor_path) == expected_sha1


@pytest.mark.parametrize(
    ("package_name", "module_name", "class_name"),
    CORE_ENTRY_POINTS,
)
def test_algorithm_donor_core_class_entry_point(
    package_name: str,
    module_name: str,
    class_name: str,
) -> None:
    package = importlib.import_module(package_name)
    donor_module = importlib.import_module(f"{package_name}.{module_name}")
    exported_class = getattr(package, class_name)

    assert class_name in package.__all__
    assert inspect.isclass(exported_class)
    assert exported_class is getattr(donor_module, class_name)
