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
        # Don't attempt to back up a destination that doesn't yet exist or is empty
        if not save.path.exists():
            print(f"  ℹ️ No existing destination to back up at {save.path}; skipping backup.")
            return

        # Collect files once to avoid a race where the directory changes between checks
        files = [f for f in save.path.rglob("*") if f.is_file()]
        if not files:
            print(f"  ℹ️ No files found to back up in {save.path}; skipping backup.")
            return

        safe_name = sanitize_filename(save.game_name)
        title_folder = self.backup_dir / f"{save.title_id}-{safe_name}"
        title_folder.mkdir(exist_ok=True, parents=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        zip_path = title_folder / f"saveBackup_{timestamp}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files:
                arcname = file.relative_to(save.path)
                zipf.write(file, arcname)

        print(f"  ✔ Backed up {len(files)} file(s) to {zip_path}")
        self._enforce_backup_limit(title_folder, self.config.max_backups)

    def _enforce_backup_limit(self, folder: Path, max_versions: int):
        zips = sorted(folder.glob("saveBackup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_zip in zips[max_versions:]:
            old_zip.unlink()

    def _is_safe_destination(self, dst: Path) -> bool:
        try:
            resolved = dst.resolve()
        except Exception:
            return False
        # Refuse obvious unsafe targets
        if str(resolved) in ('/', str(Path.home())):
            return False
        # Ensure destination is inside one of the known emulator bases
        bases = [self.config.ryujinx_base.resolve(), self.config.citron_base.resolve()]
        for base in bases:
            try:
                if resolved.is_relative_to(base):
                    return True
            except Exception:
                continue
        return False

    def _copy_save(self, src: Path, dst: Path):
        # Basic validation
        if not src.exists() or not src.is_dir():
            raise FileNotFoundError(f"Source save folder does not exist: {src}")
        if not self._is_safe_destination(dst):
            raise RuntimeError(f"Refusing to write outside known emulator roots: {dst}")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tmp = dst.parent / f".sync_tmp_{dst.name}_{timestamp}"
        old = dst.parent / f".sync_old_{dst.name}_{timestamp}"

        # Ensure clean temp
        if tmp.exists():
            shutil.rmtree(tmp)
        # Copy to temporary location first
        shutil.copytree(src, tmp)

        # Move existing dst aside (if present)
        if dst.exists():
            try:
                dst.rename(old)
            except Exception:
                shutil.move(str(dst), str(old))

        # Promote tmp -> dst
        try:
            tmp.rename(dst)
        except Exception:
            shutil.move(str(tmp), str(dst))

        # Cleanup old backup-of-destination
        if old.exists():
            try:
                shutil.rmtree(old)
            except Exception:
                print(f"  ⚠️ Warning: failed to remove old destination {old}")

        print(f"  ✔ Save copied to {dst}")
