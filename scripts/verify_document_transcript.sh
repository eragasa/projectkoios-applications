#!/usr/bin/env bash
set -euo pipefail

readonly INGESTION_COMMIT="be60640bec4fe15cc88b24161545eb1027ffbd2e"
readonly INGESTION_TREE="d386a1744f79463fd7cd0b3087ee5fc361e0f7d5"
readonly REFERENCES_COMMIT="b7581cb5f8a619883ecd73ed1d9354b85e5f57fd"
readonly REFERENCES_TREE="41c0165e2d4cb73ca41e2bb2acace1b77b7544d9"

if [[ $# -ne 0 ]]; then
  echo "usage: PROJECTKOIOS_INGESTION_REPOSITORY=/absolute/path PROJECTKOIOS_REFERENCES_REPOSITORY=/absolute/path $0" >&2
  exit 64
fi
if [[ -z "${PROJECTKOIOS_INGESTION_REPOSITORY:-}" ]]; then
  echo "PROJECTKOIOS_INGESTION_REPOSITORY is required" >&2
  exit 64
fi
if [[ -z "${PROJECTKOIOS_REFERENCES_REPOSITORY:-}" ]]; then
  echo "PROJECTKOIOS_REFERENCES_REPOSITORY is required" >&2
  exit 64
fi
if [[ "${PROJECTKOIOS_INGESTION_REPOSITORY}" != /* ]]; then
  echo "PROJECTKOIOS_INGESTION_REPOSITORY must be absolute" >&2
  exit 64
fi
if [[ "${PROJECTKOIOS_REFERENCES_REPOSITORY}" != /* ]]; then
  echo "PROJECTKOIOS_REFERENCES_REPOSITORY must be absolute" >&2
  exit 64
fi
readonly PYTHON_BIN="${PYTHON_BIN:-${PROJECTKOIOS_INGESTION_REPOSITORY}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python 3.14 environment is unavailable: ${PYTHON_BIN}" >&2
  exit 69
fi
if [[ "$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.14" ]]; then
  echo "Python environment must use Python 3.14: ${PYTHON_BIN}" >&2
  exit 69
fi
if ! git -C "${PROJECTKOIOS_INGESTION_REPOSITORY}" cat-file -e \
  "${INGESTION_COMMIT}^{commit}" 2>/dev/null; then
  echo "required ingestion commit is unavailable: ${INGESTION_COMMIT}" >&2
  exit 66
fi
observed_tree="$(
  git -C "${PROJECTKOIOS_INGESTION_REPOSITORY}" \
    rev-parse "${INGESTION_COMMIT}^{tree}"
)"
if [[ "${observed_tree}" != "${INGESTION_TREE}" ]]; then
  echo "required ingestion commit has an unexpected tree" >&2
  exit 65
fi
if ! git -C "${PROJECTKOIOS_REFERENCES_REPOSITORY}" cat-file -e \
  "${REFERENCES_COMMIT}^{commit}" 2>/dev/null; then
  echo "required references commit is unavailable: ${REFERENCES_COMMIT}" >&2
  exit 66
fi
observed_references_tree="$(
  git -C "${PROJECTKOIOS_REFERENCES_REPOSITORY}" \
    rev-parse "${REFERENCES_COMMIT}^{tree}"
)"
if [[ "${observed_references_tree}" != "${REFERENCES_TREE}" ]]; then
  echo "required references commit has an unexpected tree" >&2
  exit 65
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/koios-transcript-verify.XXXXXX")"
trap 'rm -rf "${work}"' EXIT
mkdir -p "${work}/ingestion" "${work}/references"
git -C "${PROJECTKOIOS_INGESTION_REPOSITORY}" archive "${INGESTION_COMMIT}" \
  | tar -x -C "${work}/ingestion"
git -C "${PROJECTKOIOS_REFERENCES_REPOSITORY}" archive "${REFERENCES_COMMIT}" \
  | tar -x -C "${work}/references"

export PYTHONPATH="src/python:${work}/ingestion/src/python:${work}/references/src/python${PYTHONPATH:+:${PYTHONPATH}}"
export MYPYPATH="src/python:${work}/ingestion/src/python:${work}/references/src/python"

"${PYTHON_BIN}" -m pytest -q \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__document_package.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__equation_review.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__review_queue.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__transcript.py \
  tests/repository/test__pdf_corpus_ingestion_boundaries.py
"${PYTHON_BIN}" -m ruff check \
  src/python/projectkoios/applications/pdf_corpus_ingestion/document_package.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/equation_review.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/review_queue.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/transcript.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__document_package.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__equation_review.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__review_queue.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__transcript.py
"${PYTHON_BIN}" -m ruff format --check \
  src/python/projectkoios/applications/pdf_corpus_ingestion/document_package.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/equation_review.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/review_queue.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/transcript.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__document_package.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__equation_review.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__review_queue.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__transcript.py
"${PYTHON_BIN}" -m mypy --strict \
  src/python/projectkoios/applications/pdf_corpus_ingestion/document_package.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/equation_review.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/review_queue.py \
  src/python/projectkoios/applications/pdf_corpus_ingestion/transcript.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__document_package.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__equation_review.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__review_queue.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__transcript.py
