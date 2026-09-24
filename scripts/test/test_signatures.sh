#!/usr/bin/env bash
set -euo pipefail

root_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT
repo="$temp_dir/repository"
signer_a="$temp_dir/signer-a"
signer_b="$temp_dir/signer-b"

git init --initial-branch=main --quiet "$repo"
mkdir -p "$repo/keys" "$repo/releases" "$repo/scripts"
cp "$root_dir/scripts/validate_commit_signatures.sh" "$repo/scripts/"
cp "$root_dir/scripts/validate_release_tag.sh" "$repo/scripts/"
chmod +x "$repo/scripts/validate_commit_signatures.sh" "$repo/scripts/validate_release_tag.sh"

ssh-keygen -q -t ed25519 -N '' -f "$signer_a" -C 'fixture signer A'
ssh-keygen -q -t ed25519 -N '' -f "$signer_b" -C 'fixture signer B'
public_key_a="$(< "$signer_a.pub")"
public_key_b="$(< "$signer_b.pub")"
printf 'signer-a@example.invalid namespaces="git" %s\n' "$public_key_a" > "$repo/keys/allowed_signers"
: > "$repo/keys/revoked_signers"

git -C "$repo" config user.name 'Signature Fixture A'
git -C "$repo" config user.email 'signer-a@example.invalid'
git -C "$repo" config gpg.format ssh
git -C "$repo" config user.signingkey "$signer_a.pub"
git -C "$repo" config commit.gpgsign false
git -C "$repo" config tag.gpgsign true

printf 'base\n' > "$repo/fixture.txt"
printf '# v0.0.0\n' > "$repo/releases/v0.0.0.md"
git -C "$repo" add fixture.txt keys releases
git -C "$repo" commit --quiet -m 'test: add trusted baseline'
base_commit="$(git -C "$repo" rev-parse HEAD)"

git -C "$repo" config commit.gpgsign true
printf 'signed\n' >> "$repo/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit --quiet -m 'test: add signed fixture'
signed_commit="$(git -C "$repo" rev-parse HEAD)"

(cd "$repo" && scripts/validate_commit_signatures.sh "$signed_commit" "$base_commit")
(cd "$repo" && scripts/validate_commit_signatures.sh "$base_commit..$signed_commit" "$base_commit")

git -C "$repo" config commit.gpgsign false
git -C "$repo" commit --allow-empty --quiet -m 'test: add unsigned fixture'
unsigned_commit="$(git -C "$repo" rev-parse HEAD)"
if (cd "$repo" && scripts/validate_commit_signatures.sh "$unsigned_commit" "$base_commit") >/dev/null 2>&1; then
  echo 'unsigned commit unexpectedly passed signature validation' >&2
  exit 1
fi

git -C "$repo" config commit.gpgsign true
printf '%s\n' "$public_key_a" > "$repo/keys/revoked_signers"
git -C "$repo" add keys/revoked_signers
git -C "$repo" commit --quiet -m 'test: revoke fixture signer'
revoked_baseline="$(git -C "$repo" rev-parse HEAD)"
printf 'after-revocation\n' >> "$repo/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit --quiet -m 'test: reject revoked signer'
revoked_target="$(git -C "$repo" rev-parse HEAD)"
if (cd "$repo" && scripts/validate_commit_signatures.sh "$revoked_target" "$revoked_baseline") >/dev/null 2>&1; then
  echo 'revoked signer unexpectedly passed signature validation' >&2
  exit 1
fi

git -C "$repo" checkout --quiet -b self-authorize "$base_commit"
git -C "$repo" config user.name 'Signature Fixture B'
git -C "$repo" config user.email 'new-signer@example.invalid'
git -C "$repo" config user.signingkey "$signer_b.pub"
git -C "$repo" config commit.gpgsign true
printf 'new-signer@example.invalid namespaces="git" %s\n' "$public_key_b" >> "$repo/keys/allowed_signers"
printf '# v0.0.1\n' > "$repo/releases/v0.0.1.md"
git -C "$repo" add keys/allowed_signers releases/v0.0.1.md
git -C "$repo" commit --quiet -m 'test: add untrusted signer'
self_authorized_commit="$(git -C "$repo" rev-parse HEAD)"
if (cd "$repo" && scripts/validate_commit_signatures.sh "$self_authorized_commit" "$base_commit") >/dev/null 2>&1; then
  echo 'self-authorized signer unexpectedly passed signature validation' >&2
  exit 1
fi

git -C "$repo" tag -s v0.0.1 -m 'untrusted fixture release' "$self_authorized_commit"
if (cd "$repo" && scripts/validate_release_tag.sh v0.0.1 "$base_commit") >/dev/null 2>&1; then
  echo 'self-authorized release tag unexpectedly passed validation' >&2
  exit 1
fi

git -C "$repo" checkout --quiet main
git -C "$repo" config user.name 'Signature Fixture A'
git -C "$repo" config user.email 'signer-a@example.invalid'
git -C "$repo" config user.signingkey "$signer_a.pub"
git -C "$repo" config commit.gpgsign true
git -C "$repo" tag -s v0.0.0 -m 'signed fixture release' "$signed_commit"
(cd "$repo" && scripts/validate_release_tag.sh v0.0.0 "$base_commit")
(cd "$repo" && scripts/validate_release_tag.sh v0.0.0)

git -C "$repo" -c tag.gpgsign=false tag v0.0.2 "$signed_commit"
if (cd "$repo" && scripts/validate_release_tag.sh v0.0.2 "$base_commit") >/dev/null 2>&1; then
  echo 'lightweight tag unexpectedly passed release validation' >&2
  exit 1
fi

echo 'signature validation tests passed'
