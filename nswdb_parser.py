import json
import urllib.request
from pathlib import Path
from typing import Dict, Optional
from models import GameInfo

class NSWDBParser:
    """Load and merge titledb JSON files (US.en, JP.ja, HK.zh) from local disk or GitHub.

    - Keeps the first-seen entry per TitleID (no overwrites).
    - Automatically downloads missing/invalid files into the same folder as the provided `json_path`.
    """

    DB_FILES = {
        "US.en.json": "https://raw.githubusercontent.com/blawar/titledb/master/US.en.json",
        "JP.ja.json": "https://raw.githubusercontent.com/blawar/titledb/refs/heads/master/JP.ja.json",
        "HK.zh.json": "https://raw.githubusercontent.com/blawar/titledb/refs/heads/master/HK.zh.json",
        "GB.en.json": "https://raw.githubusercontent.com/blawar/titledb/refs/heads/master/GB.en.json",
    }

    def __init__(self, json_path: Path):
        # `json_path` stays backward-compatible (usually Path('US.en.json'))
        self.json_path = json_path
        self.db_dir = json_path.parent or Path('.')
        self.game_lookup: Dict[str, GameInfo] = {}

    def load(self):
        # Try to load/ensure each DB file (US / JP / HK)
        for fname, url in self.DB_FILES.items():
            path = self.db_dir / fname
            if not path.exists() or self._is_file_empty_or_invalid(path):
                print(f"{fname} not found or invalid, attempting download from {url}...")
                try:
                    self._download_file(url, path)
                except Exception as e:
                    print(f"Warning: download of {fname} failed — continuing without it: {e}")
                    continue

            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}

            for entry in data.values():
                title_id = entry.get("id")
                name = entry.get("name")
                publisher = entry.get("publisher")
                region = entry.get("region")

                if title_id and name:
                    tid = title_id.upper()
                    # Keep the first-seen entry for a TitleID (avoid overwriting)
                    if tid in self.game_lookup:
                        continue
                    self.game_lookup[tid] = GameInfo(
                        title_id=tid,
                        name=name.strip(),
                        publisher=publisher,
                        region=region
                    )

    def _is_file_empty_or_invalid(self, path: Path) -> bool:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                json.load(f)
            return False
        except Exception:
            return True

    def _download_file(self, url: str, target_path: Path):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                status = getattr(response, 'status', None)
                if status is not None and status != 200:
                    raise Exception(f"Download failed with status {status}")
                data = response.read()
                if not data or not data.strip():
                    raise Exception("Downloaded file is empty")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, 'wb') as out_file:
                    out_file.write(data)
        except Exception:
            # cleanup incomplete file
            try:
                if target_path.exists():
                    target_path.unlink()
            except Exception:
                pass
            raise

    def get_game_info(self, title_id: str) -> Optional[GameInfo]:
        if not title_id:
            return None
        return self.game_lookup.get(title_id.upper())
