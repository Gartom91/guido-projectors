"""Package existing verified binaries, docs and a standalone Windows launcher."""

import hashlib
import argparse
import json
from pathlib import Path
import re
import zipfile

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "output"
PACKAGE = OUT / "installer"
VERSION = "1.3.0"
RELEASE_DATE = "2026-10-05"


def describe(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"name": path.name, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pc-dir", type=Path, default=OUT / "pc")
    args = parser.parse_args()
    PACKAGE.mkdir(parents=True, exist_ok=True)
    image_manifest = json.loads((OUT / "image-manifest.json").read_text())
    image_version = image_manifest["version"]
    version = VERSION
    docs = PACKAGE / "guido-dokumentacja.zip"
    with zipfile.ZipFile(docs, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted([REPO / "README.md", REPO / "NOTICE.md", *REPO.glob("docs/*.md")]):
            entry = zipfile.ZipInfo(path.relative_to(REPO).as_posix(), (*map(int, RELEASE_DATE.split("-")), 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, path.read_bytes())
    image = describe(OUT / image_manifest["image_filename"])
    if (image["sha256"] != image_manifest["compressed_sha256"] or
            image["bytes"] != image_manifest["compressed_bytes"]):
        raise ValueError("Image does not match its build manifest")
    image.update(extract_bytes=image_manifest["image_bytes"], extract_sha256=image_manifest["image_sha256"])
    # Publish the image and the verified PC binary together in the image release.
    image["url"] = f"https://github.com/Gartom91/guido-projectors/releases/download/v{image_version}/{image['name']}"
    pc_path = args.pc_dir / "ShadokProjektory-RPi.exe"
    pc = describe(pc_path)
    pc["url"] = f"https://github.com/Gartom91/guido-projectors/releases/download/v{image_version}/{pc['name']}"
    docs_metadata = describe(docs)
    docs_metadata["url"] = f"https://github.com/Gartom91/guido-projectors/releases/download/v{version}/{docs.name}"
    imager = describe(REPO / "tmp/installer/imager-v2.0.11.1.exe")
    imager["url"] = "https://github.com/raspberrypi/rpi-imager/releases/download/v2.0.11.1/imager-v2.0.11.1.exe"
    if imager["sha256"] != "94ffded522f3e2a38bdb9505440229e1411b80992a616ba16b2d7e73bd794130":
        raise ValueError("Official Imager SHA256 mismatch")
    release = {"version": version, "date": RELEASE_DATE, "image": image,
               "pc": pc, "docs": docs_metadata, "imager": imager}
    source = REPO / "installer/Install-Guido.ps1"
    text = source.read_text(encoding="utf-8-sig")
    embedded = "$script:Release = @'\n" + json.dumps(release, indent=2) + "\n'@ | ConvertFrom-Json"
    text, count = re.subn(r"(?<=# BEGIN_RELEASE_JSON\n).*?(?=\n# END_RELEASE_JSON)", lambda _: embedded, text, flags=re.S)
    if count != 1:
        raise ValueError("Release marker missing or duplicated")
    source.write_text(text, encoding="utf-8-sig", newline="\n")
    (PACKAGE / source.name).write_bytes(source.read_bytes())
    # Read the embedded block by its entire marker line, independent of quoting in the CMD preamble.
    header = ('@echo off\r\nsetlocal\r\nset "GUIDO_INSTALLER_FILE=%~f0"\r\n'
              'set "PSModulePath=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\Modules;%ProgramFiles%\\WindowsPowerShell\\Modules"\r\n'
              'set "GUIDO_DOWNLOAD_ONLY=0"\r\nset "GUIDO_NO_LAUNCH=0"\r\n'
              'if /i "%~1"=="--download-only" set "GUIDO_DOWNLOAD_ONLY=1"\r\n'
              'if /i "%~1"=="--no-launch" set "GUIDO_NO_LAUNCH=1"\r\n'
              'powershell.exe -NoLogo -NoProfile -Command "$lines=[IO.File]::ReadAllLines($env:GUIDO_INSTALLER_FILE); '
              "$begin=[Array]::IndexOf($lines,'# GUIDO_POWERSHELL_BEGIN'); if($begin -lt 0){exit 1}; "
              '& ([scriptblock]::Create(($lines[($begin+1)..($lines.Length-1)] -join [Environment]::NewLine))) '
              "-DownloadOnly:($env:GUIDO_DOWNLOAD_ONLY -eq '1') -NoLaunch:($env:GUIDO_NO_LAUNCH -eq '1')\"\r\n"
              'set "GUIDO_INSTALLER_EXIT=%ERRORLEVEL%"\r\npause\r\nexit /b %GUIDO_INSTALLER_EXIT%\r\n'
              '# GUIDO_POWERSHELL_BEGIN\r\n')
    (PACKAGE / "Install-Guido.cmd").write_text(header + text.replace("\n", "\r\n"), encoding="utf-8", newline="")
    (PACKAGE / "release.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    artifacts = [OUT / image["name"], pc_path, OUT / "image-manifest.json",
                 docs, PACKAGE / "Install-Guido.cmd", PACKAGE / "Install-Guido.ps1", PACKAGE / "release.json"]
    sums = [f"{describe(path)['sha256']}  {path.name}" for path in artifacts]
    (PACKAGE / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
    print(json.dumps({"version": version, "assets": [path.name for path in artifacts] + ["SHA256SUMS.txt"]}))


if __name__ == "__main__":
    main()
