#!/usr/bin/env bash
# Clean-checkout check: clone the branch, run unit tests and the free CPU stages on 30 photos.
# Usage: scripts/smoke_test.sh <git-branch> <photo-folder>
set -euo pipefail
BRANCH=${1:?usage: smoke_test.sh <branch> <photo-folder>}
PHOTOS=${2:?usage: smoke_test.sh <branch> <photo-folder>}
TMP=$(mktemp -d)
git clone -q -b "$BRANCH" "$(git config --get remote.origin.url)" "$TMP/repo"
mkdir "$TMP/photos" && ls "$PHOTOS" | head -30 | while read -r f; do cp "$PHOTOS/$f" "$TMP/photos/"; done
cd "$TMP/repo"
export PYTHONPATH="$TMP/repo/src"                      # run from the clone without installing it
python3 -m pytest -q
python3 -m scan3d.cli doctor
python3 -m scan3d.cli run --config configs/house.yaml --set "inputs.photos_dir=$TMP/photos" \
    --stages ingest,validate,features,sparse
cat runs/*/manifest.json | python3 -c "
import json,sys; m=json.load(sys.stdin)['stages']['sparse']['metrics']
print('SMOKE TEST: registered', m['registered_by_group'], 'models', m['num_models'])"
echo "Clone kept at $TMP/repo"
