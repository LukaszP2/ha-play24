#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "Użycie: ./release.sh <wersja> [opis]"
    echo "Przykład: ./release.sh 0.1.0 'Pierwsze stabilne wydanie'"
    exit 1
fi

NEW_VER="$1"
MSG="${2:-Wydanie v${NEW_VER}}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${REPO_DIR}/custom_components/play24/manifest.json"

python3 -c "
import json
with open('${MANIFEST}', 'r+') as f:
    d = json.load(f)
    d['version'] = '${NEW_VER}'
    f.seek(0)
    json.dump(d, f, indent=2, ensure_ascii=False)
    f.write('\n')
    f.truncate()
"

git -C "${REPO_DIR}" add .
git -C "${REPO_DIR}" commit -m "Bump version to ${NEW_VER}: ${MSG}" || true
git -C "${REPO_DIR}" tag -a "v${NEW_VER}" -m "${MSG}"
git -C "${REPO_DIR}" push origin HEAD --follow-tags
echo "Wydanie v${NEW_VER} zostało wysłane na GitHub!"
