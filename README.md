# Gab MP3-IDTagger

A tabbed desktop MP3 tag editor with integrated audio player, online tag search, multi-language support, and file/folder management.

![Python](https://img.shields.io/badge/python-3.11-blue) ![PySide6](https://img.shields.io/badge/PySide6-6.8-green) ![Mutagen](https://img.shields.io/badge/mutagen-1.48-orange)

## Features

- **Tag Editor** – read/write ID3 tags (title, artist, album, year, genre, track, comment, composer, album artist)
- **Online Tag Search** – fetch metadata from configurable sources (MusicBrainz, Discogs, Spotify, Last.fm, Deezer, Apple iTunes, TheAudioDB, Jamendo, SoundCloud)
- **File/Folder Load** – load single files or whole folders (flat or recursive) with progress dialog
- **Audio Player** – built-in media player with playlist, seek slider, volume control, and M3U export
- **File Moving** – move tagged files to a destination folder, automatically organizing into subfolders and renaming according to configurable patterns (`{artist} - {album}`, `{track} - {artist} - {title}`, etc.)
- **Multi-Language** – German, English, French, Spanish (add your own as a JSON file)
- **Configurable Sources** – add/remove/edit search API sources in Settings
- **Logging** – per-level logging (DEBUG, INFO, WARNING, ERROR) written to `mp3tagger.log`

## Screenshots

*(Screenshots to be added)*

## Requirements

- Python 3.11+
- [PySide6](https://pypi.org/project/PySide6/)
- [mutagen](https://pypi.org/project/mutagen/)

## Usage

```bash
python main.py
```

## Build EXE

```bash
python build_exe.py
```

Output: `dist/Gab_MP3-IDTagger_v0.0.1.exe`

## Build MSI Installer

```bash
python build_msi.py
```

Output: `dist/Gab_MP3-IDTagger-0.0.1.msi`

Optional arguments:

```bash
python build_msi.py --version 2.0.0 --manufacturer "YourName"
```

## Project Structure

```
├── main.py               # Main application
├── build_exe.py          # PyInstaller build script
├── build_msi.py          # MSI package builder
├── languages/            # Translation files (de.json, en.json, fr.json, es.json)
├── config.json           # User configuration (auto-created)
├── mp3tagger.log         # Log file (auto-created)
└── dist/                 # Build output
```

## Configuration

- Sources, naming patterns, log level, and language are stored in `config.json` (next to the EXE)
- Language files live inside the EXE's embedded data directory when frozen

## Online Sources

Default sources require API keys/tokens for some providers (Spotify, Discogs, Last.fm, SoundCloud). Configure them via **Settings → Tag Sources**.