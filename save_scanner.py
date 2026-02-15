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
            save_dir = folder / "0"

            if extra_data.exists() and save_dir.exists():
                # Skip empty save directories
                if not any(f.is_file() for f in save_dir.rglob("*")):
                    continue

                title_id = self._parse_title_id(extra_data)
                if not title_id:
                    continue

                # Validate TitleID against NSWDB before creating a persistent mapping
                game_info = self.nswdb.get_game_info(title_id)
                if game_info:
                    # Register mapping of Ryujinx folder -> TitleID
                    self.folder_map.register_ryujinx_folder(folder.name, title_id)
                else:
                    # Don't persist unknown/invalid title IDs — still include the save entry but mark unknown
                    game_info = GameInfo(title_id=title_id, name="Unknown (unverified)")
                file_hash = self._hash_directory(save_dir)
                last_modified = self._latest_mod_time(save_dir)

                save_entries.append(SaveEntry(
                    title_id=title_id,
                    game_name=game_info.name,
                    source="ryujinx",
                    folder_id=folder.name,
                    path=save_dir,
                    modified_time=last_modified,
                    hash=file_hash
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
            last_modified = self._latest_mod_time(folder)

            save_entries.append(SaveEntry(
                title_id=title_id,
                game_name=game_info.name,
                source="citron",
                folder_id=user_id,
                path=folder,
                modified_time=last_modified,
                hash=file_hash
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

    def _latest_mod_time(self, directory: Path) -> datetime:
        latest = max(
            (f.stat().st_mtime for f in directory.rglob("*") if f.is_file()),
            default=0.0
        )
        # If no files found, default returns 0.0; convert to datetime
        if latest:
            return datetime.fromtimestamp(latest)
        return datetime.fromtimestamp(0)
