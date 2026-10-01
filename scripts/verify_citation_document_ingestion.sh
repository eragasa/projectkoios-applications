#!/usr/bin/env bash
set -euo pipefail

readonly KSDFT_COMMIT="3ec21b4318020d700be671a8f220b2149b3d28c7"
readonly KSDFT_TREE="9953c0e99a28443426b5093852292f7cfbada2cc"
readonly REFERENCES_COMMIT="f1ca7b4aee552af131ff7af7d1408d33dd338c93"
readonly REFERENCES_TREE="b37672e36af13014dc25170be725fbf3f909c2d7"
readonly INGESTION_COMMIT="be60640bec4fe15cc88b24161545eb1027ffbd2e"
readonly INGESTION_TREE="d386a1744f79463fd7cd0b3087ee5fc361e0f7d5"

if [[ $# -ne 0 ]]; then
  echo "usage: PROJECTKOIOS_KSDFT_REPOSITORY=/absolute/path PROJECTKOIOS_REFERENCES_REPOSITORY=/absolute/path PROJECTKOIOS_INGESTION_REPOSITORY=/absolute/path $0" >&2
  exit 64
fi
for name in PROJECTKOIOS_KSDFT_REPOSITORY PROJECTKOIOS_REFERENCES_REPOSITORY PROJECTKOIOS_INGESTION_REPOSITORY; do
  value="${!name:-}"
  if [[ -z "${value}" || "${value}" != /* ]]; then
    echo "${name} is required and must be absolute" >&2
    exit 64
  fi
done
readonly PYTHON_BIN="${PYTHON_BIN:-${PROJECTKOIOS_INGESTION_REPOSITORY}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python 3.14 environment is unavailable: ${PYTHON_BIN}" >&2
  exit 69
fi
if [[ "$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.14" ]]; then
  echo "Python environment must use Python 3.14: ${PYTHON_BIN}" >&2
  exit 69
fi

verify_object() {
  local repository="$1"
  local commit="$2"
  local tree="$3"
  local label="$4"
  if ! git -C "${repository}" cat-file -e "${commit}^{commit}" 2>/dev/null; then
    echo "required ${label} commit is unavailable: ${commit}" >&2
    exit 66
  fi
  if [[ "$(git -C "${repository}" rev-parse "${commit}^{tree}")" != "${tree}" ]]; then
    echo "required ${label} commit has an unexpected tree" >&2
    exit 65
  fi
}

verify_object "${PROJECTKOIOS_KSDFT_REPOSITORY}" "${KSDFT_COMMIT}" "${KSDFT_TREE}" "ksdft target"
verify_object "${PROJECTKOIOS_REFERENCES_REPOSITORY}" "${REFERENCES_COMMIT}" "${REFERENCES_TREE}" "references"
verify_object "${PROJECTKOIOS_INGESTION_REPOSITORY}" "${INGESTION_COMMIT}" "${INGESTION_TREE}" "ingestion"

work="$(mktemp -d "${TMPDIR:-/tmp}/koios-citation-document-verify.XXXXXX")"
trap 'rm -rf "${work}"' EXIT
mkdir -p "${work}/references" "${work}/ingestion"
git -C "${PROJECTKOIOS_REFERENCES_REPOSITORY}" archive "${REFERENCES_COMMIT}" \
  | tar -x -C "${work}/references"
git -C "${PROJECTKOIOS_INGESTION_REPOSITORY}" archive "${INGESTION_COMMIT}" \
  | tar -x -C "${work}/ingestion"

export PYTHONPATH="src/python:${work}/references/src/python:${work}/ingestion/src/python${PYTHONPATH:+:${PYTHONPATH}}"
export MYPYPATH="src/python:${work}/references/src/python:${work}/ingestion/src/python"
readonly SOURCES=(
  src/python/projectkoios/applications/pdf_corpus_ingestion/__init__.py
  src/python/projectkoios/applications/pdf_corpus_ingestion/citation_document_contracts.py
  src/python/projectkoios/applications/pdf_corpus_ingestion/citation_document_custody.py
  src/python/projectkoios/applications/pdf_corpus_ingestion/citation_document_registry.py
  src/python/projectkoios/applications/pdf_corpus_ingestion/citation_document_service.py
  tests/projectkoios/applications/pdf_corpus_ingestion/test__citation_document_ingestion.py
  tests/repository/test__citation_document_boundaries.py
  tests/repository/test__pdf_corpus_ingestion_boundaries.py
)

"${PYTHON_BIN}" -m pytest -q \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__citation_document_ingestion.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__document_package.py \
  tests/projectkoios/applications/pdf_corpus_ingestion/test__transcript.py \
  tests/repository/test__citation_document_boundaries.py \
  tests/repository/test__pdf_corpus_ingestion_boundaries.py
"${PYTHON_BIN}" -m ruff check "${SOURCES[@]}"
"${PYTHON_BIN}" -m ruff format --check "${SOURCES[@]}"
"${PYTHON_BIN}" -m mypy --strict "${SOURCES[@]}"
