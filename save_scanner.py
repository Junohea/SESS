import hashlib
import struct
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from models import SaveEntry, GameInfo
from nswdb_parser import NSWDBParser
from foldermap import FolderMap

class SaveScanner:
    def __init__(self, config, nswdb_parser: NSWDBParser):
        self.config = config
        self.nswdb = nswdb_parser
        self.folder_map = FolderMap(config.mapping_path)

    def scan_ryujinx(self) -> List[SaveEntry]:
        save_entries = []
        save_root = self._resolve_ryujinx_save_root()

        if not save_root or not save_root.exists():
            return []

        for folder in save_root.iterdir():
            if not folder.is_dir():
                continue

            extra_data = folder / "ExtraData0"

            # If ExtraData0 exists we can determine the TitleID — register a folder mapping
            # for known titleIDs even if the numeric slot folders are currently empty.
            if not extra_data.exists():
                continue

            title_id = self._parse_title_id(extra_data)
            if not title_id:
                continue

            # Validate TitleID against NSWDB and persist the mapping for *known* titles.
            # (Do not persist unknown/invalid titleIDs — keep prior behavior.)
            game_info = self.nswdb.get_game_info(title_id)
            if game_info:
                self.folder_map.register_ryujinx_folder(folder.name, title_id)

            # Ryujinx may store per-user slots under numeric names (0, 1, 2...).
            # Detect any numeric slot directory and prefer the most-recent non-empty slot.
            existing_slots = [s for s in folder.iterdir() if s.is_dir() and s.name.isdigit()]

            # Consider numeric slot directories and collect per-slot diagnostics
            non_empty_slots = [s for s in existing_slots if any(f.is_file() for f in s.rglob("*"))]
            if not non_empty_slots:
                continue

            def _slot_latest_mtime(s: Path) -> float:
                try:
                    return max((f.stat().st_mtime for f in s.rglob("*") if f.is_file()), default=0.0)
                except Exception:
                    return 0.0

            # Choose the primary slot (most-recent non-empty) for the SaveEntry.path/hash
            primary_slot = max(non_empty_slots, key=_slot_latest_mtime)

            # Gather per-slot metrics and also aggregate totals for the Ryujinx SaveEntry
            slots_info = {}
            aggregated_file_count = 0
            aggregated_max_size = 0
            aggregated_latest = 0.0

            for s in non_empty_slots:
                slot_hash = self._hash_directory(s)
                slot_mtime = self._latest_mod_time(s)
                slot_file_count = 0
                slot_max_size = 0
                for f in s.rglob("*"):
                    if not f.is_file():
                        continue
                    if f.name in ("ExtraData0", "ExtraData1"):
                        continue
                    slot_file_count += 1
                    try:
                        sz = f.stat().st_size
                    except Exception:
                        sz = 0
                    if sz > slot_max_size:
                        slot_max_size = sz
                slots_info[s.name] = {
                    'hash': slot_hash,
                    'modified_time': slot_mtime,
                    'file_count': slot_file_count,
                    'max_file_size': slot_max_size,
                    'path': s,
                }
                aggregated_file_count += slot_file_count
                if slot_max_size > aggregated_max_size:
                    aggregated_max_size = slot_max_size
                mt = 0.0
                try:
                    mt = max((f.stat().st_mtime for f in s.rglob('*') if f.is_file()), default=0.0)
                except Exception:
                    mt = 0.0
                if mt > aggregated_latest:
                    aggregated_latest = mt

            # If game_info wasn't found earlier (unknown titleID), represent it as Unknown for the SaveEntry
            if not game_info:
                game_info = GameInfo(title_id=title_id, name="_Unknown (Not found in titleID json files)")

            # Primary slot determines the canonical hash/path for backward-compatible behavior
            primary_hash = slots_info[primary_slot.name]['hash']
            last_modified = datetime.fromtimestamp(aggregated_latest) if aggregated_latest else self._latest_mod_time(primary_slot)

            save_entries.append(SaveEntry(
                title_id=title_id,
                game_name=game_info.name,
                source="ryujinx",
                folder_id=folder.name,
                path=primary_slot,
                modified_time=last_modified,
                hash=primary_hash,
                file_count=aggregated_file_count,
                max_file_size=aggregated_max_size,
                slots=slots_info
            ))

        return save_entries

    def _resolve_ryujinx_save_root(self):
        """Detect the most likely Ryujinx save root under the configured base."""
        base = self.config.ryujinx_base
        candidates = [
            base / "portable/bis/user/save",
            base / "user/save",
            base / "save",
            base / "portable/user/save",
            base,
        ]
        for cand in candidates:
            if cand.exists() and cand.is_dir():
                return cand
        # As a fallback, try to find a folder containing ExtraData0 somewhere under base
        try:
            for p in base.rglob("ExtraData0"):
                # ExtraData0 is inside <folder>/ExtraData0, so parent.parent should be save root structure
                possible = p.parents[1]
                if possible.exists():
                    return possible
        except Exception:
            pass
        return None

    def scan_citron(self) -> List[SaveEntry]:
        save_entries = []
        known_ids = set(self.nswdb.game_lookup.keys())
        user_id = self.folder_map.resolve_citron_user(self.config.citron_base, known_ids)
        if not user_id:
            return []

        # Determine actual save_root. Prefer any cached base discovered by FolderMap
        cached_base = getattr(self.folder_map, 'cached_citron_base', None)
        save_root = None
        if cached_base:
            # If cached_base already points to the 0000 folder
            if cached_base.name == "0000000000000000":
                save_root = cached_base / user_id
            else:
                # Try some likely subpaths under the cached base
                candidates = [
                    cached_base / "user/nand/user/save/0000000000000000" / user_id,
                    cached_base / "user/save/0000000000000000" / user_id,
                    cached_base / "user/nand/user/save" / user_id,
                    cached_base / "user/save" / user_id,
                    cached_base / user_id,
                ]
                for cand in candidates:
                    if cand.exists() and cand.is_dir():
                        save_root = cand
                        break

        if not save_root:
            # Fallback to configured citron base
            save_root = self.config.citron_base / "user/nand/user/save/0000000000000000" / user_id

        for folder in save_root.iterdir():
            if not folder.is_dir():
                continue

            # Skip empty save folders
            if not any(f.is_file() for f in folder.rglob("*")):
                continue

            title_id = folder.name.upper()
            # Citron mappings are not persisted (they are derived from the filesystem/user id)
            # No persistent registration here - leave Ryujinx mappings separate.

            game_info = self.nswdb.get_game_info(title_id) or GameInfo(title_id=title_id, name="Unknown")
            file_hash = self._hash_directory(folder)
            # Exclude ExtraData0/ExtraData1 when computing the 'last modified' time for Citron saves
            last_modified = self._latest_mod_time(folder, exclude_names={"ExtraData0", "ExtraData1"})

            # Compute file-count and largest-file (exclude ExtraData0/ExtraData1)
            file_count = 0
            max_size = 0
            for f in folder.rglob("*"):
                if not f.is_file():
                    continue
                if f.name in ("ExtraData0", "ExtraData1"):
                    continue
                file_count += 1
                try:
                    sz = f.stat().st_size
                except Exception:
                    sz = 0
                if sz > max_size:
                    max_size = sz

            save_entries.append(SaveEntry(
                title_id=title_id,
                game_name=game_info.name,
                source="citron",
                folder_id=user_id,
                path=folder,
                modified_time=last_modified,
                hash=file_hash,
                file_count=file_count,
                max_file_size=max_size
            ))

        return save_entries

    def _parse_title_id(self, path: Path) -> Optional[str]:
        try:
            data = path.read_bytes()
            if len(data) >= 8:
                raw = data[0:8]
                title_id = ''.join(f"{b:02X}" for b in reversed(raw)).upper()
                # Validate format (16 hex characters)
                import re
                if re.match(r'^[0-9A-F]{16}$', title_id):
                    return title_id
        except Exception:
            pass
        return None

    def _hash_directory(self, directory: Path) -> str:
        """Hash directory contents deterministically.
        - include relative path to avoid collisions from identical filenames in different subfolders
        - stream file contents to avoid large memory spikes
        """
        md5 = hashlib.md5()
        for file in sorted(directory.rglob("*")):
            if not file.is_file():
                continue
            rel = file.relative_to(directory).as_posix().encode('utf-8')
            md5.update(rel)
            # stream file contents
            try:
                with file.open('rb') as fh:
                    while True:
                        chunk = fh.read(8192)
                        if not chunk:
                            break
                        md5.update(chunk)
            except Exception:
                # if a file can't be read, include its name + size as a fallback
                try:
                    md5.update(f"UNREADABLE:{file.name}:{file.stat().st_size}".encode())
                except Exception:
                    md5.update(file.name.encode())
        return md5.hexdigest()

    def _latest_mod_time(self, directory: Path, exclude_names: Optional[set] = None) -> datetime:
        """Return the latest modification time for files under `directory`.

        If `exclude_names` is provided, files whose name matches any entry in the set
        are ignored (useful to exclude ExtraData0/ExtraData1 metadata files).
        """
        if exclude_names is None:
            exclude_names = set()
        latest = max(
            (f.stat().st_mtime for f in directory.rglob("*") if f.is_file() and f.name not in exclude_names),
            default=0.0
        )
        # If no files found, default returns 0.0; convert to datetime
        if latest:
            return datetime.fromtimestamp(latest)
        return datetime.fromtimestamp(0)
