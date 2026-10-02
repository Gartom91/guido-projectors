"""Integrity checks for preserving the vendor's boot partition."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("image_build", Path(__file__).resolve().parents[1] / "image/build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_partition_digest_excludes_adjacent_partitions(tmp_path):
    image = tmp_path / "disk.img"
    image.write_bytes(b"MBR" + b"boot contents" + b"root contents")
    expected = hashlib.sha256(b"boot contents").hexdigest()
    assert build.region_digest(image, 3, 13) == expected
    image.write_bytes(b"MBR" + b"boot contents" + b"modified root")
    assert build.region_digest(image, 3, 13) == expected
    image.write_bytes(b"MBR" + b"Boot contents" + b"modified root")
    assert build.region_digest(image, 3, 13) != expected


def test_partition_digest_rejects_truncated_image(tmp_path):
    image = tmp_path / "disk.img"
    image.write_bytes(b"short")
    with pytest.raises(ValueError, match="Truncated"):
        build.region_digest(image, 3, 13)


@pytest.mark.parametrize("offset,size", [(-1, 1), (0, 0), (0, -1)])
def test_partition_digest_rejects_invalid_range(tmp_path, offset, size):
    with pytest.raises(ValueError, match="Invalid"):
        build.region_digest(tmp_path / "disk.img", offset, size)
