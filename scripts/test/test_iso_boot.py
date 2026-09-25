#!/usr/bin/env python3
"""Boot an ISO in BIOS and UEFI modes and verify its live shell appears."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


DEFAULT_TIMEOUT = 180
SCREEN_INTERVAL = 5


class BootTestError(Exception):
    pass


class QmpClient:
    def __init__(self, path: Path, process: subprocess.Popen[bytes], deadline: float):
        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.settimeout(5)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise BootTestError("QEMU exited before its monitor became ready")
            try:
                self.connection.connect(str(path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.1)
        else:
            raise BootTestError("QEMU monitor did not become ready")

        self.reader = self.connection.makefile("rb")
        self._read_message()
        self.execute("qmp_capabilities")

    def _read_message(self) -> dict[str, object]:
        line = self.reader.readline()
        if not line:
            raise BootTestError("QEMU monitor closed the connection")
        return json.loads(line)

    def execute(self, command: str, arguments: dict[str, str] | None = None) -> object:
        request_id = str(time.monotonic_ns())
        request: dict[str, object] = {"execute": command, "id": request_id}
        if arguments is not None:
            request["arguments"] = arguments
        self.connection.sendall(json.dumps(request).encode() + b"\r\n")
        while True:
            reply = self._read_message()
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                raise BootTestError(f"QEMU monitor command failed: {reply['error']}")
            return reply.get("return")

    def close(self) -> None:
        self.reader.close()
        self.connection.close()


def firmware_paths() -> tuple[Path, Path]:
    configured = os.environ.get("OMA_OVMF_CODE")
    code_candidates = [Path(configured)] if configured else []
    code_candidates.extend(
        [
            Path("/usr/share/OVMF/OVMF_CODE_4M.fd"),
            Path("/usr/share/OVMF/OVMF_CODE.fd"),
            Path("/usr/share/edk2/x64/OVMF_CODE.fd"),
            Path("/usr/share/edk2/x64/OVMF_CODE.4m.fd"),
        ]
    )
    vars_candidates = {
        "OVMF_CODE_4M.fd": "OVMF_VARS_4M.fd",
        "OVMF_CODE.fd": "OVMF_VARS.fd",
        "OVMF_CODE.4m.fd": "OVMF_VARS.4m.fd",
    }
    for code in code_candidates:
        if not code.is_file():
            continue
        vars_name = vars_candidates.get(code.name)
        if vars_name:
            vars_path = code.with_name(vars_name)
            if vars_path.is_file():
                return code, vars_path
        sibling = code.with_name("OVMF_VARS.fd")
        if sibling.is_file():
            return code, sibling
    raise BootTestError("UEFI OVMF code and vars firmware not found; install OVMF or set OMA_OVMF_CODE")


def read_qemu_log(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        return ""


def run_mode(
    iso: Path,
    mode: str,
    firmware: tuple[Path, Path] | None,
    timeout_seconds: int,
) -> None:
    qemu = shutil.which("qemu-system-x86_64")
    tesseract = shutil.which("tesseract")
    if not qemu or not tesseract:
        missing = [name for name, path in (("qemu-system-x86_64", qemu), ("tesseract", tesseract)) if not path]
        raise BootTestError(f"missing required command(s): {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix=f"oma-qemu-{mode}-") as directory:
        temp = Path(directory)
        qmp_path = temp / "qmp.sock"
        log_path = temp / "qemu.log"
        screenshot = temp / "screen.ppm"
        command = [
            qemu,
            "-machine",
            "accel=tcg",
            "-m",
            "2048",
            "-smp",
            "2",
            "-cdrom",
            str(iso),
            "-boot",
            "order=d",
            "-snapshot",
            "-display",
            f"vnc=unix:{temp / 'vnc.sock'}",
            "-qmp",
            f"unix:{qmp_path},server=on,wait=off",
            "-monitor",
            "none",
            "-serial",
            "none",
            "-no-reboot",
        ]
        if firmware:
            code, vars_template = firmware
            vars_copy = temp / "OVMF_VARS.fd"
            shutil.copyfile(vars_template, vars_copy)
            command.extend(
                [
                    "-drive",
                    f"if=pflash,format=raw,readonly=on,file={code}",
                    "-drive",
                    f"if=pflash,format=raw,file={vars_copy}",
                ]
            )

        with log_path.open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + timeout_seconds
            monitor: QmpClient | None = None
            latest_ocr = ""
            try:
                try:
                    monitor = QmpClient(qmp_path, process, deadline)
                except BootTestError as exc:
                    raise BootTestError(f"{exc}\n{read_qemu_log(log_path)}") from exc
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise BootTestError(
                            f"{mode} QEMU exited with status {process.returncode}\n{read_qemu_log(log_path)}"
                        )
                    try:
                        monitor.execute(
                            "human-monitor-command",
                            {"command-line": f"screendump {screenshot}"},
                        )
                        result = subprocess.run(
                            [tesseract, str(screenshot), "stdout", "--psm", "6"],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        latest_ocr = result.stdout
                        normalized = re.sub(r"[^a-z0-9]+", "", latest_ocr.lower())
                        if "rootohmyarch" in normalized:
                            print(f"{mode} boot reached the Archiso live shell")
                            return
                    except (OSError, subprocess.SubprocessError, BootTestError) as exc:
                        if process.poll() is not None:
                            raise BootTestError(
                                f"{mode} QEMU exited with status {process.returncode}\n{read_qemu_log(log_path)}"
                            ) from exc
                    time.sleep(SCREEN_INTERVAL)
                raise BootTestError(
                    f"{mode} boot did not reach root@oh-my-arch within {timeout_seconds}s; "
                    f"last screen text was: {latest_ocr.strip()!r}\n{read_qemu_log(log_path)}"
                )
            finally:
                if monitor is not None:
                    monitor.close()
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} ISO", file=sys.stderr)
        return 2
    iso = Path(sys.argv[1]).expanduser().resolve()
    if not iso.is_file():
        print(f"ISO does not exist: {iso}", file=sys.stderr)
        return 2
    if shutil.which("qemu-system-x86_64") is None or shutil.which("tesseract") is None:
        print("install qemu-system-x86_64 and tesseract to run ISO boot tests", file=sys.stderr)
        return 2
    try:
        timeout_seconds = int(os.environ.get("OMA_BOOT_TIMEOUT", str(DEFAULT_TIMEOUT)))
        if timeout_seconds < 1:
            raise ValueError
    except ValueError:
        print("OMA_BOOT_TIMEOUT must be a positive integer", file=sys.stderr)
        return 2

    try:
        firmware = firmware_paths()
        run_mode(iso, "BIOS", None, timeout_seconds)
        run_mode(iso, "UEFI", firmware, timeout_seconds)
    except BootTestError as exc:
        print(f"ISO boot test failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
