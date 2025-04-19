import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from models import SaveEntry, Config
import re

def sanitize_filename(name: str) -> str:
    # Replace invalid characters with underscore or strip them
    return re.sub(r'[<>:"/\\|?*™]', '_', name)

class SyncEngine:
    def __init__(self, config: Config):
        self.config = config
        self.backup_dir = config.backup_dir
        self.backup_dir.mkdir(exist_ok=True, parents=True)

    def sync(self, source: SaveEntry, destination: SaveEntry):
        """
        Sync source save to destination.
        """
        print(f"[SYNC] {source.game_name}: {source.source} → {destination.source}")
        self._backup(destination)
        self._copy_save(source.path, destination.path)

    def _backup(self, save: SaveEntry):
        safe_name = sanitize_filename(save.game_name)
        title_folder = self.backup_dir / f"{save.title_id}-{safe_name}"
        title_folder.mkdir(exist_ok=True, parents=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        zip_path = title_folder / f"saveBackup_{timestamp}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in save.path.rglob("*"):
                if file.is_file():
                    arcname = file.relative_to(save.path)
                    zipf.write(file, arcname)

        self._enforce_backup_limit(title_folder, self.config.max_backups)

    def _enforce_backup_limit(self, folder: Path, max_versions: int):
        zips = sorted(folder.glob("saveBackup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_zip in zips[max_versions:]:
            old_zip.unlink()

    def _copy_save(self, src: Path, dst: Path):
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"  ✔ Save copied to {dst}")
