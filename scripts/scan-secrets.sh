#!/usr/bin/env bash
#
# FleetFlow local secret scanner (SEC-003).
#
# Installs a pinned, checksum-verified gitleaks into a user-local cache (never
# committed) and scans the repository for secrets using .gitleaks.toml. Mirrors
# what CI runs (.github/workflows/secret-scan.yml) so developers can catch
# secrets before pushing.
#
# Usage:
#   scripts/scan-secrets.sh            # scan git history + tree (default)
#   scripts/scan-secrets.sh --staged   # scan only staged changes (pre-commit)
#   scripts/scan-secrets.sh --tree     # scan the working tree (no git history)
#
# Secrets are always redacted in output. Exit code is non-zero if any leak is
# found.
set -euo pipefail

GITLEAKS_VERSION="8.30.1"
# Official SHA-256 checksums from gitleaks_${VERSION}_checksums.txt.
SHA_LINUX_X64="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
SHA_LINUX_ARM64="e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/fleetflow-gitleaks/${GITLEAKS_VERSION}"
BIN="${CACHE_DIR}/gitleaks"

detect_asset() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$(uname -m)" in
    x86_64|amd64) arch="x64"; SHA="$SHA_LINUX_X64" ;;
    aarch64|arm64) arch="arm64"; SHA="$SHA_LINUX_ARM64" ;;
    *) echo "Unsupported architecture: $(uname -m)" >&2; exit 3 ;;
  esac
  if [ "$os" != "linux" ]; then
    echo "This helper pins linux binaries only. On $os, install gitleaks ${GITLEAKS_VERSION} manually." >&2
    exit 3
  fi
  ASSET="gitleaks_${GITLEAKS_VERSION}_linux_${arch}.tar.gz"
}

ensure_gitleaks() {
  # Prefer an already-installed matching version on PATH.
  if command -v gitleaks >/dev/null 2>&1 && \
     [ "$(gitleaks version 2>/dev/null)" = "${GITLEAKS_VERSION}" ]; then
    BIN="$(command -v gitleaks)"
    return
  fi
  if [ -x "$BIN" ] && [ "$("$BIN" version 2>/dev/null)" = "${GITLEAKS_VERSION}" ]; then
    return
  fi
  detect_asset
  echo "Installing pinned gitleaks ${GITLEAKS_VERSION} into ${CACHE_DIR} ..."
  mkdir -p "$CACHE_DIR"
  local tmp; tmp="$(mktemp -d)"
  curl -sSL -o "${tmp}/gl.tar.gz" \
    "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${ASSET}"
  echo "${SHA}  ${tmp}/gl.tar.gz" | sha256sum -c -
  tar -xzf "${tmp}/gl.tar.gz" -C "$tmp" gitleaks
  install -m 0755 "${tmp}/gitleaks" "$BIN"
  rm -rf "$tmp"
}

main() {
  local mode="${1:-}"
  ensure_gitleaks
  cd "$REPO_ROOT"
  local common=(--config .gitleaks.toml --redact --no-banner --verbose)
  case "$mode" in
    --staged)
      echo "Scanning staged changes ..."
      "$BIN" git --staged "${common[@]}" .
      ;;
    --tree)
      echo "Scanning working tree (no history) ..."
      "$BIN" dir "${common[@]}" .
      ;;
    ""|--all)
      echo "Scanning git history and tree ..."
      "$BIN" git "${common[@]}" .
      ;;
    -h|--help)
      grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $mode (use --all | --staged | --tree | --help)" >&2
      exit 2
      ;;
  esac
  echo "No secrets found."
}

main "$@"
