from __future__ import annotations

import ast
import unittest
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES_ROOT = _REPOSITORY_ROOT / "examples/projectkoios/applications"


class CalculatorAuthorityTest(unittest.TestCase):
    def test_examples_expose_no_execution_switch_or_authorization_literal(self) -> None:
        violations: list[str] = []
        for path in sorted(_EXAMPLES_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value == "--execute":
                    violations.append(f"{path}: --execute")
                if (
                    isinstance(node, ast.keyword)
                    and node.arg in {"execute", "execution_authorized"}
                    and isinstance(node.value, ast.Constant)
                    and node.value.value is True
                ):
                    violations.append(f"{path}: {node.arg}=True")
        self.assertEqual(violations, [])

    def test_examples_do_not_import_process_execution_modules(self) -> None:
        violations: list[str] = []
        for path in sorted(_EXAMPLES_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    modules = {node.module}
                else:
                    continue
                if modules & {"subprocess", "multiprocessing"}:
                    violations.append(str(path.relative_to(_REPOSITORY_ROOT)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
