import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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
        # Per-title user-selected action: 'none' | 'ryu_to_ci' | 'ci_to_ryu'
        self.user_actions = {}

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
        # Listen for scrollbar activity so action widgets can be repositioned
        self.vscroll = scroll
        try:
            self.vscroll.bind('<ButtonRelease-1>', lambda e: self._reposition_action_widgets())
            self.vscroll.bind('<B1-Motion>', lambda e: self._reposition_action_widgets())
        except Exception:
            pass

        # Bindings
        self.tree.bind('<Double-1>', self.sync_selected)
        self.tree.bind('<Button-3>', self.show_context_menu)
        # Clicking the Action column will show an inline dropdown
        # Use ButtonRelease so Treeview's internal handlers don't steal focus from the combobox
        self.tree.bind('<ButtonRelease-1>', self.on_tree_click, add='+')

        # Inline action picker values (we create a persistent Combobox per row)
        self._action_choices = ["No action", "Copy Ryujinx → Citron", "Copy Citron → Ryujinx"]
        # Map of TitleID -> Combobox widget (persistently shown for each visible row)
        self._action_widgets = {}
        # Reposition widgets on tree resize/scroll
        self.tree.bind('<Configure>', lambda e: self._reposition_action_widgets())
        self.tree.bind('<Expose>', lambda e: self._reposition_action_widgets())
        self.tree.bind('<Motion>', lambda e: self._reposition_action_widgets())
        self.tree.bind('<MouseWheel>', lambda e: self._reposition_action_widgets())


        # Buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="Sync All", command=self.sync_all).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_data).pack(side='left')
        ttk.Button(btn_frame, text="Exit", command=self.on_exit).pack(side='right')

    def browse_ryujinx(self):
        path = filedialog.askdirectory()
        if path:
            old = self.ryujinx_base.get()
            self.ryujinx_base.set(path)
            if path != old:
                self.redo_folder_mappings()
            self.refresh_data()

    def browse_citron(self):
        path = filedialog.askdirectory()
        if path:
            old = self.citron_base.get()
            self.citron_base.set(path)
            if path != old:
                self.redo_folder_mappings()
            self.refresh_data()

    def redo_folder_mappings(self):
        # Recreate the FolderMap and clear any cached mappings so
        # subsequent scans will re-register folders for the new bases.
        from pathlib import Path
        mapping_path = (self.config.mapping_path if self.config else Path("folder_mapping.json"))
        self.folder_map = FolderMap(mapping_path)
        self.folder_map.ryujinx = {}
        self.folder_map.cached_citron_user = None
        self.folder_map.cached_citron_base = None
        self.folder_map.save()
        self.citron_user_id = None

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

    def format_bytes(self, n: int) -> str:
        # Human-readable file size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if n < 1024.0:
                return f"{n:.1f}{unit}" if unit != 'B' else f"{n}B"
            n /= 1024.0
        return f"{n:.1f}TB"

    def _files_equal(self, a: 'Path', b: 'Path') -> bool:
        try:
            if a.stat().st_size != b.stat().st_size:
                return False
            # fast path: compare first/last bytes for very large files could be added, but use md5
            import hashlib
            ha = hashlib.md5()
            hb = hashlib.md5()
            with a.open('rb') as fa, b.open('rb') as fb:
                while True:
                    ca = fa.read(8192)
                    cb = fb.read(8192)
                    if not ca and not cb:
                        break
                    ha.update(ca)
                    hb.update(cb)
            return ha.digest() == hb.digest()
        except Exception:
            return False

    def _slot_contains_citron_files(self, slot_path: 'Path', citron_path: 'Path') -> bool:
        # Return True if every (non-ExtraData) file present in citron_path exists in slot_path
        try:
            for f in citron_path.rglob('*'):
                if not f.is_file():
                    continue
                if f.name in ("ExtraData0", "ExtraData1"):
                    continue
                rel = f.relative_to(citron_path)
                candidate = slot_path / rel
                if not candidate.exists() or not candidate.is_file():
                    return False
                if candidate.stat().st_size != f.stat().st_size:
                    return False
                if not self._files_equal(f, candidate):
                    return False
            return True
        except Exception:
            return False

    # --- Inline Action dropdown handlers ---
    def on_tree_click(self, event):
        # If the Action column was clicked, focus (and open) the per-row combobox for that row
        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        action_col = f"#{self.columns.index('Action') + 1}"
        if col != action_col or not row_id:
            return
        vals = self.tree.item(row_id, 'values') or []
        if len(vals) < 2:
            return
        tid = vals[1]
        cb = self._action_widgets.get(tid)
        if not cb:
            return
        try:
            cb.focus_set()
            cb.event_generate('<Down>')
        except Exception:
            pass


    def _create_action_widget_for_row(self, iid: str, tid: str):
        # Create a persistent Combobox widget for the given TitleID (if missing).
        if tid in self._action_widgets:
            return self._action_widgets[tid]
        cb = ttk.Combobox(self.root, values=self._action_choices, state='readonly', width=28)
        # Initialize selection from user_actions
        sel = self.user_actions.get(tid, 'none')
        if sel == 'none':
            cb.set('No action')
        elif sel == 'ryu_to_ci':
            cb.set('Copy Ryujinx → Citron')
        else:
            cb.set('Copy Citron → Ryujinx')
        # Bind selection to per-row handler
        cb.bind('<<ComboboxSelected>>', lambda e, t=tid, i=iid: self._on_action_widget_selected(t, i))
        self._action_widgets[tid] = cb
        return cb

    def _on_action_widget_selected(self, tid: str, iid: str):
        cb = self._action_widgets.get(tid)
        if not cb:
            return
        sel = cb.get()
        if sel == 'No action':
            action = 'none'
            display = ''
        elif sel == 'Copy Ryujinx → Citron':
            action = 'ryu_to_ci'
            display = '→'
        else:
            action = 'ci_to_ryu'
            display = '←'
        self.user_actions[tid] = action
        try:
            self.tree.set(iid, 'Action', display)
        except Exception:
            pass
        print(f"DEBUG: user_actions[{tid}] = {action}")

    def _destroy_action_widgets(self):
        for cb in list(self._action_widgets.values()):
            try:
                cb.destroy()
            except Exception:
                pass
        self._action_widgets.clear()

    def _reposition_action_widgets(self, _event=None):
        """Place each per-row combobox over its Action cell (hide if row not visible)."""
        action_col = f"#{self.columns.index('Action') + 1}"
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, 'values') or []
            if len(vals) < 2:
                continue
            tid = vals[1]
            cb = self._action_widgets.get(tid) or self._create_action_widget_for_row(iid, tid)
            bbox = self.tree.bbox(iid, action_col)
            if not bbox:
                try:
                    cb.place_forget()
                except Exception:
                    pass
                continue
            x, y, w, h = bbox
            try:
                tree_root_x = self.tree.winfo_rootx() - self.root.winfo_rootx()
                tree_root_y = self.tree.winfo_rooty() - self.root.winfo_rooty()
                place_x = tree_root_x + x
                place_y = tree_root_y + y
            except Exception:
                place_x, place_y = x, y
            try:
                cb.place(x=place_x, y=place_y, width=w, height=h)
                cb.lift()
            except Exception:
                pass

    def refresh_data(self):
        # Validate
        if not self.ryujinx_base.get() or not self.citron_base.get():
            return
        # Destroy and later recreate persistent per-row action widgets while we refresh
        self._destroy_action_widgets()
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

            # Determine status (preserve the existing "newer" indicators but augment
            # them with file-count and largest-file information). Treat a MATCH if
            # any Ryujinx slot contains the Citron files.
            st = ''
            if r and c:
                # Exact match against the canonical (primary) Ryujinx slot
                if r.hash == c.hash:
                    st = '✅ MATCH'
                else:
                    # Also consider individual Ryujinx slots — if any slot's hash equals Citron, count as MATCH
                    matched_slot = None
                    for sname, sinfo in getattr(r, 'slots', {}).items():
                        if sinfo.get('hash') == c.hash:
                            matched_slot = sname
                            break

                    # If no exact slot-hash match, check whether *any* slot contains all files from Citron
                    subset_slot = None
                    if not matched_slot:
                        try:
                            for sname, sinfo in getattr(r, 'slots', {}).items():
                                slot_path = sinfo.get('path')
                                if slot_path and self._slot_contains_citron_files(slot_path, c.path):
                                    subset_slot = sname
                                    break
                        except Exception:
                            subset_slot = None

                    if matched_slot or subset_slot:
                        slot_used = matched_slot or subset_slot
                        st = f"✅ MATCH (Ryujinx slot {slot_used})"
                    else:
                        # base newer indicator (informational only)
                        if r.modified_time > c.modified_time:
                            base = '🔺 Ryujinx newer'
                        elif c.modified_time > r.modified_time:
                            base = '🟢 Citron newer'
                        else:
                            base = '🔁 Unsynced'

                        # file-count comparison (Ryujinx uses aggregated slot counts)
                        fc_note = None
                        if getattr(r, 'file_count', 0) != getattr(c, 'file_count', 0):
                            fc_winner = 'Ryujinx' if r.file_count > c.file_count else 'Citron'
                            fc_note = f"more files: {fc_winner} ({max(r.file_count, c.file_count)} vs {min(r.file_count, c.file_count)})"

                        # largest-file comparison
                        lf_note = None
                        if getattr(r, 'max_file_size', 0) != getattr(c, 'max_file_size', 0):
                            lf_winner = 'Ryujinx' if r.max_file_size > c.max_file_size else 'Citron'
                            lf_note = f"largest file: {lf_winner} ({self.format_bytes(max(r.max_file_size, c.max_file_size))} vs {self.format_bytes(min(r.max_file_size, c.max_file_size))})"

                        notes = ' • '.join(n for n in (fc_note, lf_note) if n)
                        st = f"{base}{(' • ' + notes) if notes else ''}"
            elif r:
                st = '🟥 Only in Ryujinx'
            else:
                st = '🟥 Only in Citron' if self.folder_map.get_ryujinx_folder_id(tid) else '🚫 Run in Ryujinx'

            # Action: use user-selected action (default 'none' -> display empty)
            action = self.user_actions.get(tid, 'none')
            if action == 'ryu_to_ci':
                ac = '→'
            elif action == 'ci_to_ryu':
                ac = '←'
            else:
                ac = ''

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
            iid = self.tree.insert('', 'end', values=row, tags=tags)

        # Create / position persistent action comboboxes for visible rows
        self._reposition_action_widgets()

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
        # Use the user-selected action (default is 'none' — do nothing)
        selected_action = self.user_actions.get(title_id, 'none')
        if selected_action == 'ryu_to_ci':
            if not r:
                messagebox.showwarning("Cannot sync", "No Ryujinx save present to copy from.")
            else:
                print(f"DEBUG: syncing from Ryujinx to Citron for {title_id}")
                citron_base_used = getattr(self.folder_map, 'cached_citron_base', None)
                if citron_base_used is None:
                    citron_base_used = self.config.citron_base / 'user/nand/user/save/0000000000000000'
                dest = citron_base_used / self.citron_user_id / title_id
                self.engine.sync(r, SaveEntry(title_id, r.game_name, 'citron', self.citron_user_id, dest, r.modified_time, ''))
        elif selected_action == 'ci_to_ryu':
            if not c:
                messagebox.showwarning("Cannot sync", "No Citron save present to copy from.")
            else:
                fid = self.folder_map.get_ryujinx_folder_id(title_id)
                if not fid:
                    messagebox.showwarning("Cannot sync", "No Ryujinx folder mapping exists for this TitleID.")
                else:
                    print(f"DEBUG: syncing from Citron to Ryujinx for {title_id}")
                    existing_ryu = self.all_saves.get(title_id, {}).get('ryujinx')
                    if existing_ryu:
                        dest = existing_ryu.path
                    else:
                        dest = self.config.ryujinx_base / 'portable/bis/user/save' / fid / '0'
                    self.engine.sync(c, SaveEntry(title_id, c.game_name, 'ryujinx', fid, dest, c.modified_time, ''))
        else:
            messagebox.showinfo("No action selected", "Choose an action from the Action column before syncing.")

        # Refresh once after performing the selected sync
        self.refresh_data()

    def sync_all(self):
        # Only perform syncs for titles where the user has explicitly selected an action.
        performed = 0
        for tid, sources in self.all_saves.items():
            action = self.user_actions.get(tid, 'none')
            r = sources.get('ryujinx')
            c = sources.get('citron')
            if action == 'ryu_to_ci':
                if not r:
                    continue
                citron_base_used = getattr(self.folder_map, 'cached_citron_base', None)
                if citron_base_used is None:
                    citron_base_used = self.config.citron_base / 'user/nand/user/save/0000000000000000'
                dest = citron_base_used / self.citron_user_id / tid
                self.engine.sync(r, SaveEntry(tid, r.game_name, 'citron', self.citron_user_id, dest, r.modified_time, ''))
                performed += 1
            elif action == 'ci_to_ryu':
                if not c:
                    continue
                fid = self.folder_map.get_ryujinx_folder_id(tid)
                if not fid:
                    continue
                existing_ryu = self.all_saves.get(tid, {}).get('ryujinx')
                if existing_ryu:
                    dest = existing_ryu.path
                else:
                    # Detect preferred slot under the Ryujinx folder (prefer non-empty slots)
                    ryu_folder = self.config.ryujinx_base / 'portable/bis/user/save' / fid
                    chosen_slot = None
                    try:
                        candidates = [p for p in ryu_folder.iterdir() if p.is_dir() and p.name.isdigit()]
                        non_empty = [s for s in candidates if any(f.is_file() for f in s.rglob('*'))]
                        if non_empty:
                            chosen_slot = max(non_empty, key=lambda s: max((f.stat().st_mtime for f in s.rglob('*') if f.is_file()), default=0.0))
                        elif candidates:
                            candidates.sort(key=lambda p: int(p.name) if p.name.isdigit() else 0)
                            chosen_slot = candidates[0]
                    except Exception:
                        chosen_slot = None
                    if chosen_slot:
                        dest = chosen_slot
                    else:
                        dest = ryu_folder / '0'
                self.engine.sync(c, SaveEntry(tid, c.game_name, 'ryujinx', fid, dest, c.modified_time, ''))
                performed += 1
        if performed == 0:
            messagebox.showinfo("No actions", "No sync actions selected. Use the Action dropdown to choose which save to keep.")
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
        p = str(path)
        if platform.system() == "Windows":
            os.startfile(p)
        elif platform.system() == "Darwin":
            subprocess.call(["open", p])
        else:
            subprocess.call(["xdg-open", p])

    def on_exit(self):
        self.save_last_config()
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = SaveSyncApp(root)
    root.mainloop()
