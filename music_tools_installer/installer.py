"""Download a catalog zip, check its hash, and swap it into place."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from music_tools_installer.catalog import Product, version_newer

_HASH_CHUNK = 1024 * 1024


def default_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA is not set")
    return Path(local) / "music-tools-installer"


def apps_dir(data_dir: Path) -> Path:
    return data_dir / "apps"


def app_dir(data_dir: Path, product_id: str) -> Path:
    return apps_dir(data_dir) / product_id


def load_installed(data_dir: Path) -> dict[str, dict]:
    path = data_dir / "installed.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("installed.json must be an object")
    return data


def install_product(product: Product, data_dir: Path, force: bool = False) -> str:
    if not product.url:
        raise ValueError(f"{product.id} has no package url")
    if not _sha256_hex(product.sha256):
        raise ValueError(f"{product.id} has no sha256")
    installed = load_installed(data_dir)
    current = installed.get(product.id)
    if current and not force:
        have = str(current.get("version", ""))
        if have and not version_newer(product.version, have):
            return f"{product.id} {have} is already installed"

    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    package = tmp / f"{product.id}.zip"
    try:
        _fetch(product.url, package)
        digest = sha256_file(package)
        if digest != product.sha256:
            raise ValueError(f"{product.id} hash mismatch: {digest}")
        _swap_in(package, data_dir, product.id)
    finally:
        package.unlink(missing_ok=True)

    installed[product.id] = {
        "version": product.version,
        "sha256": product.sha256,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_installed(data_dir, installed)
    return f"installed {product.id} {product.version}"


def remove_product(product_id: str, data_dir: Path) -> str:
    installed = load_installed(data_dir)
    if product_id not in installed:
        raise ValueError(f"{product_id} is not installed")
    stop_product(product_id, data_dir)
    shutil.rmtree(app_dir(data_dir, product_id), ignore_errors=True)
    installed.pop(product_id, None)
    _write_installed(data_dir, installed)
    return f"removed {product_id}"


def run_product(product: Product, data_dir: Path) -> str:
    if product.id not in load_installed(data_dir):
        raise ValueError(f"{product.id} is not installed")
    if not product.entry:
        raise ValueError(f"{product.id} has no entry command")
    folder = app_dir(data_dir, product.id)
    if not folder.is_dir():
        raise ValueError(f"{product.id} files are missing from {folder}")
    pid = read_pid(data_dir, product.id)
    if pid is not None and pid_alive(pid):
        return f"{product.id} is already running ({pid})"

    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    argv = _argv(product.entry)
    log_path = logs / f"{product.id}.log"
    with log_path.open("ab") as log:
        log.write(f"\n$ {' '.join(argv)}\n".encode("utf-8"))
        flags = {}
        if os.name == "nt":
            flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            argv,
            cwd=folder,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            **flags,
        )
    pid = proc.pid
    if proc.poll() is None:
        # The app is supposed to keep running after this object is discarded.
        proc.returncode = 0
    _pid_path(data_dir, product.id).parent.mkdir(parents=True, exist_ok=True)
    _pid_path(data_dir, product.id).write_text(str(pid), encoding="utf-8")
    return f"started {product.id} ({pid})"


def stop_product(product_id: str, data_dir: Path) -> str:
    pid = read_pid(data_dir, product_id)
    path = _pid_path(data_dir, product_id)
    if pid is None or not pid_alive(pid):
        path.unlink(missing_ok=True)
        return f"{product_id} is not running"
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        os.kill(pid, 15)
    path.unlink(missing_ok=True)
    return f"stopped {product_id}"


def read_pid(data_dir: Path, product_id: str) -> int | None:
    path = _pid_path(data_dir, product_id)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text.isdigit():
        return None
    return int(text)


def pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes

    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def status_line(product: Product, installed: dict[str, dict]) -> str:
    current = installed.get(product.id)
    if current is None:
        state = "not installed"
    else:
        have = str(current.get("version", ""))
        if version_newer(product.version, have):
            state = f"update {product.version}"
        elif version_newer(have, product.version):
            state = f"{have} (newer than catalog)"
        else:
            state = have
    return f"{product.id:<12} {product.name:<12} {state}"


def _swap_in(package: Path, data_dir: Path, product_id: str) -> None:
    root = apps_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    incoming = root / f"{product_id}.incoming"
    previous = root / f"{product_id}.previous"
    current = root / product_id
    if incoming.exists():
        shutil.rmtree(incoming)
    incoming.mkdir()
    _safe_extract(package, incoming)
    if previous.exists():
        shutil.rmtree(previous)
    if current.exists():
        current.rename(previous)
    try:
        incoming.rename(current)
    except Exception:
        if previous.exists() and not current.exists():
            previous.rename(current)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def _safe_extract(package: Path, dest: Path) -> None:
    dest = dest.resolve()
    with zipfile.ZipFile(package) as archive:
        for info in archive.infolist():
            target = _member_target(dest, info)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def _member_target(dest: Path, info: zipfile.ZipInfo) -> Path:
    name = info.filename.replace("\\", "/")
    if "\x00" in name:
        raise ValueError(f"unsafe path in zip: {info.filename}")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise ValueError(f"symlink in zip: {info.filename}")
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts or rel.drive:
        raise ValueError(f"unsafe path in zip: {info.filename}")
    target = (dest / rel).resolve()
    if target != dest and dest not in target.parents:
        raise ValueError(f"unsafe path in zip: {info.filename}")
    return target


def _fetch(url: str, dest: Path) -> None:
    if url.startswith(("http://", "https://")):
        request = urllib.request.Request(url, headers={"User-Agent": "music-tools-installer"})
        with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as out:
            shutil.copyfileobj(response, out)
        return
    src = Path(url)
    if not src.is_file():
        raise FileNotFoundError(f"package not found: {url}")
    shutil.copyfile(src, dest)


def _argv(entry: str) -> list[str]:
    argv = shlex.split(entry)
    if not argv:
        raise ValueError("entry command is empty")
    if argv[0].lower() in {"python", "python.exe"}:
        argv[0] = sys.executable
    return argv


def _write_installed(data_dir: Path, installed: dict[str, dict]) -> None:
    path = data_dir / "installed.json"
    path.write_text(json.dumps(installed, indent=2) + "\n", encoding="utf-8")


def _pid_path(data_dir: Path, product_id: str) -> Path:
    return data_dir / "pids" / f"{product_id}.pid"


def _sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)
