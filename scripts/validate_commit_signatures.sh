#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <commit-or-revision-range> <trusted-baseline-revision>" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
requested="$1"
trusted_baseline="$2"

fail() {
  echo "commit signature validation failed: $1" >&2
  exit 1
}

case "$requested" in
  -*) fail "revision range must not begin with a dash" ;;
esac

baseline_commit="$(git rev-parse --verify "$trusted_baseline^{commit}" 2>/dev/null)" \
  || fail "invalid trusted baseline: $trusted_baseline"

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

if [[ "$requested" == *".."* ]]; then
  revision_range="$requested"
else
  git rev-parse --quiet --verify "$requested^{commit}" >/dev/null 2>&1 \
    || fail "invalid commit: $requested"
  if git rev-parse --quiet --verify "$requested^" >/dev/null 2>&1; then
    revision_range="$requested^..$requested"
  else
    revision_range="$requested"
  fi
fi

git rev-list "$revision_range" >/dev/null 2>&1 \
  || fail "invalid revision range: $revision_range"
mapfile -t commits < <(git rev-list --reverse "$revision_range")
[ "${#commits[@]}" -gt 0 ] || fail "revision range contains no commits"

for commit in "${commits[@]}"; do
  [ "$commit" != "$baseline_commit" ] \
    || fail "trusted baseline must precede every commit being validated"
  git merge-base --is-ancestor "$baseline_commit" "$commit" \
    || fail "trusted baseline is not an ancestor of commit: $commit"
  if ! git cat-file commit "$commit" | grep -q '^gpgsig '; then
    fail "commit is not signed: $commit"
  fi
  git -c gpg.format=ssh \
    -c gpg.ssh.allowedSignersFile="$allowed_signers" \
    -c gpg.ssh.revocationFile="$revoked_signers" \
    verify-commit "$commit" >/dev/null 2>&1 \
    || fail "commit signature is not trusted: $commit"
done

printf 'commit signature validation passed (%s commit(s))\n' "${#commits[@]}"
