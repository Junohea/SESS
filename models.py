from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

@dataclass
class SaveEntry:
    title_id: str
    game_name: str
    source: str  # 'ryujinx' or 'citron'
    folder_id: Optional[str]  # Used for Ryujinx folder mapping
    path: Path
    modified_time: datetime
    hash: str
    # Additional diagnostics used by the GUI for better sync decisions
    file_count: int = 0             # number of files in the save folder (exclude ExtraData0/1)
    max_file_size: int = 0          # size in bytes of the largest individual file in the folder
    # Per-slot diagnostics for Ryujinx (slot name -> {hash, modified_time, file_count, max_file_size})
    slots: Dict[str, Dict[str, Any]] = field(default_factory=dict)

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
