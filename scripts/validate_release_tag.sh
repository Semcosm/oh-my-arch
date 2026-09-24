#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
  echo "usage: $0 <release-tag> [trusted-baseline-revision [tag-object]]" >&2
  exit 2
fi

tag="$1"
trusted_baseline=""
requested_tag_object=""
[ "$#" -ge 2 ] && trusted_baseline="$2"
[ "$#" -ge 3 ] && requested_tag_object="$3"

fail() {
  echo "release tag validation failed: $1" >&2
  exit 1
}

printf '%s\n' "$tag" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' \
  || fail "tag must match v<major>.<minor>.<patch>"
case "$trusted_baseline" in
  -*) fail "trusted baseline must not begin with a dash" ;;
esac
case "$requested_tag_object" in
  -*) fail "tag object must not begin with a dash" ;;
esac

tag_ref="refs/tags/$tag"
if [ -n "$requested_tag_object" ]; then
  tag_object="$(git rev-parse --verify "$requested_tag_object^{tag}" 2>/dev/null)" \
    || fail "tag object is not an annotated tag"
else
  git rev-parse --verify "$tag_ref" >/dev/null 2>&1 \
    || fail "tag does not exist: $tag"
  tag_object="$(git rev-parse --verify "$tag_ref^{tag}" 2>/dev/null)" \
    || fail "formal release tag must be annotated"
fi

tag_commit="$(git rev-parse --verify "$tag_object^{commit}" 2>/dev/null)" \
  || fail "tag must point to a commit"
if [ -z "$trusted_baseline" ]; then
  trusted_baseline="$(git rev-parse --verify "$tag_commit^" 2>/dev/null)" \
    || fail "tag target must have a trusted parent baseline"
fi
baseline_commit="$(git rev-parse --verify "$trusted_baseline^{commit}" 2>/dev/null)" \
  || fail "invalid trusted baseline: $trusted_baseline"
[ "$baseline_commit" != "$tag_commit" ] \
  || fail "trusted baseline must precede the tagged commit"
git merge-base --is-ancestor "$baseline_commit" "$tag_commit" \
  || fail "trusted baseline is not an ancestor of the tagged commit"

git cat-file -e "$tag_commit:releases/$tag.md" \
  || fail "release notes do not exist in the tagged commit: releases/$tag.md"

trust_dir="$(mktemp -d)"
trap 'rm -rf "$trust_dir"' EXIT
allowed_signers="$trust_dir/allowed_signers"
revoked_signers="$trust_dir/revoked_signers"
for trust_file in allowed_signers revoked_signers; do
  trust_path="keys/$trust_file"
  object_type="$(git cat-file -t "$baseline_commit:$trust_path" 2>/dev/null || true)"
  [ "$object_type" = blob ] || fail "trusted baseline is missing $trust_path"
  git show "$baseline_commit:$trust_path" > "$trust_dir/$trust_file" \
    || fail "cannot read trusted baseline file: $trust_path"
done
[ -s "$allowed_signers" ] || fail "trusted baseline signer registry is empty"

if ! git cat-file commit "$tag_commit" | grep -q '^gpgsig '; then
  fail "tagged commit is not signed"
fi
git -c gpg.format=ssh \
  -c gpg.ssh.allowedSignersFile="$allowed_signers" \
  -c gpg.ssh.revocationFile="$revoked_signers" \
  verify-commit "$tag_commit" >/dev/null 2>&1 \
  || fail "tagged commit signature is not trusted"

git -c gpg.format=ssh \
  -c gpg.ssh.allowedSignersFile="$allowed_signers" \
  -c gpg.ssh.revocationFile="$revoked_signers" \
  verify-tag "$tag_object" >/dev/null 2>&1 \
  || fail "tag signature is not trusted"

printf 'release tag validation passed: %s (baseline %s)\n' "$tag" "$baseline_commit"
