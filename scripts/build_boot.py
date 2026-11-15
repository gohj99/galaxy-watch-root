#!/usr/bin/env python3
"""Replace the kernel in a Samsung boot template and sign only boot.img."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def replace_kernel(base: Path, kernel: Path, unsigned: Path) -> dict[str, int]:
    data = base.read_bytes()
    if data[:8] != b"ANDROID!":
        raise SystemExit("base boot template is not an Android boot image")
    if len(data) < 64 or data[-64:-60] != b"AVBf":
        raise SystemExit("base boot template must contain an AVB footer")
    footer = struct.unpack_from(">4s2I3Q28s", data, len(data) - 64)
    original_size = footer[3]
    if original_size <= 0 or original_size > len(data):
        raise SystemExit("base boot image has an invalid AVB original_image_size")
    page_size = 1 << 12
    kernel_size = struct.unpack_from("<I", data, 8)[0]
    ramdisk_size = struct.unpack_from("<I", data, 12)[0]
    version = struct.unpack_from("<I", data, 40)[0]
    signature_size = struct.unpack_from("<I", data, 1580)[0]
    if version != 4 or kernel_size == 0 or ramdisk_size or signature_size:
        raise SystemExit(
            "unsupported boot template: "
            f"header_version={version}, kernel_size={kernel_size}, "
            f"ramdisk_size={ramdisk_size}, signature_size={signature_size}"
        )
    image = data[:original_size]
    old_end = page_size + kernel_size
    if old_end > len(image):
        raise SystemExit("base boot kernel extends beyond the image")
    new_kernel = kernel.read_bytes()
    rebuilt = bytearray(image[:page_size]) + new_kernel + image[old_end:]
    struct.pack_into("<I", rebuilt, 8, len(new_kernel))
    old_tail = image[old_end:]
    new_tail = rebuilt[page_size + len(new_kernel):]
    if bytes(new_tail) != old_tail:
        raise SystemExit("boot tail was not preserved while replacing the kernel")
    marker = rebuilt.find(b"SEANDROIDENFORCE", page_size + len(new_kernel))
    if marker >= 0 and marker % page_size:
        raise SystemExit(
            "replacement moves SEANDROIDENFORCE off a 4 KiB boundary; "
            "the kernel size is incompatible with this boot template"
        )
    unsigned.write_bytes(rebuilt)
    return {
        "base_size": len(data),
        "base_original_image_size": original_size,
        "base_kernel_size": kernel_size,
        "new_kernel_size": len(new_kernel),
        "new_image_size": len(rebuilt),
        "tail_size": len(new_tail),
        "seandroid_marker_offset": marker,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--avbtool", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partition-size", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.base, args.kernel, args.avbtool, args.key):
        if not path.is_file():
            raise SystemExit(f"Missing required input: {path}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="boot-build-") as temp_name:
        unsigned = Path(temp_name) / "boot-unsigned.img"
        layout = replace_kernel(args.base, args.kernel, unsigned)
        shutil.copy2(unsigned, args.output)
        subprocess.run([
            sys.executable, str(args.avbtool), "add_hash_footer", "--image", str(args.output),
            "--partition_size", str(args.partition_size), "--partition_name", "boot",
            "--algorithm", "SHA256_RSA4096", "--key", str(args.key),
            "--salt", sha256(args.kernel),
        ], check=True)
    manifest = {
        "passed": True,
        "base_boot_sha256": sha256(args.base),
        "kernel_sha256": sha256(args.kernel),
        "boot_sha256": sha256(args.output),
        "boot_size": args.output.stat().st_size,
        "avb_algorithm": "SHA256_RSA4096",
        "avb_salt": sha256(args.kernel),
        "layout": layout,
        "warning": "A boot image is only usable with an unlocked matching device and a compatible boot chain.",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
