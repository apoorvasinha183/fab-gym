"""Build public desktop downloads and a static web folder from the prepared game.

python3 viz/fab3d/export_game.py --godot /path/to/Godot --out /path/to/downloads
Uses installed Godot 4.7.2 export templates. Assets are prepared once with prep.py and record_demo.py.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
PRESETS = PROJECT / "export_presets.cfg"


def archive_folder(folder, destination):
    """Publish only complete archives, and remove partial writes after failure."""
    temporary = destination.with_suffix(".partial.zip")
    try:
        shutil.make_archive(str(temporary.with_suffix("")), "zip", folder)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default="godot")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--platform", choices=["all", "macOS", "Windows", "Linux", "Web"], default="all")
    parser.add_argument("--linux-template", type=Path, help="Optional official release template kept outside the global template folder")
    parser.add_argument("--web-zip", action="store_true", help="Also zip the browser folder; requires space for a second copy")
    args = parser.parse_args()
    version = subprocess.check_output([args.godot, "--version"], text=True).strip()
    if not version.startswith("4.7.2."):
        parser.error(f"Expected Godot 4.7.2, found {version}")
    for name in ["campus.json", "cinema-built.json", "demo.json", "models/fab-building.glb",
                 "film/sand-to-chip-v10.ogv", "film/crime-and-punishment-acted.ogv"]:
        if not (PROJECT / "data" / name).is_file():
            parser.error(f"Missing prepared game asset: data/{name}. Run prep.py and record_demo.py first.")
    output = args.out.resolve()
    if output.is_relative_to(PROJECT):
        parser.error("Keep downloads outside the Godot project so exports cannot include previous builds.")
    output.mkdir(parents=True, exist_ok=True)
    presets = PRESETS.read_text()
    try:
        if args.linux_template:
            template = args.linux_template.resolve()
            if not template.is_file():
                parser.error(f"Missing Linux template: {template}")
            PRESETS.write_text(presets.replace("[preset.2.options]", '[preset.2.options]\ncustom_template/release=' + json.dumps(str(template))))
        targets = {"macOS": output / "Fab-Gym-3D-macOS.zip", "Windows": output / "windows/Fab-Gym-3D.exe",
                   "Linux": output / "linux/Fab-Gym-3D.x86_64", "Web": output / "web/index.html"}
        for platform, destination in targets.items():
            if args.platform not in ("all", platform):
                continue
            if platform in ("Windows", "Linux"):
                # Only one uncompressed desktop build exists at a time.
                with tempfile.TemporaryDirectory(prefix="fab-gym-export-", dir=output) as d:
                    target = Path(d) / destination.name
                    subprocess.run([args.godot, "--headless", "--path", str(PROJECT), "--export-release", platform, str(target)], check=True)
                    shutil.copyfile(PROJECT / "PLAYING.txt", Path(d) / "PLAYING.txt")
                    archive_folder(d, output / f"Fab-Gym-3D-{platform}.zip")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run([args.godot, "--headless", "--path", str(PROJECT), "--export-release", platform, str(destination)], check=True)
                if platform == "Web":
                    shutil.copyfile(PROJECT / "PLAYING.txt", destination.parent / "PLAYING.txt")
                    if args.web_zip:
                        archive_folder(destination.parent, output / "Fab-Gym-3D-Web.zip")
                else:
                    with zipfile.ZipFile(destination, "a", compression=zipfile.ZIP_DEFLATED) as z:
                        z.write(PROJECT / "PLAYING.txt", "PLAYING.txt")
        checksums = {}
        for path in output.glob("Fab-Gym-3D-*.zip"):
            with path.open("rb") as f:
                checksums[path.name] = hashlib.file_digest(f, "sha256").hexdigest()
        (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items())))
        print(f"Builds ready in {output}")
    finally:
        if PRESETS.read_text() != presets:
            PRESETS.write_text(presets)


if __name__ == "__main__":
    main()
