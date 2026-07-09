import sys
import os
from pathlib import Path

try:
    import PyInstaller.__main__
except ImportError:
    print("PyInstaller ist nicht installiert. Installiere...")
    os.system(f"{sys.executable} -m pip install pyinstaller")
    import PyInstaller.__main__

project_dir = Path(__file__).parent
main_script = project_dir / "main.py"
languages_dir = project_dir / "languages"
output_dir = project_dir / "dist"

languages_data = []
for f in sorted(languages_dir.glob("*.json")):
    languages_data.append(f"{f}{os.pathsep}languages")

VERSION = "0.0.1"

args = [
    str(main_script),
    f"--name=Gab_MP3-IDTagger_v{VERSION}",
    "--windowed",
    "--onefile",
    "--clean",
    f"--distpath={output_dir}",
    "--icon=NONE",
    "--add-data",
    f"{languages_dir}{os.pathsep}languages",
    "--hidden-import=mutagen",
    "--hidden-import=mutagen.mp3",
    "--hidden-import=mutagen.id3",
    "--hidden-import=mutagen.easyid3",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtGui",
]

print("=" * 60)
print("Baue Gab MP3-IDTagger.exe ...")
print("=" * 60)

PyInstaller.__main__.run(args)

print("\n" + "=" * 60)
exe_path = output_dir / "Gab_MP3-IDTagger.exe"
if exe_path.exists():
    print(f"✓ Erfolgreich erstellt: {exe_path}")
    print(f"  Größe: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
else:
    print("✗ Fehler beim Erstellen der EXE-Datei")
print("=" * 60)
