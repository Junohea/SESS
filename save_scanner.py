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
        save_root = self.config.ryujinx_base / "portable/bis/user/save"

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

                # Register mapping of folder to title_id
                self.folder_map.register_folder(folder.name, title_id)

                game_info = self.nswdb.get_game_info(title_id) or GameInfo(title_id=title_id, name="Unknown")
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

    def scan_citron(self) -> List[SaveEntry]:
        save_entries = []
        known_ids = set(self.nswdb.game_lookup.keys())
        user_id = self.folder_map.resolve_citron_user(self.config.citron_base, known_ids)
        if not user_id:
            return []

        save_root = self.config.citron_base / "user/nand/user/save/0000000000000000" / user_id

        for folder in save_root.iterdir():
            if not folder.is_dir():
                continue

            # Skip empty save folders
            if not any(f.is_file() for f in folder.rglob("*")):
                continue

            title_id = folder.name.upper()
            # Use a composite key for citron mapping
            self.folder_map.register_folder(f"citron::{user_id}::{title_id}", title_id)

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
                title_id = ''.join(f"{b:02X}" for b in reversed(raw))
                return title_id.upper()
        except Exception:
            pass
        return None

    def _hash_directory(self, directory: Path) -> str:
        md5 = hashlib.md5()
        for file in sorted(directory.rglob("*")):
            if file.is_file():
                md5.update(file.name.encode())
                md5.update(file.read_bytes())
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
