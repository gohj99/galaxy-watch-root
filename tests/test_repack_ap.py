"""Synthetic archive tests; these never contact or flash a device."""
from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import lz4.frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from repack_ap import repack, verify_footer  # noqa: E402


def make_ap(path: Path, names=None) -> None:
    if names is None:
        names = ["boot.img.lz4", "vbmeta.img.lz4", "userdata.img.lz4", "meta-data", "meta-data/fota.zip"]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            member.uid = member.gid = 1000
            member.uname = member.gname = "dpi"
            member.mtime = 1700000000
            member.mode = 0o644
            if name == "meta-data":
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                archive.addfile(member)
            else:
                data = lz4.frame.compress(b"stock:" + name.encode()) if name.endswith(".lz4") else b"fota data"
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
    payload = buffer.getvalue()
    prefix = f"Show the build information\nRBS BUILD_ID:fixture\noriginal_tar_file_size:{len(payload)}\n".encode()
    checksum = hashlib.md5(payload + prefix).hexdigest()
    path.write_bytes(payload + prefix + f"{checksum}  {path.name[:-4]}\n".encode())


class RepackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.ap = self.root / "AP_stock.tar.md5"
        self.boot = self.root / "boot.img"
        self.output = self.root / "AP_root.tar.md5"
        # Structurally minimal fixture, not a real AVB-signed image.
        self.boot.write_bytes(b"ANDROID!" + bytes(4096) + b"AVBf" + bytes(60))
        make_ap(self.ap)

    def test_roundtrip_preserves_other_payloads_and_metadata(self):
        report = repack(self.ap, self.boot, self.output)
        self.assertTrue(report["passed"])
        with tarfile.open(self.ap) as before, tarfile.open(self.output) as after:
            left, right = before.getmembers(), after.getmembers()
            self.assertEqual([x.name for x in left], [x.name for x in right])
            for old, new in zip(left, right):
                for field in ("type", "mode", "uid", "gid", "uname", "gname", "mtime", "linkname", "pax_headers"):
                    self.assertEqual(getattr(old, field), getattr(new, field))
                if old.name == "boot.img.lz4":
                    self.assertEqual(lz4.frame.decompress(after.extractfile(new).read()), self.boot.read_bytes())
                elif old.isreg():
                    self.assertEqual(old.size, new.size)
                    self.assertEqual(before.extractfile(old).read(), after.extractfile(new).read())

    def test_md5_covers_rbs_metadata_too(self):
        repack(self.ap, self.boot, self.output)
        data = self.output.read_bytes()
        prefix, checksum_line, final_empty = data.rsplit(b"\n", 2)
        self.assertEqual(final_empty, b"")
        checksum, filename = checksum_line.split(b"  ", 1)
        self.assertEqual(filename, b"AP_root.tar")
        self.assertEqual(hashlib.md5(prefix + b"\n").hexdigest().encode(), checksum)
        self.assertNotEqual(hashlib.md5(data[:verify_footer(self.output)["tar_size"]]).hexdigest().encode(), checksum)

    def test_rejects_corrupt_archive_without_output(self):
        data = bytearray(self.ap.read_bytes())
        data[1000] ^= 1
        self.ap.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            repack(self.ap, self.boot, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_unknown_footer(self):
        self.ap.write_bytes(self.ap.read_bytes().split(b"Show the build information")[0])
        with self.assertRaisesRegex(ValueError, "Unsupported AP footer"):
            repack(self.ap, self.boot, self.output)

    def test_rejects_missing_or_duplicate_boot(self):
        for names in (["vbmeta.img.lz4"], ["boot.img.lz4", "boot.img.lz4"]):
            with self.subTest(names=names):
                make_ap(self.ap, names)
                with self.assertRaises(ValueError):
                    repack(self.ap, self.boot, self.output)
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.root.glob(".repack-ap-*")), [])

    def test_refuses_existing_output(self):
        self.output.write_bytes(b"keep me")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            repack(self.ap, self.boot, self.output)
        self.assertEqual(self.output.read_bytes(), b"keep me")

    def test_refuses_boot_without_avb_footer(self):
        self.boot.write_bytes(b"ANDROID!" + bytes(100))
        with self.assertRaisesRegex(ValueError, "AVB footer"):
            repack(self.ap, self.boot, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
