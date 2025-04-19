import json
from pathlib import Path
from typing import Dict, Optional
from typing import Callable

prompt_for_choice_gui: Optional[Callable[[list[str]], Optional[str]]] = None

class FolderMap:
    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, str] = {}
        self.cached_citron_user: Optional[str] = None  # NEW
        self.load()
        
    def load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)

    def get_title_id(self, folder_id: str) -> Optional[str]:
        return self.data.get(folder_id)

    def get_folder_id(self, title_id: str) -> Optional[str]:
        for fid, tid in self.data.items():
            if tid.upper() == title_id.upper():
                return fid
        return None

    def register_folder(self, folder_id: str, title_id: str):
        self.data[folder_id] = title_id.upper()
        self.save()

    def resolve_citron_user(self, citron_base: Path, known_title_ids: set) -> Optional[str]:
        if self.cached_citron_user:
            return self.cached_citron_user

        base = citron_base / "user/nand/user/save/0000000000000000"
        candidates = []

        for folder in base.iterdir():
            if folder.is_dir():
                for subfolder in folder.iterdir():
                    if subfolder.name.upper() in known_title_ids:
                        candidates.append(folder.name)
                        break

        if not candidates:
            print("❌ No valid Citron user folder found with known titleIDs.")
            return None

        elif len(candidates) == 1:
            self.cached_citron_user = candidates[0]
            return self.cached_citron_user  # ✅ early return after setting

        elif prompt_for_choice_gui:
            self.cached_citron_user = prompt_for_choice_gui(candidates)
            return self.cached_citron_user  # ✅ early return after GUI choice

        else:
            print("Multiple Citron user folders detected. Please choose:")
            for idx, folder in enumerate(candidates):
                print(f"  [{idx}] {folder}")
            choice = input("Enter the number of the correct folder: ")
            try:
                self.cached_citron_user = candidates[int(choice.strip())]
                return self.cached_citron_user  # ✅ early return after manual input
            except (IndexError, ValueError):
                print("Invalid selection.")
                return None