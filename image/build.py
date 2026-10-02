#!/usr/bin/env python3
"""Offline overlay of a pinned official Raspberry Pi OS image. Linux/WSL only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

BASE_URL = "https://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2026-09-15/2026-09-15-raspios-trixie-armhf-lite.img.xz"
BASE_XZ_SHA256 = "c766b3fb279b95c12cb4dd22d06f8eab31972c372675d05bd0ca95b060523a7f"
BASE_IMG_SHA256 = "f6154846c674d27f61f2d91704783f105f2a8d1e40944126ca6d7f60d10644f1"
VERSION = "1.1.0"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, default=Path("/tmp/guido-image-build"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-compression", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    build = args.build_dir.resolve()
    output = (args.output_dir or repo / "output").resolve()
    build.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    compressed = build / "base.img.xz"
    if not compressed.exists():
        run("curl", "--fail", "--location", "--retry", "3", BASE_URL, "-o", str(compressed))
    if digest(compressed) != BASE_XZ_SHA256:
        raise ValueError("Niezgodna suma SHA256 bazowego obrazu XZ")
    base = build / "base.img"
    if not base.exists():
        run("xz", "--decompress", "--keep", str(compressed))
    if digest(base) != BASE_IMG_SHA256:
        raise ValueError("Niezgodna suma SHA256 rozpakowanego obrazu")
    with base.open("rb") as file:
        mbr = file.read(512)
    if mbr[510:512] != b"\x55\xaa":
        raise ValueError("Nieprawidlowy MBR")
    parts = [struct.unpack_from("<B3sB3sII", mbr, 446 + i * 16) for i in range(4)]
    if parts[0][2] != 0x0c or parts[1][2] != 0x83 or parts[2][2] or parts[3][2]:
        raise ValueError("Nieoczekiwany uklad partycji bazowego obrazu")
    root_start, root_size = parts[1][4] * 512, parts[1][5] * 512
    root = build / "root.img"
    with base.open("rb") as source, root.open("wb") as target:
        source.seek(root_start)
        remaining = root_size
        while remaining:
            chunk = source.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                raise ValueError("Niepelny obraz rootfs")
            target.write(chunk)
            remaining -= len(chunk)
    staging = build / "staging"
    staging.mkdir(exist_ok=True)
    files = {}
    for source in sorted((repo / "rpi").rglob("*.py")):
        files["/opt/guido-projectors/" + source.relative_to(repo / "rpi").as_posix()] = (source, 0o644)
    mappings = {
        "guido-config": ("/usr/local/bin/guido-config", 0o755),
        "guido-projectors.service": ("/etc/systemd/system/guido-projectors.service", 0o644),
        "guido-firstboot.service": ("/etc/systemd/system/guido-firstboot.service", 0o644),
        "guido-console.service": ("/etc/systemd/system/guido-console.service", 0o644),
        "guido-tui-sudoers": ("/etc/sudoers.d/guido-tui", 0o440),
        "00-guido-password.conf": ("/etc/ssh/sshd_config.d/00-guido-password.conf", 0o644),
        "guido-welcome.sh": ("/etc/profile.d/guido-welcome.sh", 0o644),
        "guido-journal.conf": ("/etc/systemd/journald.conf.d/guido.conf", 0o644),
    }
    for name, (destination, mode) in mappings.items():
        files[destination] = (repo / "image" / "files" / name, mode)
    files["/usr/local/share/doc/guido-projectors/administracja.md"] = (repo / "docs" / "administracja.md", 0o644)
    dirs = set()
    for destination in files:
        dirs.update(str(parent) for parent in Path(destination).parents if str(parent) != "/")
    commands = []
    for directory in sorted(dirs, key=lambda value: (value.count("/"), value)):
        commands.append(f"mkdir {directory}")
    manifest = {}
    for index, (destination, (source, mode)) in enumerate(files.items()):
        staged = staging / f"file-{index}"
        staged.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        commands.append(f'write "{staged}" {destination}')
        commands.append(f"set_inode_field {destination} mode 0{0o100000 | mode:o}")
        manifest[destination] = {"sha256": digest(staged), "mode": oct(mode)}
    commands.extend([
        "symlink /etc/systemd/system/multi-user.target.wants/guido-projectors.service ../guido-projectors.service",
        "symlink /etc/systemd/system/multi-user.target.wants/guido-firstboot.service ../guido-firstboot.service",
        "symlink /etc/systemd/system/multi-user.target.wants/guido-console.service ../guido-console.service",
        "symlink /etc/systemd/system/userconfig.service /dev/null",
        "symlink /etc/systemd/system/getty@tty1.service /dev/null",
    ])
    script = build / "debugfs.commands"
    script.write_text("\n".join(commands) + "\n")
    run("debugfs", "-w", "-f", str(script), str(root), stdout=(build / "debugfs.log").open("w"), stderr=subprocess.STDOUT)
    # debugfs can return zero even when a command failed; dump every installed file.
    for index, (destination, metadata) in enumerate(manifest.items()):
        check = staging / f"check-{index}"
        check.unlink(missing_ok=True)
        run("debugfs", "-R", f'dump {destination} "{check}"', str(root), capture_output=True)
        if not check.exists() or digest(check) != metadata["sha256"]:
            raise ValueError(f"Blad instalacji pliku {destination}; sprawdz debugfs.log")
    run("e2fsck", "-f", "-n", str(root))
    image = build / f"guido-projectory-rpi3-rpi4-{VERSION}.img"
    shutil.copyfile(base, image)
    with image.open("r+b") as target, root.open("rb") as source:
        target.seek(root_start)
        shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    for board in ("bcm2710-rpi-3-b.dtb", "bcm2711-rpi-4-b.dtb"):
        board_check = staging / board
        board_check.unlink(missing_ok=True)
        run("mcopy", "-i", f"{image}@@{parts[0][4] * 512}", f"::{board}", str(board_check))
    metadata = {
        "version": VERSION, "base_url": BASE_URL, "base_xz_sha256": BASE_XZ_SHA256,
        "base_img_sha256": BASE_IMG_SHA256, "image_sha256": digest(image),
        "image_bytes": image.stat().st_size, "supported_boards": ["Raspberry Pi 3B", "Raspberry Pi 4B"],
        "files": manifest,
    }
    if not args.skip_compression:
        run("xz", "--threads=2", "-4", "--keep", "--force", str(image))
        final = output / (image.name + ".xz")
        shutil.copyfile(Path(str(image) + ".xz"), final)
        metadata["compressed_sha256"] = digest(final)
        metadata["compressed_bytes"] = final.stat().st_size
        (output / "SHA256SUMS.txt").write_text(f"{metadata['compressed_sha256']}  {final.name}\n")
    (output / "image-manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({key: value for key, value in metadata.items() if key != "files"}, indent=2))


if __name__ == "__main__":
    main()
