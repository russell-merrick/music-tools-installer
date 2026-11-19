# music-tools-installer

Launcher for Hoarder, Reroll, and Resampler. It reads a catalog, downloads one zip per app, checks the sha256, and swaps that app into place. Each app keeps its own version.

Working name. The folder is the name.

Needs Python 3.12. No extra packages.

```powershell
cd music-tools-installer
python -m music_tools_installer list --catalog catalog.example.json
```

Or `run.bat list --catalog catalog.example.json`.

## Commands

| Command | What it does |
|---|---|
| `list` | Catalog version next to what is installed |
| `check` | Same as list. Exits 1 when an installed app is behind |
| `install <id>` | Download that app. Refuses a downgrade unless `--force` |
| `remove <id>` | Stop it and delete its app folder |
| `run <id>` | Start the catalog entry command |
| `stop <id>` | Stop that process |

`--catalog` is a file path or an `https` URL. `--data` overrides the data directory.

## Where files go

`%LOCALAPPDATA%\music-tools-installer\`

```
installed.json
apps\<id>\          contents of the zip
logs\<id>.log
pids\<id>.pid
```

The zip root is the app root. `run` uses that folder as the working directory. An update replaces the whole folder, so user data (Hoarder's `library.db`, Reroll's `user_settings.json`) has to live outside it.

`python` at the start of an entry command is the interpreter that launched the installer.

## Catalog

`catalog.example.json` lists the three apps with empty `url` and `sha256`. Those fields get filled when a zip exists. A real catalog is a file this shape, later hosted at a GitHub Releases URL:

`https://github.com/<you>/music-tools-installer/releases/latest/download/catalog.json`

Each app zip is its own release asset. This repo only stores the catalog that points at them.

## Not in this folder yet

Real app zips, a shared Python, ffmpeg, and a Setup.exe wrapper.
