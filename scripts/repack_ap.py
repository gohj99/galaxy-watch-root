#!/usr/bin/env python3
"""Repack a Samsung RBS AP tar.md5, replacing boot.img.lz4 only.

This does not sign boot, establish device compatibility, or flash anything.
It supports the RBS footer layout observed in the tested SM-L315F BZF4 AP.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path


BOOT_MEMBER = "boot.img.lz4"
CHUNK = 4 * 1024 * 1024
FOOTER = re.compile(
    rb"Show the build information\n"
    rb"RBS BUILD_ID:([\x20-\x7e]+)\n"
    rb"original_tar_file_size:([0-9]+)\n"
    rb"([0-9a-fA-F]{32})  ([\x20-\x7e]+)\n\Z"
)


def file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def rbs_prefix(build_id: str, tar_size: int) -> bytes:
    return (
        "Show the build information\n"
        f"RBS BUILD_ID:{build_id}\n"
        f"original_tar_file_size:{tar_size}\n"
    ).encode("ascii")


def verify_footer(path: Path) -> dict:
    """Verify the checksum over tar + RBS metadata, excluding its checksum line."""
    size = path.stat().st_size
    start = max(0, size - 4096)
    with path.open("rb") as handle:
        handle.seek(start)
        tail = handle.read()
    match = FOOTER.search(tail)
    if not match:
        raise ValueError("Unsupported AP footer: expected the tested Samsung RBS layout")
    tar_size = int(match[2])
    if tar_size <= 0 or tar_size % 512 or tar_size != start + match.start():
        raise ValueError("RBS original_tar_file_size does not match the tar boundary")
    checksum_end = start + match.start(3)
    digest = hashlib.md5()
    with path.open("rb") as handle:
        remaining = checksum_end
        while remaining:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                raise ValueError("Truncated AP archive")
            digest.update(chunk)
            remaining -= len(chunk)
    if digest.hexdigest() != match[3].decode("ascii").lower():
        raise ValueError("AP checksum mismatch (tar plus Samsung RBS metadata)")
    return {
        "build_id": match[1].decode("ascii"),
        "tar_size": tar_size,
        "md5_input_size": checksum_end,
        "odin_md5": digest.hexdigest(),
        "md5_verified": True,
    }


def metadata(member: tarfile.TarInfo) -> dict:
    return {
        "name": member.name, "size": member.size, "type": member.type.decode("ascii"),
        "mode": member.mode, "uid": member.uid, "gid": member.gid,
        "uname": member.uname, "gname": member.gname, "mtime": member.mtime,
        "linkname": member.linkname, "pax_headers": member.pax_headers,
        "devmajor": member.devmajor, "devminor": member.devminor,
    }


class DigestReader:
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()

    def read(self, size=-1):
        data = self.source.read(size)
        self.digest.update(data)
        return data


class DigestWriter:
    def __init__(self, target):
        self.target = target
        self.digest = hashlib.md5()
        self.count = 0

    def write(self, data):
        written = self.target.write(data)
        if written != len(data):
            raise OSError("Short write while building AP")
        self.digest.update(data)
        self.count += written
        return written

    def tell(self):
        return self.count


def repack(ap: Path, boot: Path, output: Path) -> dict:
    ap, boot, output = ap.resolve(), boot.resolve(), output.resolve()
    if not ap.is_file() or not boot.is_file():
        raise ValueError("Both --ap and --boot must be existing files")
    if output.exists() or output in {ap, boot}:
        raise ValueError("Refusing to overwrite an existing file")
    if not output.name.endswith(".tar.md5"):
        raise ValueError("--output must end with .tar.md5")
    try:
        output.name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Use an ASCII output filename for Odin") from exc
    if "\n" in output.name or "\r" in output.name:
        raise ValueError("Invalid output filename")
    footer = verify_footer(ap)
    image = boot.read_bytes()
    if len(image) < 64 or image[:8] != b"ANDROID!" or image[-64:-60] != b"AVBf":
        raise ValueError("--boot must be an Android boot image with an AVB footer")
    try:
        import lz4.frame
    except ImportError as exc:
        raise ValueError("Install the dependency first: python -m pip install lz4") from exc
    compressed = lz4.frame.compress(
        image, block_size=lz4.frame.BLOCKSIZE_MAX1MB, block_linked=False,
        content_checksum=True, block_checksum=False, store_size=True,
    )
    if lz4.frame.decompress(compressed) != image:
        raise ValueError("LZ4 round-trip verification failed")
    boot_hash = hashlib.sha256(image).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".repack-ap-", dir=output.parent)
    temp = Path(temp_name)
    expected = []
    seen = set()
    boot_count = 0
    try:
        with os.fdopen(fd, "wb") as target:
            writer = DigestWriter(target)
            with tarfile.open(fileobj=writer, mode="w|", format=tarfile.GNU_FORMAT) as dest:
                with tarfile.open(ap, mode="r|") as source:
                    for member in source:
                        if member.name in seen:
                            raise ValueError(f"Duplicate AP member: {member.name}")
                        seen.add(member.name)
                        if not (member.isreg() or member.isdir()) or member.pax_headers or member.sparse is not None:
                            raise ValueError(f"Unsupported AP member format: {member.name}")
                        if member.offset_data + member.size > footer["tar_size"]:
                            raise ValueError("AP member extends beyond the declared tar payload")
                        info = copy.copy(member)
                        if member.name == BOOT_MEMBER:
                            if not member.isreg():
                                raise ValueError("AP boot member must be a regular file")
                            boot_count += 1
                            info.size = len(compressed)
                            dest.addfile(info, io.BytesIO(compressed))
                            digest = hashlib.sha256(compressed).hexdigest()
                        elif member.isreg():
                            stream = source.extractfile(member)
                            if stream is None:
                                raise ValueError(f"Cannot read {member.name}")
                            reader = DigestReader(stream)
                            dest.addfile(info, reader)
                            digest = reader.digest.hexdigest()
                        else:
                            dest.addfile(info)
                            digest = None
                        expected.append({"metadata": metadata(info), "sha256": digest})
            if boot_count != 1:
                raise ValueError("AP must contain exactly one boot.img.lz4")
            tar_size = writer.count
            writer.write(rbs_prefix(footer["build_id"], tar_size))
            target.write(f"{writer.digest.hexdigest()}  {output.name[:-4]}\n".encode("ascii"))

        result_footer = verify_footer(temp)
        actual = []
        with tarfile.open(temp, mode="r|") as archive:
            for member in archive:
                if member.isreg():
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ValueError(f"Cannot verify {member.name}")
                    if member.name == BOOT_MEMBER:
                        payload = stream.read()
                        if hashlib.sha256(lz4.frame.decompress(payload)).hexdigest() != boot_hash:
                            raise ValueError("Output boot does not match the requested image")
                        digest = hashlib.sha256(payload).hexdigest()
                    else:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                else:
                    digest = None
                actual.append({"metadata": metadata(member), "sha256": digest})
        if actual != expected:
            raise ValueError("Repacked AP member order, metadata, or payload verification failed")
        # Exclusive creation preserves an existing output even if it appeared during verification.
        # A same-volume hard link publishes the fully verified file without a partial copy.
        os.link(temp, output)
        return {
            "passed": True,
            "source_ap": str(ap), "boot_source": str(boot), "output": str(output),
            "boot_sha256": boot_hash, "output_sha256": file_sha256(output),
            "replacement": BOOT_MEMBER, "member_count": len(actual),
            "other_member_payloads_and_metadata_preserved": True,
            "lz4_roundtrip_verified": True, "footer": result_footer,
            "scope": "Local AP packaging only; not AVB trust, device compatibility, or a flash test.",
        }
    finally:
        temp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ap", required=True, type=Path, help="Matching original AP tar.md5")
    parser.add_argument("--boot", required=True, type=Path, help="Already signed boot image")
    parser.add_argument("--output", required=True, type=Path, help="New local AP tar.md5 (must not exist)")
    parser.add_argument("--report", type=Path, help="Optional new local JSON report (must not exist)")
    args = parser.parse_args()
    if args.report and (args.report.exists() or args.report.resolve() in {
        args.ap.resolve(), args.boot.resolve(), args.output.resolve(),
    }):
        parser.exit(1, "Error: --report must be a separate, new file\n")
    try:
        result = repack(args.ap, args.boot, args.output)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, tarfile.TarError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
