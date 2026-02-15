import json
import os
from pathlib import Path
from typing import Dict, Optional
from typing import Callable

prompt_for_choice_gui: Optional[Callable[[list[str]], Optional[str]]] = None

class FolderMap:
    def __init__(self, path: Path):
        self.path = path
        # Internal maps (new schema stores a 'ryujinx' dict)
        self.ryujinx: Dict[str, str] = {}
        self.cached_citron_user: Optional[str] = None
        self.cached_citron_base: Optional[Path] = None
        self.load()
        
    def load(self):
        # Support both legacy flat maps and the new namespaced schema
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)

                # 1) New namespaced schema: { "ryujinx": { ... } }
                if isinstance(raw, dict) and 'ryujinx' in raw and isinstance(raw['ryujinx'], dict):
                    self.ryujinx = {k: v.upper() for k, v in raw['ryujinx'].items()}

                # 2) Legacy flat schema: { "<folder_id>": "<title_id>", ... }
                elif isinstance(raw, dict) and raw and all(isinstance(v, str) for v in raw.values()):
                    self.ryujinx = {k: v.upper() for k, v in raw.items()}

                else:
                    self.ryujinx = {}
            except Exception:
                self.ryujinx = {}

    def save(self):
        # Persist only the ryujinx mapping under a namespaced key for clarity
        to_write = {'ryujinx': self.ryujinx}
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(to_write, f, indent=2)

    # --- Ryujinx-specific mapping API (explicit, unambiguous) ---
    def get_ryujinx_title_id(self, folder_id: str) -> Optional[str]:
        return self.ryujinx.get(folder_id)

    def get_ryujinx_folder_id(self, title_id: str) -> Optional[str]:
        for fid, tid in self.ryujinx.items():
            if tid.upper() == title_id.upper():
                return fid
        return None

    def register_ryujinx_folder(self, folder_id: str, title_id: str):
        self.ryujinx[folder_id] = title_id.upper()
        self.save()

    # Backwards-compatible aliases that operate only on Ryujinx mappings
    def get_title_id(self, folder_id: str) -> Optional[str]:
        return self.get_ryujinx_title_id(folder_id)

    def get_folder_id(self, title_id: str) -> Optional[str]:
        return self.get_ryujinx_folder_id(title_id)

    def register_folder(self, folder_id: str, title_id: str):
        return self.register_ryujinx_folder(folder_id, title_id)

    def resolve_citron_user(self, citron_base: Path, known_title_ids: set) -> Optional[str]:
        if self.cached_citron_user:
            return self.cached_citron_user

        # Check for Citron's custom global save path in qt-config.ini
        config_file = citron_base / "user/config/qt-config.ini"
        base = None
        try:
            if config_file.exists():
                for line in config_file.read_text(encoding='utf-8', errors='ignore').splitlines():
                    if 'global_custom_save_path' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            val = parts[1].strip().strip('"').strip("'")
                            # Ignore explicit false/disabled values
                            if not val or val.lower() in ('false', '0', 'none'):
                                continue
                            # Expand environment vars and user home
                            expanded = os.path.expandvars(val)
                            p = Path(expanded).expanduser()
                            if p.exists() and p.is_dir():
                                # Try common subpaths where citron may place the actual save 0000 folder
                                candidates = [
                                    p / "user/nand/user/save/0000000000000000",
                                    p / "user/save/0000000000000000",
                                    p / "user/nand/user/save",
                                    p / "user/save",
                                    p,
                                ]
                                for cand in candidates:
                                    if cand.exists() and cand.is_dir():
                                        # If cand points to the 0000 folder, use it directly
                                        # If cand is higher-level like 'user/save', append '0000000000000000'
                                        if cand.name == "0000000000000000":
                                            base = cand
                                        else:
                                            possible = cand / "0000000000000000"
                                            if possible.exists() and possible.is_dir():
                                                base = possible
                                            else:
                                                # If cand already contains user-id folders, use it
                                                base = cand
                                        break
                                if base:
                                    break
        except Exception:
            base = None

        if base is None:
            base = citron_base / "user/nand/user/save/0000000000000000"

        # Cache the discovered base for use by callers
        try:
            self.cached_citron_base = base
        except Exception:
            self.cached_citron_base = None
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