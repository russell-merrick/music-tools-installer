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

## Plan

One installer. The three apps stay folders under `apps\<id>`. One Python runs all of them. Do not freeze each app into its own exe.

What works today: `list`, `check`, `install`, `remove`, `run`, and `stop` against a catalog. `catalog.example.json` has empty `url` and `sha256`, so `list` works and `install` does not. `run` starts the server only. It does not open a window. The desktop shortcuts (`Hoarder.lnk`, `Reroll.lnk`, `Resampler.lnk`) point at the git folders on the Desktop. Leave those for development.

Pick this up locally first. No GitHub release yet.

1. Zip each app from its current folder. Fill `url` and `sha256` in a local catalog. `install` puts the zip contents in `apps\<id>`.
2. `run` starts the server when the health check is down, then opens an Edge app window the way each repo's `launch.ps1` does. Closing the window leaves the server running.
3. A release shortcut points at the installed folder, not the git checkout.
4. Keep user data outside `apps\<id>` before the first update. An update replaces the whole folder. That means Hoarder's `library.db` and Reroll's `user_settings.json`.

Health checks to copy from the app launchers: Hoarder `GET http://127.0.0.1:8770/api/status`, Reroll `:8000/api/health`, Resampler `:8787/api/health`. Each Edge window uses its own profile under `%LOCALAPPDATA%\<App>\edge` and opens at 1280×800. Resampler's working start is `python -m resample.cli serve` with `PYTHONPATH` pointed at `src`. The catalog entry `resample serve` needs that same lookup.

After that slice works: a Setup.exe wrapper, one bundled Python, ffmpeg for Hoarder, then `catalog.json` on this repo's GitHub release and each app zip on that app's own release. The Python already on the machine is enough until the bundled runtime exists.

Repo: https://github.com/russell-merrick/music-tools-installer

## Not in this folder yet

Real app zips, a shared Python, ffmpeg, and a Setup.exe wrapper.
