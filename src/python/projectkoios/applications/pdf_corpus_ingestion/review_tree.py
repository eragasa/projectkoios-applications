"""Cycle-free validation for append-only equation-review artifact trees."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from projectkoios.references import AuthorizedRoot

EQUATION_REVIEW_CONTRACT_ID = "projectkoios.applications.pdf-corpus-equation-review"
EQUATION_REVIEW_SCHEMA_VERSION = 3
ASSISTED_EQUATION_ATTEMPT_SCHEMA_VERSION = 2
LEGACY_HUMAN_EQUATION_REVISION_SCHEMA_VERSION = 2
HUMAN_EQUATION_REVISION_SCHEMA_VERSION = 3
MAX_EQUATION_REVIEW_REVISIONS = 9_999
MAX_EQUATION_REVIEW_NOTE_CHARACTERS = 10_000
MAX_ASSISTED_PROPOSAL_CHARACTERS = 100_000
MAX_ASSISTED_PROPOSAL_BYTES = 400_000
MAX_REVIEW_ARTIFACT_BYTES = 20_000_000
MAX_REVIEW_ARTIFACTS = 2 + 4 * MAX_EQUATION_REVIEW_REVISIONS
_MAX_JSON_DEPTH = 32
_MAX_JSON_ITEMS = 200_000
_MAX_JSON_STRING_BYTES = 1_100_000
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION_DIRECTORY = re.compile(r"revision-([0-9]{4})")
_DISPOSITIONS = {
    "ACCEPT_TRANSCRIPTION",
    "REJECT_CANDIDATE",
    "REVISION_REQUIRED",
}


class ReviewTreeValidationError(ValueError):
    """A review artifact tree is partial, malformed, or inconsistently bound."""


@dataclass(frozen=True, slots=True)
class ReviewEvidenceIdentity:
    document_id: str
    candidate_id: str
    source_sha256: str
    candidate_evidence_sha256: str
    region_image_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_evidence_sha256": self.candidate_evidence_sha256,
            "candidate_id": self.candidate_id,
            "document_id": self.document_id,
            "region_image_sha256": self.region_image_sha256,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True, slots=True)
class ValidatedAssistedAttempt:
    method: str
    proposed_latex: str
    proposal_sha256: str
    attempt_id: str


@dataclass(frozen=True, slots=True)
class ValidatedRenderConfirmation:
    renderer_id: str
    renderer_version: str
    rendered_reviewer_latex_sha256: str
    rendered_obsidian_markdown_sha256: str


@dataclass(frozen=True, slots=True)
class ValidatedHumanRevision:
    disposition: str
    assistance_proposal_sha256: str | None
    reviewer_latex: str | None
    reviewer_latex_sha256: str | None
    obsidian_markdown: str | None
    obsidian_markdown_sha256: str | None
    display_mode: str | None
    render_confirmation: ValidatedRenderConfirmation | None
    note: str
    revision: int
    recorded_at_utc: datetime
    revision_id: str
    schema_version: int


@dataclass(frozen=True, slots=True)
class ValidatedReviewTree:
    assisted: ValidatedAssistedAttempt | None
    revisions: tuple[ValidatedHumanRevision, ...]
    paths: frozenset[PurePosixPath]


def validate_review_tree(
    root: AuthorizedRoot,
    *,
    candidate_root: PurePosixPath,
    binding: ReviewEvidenceIdentity,
    expected_paths: set[PurePosixPath] | None = None,
) -> ValidatedReviewTree:
    """Validate one candidate's complete assisted and human review tree."""
    paths = _collect_paths(root, candidate_root)
    if expected_paths is not None and paths != expected_paths:
        raise ReviewTreeValidationError(
            "review tree differs from the enclosing package inventory"
        )
    assisted = _validate_assisted(root, candidate_root, binding, paths)
    revisions = _validate_revisions(root, candidate_root, binding, paths)
    referenced = {
        item.assistance_proposal_sha256
        for item in revisions
        if item.assistance_proposal_sha256 is not None
    }
    if referenced and (assisted is None or referenced != {assisted.proposal_sha256}):
        raise ReviewTreeValidationError(
            "human revision history references unavailable assisted evidence"
        )
    return ValidatedReviewTree(assisted, revisions, frozenset(paths))


def _collect_paths(
    root: AuthorizedRoot,
    candidate_root: PurePosixPath,
) -> set[PurePosixPath]:
    paths: set[PurePosixPath] = set()
    assisted_root = candidate_root / "assisted"
    human_root = candidate_root / "human"
    paths.update(
        _collect_subtree(
            root,
            assisted_root,
            max_files=2,
            max_entries=8,
            max_depth=2,
        )
    )
    paths.update(
        _collect_subtree(
            root,
            human_root,
            max_files=2 * MAX_EQUATION_REVIEW_REVISIONS,
            max_entries=3 * MAX_EQUATION_REVIEW_REVISIONS + 8,
            max_depth=2,
        )
    )
    if len(paths) > MAX_REVIEW_ARTIFACTS:
        raise ReviewTreeValidationError("review tree exceeds its artifact bound")
    return paths


def _collect_subtree(
    root: AuthorizedRoot,
    relative: PurePosixPath,
    *,
    max_files: int,
    max_entries: int,
    max_depth: int,
) -> set[PurePosixPath]:
    state = root.state(relative)
    if state == "missing":
        return set()
    if state != "directory":
        raise ReviewTreeValidationError("review namespace is not a directory")
    try:
        subtree = AuthorizedRoot.existing(
            root.child_path(relative),
            label="equation review subtree",
            root_alias=root.preflight_evidence.root_alias,
            storage_class=root.preflight_evidence.storage_class,
            placeholder_probe=root.placeholder_probe,
        )
        children = subtree.iter_files(
            suffix="",
            recursive=True,
            max_files=max_files,
            max_entries=max_entries,
            max_depth=max_depth,
        )
    except (OSError, ValueError) as error:
        raise ReviewTreeValidationError(
            "review namespace inventory is unsafe"
        ) from error
    return {relative / path for path in children}


def _validate_assisted(
    root: AuthorizedRoot,
    candidate_root: PurePosixPath,
    binding: ReviewEvidenceIdentity,
    paths: set[PurePosixPath],
) -> ValidatedAssistedAttempt | None:
    attempt_root = candidate_root / "assisted/attempt-0001"
    expected_paths = {
        attempt_root / "proposal.txt",
        attempt_root / "manifest.json",
    }
    assisted_paths = {
        path
        for path in paths
        if path.parts[: len(candidate_root.parts) + 1]
        == (*candidate_root.parts, "assisted")
    }
    if not assisted_paths:
        return None
    if assisted_paths != expected_paths:
        raise ReviewTreeValidationError(
            "assisted attempt inventory is partial or unknown"
        )
    proposal = _read_bytes(
        root, attempt_root / "proposal.txt", MAX_ASSISTED_PROPOSAL_BYTES
    )
    try:
        proposed_latex = proposal.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ReviewTreeValidationError(
            "assisted proposal is not valid UTF-8"
        ) from error
    _bounded_text(
        proposed_latex,
        "assisted proposal",
        maximum=MAX_ASSISTED_PROPOSAL_CHARACTERS,
        empty=False,
    )
    manifest, _ = _read_json(root, attempt_root / "manifest.json")
    method = manifest.get("method")
    _bounded_text(method, "assisted method", maximum=500, empty=False)
    proposal_sha256 = hashlib.sha256(proposal).hexdigest()
    identity = {
        **binding.as_dict(),
        "attempt": 1,
        "contract_id": EQUATION_REVIEW_CONTRACT_ID,
        "method": method,
        "proposal_path": "proposal.txt",
        "proposal_sha256": proposal_sha256,
        "schema_version": ASSISTED_EQUATION_ATTEMPT_SCHEMA_VERSION,
        "status": "automated_unreviewed",
    }
    attempt_id = _id("equation-assisted-attempt", identity)
    expected = {
        **identity,
        "artifact_files": [
            {
                "byte_size": len(proposal),
                "relative_path": "proposal.txt",
                "sha256": proposal_sha256,
            }
        ],
        "attempt_id": attempt_id,
    }
    if manifest != expected:
        raise ReviewTreeValidationError("assisted attempt manifest is inconsistent")
    return ValidatedAssistedAttempt(
        method=str(method),
        proposed_latex=proposed_latex,
        proposal_sha256=proposal_sha256,
        attempt_id=attempt_id,
    )


def _validate_revisions(
    root: AuthorizedRoot,
    candidate_root: PurePosixPath,
    binding: ReviewEvidenceIdentity,
    paths: set[PurePosixPath],
) -> tuple[ValidatedHumanRevision, ...]:
    human_prefix = (*candidate_root.parts, "human")
    grouped: dict[int, set[PurePosixPath]] = {}
    for path in paths:
        if path.parts[: len(human_prefix)] != human_prefix:
            continue
        if len(path.parts) != len(human_prefix) + 2:
            raise ReviewTreeValidationError("human revision path is unknown")
        match = _REVISION_DIRECTORY.fullmatch(path.parts[-2])
        if match is None or path.name not in {
            "decision.json",
            "manifest.json",
            "obsidian-markdown.md",
            "reviewer-latex.txt",
        }:
            raise ReviewTreeValidationError("human revision path is unknown")
        revision = int(match.group(1))
        if not 1 <= revision <= MAX_EQUATION_REVIEW_REVISIONS:
            raise ReviewTreeValidationError("human revision number is invalid")
        grouped.setdefault(revision, set()).add(path)
    revisions = tuple(sorted(grouped))
    if revisions != tuple(range(1, len(revisions) + 1)):
        raise ReviewTreeValidationError("human revisions are non-monotonic")
    records: list[ValidatedHumanRevision] = []
    for revision in revisions:
        revision_root = candidate_root / f"human/revision-{revision:04d}"
        required_paths = {
            revision_root / "decision.json",
            revision_root / "manifest.json",
        }
        if not required_paths.issubset(grouped[revision]):
            raise ReviewTreeValidationError("human revision inventory is partial")
        decision, decision_bytes = _read_json(root, revision_root / "decision.json")
        manifest, _ = _read_json(root, revision_root / "manifest.json")
        schema_version = manifest.get("schema_version")
        if schema_version not in {
            LEGACY_HUMAN_EQUATION_REVISION_SCHEMA_VERSION,
            HUMAN_EQUATION_REVISION_SCHEMA_VERSION,
        }:
            raise ReviewTreeValidationError("human revision schema is unsupported")
        proposal_sha256 = manifest.get("assistance_proposal_sha256")
        if proposal_sha256 is not None and (
            not isinstance(proposal_sha256, str)
            or _SHA256.fullmatch(proposal_sha256) is None
        ):
            raise ReviewTreeValidationError("human proposal binding is invalid")
        disposition = manifest.get("disposition")
        if not isinstance(disposition, str) or disposition not in _DISPOSITIONS:
            raise ReviewTreeValidationError("human disposition is invalid")
        if disposition == "ACCEPT_TRANSCRIPTION" and proposal_sha256 is None:
            raise ReviewTreeValidationError("accepted revision has no proposal binding")
        note = manifest.get("note")
        _bounded_text(
            note,
            "human note",
            maximum=MAX_EQUATION_REVIEW_NOTE_CHARACTERS,
            empty=True,
        )
        recorded_at_utc = _parse_utc(manifest.get("recorded_at_utc"))
        reviewer_latex: str | None = None
        reviewer_latex_sha256: str | None = None
        obsidian_markdown: str | None = None
        obsidian_markdown_sha256: str | None = None
        display_mode: str | None = None
        render_confirmation: ValidatedRenderConfirmation | None = None
        if schema_version == LEGACY_HUMAN_EQUATION_REVISION_SCHEMA_VERSION:
            if grouped[revision] != required_paths:
                raise ReviewTreeValidationError("legacy human inventory is invalid")
            identity = {
                **binding.as_dict(),
                "assistance_proposal_sha256": proposal_sha256,
                "contract_id": EQUATION_REVIEW_CONTRACT_ID,
                "disposition": disposition,
                "note": note,
                "revision": revision,
                "schema_version": schema_version,
            }
            artifacts = [
                {
                    "byte_size": len(decision_bytes),
                    "relative_path": "decision.json",
                    "sha256": hashlib.sha256(decision_bytes).hexdigest(),
                }
            ]
        else:
            display_mode_value = manifest.get("display_mode")
            reviewer_latex_path = manifest.get("reviewer_latex_path")
            reviewer_latex_sha256_value = manifest.get("reviewer_latex_sha256")
            obsidian_markdown_path = manifest.get("obsidian_markdown_path")
            obsidian_markdown_sha256_value = manifest.get("obsidian_markdown_sha256")
            render_value = manifest.get("render_confirmation")
            if disposition == "ACCEPT_TRANSCRIPTION":
                expected_paths = required_paths | {
                    revision_root / "obsidian-markdown.md",
                    revision_root / "reviewer-latex.txt",
                }
                if grouped[revision] != expected_paths:
                    raise ReviewTreeValidationError(
                        "accepted human inventory is invalid"
                    )
                if (
                    display_mode_value not in {"INLINE", "DISPLAY"}
                    or reviewer_latex_path != "reviewer-latex.txt"
                    or not isinstance(reviewer_latex_sha256_value, str)
                    or obsidian_markdown_path != "obsidian-markdown.md"
                    or not isinstance(obsidian_markdown_sha256_value, str)
                ):
                    raise ReviewTreeValidationError(
                        "accepted representation binding is invalid"
                    )
                display_mode = str(display_mode_value)
                reviewer_latex_bytes = _read_bytes(
                    root,
                    revision_root / "reviewer-latex.txt",
                    MAX_ASSISTED_PROPOSAL_BYTES,
                )
                try:
                    reviewer_latex = reviewer_latex_bytes.decode(
                        "utf-8", errors="strict"
                    )
                except UnicodeDecodeError as error:
                    raise ReviewTreeValidationError(
                        "reviewer LaTeX is not valid UTF-8"
                    ) from error
                _bounded_text(
                    reviewer_latex,
                    "reviewer LaTeX",
                    maximum=MAX_ASSISTED_PROPOSAL_CHARACTERS,
                    empty=False,
                )
                try:
                    canonical_reviewer_latex_body(reviewer_latex)
                except ValueError as error:
                    raise ReviewTreeValidationError(
                        "reviewer LaTeX is not a canonical math body"
                    ) from error
                reviewer_latex_sha256 = hashlib.sha256(reviewer_latex_bytes).hexdigest()
                if reviewer_latex_sha256_value != reviewer_latex_sha256:
                    raise ReviewTreeValidationError("reviewer LaTeX hash is invalid")
                obsidian_markdown_bytes = _read_bytes(
                    root,
                    revision_root / "obsidian-markdown.md",
                    MAX_ASSISTED_PROPOSAL_BYTES + 5,
                )
                try:
                    obsidian_markdown = obsidian_markdown_bytes.decode(
                        "utf-8", errors="strict"
                    )
                except UnicodeDecodeError as error:
                    raise ReviewTreeValidationError(
                        "Obsidian Markdown is not valid UTF-8"
                    ) from error
                expected_markdown = canonical_obsidian_markdown(
                    reviewer_latex,
                    display_mode,
                )
                if obsidian_markdown != expected_markdown:
                    raise ReviewTreeValidationError(
                        "Obsidian Markdown is not canonical"
                    )
                obsidian_markdown_sha256 = hashlib.sha256(
                    obsidian_markdown_bytes
                ).hexdigest()
                if obsidian_markdown_sha256_value != obsidian_markdown_sha256:
                    raise ReviewTreeValidationError("Obsidian Markdown hash is invalid")
                render_confirmation = _validate_render_confirmation(
                    render_value,
                    reviewer_latex_sha256,
                    obsidian_markdown_sha256,
                )
                artifacts = [
                    {
                        "byte_size": len(decision_bytes),
                        "relative_path": "decision.json",
                        "sha256": hashlib.sha256(decision_bytes).hexdigest(),
                    },
                    {
                        "byte_size": len(obsidian_markdown_bytes),
                        "relative_path": "obsidian-markdown.md",
                        "sha256": obsidian_markdown_sha256,
                    },
                    {
                        "byte_size": len(reviewer_latex_bytes),
                        "relative_path": "reviewer-latex.txt",
                        "sha256": reviewer_latex_sha256,
                    },
                ]
            else:
                if grouped[revision] != required_paths:
                    raise ReviewTreeValidationError(
                        "non-acceptance human inventory is invalid"
                    )
                if any(
                    value is not None
                    for value in (
                        display_mode_value,
                        reviewer_latex_path,
                        reviewer_latex_sha256_value,
                        obsidian_markdown_path,
                        obsidian_markdown_sha256_value,
                        render_value,
                    )
                ):
                    raise ReviewTreeValidationError(
                        "non-acceptance carries accepted representations"
                    )
                artifacts = [
                    {
                        "byte_size": len(decision_bytes),
                        "relative_path": "decision.json",
                        "sha256": hashlib.sha256(decision_bytes).hexdigest(),
                    }
                ]
            render_identity = (
                None
                if render_confirmation is None
                else {
                    "renderer_id": render_confirmation.renderer_id,
                    "renderer_version": render_confirmation.renderer_version,
                    "rendered_obsidian_markdown_sha256": (
                        render_confirmation.rendered_obsidian_markdown_sha256
                    ),
                    "rendered_reviewer_latex_sha256": (
                        render_confirmation.rendered_reviewer_latex_sha256
                    ),
                }
            )
            identity = {
                **binding.as_dict(),
                "assistance_proposal_sha256": proposal_sha256,
                "contract_id": EQUATION_REVIEW_CONTRACT_ID,
                "display_mode": display_mode_value,
                "disposition": disposition,
                "note": note,
                "obsidian_markdown_path": obsidian_markdown_path,
                "obsidian_markdown_sha256": obsidian_markdown_sha256_value,
                "render_confirmation": render_identity,
                "reviewer_latex_path": reviewer_latex_path,
                "reviewer_latex_sha256": reviewer_latex_sha256_value,
                "revision": revision,
                "schema_version": schema_version,
            }
        revision_id = _id("equation-human-revision", identity)
        expected_decision = {
            **identity,
            "recorded_at_utc": _utc_text(recorded_at_utc),
            "revision_id": revision_id,
        }
        expected_manifest = {
            **expected_decision,
            "artifact_files": artifacts,
            "status": "human-reviewed",
        }
        if decision != expected_decision or manifest != expected_manifest:
            raise ReviewTreeValidationError("human revision manifest is inconsistent")
        records.append(
            ValidatedHumanRevision(
                disposition=disposition,
                assistance_proposal_sha256=proposal_sha256,
                reviewer_latex=reviewer_latex,
                reviewer_latex_sha256=reviewer_latex_sha256,
                obsidian_markdown=obsidian_markdown,
                obsidian_markdown_sha256=obsidian_markdown_sha256,
                display_mode=display_mode,
                render_confirmation=render_confirmation,
                note=str(note),
                revision=revision,
                recorded_at_utc=recorded_at_utc,
                revision_id=revision_id,
                schema_version=int(schema_version),
            )
        )
    return tuple(records)


def canonical_reviewer_latex_body(value: str) -> str:
    """Require exact NFC math-body text without Markdown math delimiters."""
    if value != value.strip():
        raise ValueError("reviewer LaTeX has leading or trailing whitespace")
    if "\r" in value:
        raise ValueError("reviewer LaTeX contains a carriage return")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("reviewer LaTeX is not NFC-normalized")
    if (
        len(value) >= 2
        and value.startswith("$")
        and value.endswith("$")
        and _is_unescaped(value, len(value) - 1)
    ):
        raise ValueError("reviewer LaTeX contains outer math delimiters")
    return value


def _is_unescaped(value: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and value[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 0


def canonical_obsidian_markdown(reviewer_latex: str, display_mode: str) -> str:
    """Derive the only accepted Obsidian Markdown wrapper representation."""
    canonical_reviewer_latex_body(reviewer_latex)
    if display_mode == "INLINE":
        return f"${reviewer_latex}$"
    if display_mode == "DISPLAY":
        return f"$$\n{reviewer_latex}\n$$"
    raise ValueError("display mode is unsupported")


def _validate_render_confirmation(
    value: object,
    reviewer_latex_sha256: str,
    obsidian_markdown_sha256: str,
) -> ValidatedRenderConfirmation:
    if not isinstance(value, dict) or set(value) != {
        "renderer_id",
        "renderer_version",
        "rendered_obsidian_markdown_sha256",
        "rendered_reviewer_latex_sha256",
    }:
        raise ReviewTreeValidationError("render confirmation is invalid")
    renderer_id = value.get("renderer_id")
    renderer_version = value.get("renderer_version")
    rendered_reviewer_latex_sha256 = value.get("rendered_reviewer_latex_sha256")
    rendered_obsidian_markdown_sha256 = value.get("rendered_obsidian_markdown_sha256")
    _bounded_text(renderer_id, "renderer id", maximum=500, empty=False)
    _bounded_text(renderer_version, "renderer version", maximum=500, empty=False)
    if (
        not isinstance(rendered_reviewer_latex_sha256, str)
        or _SHA256.fullmatch(rendered_reviewer_latex_sha256) is None
        or rendered_reviewer_latex_sha256 != reviewer_latex_sha256
        or not isinstance(rendered_obsidian_markdown_sha256, str)
        or _SHA256.fullmatch(rendered_obsidian_markdown_sha256) is None
        or rendered_obsidian_markdown_sha256 != obsidian_markdown_sha256
    ):
        raise ReviewTreeValidationError("rendered representation hash is invalid")
    return ValidatedRenderConfirmation(
        renderer_id=str(renderer_id),
        renderer_version=str(renderer_version),
        rendered_reviewer_latex_sha256=rendered_reviewer_latex_sha256,
        rendered_obsidian_markdown_sha256=rendered_obsidian_markdown_sha256,
    )


def _read_bytes(root: AuthorizedRoot, path: PurePosixPath, maximum: int) -> bytes:
    try:
        return root.read_bytes(path, max_bytes=maximum)
    except (OSError, ValueError) as error:
        raise ReviewTreeValidationError(
            "review artifact bytes are unavailable"
        ) from error


def _read_json(
    root: AuthorizedRoot,
    path: PurePosixPath,
) -> tuple[dict[str, object], bytes]:
    content = _read_bytes(root, path, MAX_REVIEW_ARTIFACT_BYTES)
    try:
        text = content.decode("utf-8", errors="strict")
        _validate_json_envelope(text)
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
        _validate_json_value(value)
        if content != _canonical(value):
            raise ValueError("review JSON is not canonical")
    except (OverflowError, RecursionError, UnicodeError, ValueError) as error:
        raise ReviewTreeValidationError("review JSON is malformed") from error
    if not isinstance(value, dict):
        raise ReviewTreeValidationError("review JSON must be an object")
    return value, content


def _validate_json_envelope(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_REVIEW_ARTIFACT_BYTES:
        raise ValueError("review JSON exceeds its byte limit")
    depth = 0
    in_string = False
    escaped = False
    string_bytes = 0
    for character in text:
        if in_string:
            string_bytes += len(character.encode("utf-8"))
            if string_bytes > _MAX_JSON_STRING_BYTES:
                raise ValueError("review JSON string exceeds its byte limit")
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
            string_bytes = 0
        elif character in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                raise ValueError("review JSON exceeds its depth limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("review JSON nesting is malformed")
    if depth != 0 or in_string:
        raise ValueError("review JSON nesting is malformed")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("review JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"review JSON contains non-finite number: {value}")


def _validate_json_value(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    items = 0
    while stack:
        current, depth = stack.pop()
        if depth > _MAX_JSON_DEPTH:
            raise ValueError("review JSON exceeds its depth limit")
        if isinstance(current, dict):
            items += len(current)
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            items += len(current)
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            if len(current.encode("utf-8")) > _MAX_JSON_STRING_BYTES:
                raise ValueError("review JSON string exceeds its byte limit")
        elif current is not None and not isinstance(current, bool | int | float):
            raise ValueError("review JSON contains an unsupported value")
        if items > _MAX_JSON_ITEMS:
            raise ValueError("review JSON exceeds its item limit")


def _bounded_text(
    value: object,
    field: str,
    *,
    maximum: int,
    empty: bool,
) -> str:
    if not isinstance(value, str):
        raise ReviewTreeValidationError(f"{field} must be text")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ReviewTreeValidationError(f"{field} must be valid UTF-8") from error
    if len(value) > maximum or (not empty and not value):
        raise ReviewTreeValidationError(f"{field} exceeds its character bound")
    return value


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ReviewTreeValidationError("human revision UTC time is invalid")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise ReviewTreeValidationError("human revision UTC time is invalid") from error
    if _utc_text(result) != value:
        raise ReviewTreeValidationError("human revision UTC time is not canonical")
    return result


def _utc_text(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ReviewTreeValidationError("human revision time is not UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _id(namespace: str, value: object) -> str:
    return f"{namespace}:sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8", errors="strict")
