"""Build a relocatable Apple Silicon .app and DMG from pinned public runtimes."""

import argparse
import base64
import hashlib
import json
import platform
import plistlib
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

from build_macos_app import applescript_string, icon

ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.3.1"
PYTHON_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/20260325/"
              "cpython-3.12.13%2B20260325-aarch64-apple-darwin-pgo%2Blto-full.tar.zst")
PYTHON_SHA256 = "a472b083d9c68289836bb6617b921de205a10387e07bb302c1dc8a46c4db758e"
CODEX_URL = "https://registry.npmjs.org/@openai/codex/-/codex-0.156.1-darwin-arm64.tgz"
CODEX_SHA512 = "Jg6wbdV+wmMZczhwE74GSxOYEZlViKXn6KyCw/yfrz3PAKFD14xljuPopmdhWC1+8IKU2WdN5fdmXNPt2q4HPA=="
MACHO = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def digest(path, algorithm="sha256"):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, algorithm).digest()


def download(url, target, expected, algorithm="sha256"):
    expected_bytes = bytes.fromhex(expected) if algorithm == "sha256" else base64.b64decode(expected)
    if not target.exists() or digest(target, algorithm) != expected_bytes:
        partial = target.with_suffix(".download")
        with urlopen(url, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        if digest(partial, algorithm) != expected_bytes:
            raise ValueError(f"Checksum mismatch: {target.name}")
        partial.replace(target)
    return target


def macho_files(root):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as handle:
                if handle.read(4) in MACHO:
                    yield path


def minimum_macos(path):
    with path.open("rb") as handle:
        header = handle.read(32)
        if header[:4] != b"\xcf\xfa\xed\xfe":
            return (0, 0, 0)
        commands = struct.unpack_from("<I", header, 16)[0]
        for _ in range(commands):
            command, size = struct.unpack("<II", handle.read(8))
            payload = handle.read(size - 8)
            if command == 0x32:
                encoded = struct.unpack_from("<I", payload, 4)[0]
                return (encoded >> 16, (encoded >> 8) & 255, encoded & 255)
    return (0, 0, 0)


def sign(path, identity):
    options = ["--options", "runtime", "--timestamp"] if identity != "-" else []
    result = subprocess.run(["/usr/bin/codesign", "--force", "--sign", identity, *options, str(path)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


def clean_finder_metadata(path):
    # Finder metadata only. Quarantine and other security attributes remain intact.
    for attribute in ("com.apple.ResourceFork", "com.apple.FinderInfo"):
        result = subprocess.run(["/usr/bin/xattr", "-r", "-d", attribute, str(path)],
                                capture_output=True, text=True, check=False)
        if result.returncode and "No such xattr" not in result.stderr:
            raise RuntimeError(result.stderr)


def build(output, identity="-", notary_profile=None):
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise ValueError("This builder currently targets Apple Silicon macOS only.")
    if notary_profile and not identity.startswith("Developer ID Application:"):
        raise ValueError("Notarization requires a Developer ID Application identity.")
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / "work/distribution"
    cache.mkdir(parents=True, exist_ok=True)
    python_archive = download(PYTHON_URL, cache / "python-full.tar.zst", PYTHON_SHA256)
    codex_archive = download(CODEX_URL, cache / "openai-codex-0.156.1-darwin-arm64.tgz",
                             CODEX_SHA512, "sha512")
    with tempfile.TemporaryDirectory(prefix="AIStudyPartner-build-") as temp:
        staging = Path(temp)
        source = (ROOT / "macos/launcher.applescript").read_text()
        source = source.replace("property projectRoot : __PROJECT_ROOT__\n", "")
        source = source.replace('quoted form of (projectRoot & "/scripts/app-control.sh")',
                                'quoted form of (POSIX path of (path to resource "app-control.sh"))')
        source = source.replace("__SERVICE_PORT__", "8765")
        source = source.replace("__SERVICE_URL__", applescript_string("http://127.0.0.1:8765/"))
        source = source.replace("__DISPLAY_NAME__", applescript_string("AIStudyPartner 伴讀"))
        script = staging / "launcher.applescript"
        script.write_text(source)
        app = staging / "AIStudyPartner.app"
        run(["/usr/bin/osacompile", "-o", app, script])
        resources = app / "Contents/Resources"
        # Extract only the install tree and license/metadata files from the verified Python archive.
        listing = run(["/usr/bin/tar", "-tf", python_archive], capture_output=True, text=True).stdout.splitlines()
        members = [name for name in listing if name.startswith(("python/install/", "python/licenses/", "python/LICENSE"))
                   or "/licenses/" in name or name == "python/PYTHON.json"]
        members_file = staging / "python-members.txt"
        members_file.write_text("\n".join(members) + "\n")
        unpacked = staging / "python-unpacked"
        unpacked.mkdir()
        run(["/usr/bin/tar", "-xf", python_archive, "-C", unpacked, "-T", members_file])
        shutil.move(unpacked / "python/install", resources / "python")
        licenses = resources / "licenses"
        licenses.mkdir()
        for path in (unpacked / "python").iterdir():
            if path.is_dir():
                shutil.copytree(path, licenses / path.name)
            else:
                shutil.copy2(path, licenses / path.name)
        for name in ["LICENSE", "NOTICE"]:
            url = f"https://raw.githubusercontent.com/openai/codex/rust-v0.156.1/{name}"
            with urlopen(url, timeout=30) as response:
                (licenses / f"CODEX-{name}").write_bytes(response.read())
        with tarfile.open(codex_archive) as archive:
            member = archive.getmember("package/vendor/aarch64-apple-darwin/bin/codex")
            binary = resources / "codex/bin/codex"
            binary.parent.mkdir(parents=True)
            with archive.extractfile(member) as incoming, binary.open("wb") as target:
                shutil.copyfileobj(incoming, target)
            binary.chmod(0o755)
        app_source = resources / "app/study_partner"
        app_source.mkdir(parents=True)
        # Explicit source whitelist: no repository runtime, .env, auth, transcripts, or test assets.
        for path in (ROOT / "study_partner").rglob("*"):
            relative = path.relative_to(ROOT / "study_partner")
            if (path.is_file() and (path.suffix == ".py" or relative.parts[0] == "static")
                    and "__pycache__" not in relative.parts and not path.is_symlink()):
                target = app_source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        requirements = resources / "requirements.lock.txt"
        run(["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--format",
             "requirements-txt", "--output-file", requirements], cwd=ROOT, stdout=subprocess.DEVNULL)
        run(["uv", "pip", "install", "--python", resources / "python/bin/python3.12",
             "--target", resources / "packages", "--link-mode", "copy", "--require-hashes", "--no-compile-bytecode",
             "-r", requirements])
        shutil.copy2(ROOT / "macos/bundle_bootstrap.py", resources / "bootstrap.py")
        shutil.copy2(ROOT / "macos/bundle-control.sh", resources / "app-control.sh")
        (resources / "app-control.sh").chmod(0o755)
        # Prevent writing to the signed bundle; packaged imports are run with -I -B.
        for path in resources.rglob("__pycache__"):
            shutil.rmtree(path)
        binaries = list(macho_files(resources))
        min_os = max([(13, 0, 0), *(minimum_macos(path) for path in binaries)])
        info_path = app / "Contents/Info.plist"
        info = plistlib.loads(info_path.read_bytes())
        info.update(CFBundleIdentifier="local.aistudypartner.standalone", CFBundleName="AIStudyPartner 伴讀",
                    CFBundleDisplayName="AIStudyPartner 伴讀", CFBundleShortVersionString=VERSION,
                    CFBundleVersion="4", OSAAppletStayOpen=True, LSUIElement=False,
                    LSBackgroundOnly=False, LSMultipleInstancesProhibited=True,
                    LSMinimumSystemVersion=".".join(map(str, min_os)), CFBundleIconFile="StudyPartner.icns")
        info.pop("CFBundleIconName", None)
        info.pop("LSMinimumSystemVersionByArchitecture", None)
        for key in list(info):
            if key.startswith("NS") and key.endswith("UsageDescription"):
                del info[key]
        info_path.write_bytes(plistlib.dumps(info))
        icon(resources / "StudyPartner.icns")
        shutil.copy2(resources / "StudyPartner.icns", resources / "applet.icns")
        manifest = {"version": VERSION, "architecture": "arm64", "minimum_macos": info["LSMinimumSystemVersion"],
                    "python": "3.12.13+20260325", "python_sha256": PYTHON_SHA256,
                    "codex": "0.156.1", "codex_sha512": CODEX_SHA512, "model": "gpt-6-astra",
                    "source_commit": run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                    "signing": "ad-hoc; NOT notarized" if identity == "-" else "Developer ID; see release receipt"}
        (resources / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (resources / "THIRD-PARTY-NOTICES.txt").write_text(
            "Python and its bundled dependencies: licenses/ and python/lib/python3.12/LICENSE.txt.\n"
            "Python application dependencies: packages/*.dist-info/licenses and license metadata.\n"
            "OpenAI Codex 0.156.1 (Apache-2.0): licenses/CODEX-LICENSE and CODEX-NOTICE.\n"
            "Only the Codex core binary is included; shell/code-mode/voice resources are not bundled.\n"
            "AIStudyPartner project: https://github.com/pcpcchen-coder/AIStudyPartner\n")
        clean_finder_metadata(app)
        for binary in binaries:
            sign(binary, identity)
        sign(app, identity)
        run(["/usr/bin/codesign", "--verify", "--deep", "--strict", app])
        # The App can be moved anywhere; no developer paths are used by its entry point.
        destination = output / "AIStudyPartner.app"
        if destination.exists():
            raise ValueError("Output already contains AIStudyPartner.app; choose an empty release directory.")
        shutil.move(app, destination)
    image_dir = Path(tempfile.mkdtemp(prefix="AIStudyPartner-dmg-"))
    shutil.copytree(destination, image_dir / "AIStudyPartner.app", symlinks=True)
    # File providers can attach Finder metadata in Documents; stage the disk image
    # outside synced folders and verify the exact App that will go into it.
    clean_finder_metadata(image_dir / "AIStudyPartner.app")
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", image_dir / "AIStudyPartner.app"])
    (image_dir / "Applications").symlink_to("/Applications")
    guide = (
        f"AIStudyPartner {VERSION} — Apple Silicon Mac, macOS {manifest['minimum_macos']} or later\n\n"
        "將 AIStudyPartner 拖到 Applications，再從應用程式開啟。\n"
        "不需另裝 Python、uv、Node、Codex，也不需下載 GitHub 專案。\n"
        "使用自己的 ChatGPT 帳號登入；所選模型仍須帳號權限與額度。\n"
        "按 Dock 圖示 → 關閉服務並退出。\n"
        "若舊版伴讀已執行，請先退出舊版再開啟新版。\n"
        "登入與設定存於 ~/Library/Application Support/AIStudyPartner，不包含作者帳號。\n\n"
        + ("此測試版僅 ad-hoc 簽署，尚未經 Apple 公證，下載後可能被 Gatekeeper 阻擋。\n"
           "它不是免警告的正式發行版；不要關閉系統安全檢查。\n" if identity == "-" else "")
    )
    (image_dir / "安裝說明.txt").write_text(guide)
    (output / "安裝說明.txt").write_text(guide)
    dmg = output / f"AIStudyPartner-{VERSION}-AppleSilicon.dmg"
    run(["/usr/bin/hdiutil", "create", "-volname", "AIStudyPartner", "-srcfolder", image_dir,
         "-format", "UDZO", "-o", dmg])
    if identity != "-":
        run(["/usr/bin/codesign", "--force", "--sign", identity, "--timestamp", dmg])
    if notary_profile:
        receipt = run(["xcrun", "notarytool", "submit", dmg, "--keychain-profile",
                       notary_profile, "--wait", "--output-format", "json"], capture_output=True, text=True)
        (output / "notarization.json").write_text(receipt.stdout)
        if json.loads(receipt.stdout).get("status") != "Accepted":
            raise ValueError("Apple did not accept this notarization; see notarization.json.")
        run(["xcrun", "stapler", "staple", dmg])
    shutil.rmtree(image_dir)
    (output / "SHA256SUMS.txt").write_text(f"{digest(dmg).hex()}  {dmg.name}\n")
    print(dmg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identity", default="-")
    parser.add_argument("--notary-profile")
    args = parser.parse_args()
    build(args.output, args.identity, args.notary_profile)
