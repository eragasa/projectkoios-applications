from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tomllib
import unittest
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_TRANSFER_PATH = _REPOSITORY_ROOT / "TRANSFER.toml"
_SOURCE_COMMIT = "3eb562f2d6167ec20d6f2c892c517509a7abf283"
_SOURCE_TREE = "e5daec9f5a16e03f998afb9158a101246acd40d1"
_TRANSFER_COMMIT = "4d58422e2ffed6e81c7ef2c73c8e484a8c8358c3"
_TRANSFER_TREE = "b957a5a1a42489466407a369c5516f376ce826b1"
_INVENTORY_SHA256 = "1105306fca28c9bf29815e44f38fb3c91bed922a09f93ee31386a30b4b5d41d9"
_SUBTREES = {
    "implementation": "7a50551ef1f5f03433b58d36e6b3d4b04de010cc",
    "tests": "d4b0c6f22447bf74ebc79e151f9a24bd263ed1e0",
    "documentation": "9923843c1a92acd25579c1495565ccd93419ec17",
    "examples": "a02f7193796323296bb6a79c807c235a20064abd",
}
_FIELDS = (
    "source_path",
    "target_path",
    "mode",
    "git_blob",
    "sha256",
    "byte_size",
    "role",
    "disposition",
)


class TransferInventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transfer = tomllib.loads(_TRANSFER_PATH.read_text(encoding="utf-8"))
        self.files = self.transfer["files"]

    def test_inventory_is_bound_to_independent_expected_identities(self) -> None:
        source = self.transfer["source"]
        self.assertEqual(
            (source["commit"], source["tree"]), (_SOURCE_COMMIT, _SOURCE_TREE)
        )
        self.assertEqual(source["authorized_file_count"], 122)
        self.assertEqual(source["selected_file_count"], 122)
        self.assertEqual(source["deferred_file_count"], 0)
        self.assertEqual(
            {item["role"]: item["git_tree"] for item in source["subtrees"]}, _SUBTREES
        )
        canonical = json.dumps(
            [{key: item[key] for key in _FIELDS} for item in self.files],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), _INVENTORY_SHA256)
        self.assertEqual(len({item["source_path"] for item in self.files}), 122)
        self.assertEqual(len({item["target_path"] for item in self.files}), 122)

    def test_checkout_transfer_targets_match_fixed_transfer_commit(self) -> None:
        if not (_REPOSITORY_ROOT / ".git").exists():
            self.skipTest("Git-object check requires an explicit source checkout")
        self.assertEqual(
            self._git(_REPOSITORY_ROOT, "rev-parse", f"{_TRANSFER_COMMIT}^{{tree}}")
            .decode()
            .strip(),
            _TRANSFER_TREE,
        )
        for item in self.files:
            payload = self._git(
                _REPOSITORY_ROOT, "show", f"{_TRANSFER_COMMIT}:{item['target_path']}"
            )
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(),
                item["transfer_target_sha256"],
                item["target_path"],
            )

    def test_optional_donor_checkout_matches_every_source_object(self) -> None:
        donor_value = os.environ.get("PROJECTKOIOS_FRANKENSTEIN_REPOSITORY")
        if donor_value is None:
            self.skipTest(
                "set PROJECTKOIOS_FRANKENSTEIN_REPOSITORY for donor "
                "Git-object verification"
            )
        donor = Path(donor_value).resolve()
        self.assertEqual(
            self._git(donor, "rev-parse", f"{_SOURCE_COMMIT}^{{tree}}")
            .decode()
            .strip(),
            _SOURCE_TREE,
        )
        for item in self.files:
            entry = (
                self._git(donor, "ls-tree", _SOURCE_COMMIT, "--", item["source_path"])
                .decode()
                .strip()
                .split()
            )
            self.assertEqual(
                entry[:3], [item["mode"], "blob", item["git_blob"]], item["source_path"]
            )
            payload = self._git(
                donor, "show", f"{_SOURCE_COMMIT}:{item['source_path']}"
            )
            self.assertEqual(len(payload), item["byte_size"], item["source_path"])
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(), item["sha256"], item["source_path"]
            )

    def test_records_corrected_surfaces_and_combined_candidate(self) -> None:
        inherited = tuple(
            item
            for item in self.files
            if item["disposition"] == "selected-inherited-correction-required"
        )
        self.assertEqual(
            {item["target_capability"] for item in inherited},
            {"pw_dft_scf", "pw_dft_relaxation"},
        )
        simulations = self.transfer["dependencies"]["simulations"]
        self.assertEqual(
            simulations["combined_commit"], "24dffe10c29e60afcd5fe07aaacb84921a41a43d"
        )
        self.assertEqual(
            simulations["combined_tree"], "b7897a05de39072126e6162ce6e8b8fb25be5f31"
        )
        self.assertFalse(self.transfer["correction"]["calculator_execution_authorized"])
        self.assertTrue(
            self.transfer["correction"]["combined_provider_validation_complete"]
        )

    @staticmethod
    def _git(repository: Path, *arguments: str) -> bytes:
        return subprocess.run(
            ["git", *arguments], cwd=repository, check=True, capture_output=True
        ).stdout


if __name__ == "__main__":
    unittest.main()
