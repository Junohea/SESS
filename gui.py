import tkinter as tk
from tkinter import ttk, filedialog
from models import Config, SaveEntry
from nswdb_parser import NSWDBParser
from save_scanner import SaveScanner
from syncengine import SyncEngine
from foldermap import FolderMap

from pathlib import Path
from collections import defaultdict
from datetime import datetime
import json
import os
import platform
import subprocess

CONFIG_FILE = Path(".gui_config.json")

class SaveSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Switch Save Sync Tool")

        # Variables
        self.ryujinx_base = tk.StringVar()
        self.citron_base = tk.StringVar()
        self.sort_column = "Title"
        self.sort_reverse = False
        self.show_only_unsynced = tk.BooleanVar(value=False)

        # Internal state
        self.config = None
        self.nswdb = None
        self.folder_map = None
        self.scanner = None
        self.engine = None
        self.all_saves = defaultdict(dict)
        self.citron_user_id = None

        # Set GUI prompt handler
        import foldermap
        foldermap.prompt_for_choice_gui = self.prompt_for_folder_choice

        # Build UI
        self.load_last_config()
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.refresh_data()

    def load_last_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                self.ryujinx_base.set(data.get("ryujinx_base", ""))
                self.citron_base.set(data.get("citron_base", ""))
                geo = data.get("geometry")
                if geo:
                    self.root.geometry(geo)
                self.sort_column = data.get("sort_column", self.sort_column)
                self.sort_reverse = data.get("sort_reverse", self.sort_reverse)
                self.show_only_unsynced.set(data.get("show_only_unsynced", False))
            except:
                pass

    def save_last_config(self):
        data = {
            "ryujinx_base": self.ryujinx_base.get(),
            "citron_base": self.citron_base.get(),
            "geometry": self.root.geometry(),
            "sort_column": self.sort_column,
            "sort_reverse": self.sort_reverse,
            "show_only_unsynced": self.show_only_unsynced.get()
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)

    def setup_ui(self):
        # Path frame
        path_frame = ttk.Frame(self.root)
        path_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(path_frame, text="Ryujinx:").grid(row=0, column=0, sticky='e')
        ttk.Entry(path_frame, textvariable=self.ryujinx_base, width=50).grid(row=0, column=1)
        ttk.Button(path_frame, text="Browse", command=self.browse_ryujinx).grid(row=0, column=2)
        ttk.Label(path_frame, text="Citron:").grid(row=1, column=0, sticky='e')
        ttk.Entry(path_frame, textvariable=self.citron_base, width=50).grid(row=1, column=1)
        ttk.Button(path_frame, text="Browse", command=self.browse_citron).grid(row=1, column=2)

        # Instruction
        note = ttk.Label(self.root, text="Double-click an entry to sync. Backups go to BackupHistory.", foreground='blue')
        note.pack(pady=(0,5))

        # Filter
        chk = ttk.Checkbutton(self.root, text="Show only unsynced entries", variable=self.show_only_unsynced, command=self.refresh_data)
        chk.pack()

        # Treeview
        self.columns = ("Title","TitleID","Status","Ryujinx Date","Citron Date","Action")
        self.tree = ttk.Treeview(self.root, columns=self.columns, show='headings')
        for col in self.columns:
            self.tree.heading(col, text=col, command=lambda c=col: self.on_sort_by(c))
            self.tree.column(col, width=140 if col!='Title' else 250, anchor='w')
        self.tree.pack(fill='both', expand=True, padx=10, pady=5)

        # Scrollbar
        scroll = ttk.Scrollbar(self.root, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')

        # Bindings
        self.tree.bind('<Double-1>', self.sync_selected)
        self.tree.bind('<Button-3>', self.show_context_menu)

        # Buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="Sync All", command=self.sync_all).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_data).pack(side='left')
        ttk.Button(btn_frame, text="Exit", command=self.on_exit).pack(side='right')

    def browse_ryujinx(self):
        path = filedialog.askdirectory()
        if path:
            self.ryujinx_base.set(path)
            self.refresh_data()

    def browse_citron(self):
        path = filedialog.askdirectory()
        if path:
            self.citron_base.set(path)
            self.refresh_data()

    def on_sort_by(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        self.refresh_data()

    def format_time(self, t):
        if isinstance(t, datetime):
            return t.strftime("%Y-%m-%d %H:%M")
        if isinstance(t, (int, float)):
            return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")
        return '-'

    def refresh_data(self):
        # Validate
        if not self.ryujinx_base.get() or not self.citron_base.get():
            return
        # Clear
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        # Init
        self.config = Config(
            ryujinx_base=Path(self.ryujinx_base.get()),
            citron_base=Path(self.citron_base.get()),
            backup_dir=Path("./backupHistory"),
            nswdb_xml_path=Path("US.en.json"),
            mapping_path=Path("folder_mapping.json")
        )
        self.nswdb = NSWDBParser(self.config.nswdb_xml_path)
        self.nswdb.load()
        if not self.folder_map:
            self.folder_map = FolderMap(self.config.mapping_path)
        if self.citron_user_id is None:
            self.citron_user_id = self.folder_map.resolve_citron_user(
                self.config.citron_base,
                set(self.nswdb.game_lookup.keys())
            )
            if not self.citron_user_id:
                return
        self.scanner = SaveScanner(self.config, self.nswdb)
        self.scanner.folder_map = self.folder_map
        self.engine = SyncEngine(self.config)

        # Collect saves
        ry = self.scanner.scan_ryujinx()
        ci = self.scanner.scan_citron()
        self.all_saves.clear()
        for e in ry:
            self.all_saves[e.title_id]['ryujinx'] = e
        for e in ci:
            self.all_saves[e.title_id]['citron'] = e

        # Build rows
        rows = []
        for tid, sources in self.all_saves.items():
            name = sources.get('ryujinx', sources.get('citron')).game_name
            r = sources.get('ryujinx')
            c = sources.get('citron')
            rd = self.format_time(r.modified_time) if r else '-'
            cd = self.format_time(c.modified_time) if c else '-'
            if r and c:
                if r.hash == c.hash:
                    st, ac = '✅ MATCH', ''
                elif r.modified_time > c.modified_time:
                    st, ac = '🔺 Ryujinx newer', '→'
                else:
                    st, ac = '🟢 Citron newer', '←'
            elif r:
                st, ac = '🟥 Only in Ryujinx', '→'
            else:
                st = '🟥 Only in Citron' if self.folder_map.get_title_id(tid) else '🚫 Run in Ryujinx'
                ac = '←' if c else ''
            rows.append((name, tid, st, rd, cd, ac))

        # Sort & filter
        idxs = list(self.columns)
        rows.sort(key=lambda x: x[idxs.index(self.sort_column)], reverse=self.sort_reverse)
        if self.show_only_unsynced.get():
            rows = [r for r in rows if r[2] != '✅ MATCH']

        # Tag configuration
        self.tree.tag_configure('match', background='#e0ffe0')
        self.tree.tag_configure('ryujinx_newer', background='#fff4e0')
        self.tree.tag_configure('citron_newer', background='#e0f7ff')
        self.tree.tag_configure('only_ryujinx', background='#ffdede')
        self.tree.tag_configure('only_citron', background='#dedefd')
        self.tree.tag_configure('needs_init', background='#f0f0f0')
        
        # Insert rows
        for row in rows:
            tags = []
            st = row[2]
            if st == '✅ MATCH':
                tags.append('match')
            elif 'Ryujinx newer' in st:
                tags.append('ryujinx_newer')
            elif 'Citron newer' in st:
                tags.append('citron_newer')
            elif 'Only in Ryujinx' in st:
                tags.append('only_ryujinx')
            elif 'Only in Citron' in st:
                tags.append('only_citron')
            elif 'Run in' in st:
                tags.append('needs_init')
            if row[5]:
                tags.append('syncable')
            self.tree.insert('', 'end', values=row, tags=tags)

    def sync_selected(self, event):
        # Debug: confirm method entry
        print("DEBUG: sync_selected called")
        row_id = self.tree.identify_row(event.y)
        print(f"DEBUG: identified row: {row_id}")
        if not row_id:
            return
        self.tree.selection_set(row_id)
        vals = self.tree.item(row_id, 'values')
        print(f"DEBUG: row values: {vals}")
        title_id = vals[1]
        r = self.all_saves[title_id].get('ryujinx')
        c = self.all_saves[title_id].get('citron')
        action = vals[5]
        print(f"DEBUG: action: {action}, r: {bool(r)}, c: {bool(c)}")
        if action == '→' and r:
            print(f"DEBUG: syncing from Ryujinx to Citron for {title_id}")
            dest = self.config.citron_base / 'user/nand/user/save/0000000000000000' / self.citron_user_id / title_id
            self.engine.sync(r, SaveEntry(title_id, r.game_name, 'citron', self.citron_user_id, dest, r.modified_time, ''))
        elif action == '←' and c:
            print(f"DEBUG: syncing from Citron to Ryujinx for {title_id}")
            fid = self.folder_map.get_folder_id(title_id)
            if fid:
                dest = self.config.ryujinx_base / 'portable/bis/user/save' / fid / '0'
                self.engine.sync(c, SaveEntry(title_id, c.game_name, 'ryujinx', fid, dest, c.modified_time, ''))
        # Refresh
        self.refresh_data()
        # Determine row under cursor
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        vals = self.tree.item(row_id, 'values')
        title_id = vals[1]
        r = self.all_saves[title_id].get('ryujinx')
        c = self.all_saves[title_id].get('citron')
        action = vals[5]
        if action == '→' and r:
            dest = self.config.citron_base / 'user/nand/user/save/0000000000000000' / self.citron_user_id / title_id
            self.engine.sync(r, SaveEntry(title_id, r.game_name, 'citron', self.citron_user_id, dest, r.modified_time, ''))
        elif action == '←' and c:
            fid = self.folder_map.get_folder_id(title_id)
            if fid:
                dest = self.config.ryujinx_base / 'portable/bis/user/save' / fid / '0'
                self.engine.sync(c, SaveEntry(title_id, c.game_name, 'ryujinx', fid, dest, c.modified_time, ''))
        # Refresh
        self.refresh_data()

    def sync_all(self):
        for tid, sources in self.all_saves.items():
            r = sources.get('ryujinx')
            c = sources.get('citron')
            if r and c and r.hash != c.hash:
                if r.modified_time > c.modified_time:
                    self.engine.sync(r, c)
                else:
                    self.engine.sync(c, r)
            elif r:
                dest = self.config.citron_base / 'user/nand/user/save/0000000000000000' / self.citron_user_id / tid
                self.engine.sync(r, SaveEntry(tid, r.game_name, 'citron', self.citron_user_id, dest, r.modified_time, ''))
            elif c:
                fid = self.folder_map.get_folder_id(title_id)
                if fid:
                    dest = self.config.ryujinx_base / 'portable/bis/user/save' / fid / '0'
                    self.engine.sync(c, SaveEntry(tid, c.game_name, 'ryujinx', fid, dest, c.modified_time, ''))
        self.refresh_data()

    def prompt_for_folder_choice(self, options):
        if not options:
            return None
        if len(options) == 1:
            return options[0]
        dlg = tk.Toplevel(self.root)
        dlg.title("Select Save Folder")
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text="Multiple save folders found. Select one:").pack(pady=10)
        var = tk.StringVar(value=options[0])
        for opt in options:
            ttk.Radiobutton(dlg, text=opt, variable=var, value=opt).pack(anchor='w', padx=20)
        ttk.Button(dlg, text="OK", command=dlg.destroy).pack(pady=10)
        self.root.wait_window(dlg)
        return var.get()

    def show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        vals = self.tree.item(iid, 'values')
        tid = vals[1]
        r = self.all_saves[tid].get('ryujinx')
        c = self.all_saves[tid].get('citron')
        menu = tk.Menu(self.root, tearoff=0)
        if r:
            menu.add_command(label="Open Ryujinx Save Folder", command=lambda: self.open_path(r.path))
        if c:
            menu.add_command(label="Open Citron Save Folder", command=lambda: self.open_path(c.path))
        menu.add_command(label="Open Backup Folder", command=lambda: self.open_path(self.config.backup_dir))
        menu.post(event.x_root, event.y_root)

    def open_path(self, path):
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])

    def on_exit(self):
        self.save_last_config()
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = SaveSyncApp(root)
    root.mainloop()
