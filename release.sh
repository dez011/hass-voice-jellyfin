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

# ── 3. Bump version in manifest.json and const.py ────────────────────────────
# Both must move together — a test asserts they match, and HACS reads the
# manifest while the integration reports const.VERSION.
CURRENT=$(python3 -c "import json; d=json.load(open('$MANIFEST')); print(d['version'])")
echo "Bumping $CURRENT → $VERSION"
python3 - <<PYEOF
import json, re

with open("$MANIFEST") as f:
    d = json.load(f)
d["version"] = "$VERSION"
with open("$MANIFEST", "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")

const_path = "custom_components/voice_jellyfin/const.py"
with open(const_path) as f:
    src = f.read()
new_src, n = re.subn(r'^VERSION = "[^"]*"', 'VERSION = "$VERSION"', src, count=1, flags=re.M)
if n != 1:
    raise SystemExit(f"error: could not find VERSION assignment in {const_path}")
with open(const_path, "w") as f:
    f.write(new_src)
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
git add "$MANIFEST" "$CHANGELOG" custom_components/voice_jellyfin/const.py
git commit -m "chore: release v$VERSION"
git tag "v$VERSION"

# ── 6. Push branch + tag ──────────────────────────────────────────────────────
# A local-only tag (commit + `git tag` with no push) is invisible to GitHub
# and to HACS — that's exactly how v0.2.0 went stale: it was tagged locally
# but never pushed, so HACS never saw an update.
BRANCH="$(git branch --show-current)"
echo "Pushing $BRANCH and tag v$VERSION..."
git push origin "$BRANCH"
git push origin "v$VERSION"

# ── 7. Create the GitHub Release ──────────────────────────────────────────────
# .github/workflows/release.yml is deliberately workflow_dispatch-only, NOT
# triggered by the tag push above — HACS tracks the default branch only until
# a repo has a published Release, then pins to releases from then on, so
# auto-releasing on every tag would silently stop HACS from following master.
# Cutting the actual Release is therefore this explicit step, not automatic.
if ! command -v gh >/dev/null 2>&1; then
  echo ""
  echo "⚠ gh CLI not found — tag v$VERSION was pushed but no GitHub Release was created."
  echo "  HACS will NOT see this update until one exists. Create it with:"
  echo "  gh release create v$VERSION --repo dez011/hass-voice-jellyfin --title \"v$VERSION\" --generate-notes"
  exit 0
fi

NOTES="$(printf '%b' "$ENTRY")"
gh release create "v$VERSION" \
  --repo dez011/hass-voice-jellyfin \
  --title "v$VERSION" \
  --notes "$NOTES"

echo ""
echo "✓ Released v$VERSION"
echo ""
echo "Release page:"
echo "  https://github.com/dez011/hass-voice-jellyfin/releases/tag/v$VERSION"
echo ""
echo "Then in Home Assistant: HACS → Voice Jellyfin → ⋮ → Redownload, then"
echo "restart HA Core to load the new code."
