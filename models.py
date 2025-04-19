from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

@dataclass
class SaveEntry:
    title_id: str
    game_name: str
    source: str  # 'ryujinx' or 'citron'
    folder_id: Optional[str]  # Used for Ryujinx folder mapping
    path: Path
    modified_time: datetime
    hash: str

@dataclass
class GameInfo:
    title_id: str
    name: str
    publisher: Optional[str] = None
    region: Optional[str] = None
    serial: Optional[str] = None
    release_name: Optional[str] = None

@dataclass
class Config:
    ryujinx_base: Path
    citron_base: Path
    backup_dir: Path
    nswdb_xml_path: Path
    mapping_path: Path  # where folderID→titleID map is stored
    max_backups: int = 10
