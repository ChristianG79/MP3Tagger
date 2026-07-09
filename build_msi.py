"""
MSI-Installer für Gab MP3-IDTagger (nutzt python msilib).
Nutzung: python build_msi.py [--version X.Y.Z]
"""
import sys
import argparse
import msilib
from pathlib import Path
from msilib import add_data, gen_uuid, schema
from msilib.schema import Feature, Component, Directory, File, Shortcut, FeatureComponents

project_dir = Path(__file__).parent
dist_dir = project_dir / "dist"
exe_path = dist_dir / "Gab_MP3-IDTagger.exe"
languages_dir = project_dir / "languages"

if not exe_path.exists():
    print("FEHLER: EXE nicht gefunden. Bitte zuerst build_exe.py starten.")
    sys.exit(1)

parser = argparse.ArgumentParser(description="MSI-Installer für Gab MP3-IDTagger")
parser.add_argument("--name", default="Gab MP3-IDTagger")
parser.add_argument("--manufacturer", default="Gab Software")
parser.add_argument("--version", default="0.0.1")
parser.add_argument("--description", default="MP3-Tag-Editor mit integriertem Audio-Player")
args = parser.parse_args()

app_name = args.name
manufacturer = args.manufacturer
version = args.version
description = args.description

msi_name = f"Gab_MP3-IDTagger-{version}.msi"
msi_path = dist_dir / msi_name
upgrade_code = "{F7D4B3E1-2A5C-4E8D-9B6F-1C3A5D7E9B0C}"
product_code = gen_uuid()

print("=" * 60)
print(f"Erstelle MSI: {msi_name}")
print(f"  ProductName : {app_name}")
print(f"  Version     : {version}")
print(f"  Manufacturer: {manufacturer}")
print("=" * 60)

# ------------------------------------------------------------
# DB initialisieren
# ------------------------------------------------------------
db = msilib.init_database(str(msi_path), schema, app_name, product_code, version, manufacturer)

# Feature: Feature, Feature_Parent, Title, Description, Display, Level, Directory_, Attributes
add_data(db, "Feature", [
    ("MainFeature", "", app_name, description, "", 1, "", 0),
])

# Component: Component, ComponentId, Directory_, Attributes, Condition, KeyPath
add_data(db, "Component", [
    ("MainComponent", None, "APPLICATIONFOLDER", 0, "", ""),
])

# Directory: Directory, Directory_Parent, DefaultDir
add_data(db, "Directory", [
    ("TARGETDIR", "", "SourceDir"),
    ("ProgramFilesFolder", "TARGETDIR", "."),
    ("APPLICATIONFOLDER", "ProgramFilesFolder", "Gab_MP3-IDTagger"),
])

# File: File, Component_, FileName, FileSize, Version, Language, Attributes, Sequence
files = []
seq = 1
files.append(("MainExe", "MainComponent", "Gab_MP3-IDTagger.exe", exe_path.stat().st_size,
              "", "", "", seq))
seq += 1
for f in sorted(languages_dir.glob("*.json")):
    fid = f"Lang_{f.stem}"
    files.append((fid, "MainComponent", f.name, f.stat().st_size, "", "", "", seq))
    seq += 1
add_data(db, "File", files)

# FeatureComponents: Feature_, Component_
add_data(db, "FeatureComponents", [
    ("MainFeature", "MainComponent"),
])

# Shortcut: Shortcut, Directory_, Name, Component_, Target, Arguments, Description, Hotkey, Icon_, IconIndex, ShowCmd, WkDir
add_data(db, "Shortcut", [
    ("S_MainExe", "StartMenuFolder", "Gab MP3-IDTagger", "MainComponent", "MainExe",
     "", "", "", "", "", "", ""),
])

# Upgrade: UpgradeCode, VersionMin, VersionMax, Language, Attributes, Remove, ActionProperty
add_data(db, "Upgrade", [
    (upgrade_code, "", "", "", 0, "", "OLDPRODUCTS"),
])

# InstallExecuteSequence: Action, Condition, Sequence
add_data(db, "InstallExecuteSequence", [
    ("FindRelatedProducts", "", 25),
    ("MigrateFeatureStates", "", 1200),
    ("RemoveExistingProducts", "", 6600),
])

# ------------------------------------------------------------
# CAB-Archiv
# ------------------------------------------------------------
cab = msilib.CAB("GabMP3")
cab.append(str(exe_path), "Gab_MP3-IDTagger.exe", "")
for f in sorted(languages_dir.glob("*.json")):
    cab.append(str(f), f.name, "")
cab.commit(db)

# Commit
db.Commit()

if msi_path.exists():
    print(f"\nMSI erstellt: {msi_path}")
    print(f"  Größe: {msi_path.stat().st_size / 1024 / 1024:.1f} MB")
else:
    print("\nFEHLER: MSI wurde nicht erstellt.")