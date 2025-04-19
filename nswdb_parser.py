import json
import urllib.request
from pathlib import Path
from typing import Dict, Optional
from models import GameInfo

class NSWDBParser:
    def __init__(self, json_path: Path):
        self.json_path = json_path
        self.url = "https://raw.githubusercontent.com/blawar/titledb/master/US.en.json"
        self.game_lookup: Dict[str, GameInfo] = {}

    def load(self):
        if not self.json_path.exists() or self._is_file_empty_or_invalid():
            print(f"US.en.json not found or invalid, downloading from {self.url}...")
            self._download_json()

        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for entry in data.values():
            title_id = entry.get("id")
            name = entry.get("name")
            publisher = entry.get("publisher")
            region = entry.get("region")

            if title_id and name:
                self.game_lookup[title_id.upper()] = GameInfo(
                    title_id=title_id.upper(),
                    name=name.strip(),
                    publisher=publisher,
                    region=region
                )

    def _is_file_empty_or_invalid(self) -> bool:
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                json.load(f)
            return False
        except Exception:
            return True

    def _download_json(self):
        try:
            with urllib.request.urlopen(self.url) as response:
                if response.status != 200:
                    raise Exception(f"Download failed with status {response.status}")
                data = response.read()
                if not data.strip():
                    raise Exception("Downloaded file is empty")
                with open(self.json_path, 'wb') as out_file:
                    out_file.write(data)
        except Exception as e:
            print(f"Download failed: {e}")
            if self.json_path.exists():
                self.json_path.unlink()
            raise

    def get_game_info(self, title_id: str) -> Optional[GameInfo]:
        return self.game_lookup.get(title_id.upper())
