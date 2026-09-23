#!/usr/bin/env bash
set -euo pipefail

root_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$root_dir"

./oma --help >/dev/null
./oma build --help >/dev/null
./oma check | grep -Fq 'build model check passed'
plan="$(./oma build --arch x86_64 --profile minimal --dry-run)"
printf '%s\n' "$plan" | grep -Fq 'packages:     9'
printf '%s\n' "$plan" | grep -Fq 'architectures/x86_64/packages'
printf '%s\n' "$plan" | grep -Fq 'platforms/generic/packages'
component_plan="$(./oma build --component networking --dry-run)"
printf '%s\n' "$component_plan" | grep -Fq 'components:   networking'
if ./oma build --arch aarch64 --profile minimal --dry-run >/dev/null 2>&1; then
  echo 'unsupported architecture unexpectedly accepted' >&2
  exit 1
fi
python3 -m py_compile scripts/oma.py
echo 'oma CLI tests passed'
