#!/usr/bin/env python3
"""Download and merge Samsung source archives into a kernel source tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract_tar(path: Path, target: Path) -> None:
    with tarfile.open(path, "r:*") as archive:
        root = target.resolve()
        for member in archive.getmembers():
            destination = (target / member.name).resolve()
            if destination != root and root not in destination.parents:
                raise SystemExit(f"Refusing archive path traversal: {member.name}")
        archive.extractall(target)


def safe_extract_zip(path: Path, target: Path) -> list[Path]:
    nested: list[Path] = []
    with zipfile.ZipFile(path) as archive:
        root = target.resolve()
        for member in archive.infolist():
            destination = (target / member.filename).resolve()
            if destination != root and root not in destination.parents:
                raise SystemExit(f"Refusing archive path traversal: {member.filename}")
            archive.extract(member, target)
            if member.filename.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar")):
                nested.append(target / member.filename)
    return nested


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "galaxy-watch-root source builder"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)


def merge_kernel_tree(staging: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    candidates = []
    for makefile in staging.rglob("Makefile"):
        root = makefile.parent
        if (root / "arch").is_dir() and ((root / "build.config.constants").is_file() or (root / "Kconfig").is_file()):
            candidates.append(root)
    if not candidates:
        for root in staging.rglob("kernel"):
            if (root / "arch").is_dir():
                candidates.append(root)
    if not candidates:
        raise SystemExit("Samsung archives did not contain a recognizable kernel tree")
    candidates.sort(key=lambda p: (not (p / "build.config.constants").is_file(), len(p.parts)))
    for root in candidates:
        for item in root.iterdir():
            destination = output / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", action="append", required=True, help="Samsung archive URL or local path")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="gw-source-") as temp_name:
        temp = Path(temp_name)
        downloaded: list[dict[str, str]] = []
        staging = temp / "staging"
        staging.mkdir()
        for index, value in enumerate(args.archive):
            source = Path(value)
            local = temp / f"archive-{index}{source.suffix or '.bin'}"
            if source.is_file():
                shutil.copy2(source, local)
            else:
                download(value, local)
            downloaded.append({"source": value, "sha256": sha256(local)})
            extract_dir = temp / f"extract-{index}"
            extract_dir.mkdir()
            nested = safe_extract_zip(local, extract_dir) if zipfile.is_zipfile(local) else []
            for nested_archive in nested:
                (extract_dir / "nested").mkdir(parents=True, exist_ok=True)
                safe_extract_tar(nested_archive, extract_dir / "nested")
            if not nested and tarfile.is_tarfile(local):
                safe_extract_tar(local, extract_dir)
            shutil.copytree(extract_dir, staging / str(index), dirs_exist_ok=True)
        if args.output.exists():
            shutil.rmtree(args.output)
        merge_kernel_tree(staging, args.output)
        required = [
            args.output / "Makefile",
            args.output / "build.config.constants",
            args.output / "arch/arm64",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise SystemExit("Merged Samsung source is incomplete:\n" + "\n".join(missing))
        manifest = {"archives": downloaded, "kernel_tree": str(args.output)}
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
