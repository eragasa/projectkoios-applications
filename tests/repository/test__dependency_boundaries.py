from __future__ import annotations

import ast
import unittest
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _REPOSITORY_ROOT / "src/python/projectkoios/applications"
_ALLOWED_PROJECT_PREFIXES = (
    "projectkoios.applications",
    "projectkoios.ingestion",
    "projectkoios.references",
    "projectkoios.simulations",
)


class DependencyBoundaryTest(unittest.TestCase):
    def test_package_imports_only_owned_component_contracts(
        self,
    ) -> None:
        violations: list[str] = []
        for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: tuple[str, ...]
                if isinstance(node, ast.Import):
                    modules = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    modules = (node.module,)
                else:
                    continue
                for module in modules:
                    if module.startswith("projectkoios.") and not module.startswith(
                        _ALLOWED_PROJECT_PREFIXES
                    ):
                        violations.append(
                            f"{path.relative_to(_REPOSITORY_ROOT)}: {module}"
                        )
        self.assertEqual(violations, [])

    def test_package_does_not_contain_execution_or_process_modules(self) -> None:
        forbidden = {"subprocess", "multiprocessing", "asyncio.subprocess"}
        violations: list[str] = []
        for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    modules = {node.module}
                else:
                    continue
                if modules & forbidden:
                    violations.append(str(path.relative_to(_REPOSITORY_ROOT)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
