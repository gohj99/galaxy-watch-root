#!/usr/bin/env python3
"""Apply the reproducible BakaSU integration to a Samsung source tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


BAKASU_REPOSITORY = "https://github.com/Baka-SU/BakaSU.git"
DEFAULT_BAKASU_COMMIT = "548d1dda060ca198823d8808804d01f5209ef4a9"


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install_bakasu(kernel: Path, commit: str) -> dict[str, object]:
    target = kernel / "BakaSU"
    if not target.exists():
        run("git", "clone", BAKASU_REPOSITORY, str(target))
    if git(target, "remote", "get-url", "origin") != BAKASU_REPOSITORY:
        raise SystemExit(f"Unexpected BakaSU origin: {target}")
    run("git", "fetch", "--quiet", "--tags", "origin", commit, cwd=target)
    run("git", "checkout", "--detach", "--quiet", commit, cwd=target)
    if git(target, "status", "--porcelain"):
        raise SystemExit("BakaSU checkout has local changes")
    count = int(git(target, "rev-list", "--count", "HEAD"))
    return {
        "repository": BAKASU_REPOSITORY,
        "commit": commit,
        "commit_count": count,
        "version_code": 30000 + count + 700,
        "version_name": git(target, "describe", "--tags", "--abbrev=0") + "-" + commit[:8],
    }


def install_certificate(kernel: Path, certificate: Path | None) -> dict[str, object] | None:
    if certificate is None:
        return None
    if not certificate.is_file():
        raise SystemExit(f"Configured stock certificate does not exist: {certificate}")
    target = kernel / "certs/gw7-stock-gki.pem"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(certificate, target)
    return {"file": "certs/gw7-stock-gki.pem", "sha256": sha256(certificate)}


def add_kernel_hooks(kernel: Path) -> None:
    drivers = kernel / "drivers"
    link = drivers / "kernelsu"
    expected = Path("../BakaSU/kernel")
    if link.exists() or link.is_symlink():
        if not link.is_symlink() or Path(os.readlink(link)) != expected:
            raise SystemExit(f"Existing drivers/kernelsu is not the expected BakaSU link: {link}")
    else:
        link.symlink_to(expected, target_is_directory=True)
    makefile = drivers / "Makefile"
    text = makefile.read_text()
    if "obj-$(CONFIG_KSU) += kernelsu/" not in text:
        makefile.write_text(text.rstrip() + "\n\nobj-$(CONFIG_KSU) += kernelsu/\n")
    kconfig = drivers / "Kconfig"
    text = kconfig.read_text()
    source_line = 'source "drivers/kernelsu/Kconfig"'
    if source_line not in text:
        marker = "endmenu"
        if marker not in text:
            raise SystemExit("drivers/Kconfig has no insertion point")
        kconfig.write_text(text.replace(marker, source_line + "\n" + marker, 1))


def set_config(kernel: Path, config: Path, output: Path, overrides: dict[str, str], certificate: Path | None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    target = output / ".config"
    shutil.copy2(config, target)
    config_tool = kernel / "scripts/config"
    if not config_tool.is_file():
        raise SystemExit(f"Kernel config helper is missing: {config_tool}")
    args = [str(config_tool), "--file", str(target)]
    for name, value in overrides.items():
        if value in {"y", "m"}:
            args.append(f"--{'enable' if value == 'y' else 'module'}")
            args.append(name)
        elif value == "n":
            args.extend(["--disable", name])
        else:
            args.extend(["--set-str", name, value])
    if certificate is None and "SYSTEM_TRUSTED_KEYS" in overrides:
        raise SystemExit("SYSTEM_TRUSTED_KEYS is configured but no public certificate was supplied")
    run("bash", *args)
    env = os.environ.copy()
    env.update({"ARCH": "arm64", "LLVM": "1", "LLVM_IAS": "1"})
    subprocess.run(["make", "-C", str(kernel), f"O={output}", "olddefconfig"], env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--bakasu-commit", default=DEFAULT_BAKASU_COMMIT)
    args = parser.parse_args()

    source = args.source.resolve()
    kernel = source
    required = [kernel / "Makefile", kernel / "build.config.constants", kernel / "arch/arm64"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Samsung kernel source is incomplete:\n" + "\n".join(missing))
    overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
    certificate = args.certificate.resolve() if args.certificate else None
    bakasu = install_bakasu(kernel, args.bakasu_commit)
    certificate_info = install_certificate(kernel, certificate)
    add_kernel_hooks(kernel)
    set_config(kernel, args.config.resolve(), args.output.resolve(), overrides, certificate)
    manifest = {
        "source": str(source),
        "kernel_release": git(kernel, "describe", "--always") if (kernel / ".git").is_dir() else None,
        "root_implementation": bakasu,
        "stock_module_trust": certificate_info,
        "config_sha256": sha256(args.output / ".config"),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
