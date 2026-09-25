#!/usr/bin/env python3
"""Oh My Arch build model and archiso backend adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


class OmaError(Exception):
    pass


def parse_kv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        raise OmaError(f"configuration file does not exist: {path.relative_to(ROOT)}")
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise OmaError(f"invalid configuration at {path}:{number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            words = shlex.split(value, comments=False, posix=True)
        except ValueError as exc:
            raise OmaError(f"invalid configuration at {path}:{number}: {exc}") from exc
        values[key] = words[0] if words else ""
    return values


def load_project() -> Dict[str, str]:
    values = parse_kv(CONFIG_DIR / "project.conf")
    values.update(parse_kv(CONFIG_DIR / "mirrors.conf"))
    values.update(parse_kv(CONFIG_DIR / "signing.conf"))
    return values


def load_matrix() -> Dict[str, object]:
    try:
        return json.loads((CONFIG_DIR / "matrix.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OmaError(f"cannot read build matrix: {exc}") from exc


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def is_supported(model: Dict[str, str], matrix: Dict[str, object]) -> bool:
    entries = matrix.get("supported", [])
    return any(
        isinstance(entry, dict)
        and entry.get("architecture") == model["architecture"]
        and entry.get("profile") == model["profile"]
        and entry.get("platform") == model["platform"]
        for entry in entries
    )


def supported_text(matrix: Dict[str, object]) -> str:
    entries = matrix.get("supported", [])
    if not entries:
        return "none"
    return ", ".join(
        f"{entry['architecture']}+{entry['profile']}+{entry['platform']}"
        for entry in entries
        if isinstance(entry, dict)
    )


def validate_name(value: str, kind: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise OmaError(f"invalid {kind}: {value!r}")
    return value


def package_files_for(directory: Path, preferred: str | None = None) -> List[Path]:
    if not directory.exists():
        raise OmaError(f"missing model directory: {relative(directory)}")
    if directory.is_file():
        return [directory]
    package_dir = directory / "packages"
    if not package_dir.exists():
        return []
    if package_dir.is_file():
        return [package_dir]
    if preferred and (package_dir / preferred).is_file():
        return [package_dir / preferred]
    return sorted(
        path
        for path in package_dir.rglob("*")
        if path.is_file() and path.name not in {"README.md", ".gitkeep"}
    )


def read_packages(paths: Iterable[Path]) -> Tuple[List[str], Dict[str, str]]:
    packages: List[str] = []
    origins: Dict[str, str] = {}
    seen = set()
    for path in paths:
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if any(char.isspace() for char in line):
                raise OmaError(f"invalid package name at {relative(path)}:{number}: {line!r}")
            if line not in seen:
                seen.add(line)
                packages.append(line)
                origins[line] = relative(path)
    return packages, origins


def resolve_model(args: argparse.Namespace, project: Dict[str, str], matrix: Dict[str, object]):
    architecture = validate_name(args.arch or project.get("OMA_DEFAULT_ARCH", "x86_64"), "architecture")
    profile = validate_name(args.profile or project.get("OMA_DEFAULT_PROFILE", "minimal"), "profile")
    platform = validate_name(args.platform or project.get("OMA_DEFAULT_PLATFORM", "generic"), "platform")
    model = {"architecture": architecture, "profile": profile, "platform": platform}
    if not is_supported(model, matrix):
        raise OmaError(
            f"unsupported build combination: {architecture}+{profile}+{platform}; "
            f"currently supported: {supported_text(matrix)}"
        )

    profile_dir = ROOT / "profiles" / profile
    architecture_dir = ROOT / "architectures" / architecture
    platform_dir = ROOT / "platforms" / platform
    package_files: List[Path] = []
    package_files.extend(package_files_for(ROOT / "profiles" / "base"))
    package_files.extend(package_files_for(profile_dir, f"profile-{profile}"))
    package_files.extend(package_files_for(architecture_dir))
    package_files.extend(package_files_for(platform_dir))

    components = []
    for component in args.component or []:
        component = validate_name(component, "component")
        component_dir = ROOT / "components" / component
        if not component_dir.is_dir():
            raise OmaError(f"unknown component: {component}")
        components.append(component)
        package_files.extend(package_files_for(component_dir))

    packages, origins = read_packages(package_files)
    if not packages:
        raise OmaError("the resolved package set is empty")
    return model, profile_dir, package_files, packages, origins, components


def copy_rendered_tree(source: Path, destination: Path, replacements: Dict[str, str]) -> None:
    if not source.exists():
        return
    for item in source.rglob("*"):
        if item.name in {"README.md", ".gitkeep"}:
            continue
        target = destination / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if item.is_symlink():
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(os.readlink(item))
            continue
        if item.is_dir():
            continue
        data = item.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            target.write_bytes(data)
            continue
        for key, value in replacements.items():
            text = text.replace(f"@{key}@", value)
        target.write_text(text, encoding="utf-8")


def render_file(source: Path, destination: Path, replacements: Dict[str, str]) -> None:
    text = source.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(f"@{key}@", value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def stage_profile(stage: Path, profile_dir: Path, model: Dict[str, str], project: Dict[str, str], packages: Sequence[str], version: str) -> None:
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    base_dir = ROOT / "profiles" / "base"
    profiledef = profile_dir / "profiledef.sh"
    if not profiledef.is_file():
        profiledef = base_dir / "profiledef.sh"
    pacman = profile_dir / "pacman.conf"
    if not pacman.is_file():
        pacman = base_dir / "pacman.conf"
    replacements = {
        "OMA_MIRROR_SERVER": project.get("OMA_MIRROR_SERVER", "https://geo.mirror.pkgbuild.com"),
        "OMA_ARCH": model["architecture"],
        "OMA_PROFILE": model["profile"],
        "OMA_PLATFORM": model["platform"],
        "OMA_VERSION": version,
    }
    render_file(profiledef, stage / "profiledef.sh", replacements)
    render_file(pacman, stage / "pacman.conf", replacements)
    (stage / f"packages.{model['architecture']}").write_text("".join(f"{pkg}\n" for pkg in packages), encoding="utf-8")
    copy_rendered_tree(base_dir / "airootfs", stage / "airootfs", replacements)
    copy_rendered_tree(profile_dir / "airootfs", stage / "airootfs", replacements)
    copy_rendered_tree(base_dir / "boot" / "syslinux", stage / "syslinux", replacements)
    copy_rendered_tree(base_dir / "boot" / "efiboot", stage / "efiboot", replacements)
    copy_rendered_tree(profile_dir / "boot" / "syslinux", stage / "syslinux", replacements)
    copy_rendered_tree(profile_dir / "boot" / "efiboot", stage / "efiboot", replacements)
    release_file = stage / "airootfs" / "etc" / "oh-my-arch-release"
    release_file.parent.mkdir(parents=True, exist_ok=True)
    release_file.write_text(
        "\n".join(
            [
                "NAME=Oh_My_Arch",
                "ID=oh-my-arch",
                f"BUILD_ARCH={model['architecture']}",
                f"BUILD_PROFILE={model['profile']}",
                f"BUILD_PLATFORM={model['platform']}",
                f"BUILD_VERSION={version}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--short=12", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_timestamp() -> str:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        try:
            stamp = datetime.fromtimestamp(int(source_date_epoch), tz=timezone.utc)
        except (ValueError, OverflowError) as exc:
            raise OmaError(f"invalid SOURCE_DATE_EPOCH: {source_date_epoch}") from exc
    else:
        stamp = datetime.now(timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_from_root(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def print_plan(model, package_files, packages, components, version, output_dir, work_dir) -> None:
    iso_name = f"oh-my-arch-{model['profile']}-{model['architecture']}-{version}.iso"
    print("Oh My Arch build plan")
    print(f"  architecture: {model['architecture']}")
    print(f"  profile:      {model['profile']}")
    print(f"  platform:     {model['platform']}")
    print(f"  version:      {version}")
    print(f"  components:   {', '.join(components) if components else 'none'}")
    print(f"  packages:     {len(packages)}")
    print(f"  package files: {', '.join(relative(path) for path in package_files)}")
    print(f"  output ISO:   {output_dir / iso_name}")
    print(f"  work dir:     {work_dir}")
    print("  backend:      mkarchiso")


def make_tree_removable(root: Path) -> None:
    """Restore user write/execute bits before removing backend output."""
    if not root.exists():
        return
    for directory, names, files in os.walk(root):
        os.chmod(directory, Path(directory).stat().st_mode | stat.S_IRWXU)
        for name in [*names, *files]:
            path = Path(directory) / name
            try:
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    continue
                bits = stat.S_IRWXU if stat.S_ISDIR(mode) else stat.S_IRUSR | stat.S_IWUSR
                os.chmod(path, mode | bits)
            except FileNotFoundError:
                continue


def run_build(args: argparse.Namespace) -> int:
    project = load_project()
    matrix = load_matrix()
    model, profile_dir, package_files, packages, origins, components = resolve_model(args, project, matrix)
    version = args.version or project.get("OMA_VERSION", "0.1.0")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", version):
        raise OmaError(f"invalid version: {version!r}")
    output_dir = path_from_root(args.output_dir or project.get("OMA_OUTPUT_DIR", "output"))
    work_dir = path_from_root(args.work_dir or project.get("OMA_WORK_DIR", ".oma/work"))
    print_plan(model, package_files, packages, components, version, output_dir, work_dir)
    if args.dry_run:
        return 0

    if shutil.which("mkarchiso") is None:
        raise OmaError("mkarchiso is not installed; on Arch Linux install it with: sudo pacman -S archiso")
    output_dir.mkdir(parents=True, exist_ok=True)
    stage = work_dir / f"profile-{model['profile']}-{model['architecture']}-{model['platform']}"
    stage_profile(stage, profile_dir, model, project, packages, version)
    archiso_work = work_dir / "archiso"
    if archiso_work.exists() and not args.keep_work:
        make_tree_removable(archiso_work)
        shutil.rmtree(archiso_work)
    archiso_work.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in output_dir.glob("*.iso")}
    command = ["mkarchiso", "-v", "-w", str(archiso_work), "-o", str(output_dir), str(stage)]
    print("Running:", " ".join(shlex.quote(value) for value in command))
    env = os.environ.copy()
    env.update(
        {
            "OMA_ISO_NAME": f"oh-my-arch-{model['profile']}-{model['architecture']}",
            "OMA_ISO_LABEL": f"OMA_{model['profile']}_{model['architecture']}"[:32].upper(),
            "OMA_VERSION": version,
            "OMA_ARCH": model["architecture"],
        }
    )
    try:
        subprocess.run(command, check=True, cwd=ROOT, env=env)
    except subprocess.CalledProcessError as exc:
        raise OmaError(f"mkarchiso failed with exit code {exc.returncode}") from exc

    candidates = sorted(output_dir.glob("*.iso"), key=lambda path: path.stat().st_mtime)
    candidates = [path for path in candidates if path.resolve() not in before] or candidates
    if not candidates:
        raise OmaError("mkarchiso completed but did not produce an ISO")
    source_iso = candidates[-1]
    target_iso = output_dir / f"oh-my-arch-{model['profile']}-{model['architecture']}-{version}.iso"
    if source_iso.resolve() != target_iso.resolve():
        if target_iso.exists():
            target_iso.unlink()
        source_iso.rename(target_iso)

    digest = file_sha256(target_iso)
    manifest = {
        "format": "oh-my-arch/build-manifest-v1",
        "project": project.get("OMA_PROJECT_NAME", "oh-my-arch"),
        "version": version,
        "architecture": model["architecture"],
        "profile": model["profile"],
        "platform": model["platform"],
        "components": list(components),
        "git_revision": git_revision(),
        "build_timestamp": build_timestamp(),
        "backend": {"name": "mkarchiso", "command": command},
        "packages": [{"name": package, "source": origins[package]} for package in packages],
        "artifacts": [{"path": target_iso.name, "sha256": digest, "bytes": target_iso.stat().st_size}],
    }
    manifest_path = target_iso.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "SHA256SUMS").write_text(f"{digest}  {target_iso.name}\n", encoding="utf-8")
    print(f"ISO: {target_iso}")
    print(f"Manifest: {manifest_path}")
    print(f"SHA256SUMS: {output_dir / 'SHA256SUMS'}")
    if not args.keep_work:
        shutil.rmtree(stage, ignore_errors=True)
    return 0


def run_check() -> int:
    project = load_project()
    matrix = load_matrix()
    entries = matrix.get("supported", [])
    if not isinstance(entries, list) or not entries:
        raise OmaError("build matrix has no supported combinations")
    for entry in entries:
        if not isinstance(entry, dict):
            raise OmaError("build matrix contains an invalid entry")
        args = argparse.Namespace(
            arch=entry.get("architecture"),
            profile=entry.get("profile"),
            platform=entry.get("platform"),
            component=[],
        )
        resolve_model(args, project, matrix)
    print(f"build model check passed ({len(entries)} supported combination)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    project = load_project()
    parser = argparse.ArgumentParser(
        prog=project.get("OMA_CLI_NAME", "oma"),
        description="Composable Arch image builds backed by archiso.",
    )
    subparsers = parser.add_subparsers(dest="command")
    build = subparsers.add_parser("build", help="resolve a build model and create an ISO with mkarchiso")
    build.add_argument("--arch", default=None, help="target architecture (default: x86_64)")
    build.add_argument("--profile", default=None, help="image profile (default: minimal)")
    build.add_argument("--platform", default=None, help="hardware platform (default: generic)")
    build.add_argument("--component", action="append", default=[], help="optional component; may be repeated")
    build.add_argument("--version", help="artifact version (default: project.conf)")
    build.add_argument("--output-dir", help="artifact output directory")
    build.add_argument("--work-dir", help="temporary build directory")
    build.add_argument("--dry-run", action="store_true", help="print the resolved build plan without invoking mkarchiso")
    build.add_argument("--keep-work", action="store_true", help="keep generated archiso work and staging files")
    subparsers.add_parser("check", help="validate supported build combinations and package manifests")
    subparsers.add_parser("matrix", help="show the declared architecture/profile/platform matrix")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return run_build(args)
        if args.command == "check":
            return run_check()
        if args.command == "matrix":
            print(json.dumps(load_matrix(), indent=2, sort_keys=True))
            return 0
        parser.print_help()
        return 0
    except OmaError as exc:
        print(f"oma: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
