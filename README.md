# Switch Emulator Save Sync

A cross-emulator save synchronizer for Nintendo Switch save data, currently attempting to support Ryujinx and Citron (Yuzu-based) save formats.

### ❗**Use at your own risk: This touches save files**❗

## Quick Overview
- **Bidirectional syncing:** Copy the newest save data between Ryujinx and Citron.
- **Automatic backups:** Before overwriting, saves are zipped and stored (10-save history).


## Installation & Usage
- Clone the repo: `git clone`
- Launch the program: `python gui.py`

## Features

### Scan Saves: Automatically detect and parse save data:
- Reads Ryujinx folders `portable/bis/user/save/<hex>` and extracts titleID from `ExtraData0`
- Reads Citron per-titleID folders `user/nand/user/save/<userID>/<titleID>`

### Sync Saves:
- Single-game sync via double‑click.
- Bulk sync with Sync All button.

### Directional sync: 
- Ryujinx → Citron
- Citron → Ryujinx

### Automatic Backups:
- Zipped backups stored under `backupHistory/<TITLEID>-<GameName>/`
- Keeps up to 10 of the last backups by default (configurable in code).

### Folder Mapping:
- Persists mapping of Ryujinx hex folders ↔ Title IDs in `folder_mapping.json` (note: this is unique per installation)
- Automatically resolves Citron user folder once per session.

### GUI Features:
- Right-click context menu for opening save or backup folders.
- Sortable columns with visual ↑/↓ indicators.
- Color‑coded rows by sync status.
- Filter to show only unsynced entries.
- Persists last-used paths, window size, sort/filter settings in .gui_config.json.


## Usage

### GUI Mode
1. Launch gui.py.
2. Browse to your Ryujinx and Citron base directories.
3. The tool will scan, identify, and display all saves.
4. Double‑click a row to sync that save. (or use Sync All to batch‑sync everything)
5. Right‑click to open save or backup folders.

### CLI Mode (for scripting)
- not yet implemented

## Troubleshooting

### No saves detected:
- Ensure you’ve run the game at least once in Ryujinx to allow it to generate the folders and metadata
- Check that `ExtraData0` and subfolder `0` exist and contain files.

### Empty backups or stale data:
- Remove unwanted backups manually under backupHistory/.
- Delete .gui_config.json or folder_mapping.json to reset.

### Game names are wrong or missing
- Delete `US.en.json` and let the application redownload the latest version

### Sync fails silently:
- Open a console alongside the GUI to see DEBUG or error prints.
- Confirm you chose the correct Citron user folder when prompted.


## Planned Features
- Support for restoring from a specific backup 
- Add support for more emulators
- Better UI?
- CLI stuff


## 🛠️ Contributing

Feel free to add support for additional emulator save formats, improve the backup retention policy (maybe a configurable UI slider), enhance error reporting and logging, or whatever else!

Pull requests and issues are welcome! 