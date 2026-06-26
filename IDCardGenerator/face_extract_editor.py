"""
Face Extraction Editor

Standalone dialog for previewing and tuning face-crop settings on one sample
photo, then batch-applying those settings to an entire folder of photos.

Layout
------
Left   — original photo with two overlaid boxes:
           • blue  = raw Haar-detected face bounding box
           • green = final crop area (padded + zoom + shift)
         Drag the centre of the crop box to reposition it.
         Drag an edge to resize that dimension only (width or height);
         drag a corner to resize both at once.
         Scroll wheel zooms in/out.

Centre — extracted face preview (what the saved file will look like).

Right  — controls: Zoom, Brightness, Contrast, Shape, Flip;
         progress bar; Apply to Folder button.

Review mode
-----------
"Review All Photos…" lets the user pick a folder and see every extracted
result at once in a thumbnail grid, so mistakes are easy to spot before
batch-saving. Clicking a thumbnail drops into the normal single-photo editor
for that file (pre-loaded with any earlier per-photo edit), with Prev/Next
buttons to step through the whole folder and a "Back to Grid" button to
re-check everything.

Editing a single photo only ever affects that one photo (saved as a
per-photo override) — every other photo starts from neutral defaults
("initial selection") until the user either edits it individually too, or
clicks "Use These Settings for All" to make the currently-open photo's
tuning the default for every photo that hasn't been customised yet.
"""

import os
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageTk

from card_generator import extract_face_custom


class FaceExtractEditorDialog(tk.Toplevel):
    """
    Preview face-crop settings on a sample photo and batch-save to a folder.
    No card template is involved — this is purely a photo pre-processing tool.
    """

    _IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

    # Neutral starting point for any photo that hasn't been individually
    # tuned and hasn't been covered by an explicit "apply to all".
    _DEFAULT_PARAMS = {
        "zoom":         1.0,
        "shift_x":      0.0,
        "shift_y":      0.0,
        "width_scale":  1.0,
        "height_scale": 1.0,
        "shape":        "passport",
        "brightness":   1.0,
        "contrast":     1.0,
        "flip_h":       False,
        "flip_v":       False,
    }

    def __init__(self, parent: tk.Widget, sample_photo_path: str):
        super().__init__(parent)
        self.title(f"Face Extraction Editor — {Path(sample_photo_path).name}")
        self.geometry("1200x700")
        self.minsize(900, 560)
        self.resizable(True, True)

        try:
            self._photo = Image.open(sample_photo_path).convert("RGB")
        except Exception as exc:
            messagebox.showerror("Cannot Open Photo", str(exc), parent=parent)
            self.destroy()
            return

        self._sample_path = sample_photo_path

        # Current extraction parameters — edits here apply only to this one
        # photo (self._sample_path); they don't change what other photos in
        # a folder get unless the user clicks "Use These Settings for All".
        self._params: dict = dict(self._DEFAULT_PARAMS)

        # Latest detection results (updated on every redraw)
        self._face_bbox: "tuple | None" = None   # (x1,y1,x2,y2) in original px
        self._crop_bbox: "tuple | None" = None   # (x1,y1,x2,y2) in original px
        self._extracted: "Image.Image | None" = None

        # Canvas render helpers
        self._orig_scale:  float = 1.0
        self._orig_offset: "tuple[int,int]" = (0, 0)
        self._drag_start:  "tuple[int,int] | None" = None
        self._drag_base:   "tuple[float,float]" = (0.0, 0.0)
        self._drag_mode:   "str | None" = None   # "move" | "left"/"right"/"top"/"bottom" | "tl"/"tr"/"bl"/"br"
        self._resize_base: "tuple[float,float]" = (1.0, 1.0)   # width_scale, height_scale at drag start
        self._box_base:    "tuple[float,float,float,float] | None" = None  # crop_bbox at drag start (orig px)
        self._orig_img_ref  = None   # ImageTk refs — prevent GC
        self._prev_img_ref  = None

        self._processing = False     # True while batch thread runs

        # Review-all-photos state
        self._overrides:     "dict[str, dict]" = {}   # abs path -> saved per-photo params
        self._base_params:   "dict | None" = None      # default params for un-edited photos
        self._review_files:  "list[Path]" = []
        self._review_index:  int = -1
        self._review_src_dir: "Path | None" = None

        self._build_ui()
        self._bind_events()
        self.after(80, self._redraw)

        self.transient(parent)
        self.grab_set()
        self.wait_window()

    # ──────────────────────────────────────────────────────────── UI ──────────

    def _build_ui(self):
        # Review-mode banner — created but left unpacked until review starts
        self._review_banner = tk.Frame(self, bg="#FFF3E0")
        self._build_review_banner()

        root = tk.Frame(self)
        self._root_frame = root
        root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # ── Left: original photo with overlays ────────────────────────────
        orig_lf = tk.LabelFrame(root, text=" Original Photo — drag centre to move, edges/corners to resize ")
        orig_lf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._orig_canvas = tk.Canvas(orig_lf, bg="#2a2a2a", cursor="fleur")
        self._orig_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        legend = tk.Frame(orig_lf)
        legend.pack(fill=tk.X, padx=6, pady=(0, 3))
        for color, label in [("#4FC3F7", "detected face"), ("#69F0AE", "crop area")]:
            c = tk.Canvas(legend, width=14, height=14,
                          bg=self.cget("bg"), highlightthickness=0)
            c.pack(side=tk.LEFT)
            c.create_rectangle(2, 2, 12, 12, fill=color, outline="")
            tk.Label(legend, text=label, font=("Arial", 7),
                     fg="#666").pack(side=tk.LEFT, padx=(0, 10))

        # ── Centre: extracted preview ─────────────────────────────────────
        prev_lf = tk.LabelFrame(root, text=" Extracted Preview ", width=240)
        prev_lf.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 0))
        prev_lf.pack_propagate(False)

        self._prev_canvas = tk.Canvas(prev_lf, bg="#424242")
        self._prev_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ── Right: controls ───────────────────────────────────────────────
        ctrl = tk.Frame(root, width=215)
        ctrl.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 0))
        ctrl.pack_propagate(False)

        # Zoom
        tk.Label(ctrl, text="Zoom out", font=("Arial", 9, "bold")).pack(anchor="w")
        self._zoom_var = tk.DoubleVar(value=1.0)
        ttk.Scale(ctrl, from_=0.3, to=4.0, variable=self._zoom_var,
                  orient=tk.HORIZONTAL, command=self._on_change).pack(fill=tk.X)
        self._zoom_lbl = tk.Label(ctrl, text="  1.00×", anchor="w", font=("Arial", 8))
        self._zoom_lbl.pack(anchor="w", pady=(0, 8))

        # Brightness
        tk.Label(ctrl, text="Brightness", font=("Arial", 9, "bold")).pack(anchor="w")
        self._bright_var = tk.DoubleVar(value=1.0)
        ttk.Scale(ctrl, from_=0.2, to=2.5, variable=self._bright_var,
                  orient=tk.HORIZONTAL, command=self._on_change).pack(fill=tk.X)
        self._bright_lbl = tk.Label(ctrl, text="  1.00×", anchor="w", font=("Arial", 8))
        self._bright_lbl.pack(anchor="w", pady=(0, 8))

        # Contrast
        tk.Label(ctrl, text="Contrast", font=("Arial", 9, "bold")).pack(anchor="w")
        self._contrast_var = tk.DoubleVar(value=1.0)
        ttk.Scale(ctrl, from_=0.2, to=2.5, variable=self._contrast_var,
                  orient=tk.HORIZONTAL, command=self._on_change).pack(fill=tk.X)
        self._contrast_lbl = tk.Label(ctrl, text="  1.00×", anchor="w", font=("Arial", 8))
        self._contrast_lbl.pack(anchor="w", pady=(0, 8))

        # Shape
        tk.Label(ctrl, text="Output shape", font=("Arial", 9, "bold")).pack(anchor="w")
        self._shape_var = tk.StringVar(value="passport")
        shape_row = tk.Frame(ctrl)
        shape_row.pack(fill=tk.X, pady=(0, 8))
        for val, lbl in [("passport", "Passport"), ("circle", "Circle")]:
            tk.Radiobutton(shape_row, text=lbl, variable=self._shape_var,
                           value=val, command=self._on_change,
                           font=("Arial", 9)).pack(side=tk.LEFT)

        # Flip
        flip_row = tk.Frame(ctrl)
        flip_row.pack(fill=tk.X, pady=(0, 6))
        self._flip_h_var = tk.BooleanVar()
        self._flip_v_var = tk.BooleanVar()
        tk.Checkbutton(flip_row, text="Flip H", variable=self._flip_h_var,
                       command=self._on_change,
                       font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Checkbutton(flip_row, text="Flip V", variable=self._flip_v_var,
                       command=self._on_change,
                       font=("Arial", 9)).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Separator(ctrl).pack(fill=tk.X, pady=6)

        tk.Button(ctrl, text="Reset", command=self._reset,
                  bg="#F57C00", fg="white", relief=tk.FLAT,
                  pady=3).pack(fill=tk.X, pady=2)

        ttk.Separator(ctrl).pack(fill=tk.X, pady=8)

        tk.Label(ctrl,
                 text="Check every photo before saving:",
                 font=("Arial", 8), fg="#555", justify=tk.LEFT).pack(anchor="w")

        self._review_btn = tk.Button(
            ctrl, text="🖼  Review All Photos…",
            command=self._start_review,
            bg="#1565C0", fg="white", font=("Arial", 9, "bold"),
            relief=tk.FLAT, pady=6,
        )
        self._review_btn.pack(fill=tk.X, pady=(4, 4))

        self._apply_all_btn = tk.Button(
            ctrl, text="📋  Use These Settings for All",
            command=self._apply_settings_to_all,
            bg="#455A64", fg="white", font=("Arial", 9),
            relief=tk.FLAT, pady=5,
        )
        self._apply_all_btn.pack(fill=tk.X, pady=(0, 8))

        tk.Label(ctrl,
                 text="Save each photo with its own edited\n"
                      "settings (or the default, if untouched):",
                 font=("Arial", 8), fg="#555", justify=tk.LEFT).pack(anchor="w")

        self._apply_btn = tk.Button(
            ctrl, text="⟳  Apply to Folder…",
            command=self._apply_to_folder,
            bg="#00695C", fg="white", font=("Arial", 10, "bold"),
            relief=tk.FLAT, pady=8,
        )
        self._apply_btn.pack(fill=tk.X, pady=(6, 2))

        tk.Button(ctrl, text="✖  Close", command=self.destroy,
                  relief=tk.FLAT, pady=6).pack(fill=tk.X)

        # Progress (hidden until batch runs)
        self._prog_frame = tk.Frame(ctrl)
        self._prog_frame.pack(fill=tk.X, pady=(10, 0))
        self._prog_var = tk.DoubleVar()
        self._prog_bar = ttk.Progressbar(
            self._prog_frame, variable=self._prog_var, maximum=100)
        self._prog_bar.pack(fill=tk.X)
        self._prog_lbl = tk.Label(
            self._prog_frame, text="", font=("Arial", 7),
            fg="#555", wraplength=200, justify=tk.LEFT)
        self._prog_lbl.pack(anchor="w", pady=(2, 0))

        tk.Label(ctrl,
                 text="\nDrag centre = shift crop\nDrag edge = resize W or H\n"
                      "Drag corner = resize both\nScroll = zoom",
                 font=("Arial", 7), fg="#999", justify=tk.LEFT).pack(anchor="w")

    def _build_review_banner(self):
        b = self._review_banner
        self._review_lbl = tk.Label(b, text="", font=("Arial", 9, "bold"),
                                     bg="#FFF3E0", fg="#E65100")
        self._review_lbl.pack(side=tk.LEFT, padx=8, pady=4)
        tk.Button(b, text="◀ Prev", relief=tk.FLAT,
                  command=lambda: self._review_move(-1)).pack(side=tk.LEFT, padx=2, pady=4)
        tk.Button(b, text="Next ▶", relief=tk.FLAT,
                  command=lambda: self._review_move(1)).pack(side=tk.LEFT, padx=2, pady=4)
        tk.Button(b, text="🔲 Back to Grid", relief=tk.FLAT,
                  command=self._review_back_to_grid).pack(side=tk.LEFT, padx=(12, 2), pady=4)
        tk.Button(b, text="✖ Exit Review", relief=tk.FLAT,
                  command=self._exit_review).pack(side=tk.LEFT, padx=2, pady=4)

    # ──────────────────────────────────────────────────────── events ──────────

    def _bind_events(self):
        self._orig_canvas.bind("<Configure>",      lambda _: self._redraw())
        self._orig_canvas.bind("<ButtonPress-1>",  self._on_press)
        self._orig_canvas.bind("<B1-Motion>",      self._on_drag)
        self._orig_canvas.bind("<ButtonRelease-1>",self._on_release)
        self._orig_canvas.bind("<Motion>",         self._on_hover)
        self._orig_canvas.bind("<MouseWheel>",     self._on_scroll)   # Windows
        self._orig_canvas.bind("<Button-4>",       self._on_scroll)   # Linux up
        self._orig_canvas.bind("<Button-5>",       self._on_scroll)   # Linux down
        self._prev_canvas.bind("<Configure>",      lambda _: self._redraw_preview())

    _EDGE_MARGIN = 10   # screen px tolerance for grabbing an edge/corner handle

    _CURSORS = {
        "move":   "fleur",
        "left":   "sb_h_double_arrow",
        "right":  "sb_h_double_arrow",
        "top":    "sb_v_double_arrow",
        "bottom": "sb_v_double_arrow",
        "tl":     "size_nw_se",
        "br":     "size_nw_se",
        "tr":     "size_ne_sw",
        "bl":     "size_ne_sw",
    }

    def _hit_test(self, x: int, y: int) -> "str | None":
        """Return which handle of the crop box (screen coords x,y) is under the cursor."""
        if self._crop_bbox is None or self._orig_scale < 1e-6:
            return None
        x1, y1, x2, y2 = self._crop_bbox
        sx1 = x1 * self._orig_scale + self._orig_offset[0]
        sy1 = y1 * self._orig_scale + self._orig_offset[1]
        sx2 = x2 * self._orig_scale + self._orig_offset[0]
        sy2 = y2 * self._orig_scale + self._orig_offset[1]
        m = self._EDGE_MARGIN

        near_left   = abs(x - sx1) <= m
        near_right  = abs(x - sx2) <= m
        near_top    = abs(y - sy1) <= m
        near_bottom = abs(y - sy2) <= m
        inside_x = sx1 - m <= x <= sx2 + m
        inside_y = sy1 - m <= y <= sy2 + m

        if near_left and near_top and inside_x and inside_y:
            return "tl"
        if near_right and near_top and inside_x and inside_y:
            return "tr"
        if near_left and near_bottom and inside_x and inside_y:
            return "bl"
        if near_right and near_bottom and inside_x and inside_y:
            return "br"
        if near_left and sy1 <= y <= sy2:
            return "left"
        if near_right and sy1 <= y <= sy2:
            return "right"
        if near_top and sx1 <= x <= sx2:
            return "top"
        if near_bottom and sx1 <= x <= sx2:
            return "bottom"
        if sx1 < x < sx2 and sy1 < y < sy2:
            return "move"
        return None

    def _on_hover(self, event):
        if self._drag_start is not None:
            return   # cursor already locked to the active drag mode
        mode = self._hit_test(event.x, event.y)
        self._orig_canvas.config(cursor=self._CURSORS.get(mode, ""))

    def _on_press(self, event):
        self._drag_start = (event.x, event.y)
        self._drag_base   = (self._params["shift_x"], self._params["shift_y"])
        self._resize_base = (self._params["width_scale"], self._params["height_scale"])
        self._box_base    = self._crop_bbox
        self._drag_mode    = self._hit_test(event.x, event.y) or "move"
        self._orig_canvas.config(cursor=self._CURSORS.get(self._drag_mode, "fleur"))

    def _on_drag(self, event):
        if self._drag_start is None or self._crop_bbox is None or self._box_base is None:
            return
        if self._orig_scale < 1e-6:
            return

        dx_px = event.x - self._drag_start[0]
        dy_px = event.y - self._drag_start[1]
        dx_orig = dx_px / self._orig_scale
        dy_orig = dy_px / self._orig_scale

        x1, y1, x2, y2 = self._box_base
        half_w = max(1.0, (x2 - x1) / 2)
        half_h = max(1.0, (y2 - y1) / 2)
        base_ws, base_hs = self._resize_base
        mode = self._drag_mode

        if mode == "move":
            cw = max(1, x2 - x1)
            ch = max(1, y2 - y1)
            self._params["shift_x"] = self._drag_base[0] + dx_px / (cw * self._orig_scale)
            self._params["shift_y"] = self._drag_base[1] + dy_px / (ch * self._orig_scale)
            self._redraw()
            return

        # Resize: derive a new width/height scale from how far the grabbed
        # edge/corner moved, relative to the box size at drag-start.
        if "right" in mode or mode in ("tr", "br"):
            new_half_w = max(5.0, half_w + dx_orig)
            self._params["width_scale"] = max(0.2, min(4.0, base_ws * new_half_w / half_w))
        elif "left" in mode or mode in ("tl", "bl"):
            new_half_w = max(5.0, half_w - dx_orig)
            self._params["width_scale"] = max(0.2, min(4.0, base_ws * new_half_w / half_w))

        if "bottom" in mode or mode in ("bl", "br"):
            new_half_h = max(5.0, half_h + dy_orig)
            self._params["height_scale"] = max(0.2, min(4.0, base_hs * new_half_h / half_h))
        elif "top" in mode or mode in ("tl", "tr"):
            new_half_h = max(5.0, half_h - dy_orig)
            self._params["height_scale"] = max(0.2, min(4.0, base_hs * new_half_h / half_h))

        self._redraw()

    def _on_release(self, _event):
        self._drag_start = None
        self._drag_mode = None
        self._box_base = None

    def _on_scroll(self, event):
        if hasattr(event, "delta") and event.delta:
            # scroll up = zoom in on the face = less padding = lower zoom value
            factor = 0.9 if event.delta > 0 else 1.1
        else:
            factor = 0.9 if event.num == 4 else 1.1
        self._params["zoom"] = max(0.3, min(4.0, self._params["zoom"] * factor))
        self._zoom_var.set(self._params["zoom"])
        self._zoom_lbl.config(text=f"  {self._params['zoom']:.2f}×")
        self._redraw()

    def _on_change(self, _val=None):
        self._params["zoom"]       = self._zoom_var.get()
        self._params["brightness"] = self._bright_var.get()
        self._params["contrast"]   = self._contrast_var.get()
        self._params["shape"]      = self._shape_var.get()
        self._params["flip_h"]     = self._flip_h_var.get()
        self._params["flip_v"]     = self._flip_v_var.get()
        self._zoom_lbl.config(text=f"  {self._params['zoom']:.2f}×")
        self._bright_lbl.config(text=f"  {self._params['brightness']:.2f}×")
        self._contrast_lbl.config(text=f"  {self._params['contrast']:.2f}×")
        self._redraw()

    # ──────────────────────────────────────────────────────── drawing ─────────

    def _redraw(self):
        result, face_bbox, crop_bbox = extract_face_custom(
            self._photo, **self._params
        )
        self._face_bbox = face_bbox
        self._crop_bbox = crop_bbox
        self._extracted = result
        self._redraw_original()
        self._redraw_preview()

    def _redraw_original(self):
        cw = self._orig_canvas.winfo_width()
        ch = self._orig_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        pw, ph = self._photo.width, self._photo.height
        scale = min(cw / pw, ch / ph) * 0.97
        self._orig_scale = scale
        nw = int(pw * scale)
        nh = int(ph * scale)
        ox = (cw - nw) // 2
        oy = (ch - nh) // 2
        self._orig_offset = (ox, oy)

        # Base image
        base = self._photo.resize((nw, nh), Image.LANCZOS).convert("RGBA")

        # Dim the area outside the crop box
        if self._crop_bbox:
            x1, y1, x2, y2 = self._crop_bbox
            sx1, sy1 = int(x1 * scale), int(y1 * scale)
            sx2, sy2 = int(x2 * scale), int(y2 * scale)

            dim = Image.new("RGBA", (nw, nh), (0, 0, 0, 110))
            ImageDraw.Draw(dim).rectangle(
                [sx1, sy1, sx2, sy2], fill=(0, 0, 0, 0)
            )
            base = Image.alpha_composite(base, dim)

            draw = ImageDraw.Draw(base)
            # Green crop box
            for d in range(3):
                draw.rectangle(
                    [sx1 + d, sy1 + d, sx2 - d - 1, sy2 - d - 1],
                    outline="#69F0AE",
                )

        # Blue face detection box
        if self._face_bbox:
            draw = ImageDraw.Draw(base)
            fx1, fy1, fx2, fy2 = self._face_bbox
            sfx1 = int(fx1 * scale)
            sfy1 = int(fy1 * scale)
            sfx2 = int(fx2 * scale)
            sfy2 = int(fy2 * scale)
            for d in range(2):
                draw.rectangle(
                    [sfx1 + d, sfy1 + d, sfx2 - d - 1, sfy2 - d - 1],
                    outline="#4FC3F7",
                )

        self._orig_img_ref = ImageTk.PhotoImage(base.convert("RGB"))
        self._orig_canvas.delete("all")
        self._orig_canvas.create_image(ox, oy, anchor=tk.NW,
                                       image=self._orig_img_ref)

    def _redraw_preview(self):
        if self._extracted is None:
            return
        cw = self._prev_canvas.winfo_width()
        ch = self._prev_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        img = self._extracted.convert("RGBA")
        scale = min(cw / img.width, ch / img.height) * 0.95
        nw = max(1, int(img.width  * scale))
        nh = max(1, int(img.height * scale))
        scaled = img.resize((nw, nh), Image.LANCZOS)

        # Checkerboard background for transparency (circle shape)
        bg = Image.new("RGB", (cw, ch), "#424242")
        ox = (cw - nw) // 2
        oy = (ch - nh) // 2
        bg.paste(scaled.convert("RGB"), (ox, oy),
                 scaled.split()[3] if scaled.mode == "RGBA" else None)

        self._prev_img_ref = ImageTk.PhotoImage(bg)
        self._prev_canvas.delete("all")
        self._prev_canvas.create_image(0, 0, anchor=tk.NW, image=self._prev_img_ref)

    # ──────────────────────────────────────────────────────── actions ─────────

    def _reset(self):
        self._params.update(self._DEFAULT_PARAMS)
        self._zoom_var.set(1.0)
        self._bright_var.set(1.0)
        self._contrast_var.set(1.0)
        self._shape_var.set("passport")
        self._flip_h_var.set(False)
        self._flip_v_var.set(False)
        self._zoom_lbl.config(text="  1.00×")
        self._bright_lbl.config(text="  1.00×")
        self._contrast_lbl.config(text="  1.00×")
        self._redraw()

    # ───────────────────────────────────────────────────── review mode ───────

    def _params_for(self, fpath: "Path") -> dict:
        """Params that apply to *fpath*: its saved override, else the baseline."""
        override = self._overrides.get(str(fpath))
        return dict(override) if override else dict(self._base_params or self._params)

    def _sync_controls_from_params(self):
        self._zoom_var.set(self._params["zoom"])
        self._bright_var.set(self._params["brightness"])
        self._contrast_var.set(self._params["contrast"])
        self._shape_var.set(self._params["shape"])
        self._flip_h_var.set(self._params["flip_h"])
        self._flip_v_var.set(self._params["flip_v"])
        self._zoom_lbl.config(text=f"  {self._params['zoom']:.2f}×")
        self._bright_lbl.config(text=f"  {self._params['brightness']:.2f}×")
        self._contrast_lbl.config(text=f"  {self._params['contrast']:.2f}×")

    def _start_review(self):
        """Pick a folder and open the thumbnail grid so the user can verify
        every extracted photo, then click any one to fine-tune it."""
        if self._processing:
            return
        initial = str(Path(self._sample_path).parent)
        src = filedialog.askdirectory(title="Select Folder to Review", initialdir=initial)
        if not src:
            return
        src_path = Path(src)
        files = sorted(
            f for f in src_path.iterdir()
            if f.is_file() and f.suffix.lower() in self._IMG_EXTS
        )
        if not files:
            messagebox.showinfo("No Images",
                                f"No image files found in:\n{src}", parent=self)
            return

        self._review_src_dir = src_path
        # The sample photo currently on screen keeps whatever tuning it has
        # — saved as its own override — but that tuning must NOT leak onto
        # every other photo. Everyone else starts from neutral defaults
        # until individually edited or "Use These Settings for All" is used.
        if dict(self._params) != self._DEFAULT_PARAMS:
            self._overrides[self._sample_path] = dict(self._params)
        if self._base_params is None:
            self._base_params = dict(self._DEFAULT_PARAMS)
        self._review_files = files
        _ReviewGridDialog(self, files)

    def _apply_settings_to_all(self):
        """Make the currently-open photo's tuning the default for every
        photo that hasn't been individually customised."""
        if not messagebox.askyesno(
            "Use for All Photos",
            "Use this photo's current crop / zoom / brightness / shape "
            "settings as the default for every photo that hasn't been "
            "individually edited?\n\n"
            "Photos you've already customised one-by-one will keep their "
            "own settings.",
            parent=self,
        ):
            return
        self._base_params = dict(self._params)
        messagebox.showinfo(
            "Applied",
            "These settings are now the default for every un-edited photo.",
            parent=self,
        )

    def _open_for_edit(self, files: "list[Path]", idx: int):
        """Load photo *idx* from *files* into the main editor for individual tuning."""
        self._review_files = files
        self._review_index = idx
        fpath = files[idx]
        try:
            self._photo = Image.open(fpath).convert("RGB")
        except Exception as exc:
            messagebox.showerror("Cannot Open Photo", str(exc), parent=self)
            return

        self._sample_path = str(fpath)
        self.title(f"Face Extraction Editor — {fpath.name}")

        self._params = self._params_for(fpath)
        self._sync_controls_from_params()

        self._review_banner.pack(side=tk.TOP, fill=tk.X, before=self._root_frame)
        self._update_review_label()
        self._redraw()

    def _update_review_label(self):
        n = len(self._review_files)
        i = self._review_index + 1
        name = Path(self._sample_path).name
        self._review_lbl.config(text=f"Reviewing {i}/{n} — {name}")

    def _review_move(self, delta: int):
        if not self._review_files or self._review_index < 0:
            return
        # Persist any edits made to the current photo before moving on
        self._overrides[self._sample_path] = dict(self._params)
        new_idx = self._review_index + delta
        if new_idx < 0 or new_idx >= len(self._review_files):
            messagebox.showinfo(
                "Review",
                "Already at the " + ("first" if new_idx < 0 else "last") + " photo.",
                parent=self,
            )
            return
        self._open_for_edit(self._review_files, new_idx)

    def _review_back_to_grid(self):
        if self._review_files and self._review_index >= 0:
            self._overrides[self._sample_path] = dict(self._params)
        _ReviewGridDialog(self, self._review_files)

    def _exit_review(self):
        if self._review_files and self._review_index >= 0:
            self._overrides[self._sample_path] = dict(self._params)
        self._review_banner.pack_forget()
        self._review_index = -1

    def _apply_to_folder(self):
        if self._processing:
            return

        # If the user mid-edited a photo in review mode, save it first.
        if self._review_files and self._review_index >= 0:
            self._overrides[self._sample_path] = dict(self._params)

        initial = str(self._review_src_dir) if self._review_src_dir else None
        src = filedialog.askdirectory(title="Select Source Photo Folder", initialdir=initial)
        if not src:
            return

        src_path    = Path(src)
        default_out = src_path.parent / (src_path.name + "_faces")
        out = filedialog.askdirectory(
            title=f"Select Output Folder  (default: {default_out})")
        if not out:
            out = str(default_out)

        files = sorted(
            f for f in src_path.iterdir()
            if f.is_file() and f.suffix.lower() in self._IMG_EXTS
        )
        if not files:
            messagebox.showinfo("No Images",
                                f"No image files found in:\n{src}", parent=self)
            return

        os.makedirs(out, exist_ok=True)
        # Per-photo overrides (from review mode) take precedence; everything
        # else falls back to the current/base settings.
        base_params = dict(self._base_params or self._params)
        overrides   = dict(self._overrides)

        self._processing = True
        self._apply_btn.config(state=tk.DISABLED, text="Processing…")
        self._prog_var.set(0)
        self._prog_lbl.config(text="Starting…")
        total = len(files)

        def _update(i: int, name: str):
            pct = i / total * 100
            self._prog_var.set(pct)
            self._prog_lbl.config(text=f"{i}/{total}  {name}")

        def _finish(ok: int, skip: int, err: int):
            self._processing = False
            self._apply_btn.config(state=tk.NORMAL, text="⟳  Apply to Folder…")
            self._prog_var.set(100)
            self._prog_lbl.config(text=f"Done — {ok} saved, {skip} no-face, {err} errors")
            messagebox.showinfo(
                "Extraction Complete",
                f"Faces extracted and saved\n\n"
                f"  Faces found  : {ok}\n"
                f"  No face (saved as-is) : {skip}\n"
                f"  Errors       : {err}\n\n"
                f"Output folder:\n{out}",
                parent=self,
            )

        def run():
            ok = skip = err = 0
            for i, fpath in enumerate(files, 1):
                self.after(0, lambda i=i, n=fpath.name: _update(i, n))
                try:
                    params = overrides.get(str(fpath), base_params)
                    ext    = ".png" if params["shape"] == "circle" else ".jpg"
                    img = Image.open(fpath).convert("RGB")
                    result, _, crop_bbox = extract_face_custom(img, **params)
                    dest = os.path.join(out, fpath.stem + ext)
                    if params["shape"] == "circle":
                        result.convert("RGBA").save(dest, "PNG")
                    else:
                        result.convert("RGB").save(dest, "JPEG", quality=95)
                    if crop_bbox is None:
                        skip += 1
                    else:
                        ok += 1
                except Exception as exc:
                    print(f"[face extract] {fpath.name}: {exc}")
                    err += 1

            self.after(0, lambda: _finish(ok, skip, err))

        threading.Thread(target=run, daemon=True).start()


class _ReviewGridDialog(tk.Toplevel):
    """
    Modal thumbnail grid of every photo in a folder, rendered with its
    current (override or baseline) extraction settings, so the user can
    verify all results at a glance. Click any thumbnail to drop into the
    main editor and fine-tune that one photo.
    """

    _COLS  = 6
    _THUMB = 130

    def __init__(self, editor: "FaceExtractEditorDialog", files: "list[Path]"):
        super().__init__(editor)
        self._editor = editor
        self._files  = files

        self.title(f"Review {len(files)} Photos")
        self.geometry("980x680")
        self.minsize(640, 420)

        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(top,
                 text="Click any photo to edit it individually. "
                      "Orange outline = already customised.",
                 font=("Arial", 9), fg="#555", anchor="w").pack(anchor="w")
        self._status_lbl = tk.Label(top, text="", font=("Arial", 8), fg="#888")
        self._status_lbl.pack(anchor="w")

        body = tk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._canvas = tk.Canvas(body, bg="#333", highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._grid_frame = tk.Frame(self._canvas, bg="#333")
        self._grid_win = self._canvas.create_window((0, 0), window=self._grid_frame, anchor="nw")
        self._grid_frame.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._grid_win, width=e.width),
        )
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-4>", self._on_wheel)
        self._canvas.bind("<Button-5>", self._on_wheel)

        bottom = tk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=8)
        tk.Button(bottom, text="✖  Close", command=self.destroy,
                  relief=tk.FLAT, pady=4).pack(side=tk.RIGHT)

        self._img_refs: list = []   # keep PhotoImage refs alive

        self.transient(editor)
        self.grab_set()
        self.after(50, self._build_thumbnails)

    def _on_wheel(self, event):
        if hasattr(event, "delta") and event.delta:
            self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        else:
            self._canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

    def _build_thumbnails(self):
        total = len(self._files)
        self._status_lbl.config(text=f"Building previews… 0/{total}")

        def worker():
            for i, fpath in enumerate(self._files):
                params = self._editor._params_for(fpath)
                try:
                    img = Image.open(fpath).convert("RGB")
                    result, _, _ = extract_face_custom(img, **params)
                    thumb = result.convert("RGBA")
                    thumb.thumbnail((self._THUMB, self._THUMB), Image.LANCZOS)
                except Exception:
                    thumb = Image.new("RGBA", (self._THUMB, self._THUMB), "#555")
                self.after(0, lambda i=i, fpath=fpath, thumb=thumb:
                           self._add_cell(i, fpath, thumb, total))

        threading.Thread(target=worker, daemon=True).start()

    def _add_cell(self, idx: int, fpath: "Path", thumb: Image.Image, total: int):
        if not self.winfo_exists():
            return
        row, col = divmod(idx, self._COLS)
        is_override = str(fpath) in self._editor._overrides
        cell = tk.Frame(self._grid_frame, bg="#FF9800" if is_override else "#666",
                         padx=2, pady=2, cursor="hand2")
        cell.grid(row=row, column=col, padx=6, pady=6)

        photo_img = ImageTk.PhotoImage(thumb)
        self._img_refs.append(photo_img)

        inner = tk.Frame(cell, bg="#222")
        inner.pack()
        img_lbl = tk.Label(inner, image=photo_img, bg="#222", cursor="hand2")
        img_lbl.pack()
        name_lbl = tk.Label(inner, text=fpath.name, font=("Arial", 7),
                             fg="#ddd", bg="#222", wraplength=self._THUMB)
        name_lbl.pack()

        def _open(_e=None, idx=idx):
            self._editor._open_for_edit(self._files, idx)
            self.destroy()

        for widget in (cell, inner, img_lbl, name_lbl):
            widget.bind("<Button-1>", _open)

        done = idx + 1
        self._status_lbl.config(
            text=f"Building previews… {done}/{total}" if done < total
                 else f"{total} photos — click one to edit individually"
        )
