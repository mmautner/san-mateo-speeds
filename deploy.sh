#!/usr/bin/env bash
# Build and publish the speeds page to maxmautner.com/<base>/ (base from site/config.json).
#
#   ./deploy.sh              build, upload changed files, invalidate CloudFront
#   ./deploy.sh --dry-run    build and show what would upload; change nothing
#   ./deploy.sh --force      upload every file, even ones already live
#
# Only keys under s3://<bucket>/<base>/ are ever written. Nothing is ever deleted.
# The blog's own deploy (s3_website) must ignore this prefix: add ^san-mateo-speeds/
# to ignore_on_server in the blog's s3_website.yml, or a blog push will delete it.
#
# Credentials come from the AWS profile in $AWS_PROFILE (default "default").
set -euo pipefail
cd "$(dirname "$0")"

DRY=0; FORCE=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --force) FORCE=1 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

PY=python3
cfg() { "$PY" -c "import json,sys; print(json.load(open('site/config.json'))[sys.argv[1]])" "$1"; }
BUCKET="$(cfg s3_bucket)"
CF_ID="$(cfg cloudfront_distribution_id)"
PREFIX="$(cfg base | sed 's#^/*##; s#/*$##')"
export AWS_PROFILE="${AWS_PROFILE:-default}"

# Never let a config mistake point this at the bucket root or outside the prefix.
if [[ -z "$BUCKET" || -z "$PREFIX" || "$PREFIX" == *..* || "$PREFIX" == */* ]]; then
  echo "refusing: bucket='$BUCKET' prefix='$PREFIX'" >&2; exit 1
fi
DEST="s3://$BUCKET/$PREFIX/"

echo "==> Building site"
"$PY" build_site.py
echo "==> Rendering preview images"
pipeline/.venv/bin/python site/og/make_og.py

echo "==> Staging (gzip text files, as the blog does; CloudFront does not compress)"
STAGE=.deploy
rm -rf "$STAGE"
cp -R "dist/$PREFIX" "$STAGE"
find "$STAGE" -type f \( -name '*.html' -o -name '*.css' -o -name '*.js' -o -name '*.json' \) -print0 |
  while IFS= read -r -d '' f; do gzip -9 -n -c "$f" > "$f.gz" && mv "$f.gz" "$f"; done

echo "==> Comparing with what's live"
UPLOAD=.deploy-changed
rm -rf "$UPLOAD"
if [[ $FORCE == 1 ]]; then
  cp -R "$STAGE" "$UPLOAD"
else
  aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "$PREFIX/" --output json > .deploy-remote.json
  "$PY" - "$STAGE" "$UPLOAD" "$PREFIX" .deploy-remote.json <<'PY'
import hashlib, json, shutil, sys
from pathlib import Path
stage, upload, prefix, remote = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
live = {o["Key"]: o["ETag"].strip('"') for o in (json.loads(Path(remote).read_text() or "{}").get("Contents") or [])}
changed = new = 0
for f in sorted(p for p in stage.rglob("*") if p.is_file()):
    key = f"{prefix}/{f.relative_to(stage).as_posix()}"
    # The 20 MB survey PDF goes up as a multipart upload, whose ETag isn't an MD5; it never changes, so a key
    # with a composite ETag counts as live. Use --force to re-upload it.
    etag = live.get(key)
    if etag and ("-" in etag or etag == hashlib.md5(f.read_bytes()).hexdigest()):
        continue
    new += key not in live
    changed += 1
    dest = upload / f.relative_to(stage)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f, dest)
total = sum(1 for p in stage.rglob("*") if p.is_file())
print(f"   {changed} of {total} files changed ({new} new); {total - changed} already live")
PY
  rm -f .deploy-remote.json
fi
mkdir -p "$UPLOAD"
N_UPLOAD=$(find "$UPLOAD" -type f | wc -l | tr -d ' ')

if [[ $DRY == 1 ]]; then SYNC=(aws s3 sync "$UPLOAD/" "$DEST" --dryrun)
else SYNC=(aws s3 sync "$UPLOAD/" "$DEST" --only-show-errors); fi

up() { # pattern content-type cache-seconds [gzip]
  local enc=(); [[ "${4:-}" == gzip ]] && enc=(--content-encoding gzip)
  "${SYNC[@]}" --exclude '*' --include "$1" --content-type "$2" --cache-control "max-age=$3" ${enc[@]+"${enc[@]}"}
}
echo "==> Uploading $N_UPLOAD files to $DEST"
up '*.pdf'  'application/pdf'                 86400
up '*.png'  'image/png'                       86400
up '*.json' 'application/json; charset=utf-8'  3600 gzip
up '*.css'  'text/css; charset=utf-8'          3600 gzip
up '*.js'   'text/javascript; charset=utf-8'   3600 gzip
up '*.html' 'text/html; charset=utf-8'          300 gzip

if [[ $DRY == 0 && $N_UPLOAD == 0 ]]; then
  echo "==> Nothing changed; no invalidation needed."
elif [[ $DRY == 0 ]]; then
  echo "==> Invalidating CloudFront $CF_ID /$PREFIX/*"
  aws cloudfront create-invalidation --distribution-id "$CF_ID" --paths "/$PREFIX/*" \
    --query 'Invalidation.{id:Id,status:Status}' --output text
  echo "==> Live at https://maxmautner.com/$PREFIX/"
else
  echo "==> Dry run: nothing uploaded, nothing invalidated."
fi
