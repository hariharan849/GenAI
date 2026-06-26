"""
ID Card Generator — main application.

Workflow:
  1. Load Excel → "Map Columns" dialog appears to bind Excel headers to card roles
  2. Load Template image (PNG/JPG — labels already printed in image)
  3. Load Config (JSON)
  4. "Configure Fields" → click on the template canvas to place each value;
     excel_column is a dropdown of actual Excel headers
  5. Double-click a student → Photo Editor (pan / zoom / rotate)
  6. "Generate All" → per-student JPGs + optional A4 print sheet
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

from card_generator import CardGenerator, FIELD_COLORS, detect_photo_region
from photo_editor import PhotoEditorDialog
from face_extract_editor import FaceExtractEditorDialog


# ──────────────────────────────────────────── font discovery ─────────────────

def _discover_fonts() -> list[str]:
    """Return sorted font base-names from C:/Windows/Fonts that work with _get_font."""
    fonts_dir = Path("C:/Windows/Fonts")
    _FALLBACK_FONTS = sorted([
        "arial", "calibri", "verdana", "tahoma", "georgia",
        "times", "impact", "trebuc", "comic", "cour",
    ])
    if not fonts_dir.exists():
        return _FALLBACK_FONTS

    _VARIANT_SUFFIXES = frozenset([
        "bd", "b", "bi", "i", "z", "it",
        "bold", "italic", "bolditalic", "semibold",
        "light", "medium", "black", "thin", "extrabold",
        "condensed", "narrow", "regular",
    ])

    stems = {p.stem.lower() for p in fonts_dir.glob("*.ttf")}
    stems |= {p.stem.lower() for p in fonts_dir.glob("*.otf")}

    base_names: set[str] = set()
    for stem in stems:
        # Hyphen-separated variant (e.g. "fontname-bold")
        if "-" in stem:
            base, _, suffix = stem.rpartition("-")
            if suffix in _VARIANT_SUFFIXES and base in stems:
                continue
        # Short trailing suffix (e.g. "arialbd" → base "arial" exists)
        is_variant = False
        for suf in sorted(_VARIANT_SUFFIXES, key=len, reverse=True):
            if len(stem) > len(suf) + 2 and stem.endswith(suf):
                if stem[: -len(suf)] in stems:
                    is_variant = True
                    break
        if not is_variant:
            base_names.add(stem)

    return sorted(base_names) or _FALLBACK_FONTS


# ─────────────────────────────── fallback keyword lists (auto-detect only) ───
# Used ONLY when no column_map entry exists for a role.
_FALLBACK: dict[str, list[str]] = {
    "name":    ["name", "student name", "student_name"],
    "class":   ["class", "class & sec", "section", "class_sec"],
    "admn":    ["admn", "admission", "admn no", "admission no", "admn_no"],
    "photo":   ["photo", "photo path", "image", "photo_path"],
    "dob":     ["dob", "date of birth", "d.o.b", "birth"],
    "blood":   ["blood", "blood group", "bg"],
    "father":  ["father", "father name", "parent"],
    "address": ["address", "addr"],
    "contact": ["contact", "phone", "mobile", "mob"],
}

# Roles shown in the Column Map dialog (role_key, friendly label)
_ROLES = [
    ("name",    "Student Name"),
    ("class",   "Class / Section"),
    ("admn",    "Admission Number"),
    ("photo",   "Photo File Path"),
    ("dob",     "Date of Birth"),
    ("blood",   "Blood Group"),
    ("father",  "Father Name"),
    ("address", "Address"),
    ("contact", "Contact Number"),
]


# ────────────────────────────────────────── column resolution helpers ─────────

def _fallback_col(df, role: str) -> str | None:
    """Fuzzy-match role against actual Excel column names as a last resort."""
    cols_lower = {c.lower().strip(): c for c in df.columns}
    if role.lower() in cols_lower:
        return cols_lower[role.lower()]
    for keyword in _FALLBACK.get(role, []):
        if keyword in cols_lower:
            return cols_lower[keyword]
    return None


# ─────────────────────────────────────────────────── UI micro-helpers ─────────

def _sep(parent):
    ttk.Separator(parent, orient=tk.VERTICAL).pack(
        side=tk.LEFT, fill=tk.Y, padx=4, pady=4)


def _tbtn(parent, text, cmd, bg="#1976D2"):
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg="white", relief=tk.FLAT,
                  padx=9, pady=5, font=("Arial", 9))
    b.pack(side=tk.LEFT, padx=3, pady=4)
    return b


def _lbtn(parent, text, cmd, bg="#546E7A"):
    tk.Button(parent, text=text, command=cmd,
              bg=bg, fg="white", relief=tk.FLAT,
              padx=7, pady=3).pack(side=tk.LEFT, padx=2)


def _entry_row(frame, label: str, value, row: int) -> tk.StringVar:
    tk.Label(frame, text=f"{label}:", width=9, anchor="e").grid(
        row=row, column=0, padx=5, pady=2, sticky="e")
    var = tk.StringVar(value=str(value))
    tk.Entry(frame, textvariable=var, width=9).grid(
        row=row, column=1, sticky="w", padx=4, pady=2)
    return var


# ──────────────────────────────────────────────── Column Map Dialog ───────────

class ColumnMapDialog(tk.Toplevel):
    """
    Shown after loading Excel.
    User assigns each card role (Name, Class, Admn …) to an actual Excel column.
    Result is saved into config["column_map"] and config["photo_column"].
    """

    def __init__(self, parent, gen: CardGenerator, excel_columns: list[str]):
        super().__init__(parent)
        self.title("Map Excel Columns → Card Fields")
        self.resizable(False, False)
        self._gen = gen
        self._columns = excel_columns
        self._vars: dict[str, tk.StringVar] = {}
        self._build_ui()
        self.transient(parent)
        self.grab_set()
        self.wait_window()

    def _build_ui(self):
        self.geometry("480x440")

        tk.Label(self,
                 text="Which Excel column holds each piece of information?",
                 font=("Arial", 10, "bold")).pack(pady=(14, 2), padx=14, anchor="w")
        tk.Label(self,
                 text="The app reads actual column headers — select from the dropdown.",
                 font=("Arial", 8), fg="#555").pack(padx=14, anchor="w")

        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

        current_map = {k: v for k, v in
                       self._gen.config.get("column_map", {}).items()
                       if not k.startswith("_")}
        choices = ["(skip)"] + self._columns

        _cols_ci = {c.lower().strip(): c for c in self._columns}

        for ri, (role, display) in enumerate(_ROLES):
            tk.Label(frame, text=f"{display}:", width=20, anchor="e",
                     font=("Arial", 9)).grid(row=ri, column=0, padx=6, pady=5, sticky="e")

            # Priority: existing map (case-insensitive) → auto-guess → "(skip)"
            existing = current_map.get(role, "")
            if existing and existing.lower().strip() in _cols_ci:
                default = _cols_ci[existing.lower().strip()]
            else:
                default = self._auto_guess(role) or "(skip)"
            var = tk.StringVar(value=default)
            self._vars[role] = var

            cb = ttk.Combobox(frame, textvariable=var, values=choices,
                               state="readonly", width=26)
            cb.grid(row=ri, column=1, padx=6, pady=5, sticky="w")

        bf = tk.Frame(self)
        bf.pack(pady=12)
        tk.Button(bf, text="Save Mapping", command=self._save,
                  bg="#388E3C", fg="white", relief=tk.FLAT, padx=14, pady=5
                  ).pack(side=tk.LEFT, padx=8)
        tk.Button(bf, text="Skip", command=self.destroy,
                  relief=tk.FLAT, padx=14, pady=5).pack(side=tk.LEFT)

    def _auto_guess(self, role: str) -> str | None:
        cols_lower = {c.lower().strip(): c for c in self._columns}
        # Direct role name match first (e.g. role "address" → column "Address")
        if role.lower() in cols_lower:
            return cols_lower[role.lower()]
        for keyword in _FALLBACK.get(role, []):
            if keyword in cols_lower:
                return cols_lower[keyword]
        return None

    def _save(self):
        mapping: dict[str, str] = {}
        for role, var in self._vars.items():
            val = var.get()
            if val and val != "(skip)":
                mapping[role] = val

        self._gen.config["column_map"] = mapping
        # Keep photo_column in sync (used by card_generator for photo loading)
        if "photo" in mapping:
            self._gen.config["photo_column"] = mapping["photo"]
        self.destroy()


# ──────────────────────────────────────────────────── main window ────────────

class IDCardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ID Card Generator")
        self.root.geometry("1280x830")
        self.root.minsize(900, 620)

        self._gen = CardGenerator()
        self._config_path: str | None = None
        self._output_dir:  str | None = None
        self._preview_idx: int | None = None

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

    # ── column resolution ─────────────────────────────────────────────────────

    def _col(self, role: str) -> str | None:
        """
        Resolve a card role to the actual Excel column name.
        Priority: config column_map (case-insensitive key) → fuzzy fallback.
        """
        mapping = {k: v for k, v in
                   self._gen.config.get("column_map", {}).items()
                   if not k.startswith("_")}
        # Exact key first, then case-insensitive key match
        if role in mapping:
            return mapping[role]
        mapping_ci = {k.lower(): v for k, v in mapping.items()}
        if role.lower() in mapping_ci:
            return mapping_ci[role.lower()]
        # Fallback: keyword match against real df columns
        if self._gen.df is not None:
            return _fallback_col(self._gen.df, role)
        return None

    # ── menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)

        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="File", menu=fm)
        fm.add_command(label="Load Excel…",           command=self._load_excel)
        fm.add_command(label="Map Columns…",          command=self._map_columns)
        fm.add_command(label="Load Template Image…",  command=self._load_template)
        fm.add_separator()
        fm.add_command(label="Load Config…",          command=self._load_config)
        fm.add_command(label="Save Config",           command=self._save_config)
        fm.add_command(label="Save Config As…",       command=self._save_config_as)
        fm.add_separator()
        fm.add_command(label="Set Output Folder…",    command=self._pick_output_dir)
        fm.add_separator()
        fm.add_command(label="Exit",                  command=self.root.quit)

        gm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Generate", menu=gm)
        gm.add_command(label="Preview Selected",      command=self._preview_selected)
        gm.add_command(label="Generate Selected",     command=self._generate_selected)
        gm.add_command(label="Generate All Cards",    command=self._generate_all)
        gm.add_separator()
        gm.add_command(label="Create Print Sheet…",   command=self._create_print_sheet)

        tm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Tools", menu=tm)
        tm.add_command(label="Extract Faces from Folder…",       command=self._extract_faces_folder)
        tm.add_command(label="Set Photo Transform for All…",     command=self._set_photo_transform_all)

    # ── toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg="#ECEFF1", bd=1, relief=tk.GROOVE)
        bar.pack(fill=tk.X)

        _tbtn(bar, "Load Excel",       self._load_excel)
        _tbtn(bar, "Map Columns",      self._map_columns,        "#00838F")
        _tbtn(bar, "Load Template",    self._load_template)
        _tbtn(bar, "Load Config",      self._load_config)
        _tbtn(bar, "Save Config",      self._save_config,        "#546E7A")
        _sep(bar)
        _tbtn(bar, "Configure Fields",   self._open_field_config,    "#7B1FA2")
        _tbtn(bar, "Mapping Template",  self._load_mapping_template, "#5D4037")
        _sep(bar)
        _tbtn(bar, "Generate All",     self._generate_all,          "#388E3C")
        _tbtn(bar, "Print Sheet",      self._create_print_sheet, "#E65100")
        _sep(bar)
        _tbtn(bar, "Extract Faces",    self._extract_faces_folder, "#6A1B9A")
        _tbtn(bar, "Photo Transform…", self._set_photo_transform_all, "#00695C")

        self._status_var = tk.StringVar(
            value="Ready — load an Excel file and template image to begin.")
        tk.Label(bar, textvariable=self._status_var,
                 bg="#ECEFF1", fg="#37474F", font=("Arial", 8)
                 ).pack(side=tk.RIGHT, padx=10)

    # ── body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # Left: student list
        left = tk.Frame(paned, width=390)
        paned.add(left, weight=1)

        hdr = tk.Frame(left)
        hdr.pack(fill=tk.X, pady=(0, 4))
        tk.Label(hdr, text="Students", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self._count_lbl = tk.Label(hdr, text="(0 loaded)", fg="#777")
        self._count_lbl.pack(side=tk.LEFT, padx=6)

        sf = tk.Frame(left)
        sf.pack(fill=tk.X, pady=(0, 4))
        tk.Label(sf, text="Search:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_tree())
        tk.Entry(sf, textvariable=self._search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        tw = tk.Frame(left)
        tw.pack(fill=tk.BOTH, expand=True)
        self._tree = ttk.Treeview(
            tw, columns=("name", "class", "admn", "photo"),
            show="headings", selectmode="browse")
        for col, w, lbl in [("name", 160, "Name"), ("class", 65, "Class"),
                             ("admn", 75, "Admn No"), ("photo", 70, "Photo")]:
            self._tree.heading(col, text=lbl)
            self._tree.column(col, width=w, stretch=(col == "name"))
        vsb = ttk.Scrollbar(tw, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-Button-1>",  self._on_dbl)

        act = tk.Frame(left)
        act.pack(fill=tk.X, pady=5)
        _lbtn(act, "Edit Photo",    self._edit_photo,           "#1976D2")
        _lbtn(act, "Preview Card",  self._preview_selected,     "#546E7A")
        _lbtn(act, "Generate Card", self._generate_selected,    "#388E3C")

        act2 = tk.Frame(left)
        act2.pack(fill=tk.X, pady=(0, 4))
        _lbtn(act2, "Apply Transform to All", self._apply_transform_to_all, "#6A1B9A")

        # Right: preview
        right = tk.Frame(paned)
        paned.add(right, weight=3)
        tk.Label(right, text="Card Preview",
                 font=("Arial", 10, "bold")).pack(pady=(0, 4))
        self._canvas = tk.Canvas(right, bg="#424242")
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self._canvas.bind("<Configure>", lambda _: self._redraw_preview())
        self._canvas_img = None

    # ── status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        self._progress_var = tk.DoubleVar()
        ttk.Progressbar(sb, variable=self._progress_var, maximum=100
                        ).pack(fill=tk.X, padx=4, pady=2)

    def _set_status(self, msg: str):
        self._status_var.set(msg)
        self.root.update_idletasks()

    # ── Excel + column map ───────────────────────────────────────────────────

    def _load_excel(self):
        path = filedialog.askopenfilename(
            title="Open Excel File",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")])
        if not path:
            return
        try:
            self._gen.load_excel(path)
        except Exception as exc:
            messagebox.showerror("Excel Error", str(exc))
            return

        n = len(self._gen.df)
        cols = list(self._gen.df.columns)
        self._set_status(f"Loaded {n} students, {len(cols)} columns — {Path(path).name}")

        # Show column mapping dialog automatically
        ColumnMapDialog(self.root, self._gen, cols)

        self._refresh_tree()
        self._set_status(
            f"Loaded {n} students — {Path(path).name}  "
            f"| columns mapped: {len(self._gen.config.get('column_map', {}))}")

    def _map_columns(self):
        """Re-open the column map dialog (e.g. after loading a different Excel)."""
        if self._gen.df is None:
            messagebox.showinfo("No Excel", "Load an Excel file first.")
            return
        cols = list(self._gen.df.columns)
        ColumnMapDialog(self.root, self._gen, cols)
        self._refresh_tree()

    def _refresh_tree(self):
        df = self._gen.df
        if df is None:
            return
        self._tree.delete(*self._tree.get_children())

        nc = self._col("name")
        cc = self._col("class")
        ac = self._col("admn")
        pc = self._col("photo")

        q = self._search_var.get().lower()
        count = 0
        for i, (_, row) in enumerate(df.iterrows()):
            name = str(row.get(nc, "")).strip() if nc else ""
            cls  = str(row.get(cc, "")).strip() if cc else ""
            admn = str(row.get(ac, "")).strip() if ac else ""
            photo_path = str(row.get(pc, "")).strip() if pc else ""
            if q and q not in name.lower() and q not in admn.lower():
                continue
            edited = "★" if i in self._gen.photo_transforms else (
                "✓" if photo_path and os.path.exists(photo_path) else "✗")
            self._tree.insert("", tk.END, iid=str(i),
                              values=(name, cls, admn, edited))
            count += 1

        self._count_lbl.config(text=f"({count} shown)")

    # ── template ──────────────────────────────────────────────────────────────

    def _load_template(self):
        path = filedialog.askopenfilename(
            title="Open Template Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All", "*.*")])
        if not path:
            return
        try:
            self._gen.load_template(path)
            w = self._gen.template_image.width
            h = self._gen.template_image.height
            hints: list[str] = []

            # Auto-detect photo region (CV2) if not already in config
            if not self._gen.config.get("photo_region"):
                region = detect_photo_region(self._gen.template_image)
                if region:
                    self._gen.config["photo_region"] = region
                    hints.append(f"photo region ({region['shape']}) auto-detected")

            # Auto-detect text field positions via OCR if not already configured
            if not self._gen.config.get("fields"):
                detected = []

                # Pass 1 — suffix-based (NAME1 / class1 / dob1 … style mapping template)
                try:
                    detected, mapping_region = \
                        self._gen.auto_detect_from_mapping_template(path)
                    # Also grab the photo region if detection found one and config lacks it
                    if mapping_region and not self._gen.config.get("photo_region"):
                        self._gen.config["photo_region"] = mapping_region
                except Exception:
                    pass

                # Pass 2 — label-based fallback (blank templates with "Class & Sec :" etc.)
                if not detected:
                    try:
                        excel_cols = (self._gen.df.columns.tolist()
                                      if self._gen.df is not None else None)
                        detected = self._gen.auto_detect_fields(excel_columns=excel_cols)
                    except Exception:
                        pass  # Tesseract not available — user must configure manually

                if detected:
                    self._gen.config["fields"] = detected
                    hints.append(f"{len(detected)} text fields auto-detected")

            suffix = ("  — " + ", ".join(hints)) if hints else ""
            self._set_status(f"Template: {Path(path).name}  ({w}×{h} px){suffix}")
            self._redraw_preview()
        except Exception as exc:
            messagebox.showerror("Template Error", str(exc))

    def _load_mapping_template(self):
        """
        Load a mapping template (same layout as the blank template but with
        placeholder text like 'name1', 'class1', 'dob1' …) and auto-detect:
          • photo circle region via CV2 contour analysis
          • text field positions via Tesseract OCR
        """
        if self._gen.template_image is None:
            messagebox.showinfo("Load Template First",
                "Load the blank template image first, then load the mapping template.")
            return
        path = filedialog.askopenfilename(
            title="Open Mapping Template (template with placeholder text)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All", "*.*")])
        if not path:
            return

        fields: list[dict] = []
        photo_region: dict | None = None

        try:
            fields, photo_region = self._gen.auto_detect_from_mapping_template(path)
        except RuntimeError as exc:
            # Tesseract unavailable — still attempt CV2 circle detection alone
            try:
                photo_region = detect_photo_region(Image.open(path))
            except Exception:
                pass
            if photo_region is None:
                messagebox.showerror("Detection Error", str(exc))
                return
            messagebox.showwarning(
                "OCR Unavailable",
                f"Install pytesseract + Tesseract for text-field detection.\n\n"
                f"Photo region ({photo_region['shape']}) detected at "
                f"({photo_region['x']}, {photo_region['y']})  "
                f"{photo_region['width']}×{photo_region['height']} px")
        except Exception as exc:
            messagebox.showerror("Detection Error", str(exc))
            return

        if not fields and photo_region is None:
            messagebox.showinfo("Nothing Detected",
                "No placeholder text or circle found.\n"
                "Make sure the mapping template has text like 'name1', 'class1' …")
            return

        # Build a human-readable summary for the confirmation dialog
        lines: list[str] = ["Detected the following layout:"]
        if photo_region:
            lines.append(
                f"\nPhoto region ({photo_region['shape']}) — "
                f"({photo_region['x']}, {photo_region['y']})  "
                f"{photo_region['width']}×{photo_region['height']} px")
        if fields:
            lines.append(f"\n{len(fields)} text field(s):")
            for f in fields:
                lines.append(
                    f"  • {f['excel_column']}  @  ({f['x']}, {f['y']})"
                    f"  size {f['size']}  align={f['align']}")
        lines.append("\nApply these positions to the config?")

        if not messagebox.askyesno("Apply Detected Layout?", "\n".join(lines)):
            return

        if photo_region:
            self._gen.config["photo_region"] = photo_region
        if fields:
            self._gen.config["fields"] = fields

        self._set_status(
            f"Auto-detected: {len(fields)} field(s)"
            + (f" + photo region ({photo_region['shape']})" if photo_region else "")
            + f" from {Path(path).name}")
        self._redraw_preview()

    # ── config ────────────────────────────────────────────────────────────────

    def _load_config(self):
        path = filedialog.askopenfilename(
            title="Open Config",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            self._gen.load_config(path)
            self._config_path = path
            self._set_status(f"Config: {Path(path).name}")
            self._redraw_preview()
        except Exception as exc:
            messagebox.showerror("Config Error", str(exc))

    def _save_config(self):
        if not self._config_path:
            self._save_config_as()
            return
        try:
            self._gen.save_config(self._config_path)
            self._set_status(f"Saved: {Path(self._config_path).name}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))

    def _save_config_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Config As", defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if path:
            self._config_path = path
            self._save_config()

    def _pick_output_dir(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self._output_dir = d
            self._set_status(f"Output: {d}")

    def _get_output_dir(self) -> str | None:
        if not self._output_dir:
            self._output_dir = filedialog.askdirectory(title="Select Output Folder")
        return self._output_dir

    # ── field config ──────────────────────────────────────────────────────────

    def _open_field_config(self):
        excel_cols = list(self._gen.df.columns) if self._gen.df is not None else []
        FieldConfigDialog(self.root, self._gen, excel_cols)
        self._redraw_preview()

    # ── photo editor ──────────────────────────────────────────────────────────

    def _edit_photo(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Select Student", "Select a student first.")
            return
        if self._gen.template_image is None:
            messagebox.showinfo("No Template", "Load a template image first.")
            return
        idx = int(sel[0])
        df  = self._gen.df
        row = df.iloc[idx].to_dict()
        pc  = self._col("photo")
        nc  = self._col("name")
        photo_path   = str(row.get(pc, "")).strip() if pc else ""
        student_name = str(row.get(nc, f"Student {idx}")).strip() if nc else f"Student {idx}"
        region = self._gen.config.get("photo_region", {
            "x": 200, "y": 100, "width": 150, "height": 180, "shape": "circle"})

        dlg = PhotoEditorDialog(
            self.root, self._gen.template_image, region,
            photo_path=photo_path if os.path.exists(photo_path) else None,
            initial_transform=self._gen.photo_transforms.get(idx),
            student_name=student_name)

        if dlg.result is not None:
            if dlg.apply_to_all and self._gen.df is not None:
                # Stamp the same transform on every student
                for i in range(len(self._gen.df)):
                    self._gen.photo_transforms[i] = dlg.result
                self._set_status(
                    f"Transform applied to all {len(self._gen.df)} students")
            else:
                self._gen.photo_transforms[idx] = dlg.result
                self._set_status(f"Photo saved for {student_name}")
            self._refresh_tree()
            self._preview_idx = idx
            self._redraw_preview()

    def _apply_transform_to_all(self):
        """Copy the selected student's saved photo transform to every student."""
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Select Student",
                "Select a student whose photo transform you want to copy to all.")
            return
        idx = int(sel[0])
        tfm = self._gen.photo_transforms.get(idx)
        if tfm is None:
            messagebox.showinfo("No Transform",
                "This student has no saved photo transform yet.\n"
                "Open Photo Editor and accept a transform first.")
            return
        if not messagebox.askyesno(
            "Apply to All",
            f"Copy this student's photo transform (zoom, pan, brightness, contrast, flip) "
            f"to all {len(self._gen.df)} students?"
        ):
            return
        for i in range(len(self._gen.df)):
            self._gen.photo_transforms[i] = dict(tfm)
        self._refresh_tree()
        self._set_status(
            f"Transform applied to all {len(self._gen.df)} students")

    def _set_photo_transform_all(self):
        """
        Let the user pick any one photo, edit it in the photo editor,
        then stamp the resulting transform onto every loaded student.
        No student needs to be selected first.
        """
        if self._gen.template_image is None:
            messagebox.showinfo("No Template", "Load a template image first.")
            return

        photo_path = filedialog.askopenfilename(
            title="Select a Sample Photo to Set Transform for All Students",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not photo_path:
            return

        region = self._gen.config.get("photo_region", {
            "x": 200, "y": 100, "width": 150, "height": 180, "shape": "circle",
        })

        dlg = PhotoEditorDialog(
            self.root, self._gen.template_image, region,
            photo_path=photo_path,
            initial_transform=None,
            student_name="Sample — applies to ALL students",
        )

        if dlg.result is None:
            return

        tfm = dict(dlg.result)
        n = len(self._gen.df) if self._gen.df is not None else 0

        if n == 0:
            messagebox.showinfo(
                "No Students Loaded",
                "Transform saved. Load an Excel file to apply it to students.",
            )
            return

        for i in range(n):
            self._gen.photo_transforms[i] = dict(tfm)

        self._refresh_tree()
        self._set_status(f"Photo transform applied to all {n} students")
        messagebox.showinfo(
            "Done",
            f"Transform applied to all {n} students.\n\n"
            "Preview any student card to confirm, then Generate All.",
        )

    # ── preview ───────────────────────────────────────────────────────────────

    def _on_select(self, _e):
        sel = self._tree.selection()
        if sel:
            self._preview_idx = int(sel[0])
            self._redraw_preview()

    def _on_dbl(self, _e):
        self._edit_photo()

    def _preview_selected(self):
        if self._gen.df is None:
            self._set_status("Load an Excel file first.")
            return
        if self._gen.template_image is None:
            self._set_status("Load a template image first.")
            return
        sel = self._tree.selection()
        if not sel:
            self._set_status("Select a student in the list to preview.")
            return
        self._preview_idx = int(sel[0])
        self._redraw_preview()

    def _redraw_preview(self):
        if (self._preview_idx is None
                or self._gen.df is None
                or self._gen.template_image is None):
            return
        try:
            row = self._gen.df.iloc[self._preview_idx].to_dict()
            card = self._gen.generate_card(
                row, self._gen.photo_transforms.get(self._preview_idx))
            self._blit_canvas(card)
        except Exception as exc:
            self._set_status(f"Preview error: {exc}")

    def _blit_canvas(self, img: Image.Image):
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 10 or h < 10:
            return
        scale = min(w / img.width, h / img.height) * 0.97
        nw, nh = int(img.width * scale), int(img.height * scale)
        scaled = img.resize((nw, nh), Image.LANCZOS)
        self._canvas_img = ImageTk.PhotoImage(scaled)
        self._canvas.delete("all")
        self._canvas.create_image(
            (w - nw) // 2, (h - nh) // 2, anchor=tk.NW, image=self._canvas_img)

    # ── generate ──────────────────────────────────────────────────────────────

    def _generate_selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Select Student", "Select a student first.")
            return
        out = self._get_output_dir()
        if not out:
            return
        idx = int(sel[0])
        df  = self._gen.df
        row = df.iloc[idx].to_dict()
        try:
            card = self._gen.generate_card(row, self._gen.photo_transforms.get(idx))
            nc = self._col("name")
            ac = self._col("admn")
            name = str(row.get(nc, f"student_{idx}")).strip() if nc else f"student_{idx}"
            admn = str(row.get(ac, str(idx))).strip() if ac else str(idx)
            safe = "".join(c for c in f"{admn}_{name}" if c not in r'\/:*?"<>|')
            path = os.path.join(out, f"{safe}.jpg")
            card.save(path, "JPEG", quality=95)
            self._set_status(f"Saved: {Path(path).name}")
            messagebox.showinfo("Done", f"Card saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    # ── face extraction tool ──────────────────────────────────────────────────

    def _extract_faces_folder(self):
        """
        Open the Face Extraction Editor: user picks one sample photo, tunes
        crop/zoom/brightness/contrast/shape, then applies those settings to an
        entire folder via the editor's "Apply to Folder…" button.

        From there, "Review All Photos…" shows every extracted result in a
        thumbnail grid so mistakes are easy to spot, and clicking any
        thumbnail opens it for individual editing with Prev/Next navigation.
        """
        photo_path = filedialog.askopenfilename(
            title="Select a Sample Photo to Preview Extraction Settings",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not photo_path:
            return
        FaceExtractEditorDialog(self.root, photo_path)

    def _generate_all(self):
        if self._gen.df is None:
            messagebox.showinfo("No Data", "Load Excel data first.")
            return
        if self._gen.template_image is None:
            messagebox.showinfo("No Template", "Load a template image first.")
            return
        out = self._get_output_dir()
        if not out:
            return

        def run():
            def prog(cur, total):
                self._progress_var.set(cur / total * 100)
                self._set_status(f"Generating {cur}/{total}…")
            try:
                results = self._gen.generate_all(out, progress_callback=prog)
                self._progress_var.set(100)

                # Auto-create A4 print sheets (5 × 2, 10 px row gap)
                sheets = []
                pdf_path = ""
                if results:
                    self._set_status("Building A4 print sheets…")
                    pages = self._gen.create_print_sheet(results)
                    for i, page in enumerate(pages, 1):
                        p = os.path.join(out, f"print_sheet_{i:02d}.jpg")
                        page.save(p, "JPEG", quality=95)
                        sheets.append(p)

                    self._set_status("Building PDF…")
                    pdf_path = os.path.join(out, "print_sheets.pdf")
                    pages[0].save(
                        pdf_path, "PDF", save_all=True,
                        append_images=pages[1:], resolution=300,
                    )

                self._set_status(
                    f"Done — {len(results)} cards + {len(sheets)} sheet(s) + PDF → {out}")
                messagebox.showinfo(
                    "Done",
                    f"{len(results)} cards saved.\n"
                    f"{len(sheets)} A4 print sheet(s) created.\n"
                    f"PDF: {os.path.basename(pdf_path)}\n\n{out}")
            except Exception as exc:
                messagebox.showerror("Error", str(exc))

        threading.Thread(target=run, daemon=True).start()

    def _create_print_sheet(self):
        out = self._get_output_dir()
        if not out:
            return
        cards = sorted(
            str(p) for p in Path(out).glob("*.jpg")
            if not p.name.startswith("print_sheet"))
        if not cards:
            messagebox.showinfo("No Cards", "Generate cards first.")
            return
        dlg = PrintSheetDialog(self.root)
        if dlg.result is None:
            return
        try:
            pages = self._gen.create_print_sheet(cards, dlg.result["dpi"])
            for i, page in enumerate(pages, 1):
                p = os.path.join(out, f"print_sheet_{i:02d}.jpg")
                page.save(p, "JPEG", quality=95, dpi=(dlg.result["dpi"],) * 2)
            self._set_status(f"Created {len(pages)} print sheet(s)")
            messagebox.showinfo("Done", f"{len(pages)} print sheet(s) → {out}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))


# ──────────────────────────────────────── FieldConfigDialog ──────────────────

class FieldConfigDialog(tk.Toplevel):
    """
    Visual field configuration.

    LEFT  — photo-region form + field list + property editor
            (excel_column is a DROPDOWN of actual Excel headers)
    RIGHT — template canvas: coloured dots mark each field position;
            click anywhere to re-position the selected field.
    """

    def __init__(self, parent: tk.Widget, gen: CardGenerator,
                 excel_columns: list[str]):
        super().__init__(parent)
        self.title("Configure Template Fields")
        self.geometry("1100x700")
        self.minsize(800, 560)
        self._gen = gen
        self._excel_cols = excel_columns  # actual headers from the loaded Excel
        self._sel: int | None = None
        self._tpl_scale  = 1.0
        self._tpl_offset = (0, 0)
        self._tpl_img_ref = None
        self._build_ui()
        self.transient(parent)
        self.grab_set()

    # ── layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ── Left ─────────────────────────────────────────────────────────────
        left = tk.Frame(paned, width=380)
        paned.add(left, weight=1)

        # Photo region
        pr_frame = tk.LabelFrame(left, text=" Photo Region ")
        pr_frame.pack(fill=tk.X, padx=4, pady=(0, 6))
        cfg_pr = self._gen.config.get("photo_region", {})
        self._pr = {
            "x":      _entry_row(pr_frame, "X",      cfg_pr.get("x", 200),    0),
            "y":      _entry_row(pr_frame, "Y",      cfg_pr.get("y", 100),    1),
            "width":  _entry_row(pr_frame, "Width",  cfg_pr.get("width", 150), 2),
            "height": _entry_row(pr_frame, "Height", cfg_pr.get("height",180), 3),
        }
        sr = tk.Frame(pr_frame)
        sr.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        tk.Label(sr, text="Shape:", width=9, anchor="e").pack(side=tk.LEFT)
        self._pr_shape = tk.StringVar(value=cfg_pr.get("shape", "circle"))
        ttk.Combobox(sr, textvariable=self._pr_shape,
                     values=["circle", "rect"], width=8,
                     state="readonly").pack(side=tk.LEFT, padx=4)

        pcr = tk.Frame(pr_frame)
        pcr.grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        tk.Label(pcr, text="Photo col:", width=9, anchor="e").pack(side=tk.LEFT)
        self._photo_col = tk.StringVar(
            value=self._gen.config.get("photo_column", "photo"))
        ttk.Combobox(pcr, textvariable=self._photo_col,
                     values=[""] + self._excel_cols, width=14,
                     state="readonly" if self._excel_cols else "normal"
                     ).pack(side=tk.LEFT, padx=4)

        pr_btn_row = tk.Frame(pr_frame)
        pr_btn_row.grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        tk.Button(pr_btn_row, text="Apply", command=self._apply_pr,
                  bg="#43A047", fg="white", relief=tk.FLAT,
                  padx=8).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(pr_btn_row, text="Auto-Detect Photo Region (CV2)",
                  command=self._detect_circle_cv2,
                  bg="#0097A7", fg="white", relief=tk.FLAT,
                  padx=8).pack(side=tk.LEFT)

        # Field list
        fl_frame = tk.LabelFrame(
            left, text=" Text Fields  (select → click template canvas to position) ")
        fl_frame.pack(fill=tk.X, padx=4, pady=(0, 6))

        bf = tk.Frame(fl_frame)
        bf.pack(fill=tk.X, pady=2)
        _lbtn(bf, "+ Add",    self._add_field,    "#1976D2")
        _lbtn(bf, "− Remove", self._remove_field, "#C62828")
        _lbtn(bf, "⟳ OCR detect", self._auto_detect, "#7B1FA2")

        self._listbox = tk.Listbox(fl_frame, selectmode=tk.SINGLE,
                                    activestyle="none", height=7)
        lsb = ttk.Scrollbar(fl_frame, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=lsb.set)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.pack(fill=tk.X, padx=4, pady=4)
        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)

        # Field property editor
        ed = tk.LabelFrame(left, text=" Selected Field Properties ")
        ed.pack(fill=tk.BOTH, expand=True, padx=4)
        ed.columnconfigure(1, weight=1)

        def _all_btn(row: int, key: str):
            tk.Button(ed, text="→All", font=("Arial", 7),
                      command=lambda k=key: self._apply_to_all(k),
                      bg="#90A4AE", fg="white", relief=tk.FLAT,
                      padx=3, pady=0).grid(row=row, column=2, padx=(0, 3), pady=2, sticky="w")

        # Row 0 — Excel column (no →All)
        tk.Label(ed, text="Excel col:", width=12, anchor="e").grid(
            row=0, column=0, padx=5, pady=3, sticky="e")
        self._col_var = tk.StringVar()
        col_choices = [""] + self._excel_cols
        self._col_cb = ttk.Combobox(ed, textvariable=self._col_var,
                                     values=col_choices, width=18,
                                     state="readonly" if self._excel_cols else "normal")
        self._col_cb.grid(row=0, column=1, columnspan=2, sticky="w", padx=4, pady=3)

        # Rows 1-3, 7-12 — plain text entries (no →All on position/layout fields)
        _plain_rows = [
            (1,  "Label pfx:",   "label",        ""),
            (2,  "X:",           "x",            "0"),
            (3,  "Y:",           "y",            "0"),
            (7,  "Max width:",   "max_width",    "0"),
            (8,  "Line height:", "line_height",  "16"),
            (9,  "Wrap X:",      "wrap_x",       "0"),
            # multiline extras (rows 10-12)
            (10, "Split on:",    "split_on",     ""),
            (11, "Last line X:", "last_line_x",  ""),
            (12, "Last line Y:", "last_line_y",  ""),
        ]
        self._fvars: dict[str, tk.StringVar] = {}
        for row, lbl, key, dflt in _plain_rows:
            tk.Label(ed, text=lbl, width=12, anchor="e").grid(
                row=row, column=0, padx=5, pady=2, sticky="e")
            var = tk.StringVar(value=dflt)
            self._fvars[key] = var
            tk.Entry(ed, textvariable=var, width=16).grid(
                row=row, column=1, columnspan=2, sticky="w", padx=4, pady=2)

        # Row 4 — Font (combobox dropdown) + →All
        tk.Label(ed, text="Font:", width=12, anchor="e").grid(
            row=4, column=0, padx=5, pady=2, sticky="e")
        var = tk.StringVar(value="arial")
        self._fvars["font"] = var
        _fonts = _discover_fonts()
        self._font_cb = ttk.Combobox(ed, textvariable=var, values=_fonts,
                                      width=14, font=("Arial", 9))
        self._font_cb.grid(row=4, column=1, sticky="w", padx=4, pady=2)
        _all_btn(4, "font")

        # Row 5 — Size + →All
        tk.Label(ed, text="Size:", width=12, anchor="e").grid(
            row=5, column=0, padx=5, pady=2, sticky="e")
        var = tk.StringVar(value="12")
        self._fvars["size"] = var
        tk.Entry(ed, textvariable=var, width=6).grid(
            row=5, column=1, sticky="w", padx=4, pady=2)
        _all_btn(5, "size")

        # Row 6 — Color (with picker button) + →All
        tk.Label(ed, text="Color:", width=12, anchor="e").grid(
            row=6, column=0, padx=5, pady=2, sticky="e")
        var = tk.StringVar(value="#000000")
        self._fvars["color"] = var
        color_row = tk.Frame(ed)
        color_row.grid(row=6, column=1, sticky="w", pady=2)
        tk.Entry(color_row, textvariable=var, width=9).pack(side=tk.LEFT)
        tk.Button(color_row, text="…",
                  command=lambda k="color": self._pick_color(k),
                  width=2).pack(side=tk.LEFT, padx=2)
        _all_btn(6, "color")

        # Row 13 — Align + →All
        tk.Label(ed, text="Align:", width=12, anchor="e").grid(
            row=13, column=0, padx=5, pady=2, sticky="e")
        self._align_var = tk.StringVar(value="left")
        ttk.Combobox(ed, textvariable=self._align_var,
                     values=["left", "center", "right"], width=8,
                     state="readonly").grid(row=13, column=1, sticky="w", padx=4, pady=2)
        _all_btn(13, "align")

        # Row 14 — Transform + →All
        tk.Label(ed, text="Transform:", width=12, anchor="e").grid(
            row=14, column=0, padx=5, pady=2, sticky="e")
        self._trans_var = tk.StringVar(value="")
        ttk.Combobox(ed, textvariable=self._trans_var,
                     values=["", "upper", "lower", "title"], width=8,
                     state="readonly").grid(row=14, column=1, sticky="w", padx=4, pady=2)
        _all_btn(14, "transform")

        # Row 15 — Bold + →All
        tk.Label(ed, text="Bold:", width=12, anchor="e").grid(
            row=15, column=0, padx=5, pady=2, sticky="e")
        self._bold_var = tk.BooleanVar()
        tk.Checkbutton(ed, variable=self._bold_var).grid(
            row=15, column=1, sticky="w", padx=4, pady=2)
        _all_btn(15, "bold")

        # Row 16 — Action buttons
        bf2 = tk.Frame(ed)
        bf2.grid(row=16, column=0, columnspan=3, pady=6)
        tk.Button(bf2, text="Apply", command=self._apply_field,
                  bg="#43A047", fg="white", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=4)
        tk.Button(bf2, text="Font+Size+Bold → All", command=self._apply_font_to_all,
                  bg="#E65100", fg="white", relief=tk.FLAT, padx=6).pack(side=tk.LEFT, padx=4)
        tk.Button(bf2, text="Save Config", command=self._save,
                  bg="#1976D2", fg="white", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=4)
        tk.Button(bf2, text="Close", command=self.destroy,
                  relief=tk.FLAT, padx=10).pack(side=tk.LEFT)

        self._refresh_list()

        # ── Right: template canvas ────────────────────────────────────────────
        right = tk.Frame(paned)
        paned.add(right, weight=2)

        # Top bar: instruction + live coordinate readout
        info = tk.Frame(right)
        info.pack(fill=tk.X, pady=(0, 2))
        tk.Label(info,
                 text="Click template to position field  |  Arrow keys nudge 1 px (Shift = 5 px)",
                 font=("Arial", 9, "italic"), fg="#555").pack(side=tk.LEFT, padx=6)
        tk.Button(info, text="Refresh", command=self._draw_template,
                  relief=tk.FLAT, padx=6, pady=2).pack(side=tk.RIGHT, padx=4)
        self._coord_lbl = tk.Label(info, text="x=—  y=—",
                                   font=("Arial", 8, "bold"), fg="#37474F", width=14)
        self._coord_lbl.pack(side=tk.RIGHT, padx=4)

        # Alignment + grid toolbar
        tools = tk.Frame(right, bg="#ECEFF1")
        tools.pack(fill=tk.X, padx=4, pady=(0, 3))
        tk.Label(tools, text="Align:", bg="#ECEFF1",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(4, 2))
        for _lbl, _cmd in [
            ("⊕ Center H", self._align_center_h),
            ("⊕ Center V", self._align_center_v),
            ("↕ All→X",    self._align_same_x),
            ("↔ All→Y",    self._align_same_y),
        ]:
            tk.Button(tools, text=_lbl, command=_cmd,
                      bg="#546E7A", fg="white", relief=tk.FLAT,
                      font=("Arial", 8), padx=4, pady=1).pack(side=tk.LEFT, padx=2)
        ttk.Separator(tools, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=2)
        tk.Label(tools, text="Grid:", bg="#ECEFF1",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(0, 2))
        self._grid_visible = tk.BooleanVar(value=False)
        tk.Checkbutton(tools, text="Show", variable=self._grid_visible,
                       command=self._draw_template, bg="#ECEFF1",
                       font=("Arial", 8)).pack(side=tk.LEFT)
        self._snap_to_grid = tk.BooleanVar(value=False)
        tk.Checkbutton(tools, text="Snap", variable=self._snap_to_grid,
                       bg="#ECEFF1", font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Label(tools, text="Spacing:", bg="#ECEFF1",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(6, 1))
        self._grid_spacing = tk.IntVar(value=50)
        tk.Spinbox(tools, textvariable=self._grid_spacing,
                   from_=5, to=500, increment=5, width=4,
                   font=("Arial", 8),
                   command=self._draw_template).pack(side=tk.LEFT)
        tk.Label(tools, text="px", bg="#ECEFF1",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(1, 0))

        # Ruler frame: corner + h-ruler + v-ruler + template canvas
        ruler_frame = tk.Frame(right)
        ruler_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 2))
        ruler_frame.columnconfigure(1, weight=1)
        ruler_frame.rowconfigure(1, weight=1)

        tk.Canvas(ruler_frame, width=20, height=20,
                  bg="#90A4AE", highlightthickness=0).grid(row=0, column=0)
        self._h_ruler = tk.Canvas(ruler_frame, height=20,
                                   bg="#CFD8DC", highlightthickness=0)
        self._h_ruler.grid(row=0, column=1, sticky="ew")
        self._v_ruler = tk.Canvas(ruler_frame, width=20,
                                   bg="#CFD8DC", highlightthickness=0)
        self._v_ruler.grid(row=1, column=0, sticky="ns")

        cf = tk.Frame(ruler_frame, bd=1, relief=tk.SUNKEN)
        cf.grid(row=1, column=1, sticky="nsew")
        self._tpl_canvas = tk.Canvas(cf, bg="#333", cursor="crosshair")
        self._tpl_canvas.pack(fill=tk.BOTH, expand=True)
        self._tpl_canvas.bind("<Button-1>",  self._on_canvas_click)
        self._tpl_canvas.bind("<Configure>", lambda _: self._draw_template())
        self._tpl_canvas.bind("<Motion>",    self._on_mouse_move)
        self._tpl_canvas.bind("<Leave>",     self._on_mouse_leave)

        # Arrow-key nudge — bind to dialog so keys work regardless of focus
        for _key, _dx, _dy in [
            ("<Left>", -1, 0), ("<Right>", 1, 0),
            ("<Up>", 0, -1),   ("<Down>", 0, 1),
            ("<Shift-Left>", -5, 0), ("<Shift-Right>", 5, 0),
            ("<Shift-Up>", 0, -5),   ("<Shift-Down>", 0, 5),
        ]:
            self.bind(_key, lambda e, dx=_dx, dy=_dy: self._nudge(dx, dy))

        tk.Label(right,
                 text=(
                     "● dots = fields  |  yellow ring = selected  |  "
                     "click = position  |  ↑↓←→ = nudge 1 px  |  Shift+↑↓←→ = 5 px"
                 ),
                 font=("Arial", 8), fg="#666").pack(padx=4, anchor="w")

    # ── template canvas ───────────────────────────────────────────────────────

    def _draw_template(self):
        cw = self._tpl_canvas.winfo_width()
        ch = self._tpl_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        tpl = self._gen.template_image
        if tpl is None:
            self._tpl_canvas.delete("all")
            self._tpl_canvas.create_text(cw // 2, ch // 2,
                                          text="No template loaded",
                                          fill="white", font=("Arial", 12))
            return

        scale = min(cw / tpl.width, ch / tpl.height) * 0.97
        self._tpl_scale = scale
        nw, nh = int(tpl.width * scale), int(tpl.height * scale)
        ox, oy = (cw - nw) // 2, (ch - nh) // 2
        self._tpl_offset = (ox, oy)

        overlay = tpl.convert("RGB").resize((nw, nh), Image.LANCZOS).copy()
        draw = ImageDraw.Draw(overlay)
        font_tiny = ImageFont.load_default()

        for fi, field in enumerate(self._gen.config.get("fields", [])):
            color = FIELD_COLORS[fi % len(FIELD_COLORS)]
            fx = int(field.get("x", 0) * scale)
            fy = int(field.get("y", 0) * scale)
            r = 6
            draw.ellipse([fx - r, fy - r, fx + r, fy + r],
                         fill=color, outline="white")
            label = (field.get("excel_column") or field.get("id") or f"f{fi}")[:10]
            draw.text((fx + r + 2, fy - 6), label,
                      fill=color, font=font_tiny)

        # Highlight selected field
        if self._sel is not None:
            fields = self._gen.config.get("fields", [])
            if self._sel < len(fields):
                sf = fields[self._sel]
                fx = int(sf.get("x", 0) * scale)
                fy = int(sf.get("y", 0) * scale)
                draw.ellipse([fx - 11, fy - 11, fx + 11, fy + 11],
                             outline="yellow", width=3)

        self._tpl_img_ref = ImageTk.PhotoImage(overlay)
        self._tpl_canvas.delete("all")
        self._tpl_canvas.create_image(ox, oy, anchor=tk.NW, image=self._tpl_img_ref)
        self._draw_grid()
        self._draw_rulers()

    def _draw_grid(self):
        """Overlay a dashed grid on the template canvas when grid is enabled."""
        if not self._grid_visible.get() or self._gen.template_image is None:
            return
        spacing = self._grid_spacing.get()
        if spacing < 1:
            return
        tpl = self._gen.template_image
        scale = self._tpl_scale
        ox, oy = self._tpl_offset
        x1, y1 = ox, oy
        x2, y2 = ox + tpl.width * scale, oy + tpl.height * scale
        for tx in range(0, tpl.width + 1, spacing):
            sx = ox + tx * scale
            self._tpl_canvas.create_line(sx, y1, sx, y2,
                                          fill="#1976D2", dash=(2, 4), tags="grid")
        for ty in range(0, tpl.height + 1, spacing):
            sy = oy + ty * scale
            self._tpl_canvas.create_line(x1, sy, x2, sy,
                                          fill="#1976D2", dash=(2, 4), tags="grid")

    def _draw_rulers(self):
        """Redraw pixel rulers to match the current template scale and offset."""
        if self._gen.template_image is None:
            return
        tpl = self._gen.template_image
        scale = self._tpl_scale
        ox, oy = self._tpl_offset

        # Choose a readable tick interval: aim for ~60 screen-px between major ticks
        raw = 60.0 / max(scale, 0.001)
        nice = [5, 10, 20, 25, 50, 100, 200, 250, 500, 1000]
        major = min(nice, key=lambda v: abs(v - raw))
        minor = max(1, major // 5)

        # ── Horizontal ruler ─────────────────────────────────────────────────
        hr = self._h_ruler
        hw = hr.winfo_width()
        hh = hr.winfo_height() or 20
        if hw < 2:
            return
        hr.delete("ruler")
        for tx in range(0, tpl.width + 1, minor):
            sx = ox + tx * scale
            if sx < 0 or sx > hw:
                continue
            is_major = (tx % major == 0)
            tick_h = hh - 2 if is_major else hh // 3
            hr.create_line(sx, hh, sx, hh - tick_h, fill="#546E7A", tags="ruler")
            if is_major and tx > 0:
                hr.create_text(sx + 1, 1, text=str(tx), anchor="nw",
                               font=("Arial", 6), fill="#37474F", tags="ruler")

        # ── Vertical ruler ────────────────────────────────────────────────────
        vr = self._v_ruler
        vw = vr.winfo_width() or 20
        vh = vr.winfo_height()
        if vh < 2:
            return
        vr.delete("ruler")
        for ty in range(0, tpl.height + 1, minor):
            sy = oy + ty * scale
            if sy < 0 or sy > vh:
                continue
            is_major = (ty % major == 0)
            tick_w = vw - 2 if is_major else vw // 3
            vr.create_line(vw, sy, vw - tick_w, sy, fill="#546E7A", tags="ruler")
            if is_major and ty > 0:
                vr.create_text(1, sy + 1, text=str(ty), anchor="nw",
                               font=("Arial", 6), fill="#37474F", tags="ruler")

    def _on_mouse_move(self, event):
        """Update the live coordinate label, crosshair, and ruler cursor marks."""
        ox, oy = self._tpl_offset
        tx = int((event.x - ox) / self._tpl_scale)
        ty = int((event.y - oy) / self._tpl_scale)
        tpl = self._gen.template_image
        if tpl and 0 <= tx <= tpl.width and 0 <= ty <= tpl.height:
            self._coord_lbl.config(text=f"x={tx}  y={ty}")
        else:
            self._coord_lbl.config(text="x=—  y=—")

        # Crosshair on canvas
        self._tpl_canvas.delete("crosshair")
        cw = self._tpl_canvas.winfo_width()
        ch = self._tpl_canvas.winfo_height()
        self._tpl_canvas.create_line(event.x, 0, event.x, ch,
                                      fill="#FF5722", dash=(4, 4), tags="crosshair")
        self._tpl_canvas.create_line(0, event.y, cw, event.y,
                                      fill="#FF5722", dash=(4, 4), tags="crosshair")

        # Cursor tick on rulers
        self._h_ruler.delete("cursor")
        self._v_ruler.delete("cursor")
        hh = self._h_ruler.winfo_height() or 20
        vw = self._v_ruler.winfo_width() or 20
        self._h_ruler.create_line(event.x, 0, event.x, hh,
                                   fill="#FF5722", width=1, tags="cursor")
        self._v_ruler.create_line(0, event.y, vw, event.y,
                                   fill="#FF5722", width=1, tags="cursor")

    def _on_mouse_leave(self, _event):
        self._tpl_canvas.delete("crosshair")
        self._h_ruler.delete("cursor")
        self._v_ruler.delete("cursor")
        self._coord_lbl.config(text="x=—  y=—")

    def _snap_point(self, tx: int, ty: int) -> "tuple[int,int]":
        if not self._snap_to_grid.get():
            return tx, ty
        s = self._grid_spacing.get()
        if s < 1:
            return tx, ty
        return round(tx / s) * s, round(ty / s) * s

    def _nudge(self, dx: int, dy: int):
        """Move the selected field by (dx, dy) template pixels."""
        if self._sel is None:
            return
        fields = self._gen.config.get("fields", [])
        if self._sel >= len(fields):
            return
        f = fields[self._sel]
        f["x"] = max(0, f.get("x", 0) + dx)
        f["y"] = max(0, f.get("y", 0) + dy)
        self._fvars["x"].set(str(f["x"]))
        self._fvars["y"].set(str(f["y"]))
        self._refresh_list()
        self._listbox.selection_set(self._sel)
        self._draw_template()

    def _align_center_h(self):
        """Move selected field to the horizontal centre of the template."""
        if self._sel is None or self._gen.template_image is None:
            return
        fields = self._gen.config.get("fields", [])
        if self._sel >= len(fields):
            return
        fields[self._sel]["x"] = self._gen.template_image.width // 2
        self._fvars["x"].set(str(fields[self._sel]["x"]))
        self._refresh_list()
        self._listbox.selection_set(self._sel)
        self._draw_template()

    def _align_center_v(self):
        """Move selected field to the vertical centre of the template."""
        if self._sel is None or self._gen.template_image is None:
            return
        fields = self._gen.config.get("fields", [])
        if self._sel >= len(fields):
            return
        fields[self._sel]["y"] = self._gen.template_image.height // 2
        self._fvars["y"].set(str(fields[self._sel]["y"]))
        self._refresh_list()
        self._listbox.selection_set(self._sel)
        self._draw_template()

    def _align_same_x(self):
        """Set every other field to the same X as the selected field."""
        if self._sel is None:
            return
        fields = self._gen.config.get("fields", [])
        if self._sel >= len(fields):
            return
        ref_x = fields[self._sel].get("x", 0)
        for i, f in enumerate(fields):
            if i != self._sel:
                f["x"] = ref_x
        self._refresh_list()
        self._listbox.selection_set(self._sel)
        self._draw_template()

    def _align_same_y(self):
        """Set every other field to the same Y as the selected field."""
        if self._sel is None:
            return
        fields = self._gen.config.get("fields", [])
        if self._sel >= len(fields):
            return
        ref_y = fields[self._sel].get("y", 0)
        for i, f in enumerate(fields):
            if i != self._sel:
                f["y"] = ref_y
        self._refresh_list()
        self._listbox.selection_set(self._sel)
        self._draw_template()

    def _on_canvas_click(self, event):
        if self._sel is None:
            return
        ox, oy = self._tpl_offset
        tx = int((event.x - ox) / self._tpl_scale)
        ty = int((event.y - oy) / self._tpl_scale)
        tx, ty = self._snap_point(tx, ty)
        tpl = self._gen.template_image
        if tpl and not (0 <= tx <= tpl.width and 0 <= ty <= tpl.height):
            return
        fields = self._gen.config.get("fields", [])
        if self._sel < len(fields):
            fields[self._sel]["x"] = tx
            fields[self._sel]["y"] = ty
            self._fvars["x"].set(str(tx))
            self._fvars["y"].set(str(ty))
            self._refresh_list()
            self._listbox.selection_set(self._sel)
            self._draw_template()

    # ── field list ────────────────────────────────────────────────────────────

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        for fi, f in enumerate(self._gen.config.get("fields", [])):
            col   = f.get("excel_column") or f.get("id") or "—"
            color = FIELD_COLORS[fi % len(FIELD_COLORS)]
            self._listbox.insert(tk.END,
                f"{col}  @ ({f.get('x', 0)}, {f.get('y', 0)})")
            self._listbox.itemconfig(fi, fg=color, selectforeground=color)

    def _on_list_select(self, _):
        sel = self._listbox.curselection()
        if not sel:
            return
        self._sel = sel[0]
        fields = self._gen.config.get("fields", [])
        if self._sel >= len(fields):
            return
        f = fields[self._sel]
        # Populate excel_column dropdown
        self._col_var.set(f.get("excel_column", ""))
        # Populate other fields
        for key, var in self._fvars.items():
            var.set(str(f.get(key, "")))
        self._align_var.set(f.get("align", "left"))
        self._trans_var.set(f.get("transform", ""))
        self._bold_var.set(bool(f.get("bold", False)))
        self._draw_template()

    def _add_field(self):
        if "fields" not in self._gen.config:
            self._gen.config["fields"] = []
        first_col = self._excel_cols[0] if self._excel_cols else "name"
        self._gen.config["fields"].append({
            "excel_column": first_col, "label": "", "x": 100, "y": 100,
            "font": "arial", "size": 12, "bold": False, "color": "#000000",
            "align": "left", "transform": "", "max_width": 0,
            "line_height": 16, "wrap_x": 100,
        })
        self._refresh_list()
        idx = len(self._gen.config["fields"]) - 1
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._on_list_select(None)

    def _remove_field(self):
        if self._sel is None:
            return
        self._gen.config.get("fields", []).pop(self._sel)
        self._sel = None
        self._refresh_list()
        self._draw_template()

    def _apply_field(self):
        if self._sel is None:
            return
        fields = self._gen.config.get("fields", [])
        if self._sel >= len(fields):
            return
        f = fields[self._sel]
        f["excel_column"] = self._col_var.get()
        for key, var in self._fvars.items():
            val = var.get()
            if key in ("x", "y", "size", "max_width", "line_height", "wrap_x"):
                try:
                    val = int(val)
                except ValueError:
                    val = 0
                f[key] = val
            elif key in ("last_line_x", "last_line_y"):
                # Optional integer — remove the key when field is left blank
                stripped = val.strip()
                if stripped:
                    try:
                        f[key] = int(stripped)
                    except ValueError:
                        f.pop(key, None)
                else:
                    f.pop(key, None)
            else:
                f[key] = val
        f["align"]     = self._align_var.get()
        f["transform"] = self._trans_var.get()
        f["bold"]      = self._bold_var.get()
        self._refresh_list()
        self._listbox.selection_set(self._sel)
        self._draw_template()

    def _apply_to_all(self, key: str):
        """Apply the current value of *key* from the property editor to every field."""
        fields = self._gen.config.get("fields", [])
        if not fields:
            return
        if key == "font":
            val = self._fvars["font"].get().strip() or "arial"
            for f in fields:
                f["font"] = val
        elif key == "size":
            try:
                val = int(self._fvars["size"].get())
            except ValueError:
                messagebox.showerror("Invalid", "Size must be an integer.", parent=self)
                return
            for f in fields:
                f["size"] = val
                f["line_height"] = val + 4
        elif key == "color":
            val = self._fvars["color"].get()
            for f in fields:
                f["color"] = val
        elif key == "align":
            val = self._align_var.get()
            for f in fields:
                f["align"] = val
        elif key == "bold":
            val = self._bold_var.get()
            for f in fields:
                f["bold"] = val
        elif key == "transform":
            val = self._trans_var.get()
            for f in fields:
                f["transform"] = val
        self._refresh_list()
        if self._sel is not None:
            self._listbox.selection_set(self._sel)
        self._draw_template()

    def _apply_font_to_all(self):
        """Apply font family, size, and bold to every field at once."""
        self._apply_to_all("font")
        self._apply_to_all("size")
        self._apply_to_all("bold")

    def _apply_pr(self):
        try:
            self._gen.config["photo_region"] = {
                "x":      int(self._pr["x"].get()),
                "y":      int(self._pr["y"].get()),
                "width":  int(self._pr["width"].get()),
                "height": int(self._pr["height"].get()),
                "shape":  self._pr_shape.get(),
            }
            self._gen.config["photo_column"] = self._photo_col.get()
            self._draw_template()
        except ValueError:
            messagebox.showerror("Invalid", "Photo region values must be integers.", parent=self)

    def _detect_circle_cv2(self):
        """Run CV2 contour + HoughCircles detection on the loaded template and
        populate the photo-region form fields automatically."""
        if self._gen.template_image is None:
            messagebox.showinfo("No Template", "Load a template image first.", parent=self)
            return
        region = detect_photo_region(self._gen.template_image)
        if region is None:
            messagebox.showinfo(
                "Region Not Found",
                "No circular or rectangular photo region detected in the current template.\n"
                "Configure the photo region manually or try a different template.",
                parent=self)
            return
        self._pr["x"].set(str(region["x"]))
        self._pr["y"].set(str(region["y"]))
        self._pr["width"].set(str(region["width"]))
        self._pr["height"].set(str(region["height"]))
        self._pr_shape.set(region["shape"])
        self._apply_pr()
        messagebox.showinfo(
            "Region Detected",
            f"Photo region set to:\n"
            f"  Position : ({region['x']}, {region['y']})\n"
            f"  Size     : {region['width']} × {region['height']} px\n"
            f"  Shape    : {region['shape']}",
            parent=self)

    def _pick_color(self, key: str):
        col = colorchooser.askcolor(color=self._fvars[key].get(), parent=self)
        if col[1]:
            self._fvars[key].set(col[1])

    def _auto_detect(self):
        if self._gen.template_image is None:
            messagebox.showinfo("No Template", "Load a template image first.", parent=self)
            return
        try:
            excel_cols = (self._gen.df.columns.tolist()
                          if self._gen.df is not None else None)
            detected = self._gen.auto_detect_fields(excel_columns=excel_cols)
        except RuntimeError as exc:
            messagebox.showerror("OCR Error", str(exc), parent=self)
            return
        if not detected:
            messagebox.showinfo("OCR",
                "No known labels found. Ensure Tesseract is installed.", parent=self)
            return
        if messagebox.askyesno(
            "OCR Auto-Detect",
            f"Found {len(detected)} field positions.\nReplace current field list?",
            parent=self
        ):
            self._gen.config["fields"] = detected
            self._sel = None
            self._refresh_list()
            self._draw_template()

    def _save(self):
        path = filedialog.asksaveasfilename(
            title="Save Config", defaultextension=".json",
            filetypes=[("JSON", "*.json")], parent=self)
        if path:
            self._gen.save_config(path)


# ──────────────────────────────────────────── PrintSheetDialog ───────────────

class PrintSheetDialog(tk.Toplevel):
    """Ask for DPI only — layout is fixed at 5 × 2 (10 cards per A4 page)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Print Sheet Settings")
        self.geometry("280x160")
        self.resizable(False, False)
        self.result = None

        tk.Label(self, text="Layout: 5 columns × 2 rows (10 per page)",
                 anchor="w", fg="#555").pack(fill=tk.X, padx=20, pady=(16, 6))

        tk.Label(self, text="DPI:", anchor="w").pack(
            fill=tk.X, padx=20, pady=(4, 2))
        self._dpi = tk.IntVar(value=300)
        ttk.Combobox(self, textvariable=self._dpi,
                     values=[150, 200, 300], width=8).pack(padx=20, anchor="w")

        bf = tk.Frame(self)
        bf.pack(pady=16)
        tk.Button(bf, text="Create", command=self._ok,
                  bg="#388E3C", fg="white", relief=tk.FLAT, padx=12).pack(side=tk.LEFT, padx=6)
        tk.Button(bf, text="Cancel", command=self.destroy,
                  relief=tk.FLAT, padx=12).pack(side=tk.LEFT)

        self.transient(parent)
        self.grab_set()
        self.wait_window()

    def _ok(self):
        self.result = {"dpi": self._dpi.get()}
        self.destroy()


# ──────────────────────────────────────────────────── entry point ────────────

if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except Exception:
        pass
    IDCardApp(root)
    root.mainloop()
