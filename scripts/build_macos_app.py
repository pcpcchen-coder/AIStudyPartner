"""Build a local launcher .app without Xcode or bundling credentials/student data."""

import argparse
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from macos_lifecycle import temporary_apps
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ID = "local.aistudypartner.desktop"


def applescript_string(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def icon(path):
    image = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 32, 992, 992), radius=218, fill="#28746a")
    # Open book, central fold, and a warm four-point guiding star.
    draw.polygon([(200, 300), (365, 265), (512, 325), (659, 265), (824, 300),
                  (824, 746), (659, 711), (512, 778), (365, 711), (200, 746)], fill="#f8f9f5")
    draw.line([(512, 345), (512, 738)], fill="#a9c9b8", width=18)
    for offset in (0, 85, 170):
        draw.line([(256, 405 + offset), (433, 438 + offset)], fill="#a9c9b8", width=20)
        draw.line([(591, 438 + offset), (768, 405 + offset)], fill="#a9c9b8", width=20)
    draw.ellipse((680, 137, 922, 379), fill="#28746a")
    draw.polygon([(801, 137), (829, 230), (922, 258), (829, 286),
                  (801, 379), (773, 286), (680, 258), (773, 230)], fill="#efce82")
    image.save(path, format="ICNS")


def build(destination, name="AIStudyPartner 伴讀", port=8765):
    destination = Path(destination).expanduser().absolute()
    if destination.suffix != ".app":
        raise ValueError("安裝位置必須以 .app 結尾。")
    if destination.exists():
        info = destination / "Contents/Info.plist"
        if not info.exists() or plistlib.loads(info.read_bytes()).get("CFBundleIdentifier") not in {BUNDLE_ID, "local.aistudypartner.standalone"}:
            raise ValueError("目的位置有其他 App，未覆蓋。")
        # Do not replace an active applet; its quit handler must stay intact.
        running = subprocess.run(["/bin/ps", "-axo", "command="], capture_output=True, text=True, check=True)
        if str(destination / "Contents/MacOS/applet") in running.stdout:
            raise ValueError("請先退出伴讀 App，再重新安裝。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "macos/launcher.applescript").read_text()
    for token, value in {
        "__PROJECT_ROOT__": applescript_string(str(ROOT)),
        "__SERVICE_PORT__": str(port),
        "__SERVICE_URL__": applescript_string(f"http://127.0.0.1:{port}/"),
        "__DISPLAY_NAME__": applescript_string(name),
    }.items():
        source = source.replace(token, value)
    with temporary_apps("AIStudyPartner-launcher-") as temporary:
        script = Path(temporary) / "launcher.applescript"
        script.write_text(source)
        app = Path(temporary) / destination.name
        subprocess.run(["/usr/bin/osacompile", "-o", str(app), str(script)], check=True)
        info_path = app / "Contents/Info.plist"
        info = plistlib.loads(info_path.read_bytes())
        info.update(CFBundleIdentifier=BUNDLE_ID, CFBundleName=name, CFBundleDisplayName=name,
                    CFBundleShortVersionString="0.2.0", CFBundleVersion="2",
                    LSUIElement=False, LSBackgroundOnly=False, LSMultipleInstancesProhibited=True,
                    LSMinimumSystemVersion="13.0",
                    NSAppleScriptEnabled=True, OSAAppletStayOpen=True, CFBundleIconFile="StudyPartner.icns")
        info.pop("CFBundleIconName", None)  # Otherwise the system applet asset overrides our icon.
        for key in list(info):
            if key.startswith("NS") and key.endswith("UsageDescription"):
                del info[key]
        info_path.write_bytes(plistlib.dumps(info))
        icon(app / "Contents/Resources/StudyPartner.icns")
        shutil.copyfile(app / "Contents/Resources/StudyPartner.icns",
                        app / "Contents/Resources/applet.icns")
        # Ad-hoc signing is local integrity only, not Developer ID distribution/notarization.
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True)
        # Both installers use the same replace/backup/unregister procedure.
        sys.path.insert(0, str(ROOT))
        from study_partner.installation import install

        directories = [destination.parent]
        if destination.parent == Path.home() / "Applications":
            directories.append(Path("/Applications"))
        install(app, directories=directories, destination=destination)
    subprocess.run([("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                     "LaunchServices.framework/Support/lsregister"), "-f", str(destination)], check=True)
    print(destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path.home() / "Applications/AIStudyPartner.app")
    parser.add_argument("--name", default="AIStudyPartner 伴讀")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("App 打包僅支援 macOS。")
    build(args.output, args.name, args.port)
