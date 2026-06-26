#!/usr/bin/env bash
# Usage: ./release.sh <version> "<comma-separated changelog items>"
# Example: ./release.sh 0.2.0 "Added Apple TV support, Fixed ADB timeout"
set -euo pipefail

VERSION="${1:-}"
CHANGES="${2:-}"

if [[ -z "$VERSION" ]]; then
  echo "Usage: $0 <version> \"<changelog items>\""
  exit 1
fi

MANIFEST="custom_components/voice_jellyfin/manifest.json"
CHANGELOG="CHANGELOG.md"
DATE=$(date +%Y-%m-%d)

# ── 1. Validate version format ────────────────────────────────────────────────
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: version must be semver (e.g. 1.2.3), got: $VERSION"
  exit 1
fi

# ── 2. Check for uncommitted changes ─────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: uncommitted changes present. Commit or stash before releasing."
  exit 1
fi

# ── 3. Bump version in manifest.json ─────────────────────────────────────────
CURRENT=$(python3 -c "import json; d=json.load(open('$MANIFEST')); print(d['version'])")
echo "Bumping $CURRENT → $VERSION"
python3 - <<PYEOF
import json, sys
with open("$MANIFEST") as f:
    d = json.load(f)
d["version"] = "$VERSION"
with open("$MANIFEST", "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
PYEOF

# ── 4. Build CHANGELOG entry ──────────────────────────────────────────────────
ENTRY="## [$VERSION] — $DATE\n\n"

if [[ -n "$CHANGES" ]]; then
  # Split comma-separated items into bullet points
  IFS=',' read -ra ITEMS <<< "$CHANGES"
  for item in "${ITEMS[@]}"; do
    trimmed="${item#"${item%%[![:space:]]*}"}"   # ltrim
    trimmed="${trimmed%"${trimmed##*[![:space:]]}"}" # rtrim
    ENTRY+="- $trimmed\n"
  done
fi
ENTRY+="\n"

# Prepend to CHANGELOG.md (create if missing)
if [[ -f "$CHANGELOG" ]]; then
  EXISTING=$(cat "$CHANGELOG")
  # Don't add a header if one already exists at the top
  if head -1 "$CHANGELOG" | grep -q "^# Changelog"; then
    # Insert after the first line
    { head -1 "$CHANGELOG"; echo; printf '%b' "$ENTRY"; tail -n +2 "$CHANGELOG"; } > "$CHANGELOG.tmp"
  else
    { printf '%b' "$ENTRY"; cat "$CHANGELOG"; } > "$CHANGELOG.tmp"
  fi
  mv "$CHANGELOG.tmp" "$CHANGELOG"
else
  printf '# Changelog\n\n%b' "$ENTRY" > "$CHANGELOG"
fi

# ── 5. Commit + tag ───────────────────────────────────────────────────────────
git add "$MANIFEST" "$CHANGELOG"
git commit -m "chore: release v$VERSION"
git tag "v$VERSION"

echo ""
echo "✓ Released v$VERSION"
echo ""
echo "Push to GitHub with:"
echo "  git push origin main && git push origin v$VERSION"
echo ""
echo "The GitHub Actions release workflow will trigger on the tag push."
