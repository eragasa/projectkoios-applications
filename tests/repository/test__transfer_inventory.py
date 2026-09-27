from __future__ import annotations

import hashlib
import subprocess
import tomllib
import unittest
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_TRANSFER_PATH = _REPOSITORY_ROOT / "TRANSFER.toml"


class TransferInventoryTest(unittest.TestCase):
    def test_records_all_authorized_source_and_transfer_target_identities(self) -> None:
        transfer = tomllib.loads(_TRANSFER_PATH.read_text(encoding="utf-8"))
        files = transfer["files"]
        source_paths = tuple(item["source_path"] for item in files)
        target_paths = tuple(item["target_path"] for item in files)

        self.assertEqual(len(files), 122)
        self.assertEqual(len(source_paths), len(set(source_paths)))
        self.assertEqual(len(target_paths), len(set(target_paths)))
        self.assertEqual(transfer["source"]["authorized_file_count"], 122)
        self.assertEqual(transfer["source"]["selected_file_count"], 122)
        self.assertEqual(transfer["source"]["deferred_file_count"], 0)
        self.assertFalse(transfer["boundaries"]["calculator_execution_authorized"])
        simulations = transfer["dependencies"]["simulations"]
        self.assertTrue(simulations["combined_provider_revision_available"])
        self.assertEqual(
            simulations["combined_commit"],
            "24dffe10c29e60afcd5fe07aaacb84921a41a43d",
        )
        self.assertEqual(
            simulations["combined_tree"],
            "b7897a05de39072126e6162ce6e8b8fb25be5f31",
        )

        transfer_commit = transfer["correction"]["transfer_commit"]
        for item in files:
            payload = subprocess.run(
                ["git", "show", f"{transfer_commit}:{item['target_path']}"],
                cwd=_REPOSITORY_ROOT,
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(),
                item["transfer_target_sha256"],
                item["target_path"],
            )

    def test_records_both_corrected_inherited_surfaces(self) -> None:
        transfer = tomllib.loads(_TRANSFER_PATH.read_text(encoding="utf-8"))
        inherited = tuple(
            item
            for item in transfer["files"]
            if item["disposition"] == "selected-inherited-correction-required"
        )
        self.assertEqual(len(inherited), 2)
        self.assertEqual(
            {item["target_capability"] for item in inherited},
            {"pw_dft_scf", "pw_dft_relaxation"},
        )
        self.assertFalse(transfer["correction"]["calculator_execution_authorized"])
        self.assertTrue(transfer["correction"]["combined_provider_validation_complete"])
        self.assertTrue(
            transfer["boundaries"]["combined_provider_compatibility_claimed"]
        )


if __name__ == "__main__":
    unittest.main()
