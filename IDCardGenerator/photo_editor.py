"""
Interactive photo editor dialog.

Shows the full card template with the photo region highlighted.
The user can pan (drag), zoom (scroll wheel), and rotate (slider)
the student photo within the masked region — like cropping in Photoshop.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageTk

from card_generator import apply_photo_transform


class PhotoEditorDialog(tk.Toplevel):
    """
    Modal dialog for editing one student's photo placement.

    Result: transform dict {x, y, scale, rotation} if accepted, else None.
    """

    def __init__(
        self,
        parent: tk.Widget,
        template_image: Image.Image,
        photo_region: dict,
        photo_path: str | None = None,
        initial_transform: dict | None = None,
        student_name: str = "",
    ):
        super().__init__(parent)
        self.title(f"Photo Editor — {student_name or 'Student'}")
        self.resizable(True, True)
        self.minsize(800, 560)

        self._template = template_image
        self._region = photo_region
        self._photo: Image.Image | None = None
        self.result: dict | None = None
        self.apply_to_all: bool = False   # set True when user clicks "Apply to All"

        # Transform state (in template pixel space)
        if initial_transform:
            self._tfm = dict(initial_transform)
            self._tfm.setdefault("brightness", 1.0)
            self._tfm.setdefault("contrast",   1.0)
            self._tfm.setdefault("flip_h",     False)
            self._tfm.setdefault("flip_v",     False)
        else:
            self._tfm = {
                "x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0,
                "brightness": 1.0, "contrast": 1.0, "flip_h": False, "flip_v": False,
            }
        # bg_fill is stored separately from _tfm so sliders don't include it
        self._initial_bg = bool(initial_transform.get("bg_color")) if initial_transform else False

        # Canvas display info
        self._display_scale: float = 1.0
        self._canvas_offset: tuple[int, int] = (0, 0)  # top-left of template on canvas
        self._drag_start: tuple[int, int] | None = None
        self._drag_base: tuple[float, float] = (0.0, 0.0)
        self._canvas_img = None  # hold reference to prevent GC

        self._build_ui()
        self._bind_events()

        if photo_path:
            self._load_photo_from_path(photo_path)

        # Deferred first draw (canvas size not known until shown)
        self.after(100, self._redraw)

        self.transient(parent)
        self.grab_set()
        self.wait_window()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.geometry("1100x720")

        root_frame = tk.Frame(self)
        root_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ── Left: canvas ──────────────────────────────────────────────────
        canvas_frame = tk.LabelFrame(
            root_frame, text=" Card Preview — drag photo to position "
        )
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(canvas_frame, bg="#555", cursor="fleur")
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ── Right: controls ───────────────────────────────────────────────
        ctrl = tk.Frame(root_frame, width=220)
        ctrl.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        ctrl.pack_propagate(False)

        tk.Button(
            ctrl, text="📂  Load Photo",
            command=self._browse_photo,
            bg="#1976D2", fg="white", font=("Arial", 10, "bold"),
            relief=tk.FLAT, pady=6,
        ).pack(fill=tk.X, pady=(0, 8))

        # ── Pan / Zoom / Rotate ──────────────────────────────────────────
        adj = tk.LabelFrame(ctrl, text=" Adjust ", font=("Arial", 8, "bold"))
        adj.pack(fill=tk.X, pady=(0, 6))

        tk.Label(adj, text="Zoom", font=("Arial", 8, "bold")).pack(anchor="w", padx=4)
        self._scale_var = tk.DoubleVar(value=self._tfm["scale"])
        self._scale_slider = ttk.Scale(
            adj, from_=0.05, to=8.0, variable=self._scale_var,
            orient=tk.HORIZONTAL, command=self._on_slider_change,
        )
        self._scale_slider.pack(fill=tk.X, padx=4)
        self._scale_lbl = tk.Label(adj, text=self._fmt_scale(), anchor="w", font=("Arial", 8))
        self._scale_lbl.pack(anchor="w", padx=4, pady=(0, 4))

        tk.Label(adj, text="Rotation", font=("Arial", 8, "bold")).pack(anchor="w", padx=4)
        self._rot_var = tk.DoubleVar(value=self._tfm["rotation"])
        self._rot_slider = ttk.Scale(
            adj, from_=-180, to=180, variable=self._rot_var,
            orient=tk.HORIZONTAL, command=self._on_slider_change,
        )
        self._rot_slider.pack(fill=tk.X, padx=4)
        self._rot_lbl = tk.Label(adj, text=self._fmt_rot(), anchor="w", font=("Arial", 8))
        self._rot_lbl.pack(anchor="w", padx=4, pady=(0, 4))

        tk.Label(adj, text="Pan offset", font=("Arial", 8, "bold")).pack(anchor="w", padx=4)
        self._pos_lbl = tk.Label(adj, text=self._fmt_pos(), anchor="w", font=("Arial", 8))
        self._pos_lbl.pack(anchor="w", padx=4, pady=(0, 4))

        # ── Brightness / Contrast / Flip ─────────────────────────────────
        enhance = tk.LabelFrame(ctrl, text=" Enhance ", font=("Arial", 8, "bold"))
        enhance.pack(fill=tk.X, pady=(0, 6))

        tk.Label(enhance, text="Brightness", font=("Arial", 8, "bold")).pack(anchor="w", padx=4)
        self._bright_var = tk.DoubleVar(value=self._tfm.get("brightness", 1.0))
        ttk.Scale(
            enhance, from_=0.2, to=2.5, variable=self._bright_var,
            orient=tk.HORIZONTAL, command=self._on_slider_change,
        ).pack(fill=tk.X, padx=4)
        self._bright_lbl = tk.Label(enhance, text=self._fmt_bright(), anchor="w", font=("Arial", 8))
        self._bright_lbl.pack(anchor="w", padx=4, pady=(0, 4))

        tk.Label(enhance, text="Contrast", font=("Arial", 8, "bold")).pack(anchor="w", padx=4)
        self._contrast_var = tk.DoubleVar(value=self._tfm.get("contrast", 1.0))
        ttk.Scale(
            enhance, from_=0.2, to=2.5, variable=self._contrast_var,
            orient=tk.HORIZONTAL, command=self._on_slider_change,
        ).pack(fill=tk.X, padx=4)
        self._contrast_lbl = tk.Label(enhance, text=self._fmt_contrast(), anchor="w", font=("Arial", 8))
        self._contrast_lbl.pack(anchor="w", padx=4, pady=(0, 4))

        flip_row = tk.Frame(enhance)
        flip_row.pack(fill=tk.X, padx=4, pady=(0, 4))
        self._flip_h_var = tk.BooleanVar(value=bool(self._tfm.get("flip_h", False)))
        self._flip_v_var = tk.BooleanVar(value=bool(self._tfm.get("flip_v", False)))
        tk.Checkbutton(
            flip_row, text="Flip H", variable=self._flip_h_var,
            command=self._on_flip_change, font=("Arial", 8),
        ).pack(side=tk.LEFT)
        tk.Checkbutton(
            flip_row, text="Flip V", variable=self._flip_v_var,
            command=self._on_flip_change, font=("Arial", 8),
        ).pack(side=tk.LEFT, padx=(6, 0))

        # ── Quick actions ─────────────────────────────────────────────────
        ttk.Separator(ctrl).pack(fill=tk.X, pady=4)

        row1 = tk.Frame(ctrl)
        row1.pack(fill=tk.X, pady=2)
        tk.Button(row1, text="Cover", command=self._fit_cover,
                  bg="#43A047", fg="white", relief=tk.FLAT, pady=3,
                  font=("Arial", 8)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(row1, text="Fit Full", command=self._fit_contain,
                  bg="#7B1FA2", fg="white", relief=tk.FLAT, pady=3,
                  font=("Arial", 8)).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(ctrl, text="Reset All", command=self._reset,
                  bg="#F57C00", fg="white", relief=tk.FLAT, pady=3,
                  font=("Arial", 8)).pack(fill=tk.X, pady=2)

        bg_row = tk.Frame(ctrl)
        bg_row.pack(fill=tk.X, pady=(2, 0))
        self._bg_var = tk.BooleanVar(value=self._initial_bg)
        tk.Checkbutton(
            bg_row, text="White background fill",
            variable=self._bg_var, command=self._redraw,
            font=("Arial", 8),
        ).pack(anchor="w")

        # ── Hint ─────────────────────────────────────────────────────────
        tk.Label(
            ctrl,
            text="Drag=pan  Scroll=zoom  Green=region",
            justify=tk.LEFT, fg="#777", font=("Arial", 7),
        ).pack(anchor="w", pady=(4, 0))

        ttk.Separator(ctrl).pack(fill=tk.X, pady=6)

        tk.Button(
            ctrl, text="✔  Accept",
            command=self._accept,
            bg="#388E3C", fg="white", font=("Arial", 11, "bold"),
            relief=tk.FLAT, pady=8,
        ).pack(fill=tk.X, pady=2)
        tk.Button(
            ctrl, text="⟳  Apply to All Students",
            command=self._accept_all,
            bg="#0277BD", fg="white", font=("Arial", 9, "bold"),
            relief=tk.FLAT, pady=6,
        ).pack(fill=tk.X, pady=2)
        tk.Button(
            ctrl, text="✖  Cancel",
            command=self.destroy,
            relief=tk.FLAT, pady=6,
        ).pack(fill=tk.X)

    # --------------------------------------------------------------- events

    def _bind_events(self):
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<MouseWheel>", self._on_scroll)  # Windows
        self._canvas.bind("<Button-4>", self._on_scroll)   # Linux scroll up
        self._canvas.bind("<Button-5>", self._on_scroll)   # Linux scroll down
        self._canvas.bind("<Configure>", lambda _: self._redraw())

    def _on_press(self, event):
        self._drag_start = (event.x, event.y)
        self._drag_base = (self._tfm["x"], self._tfm["y"])

    def _on_drag(self, event):
        if self._drag_start is None:
            return
        dx = (event.x - self._drag_start[0]) / self._display_scale
        dy = (event.y - self._drag_start[1]) / self._display_scale
        self._tfm["x"] = self._drag_base[0] + dx
        self._tfm["y"] = self._drag_base[1] + dy
        self._pos_lbl.config(text=self._fmt_pos())
        self._redraw()

    def _on_release(self, _event):
        self._drag_start = None

    def _on_scroll(self, event):
        # Windows uses event.delta; Linux uses event.num
        if hasattr(event, "delta") and event.delta:
            factor = 1.1 if event.delta > 0 else 0.9
        else:
            factor = 1.1 if event.num == 4 else 0.9
        self._tfm["scale"] = max(0.05, min(8.0, self._tfm["scale"] * factor))
        self._scale_var.set(self._tfm["scale"])
        self._scale_lbl.config(text=self._fmt_scale())
        self._redraw()

    def _on_slider_change(self, _val=None):
        self._tfm["scale"]      = self._scale_var.get()
        self._tfm["rotation"]   = self._rot_var.get()
        self._tfm["brightness"] = self._bright_var.get()
        self._tfm["contrast"]   = self._contrast_var.get()
        self._scale_lbl.config(text=self._fmt_scale())
        self._rot_lbl.config(text=self._fmt_rot())
        self._bright_lbl.config(text=self._fmt_bright())
        self._contrast_lbl.config(text=self._fmt_contrast())
        self._redraw()

    def _on_flip_change(self):
        self._tfm["flip_h"] = self._flip_h_var.get()
        self._tfm["flip_v"] = self._flip_v_var.get()
        self._redraw()

    # --------------------------------------------------------------- actions

    def _browse_photo(self):
        path = filedialog.askopenfilename(
            title="Select Student Photo",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._load_photo_from_path(path)

    def _load_photo_from_path(self, path: str):
        try:
            self._photo = Image.open(path).convert("RGBA")
            self._fit_cover()
        except Exception as exc:
            messagebox.showerror("Error", f"Cannot load photo:\n{exc}", parent=self)

    def _fit_cover(self):
        """Scale photo so it covers the region; reset pan/rotation."""
        if self._photo is None:
            return
        self._tfm.update(x=0.0, y=0.0, scale=1.0, rotation=0.0)
        self._sync_sliders()
        self._redraw()

    def _fit_contain(self):
        """Scale photo so it fits entirely within the region."""
        if self._photo is None:
            return
        rw, rh = self._region["width"], self._region["height"]
        cover_scale = max(rw / self._photo.width, rh / self._photo.height)
        contain_scale = min(rw / self._photo.width, rh / self._photo.height)
        # user_scale is a multiplier on cover_scale; adjust accordingly
        ratio = contain_scale / cover_scale
        self._tfm.update(x=0.0, y=0.0, scale=ratio, rotation=0.0)
        self._sync_sliders()
        self._redraw()

    def _reset(self):
        self._tfm = {
            "x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0,
            "brightness": 1.0, "contrast": 1.0, "flip_h": False, "flip_v": False,
        }
        self._flip_h_var.set(False)
        self._flip_v_var.set(False)
        self._sync_sliders()
        self._redraw()

    def _accept(self):
        self.result = dict(self._tfm)
        if self._bg_var.get():
            self.result["bg_color"] = [255, 255, 255]
        else:
            self.result.pop("bg_color", None)
        self.destroy()

    def _accept_all(self):
        """Save transform and signal the caller to apply it to every student."""
        self.result = dict(self._tfm)
        if self._bg_var.get():
            self.result["bg_color"] = [255, 255, 255]
        else:
            self.result.pop("bg_color", None)
        self.apply_to_all = True
        self.destroy()

    # --------------------------------------------------------------- drawing

    def _redraw(self):
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Compose card preview
        preview = self._compose()

        # Scale to fit canvas
        scale = min(cw / preview.width, ch / preview.height) * 0.97
        self._display_scale = scale
        pw, ph = int(preview.width * scale), int(preview.height * scale)
        scaled = preview.resize((pw, ph), Image.LANCZOS)

        ox = (cw - pw) // 2
        oy = (ch - ph) // 2
        self._canvas_offset = (ox, oy)

        self._canvas_img = ImageTk.PhotoImage(scaled)
        self._canvas.delete("all")
        self._canvas.create_image(ox, oy, anchor=tk.NW, image=self._canvas_img)

    def _compose(self) -> Image.Image:
        card = self._template.copy().convert("RGBA")

        region = self._region
        if self._photo is not None:
            bg = (255, 255, 255) if self._bg_var.get() else None
            composed = apply_photo_transform(self._photo, region, self._tfm, bg_color=bg)
            card.paste(composed, (region["x"], region["y"]), composed)

        # Draw green outline around the photo region
        draw = ImageDraw.Draw(card)
        rx, ry = region["x"], region["y"]
        rw, rh = region["width"], region["height"]
        outline_color = "#00E676"

        if region.get("shape") == "circle":
            for d in range(0, 5, 2):
                draw.ellipse(
                    [rx + d, ry + d, rx + rw - d - 1, ry + rh - d - 1],
                    outline=outline_color,
                )
        else:
            draw.rectangle([rx, ry, rx + rw - 1, ry + rh - 1], outline=outline_color, width=3)

        return card

    # ------------------------------------------------------------ helpers

    def _sync_sliders(self):
        self._scale_var.set(self._tfm["scale"])
        self._rot_var.set(self._tfm["rotation"])
        self._bright_var.set(self._tfm.get("brightness", 1.0))
        self._contrast_var.set(self._tfm.get("contrast", 1.0))
        self._flip_h_var.set(bool(self._tfm.get("flip_h", False)))
        self._flip_v_var.set(bool(self._tfm.get("flip_v", False)))
        self._scale_lbl.config(text=self._fmt_scale())
        self._rot_lbl.config(text=self._fmt_rot())
        self._bright_lbl.config(text=self._fmt_bright())
        self._contrast_lbl.config(text=self._fmt_contrast())
        self._pos_lbl.config(text=self._fmt_pos())

    def _fmt_scale(self) -> str:
        return f"  {self._tfm.get('scale', 1.0):.2f}×"

    def _fmt_rot(self) -> str:
        return f"  {self._tfm.get('rotation', 0.0):.1f}°"

    def _fmt_pos(self) -> str:
        return f"  x={self._tfm.get('x', 0):.0f}  y={self._tfm.get('y', 0):.0f}"

    def _fmt_bright(self) -> str:
        return f"  {self._tfm.get('brightness', 1.0):.2f}×"

    def _fmt_contrast(self) -> str:
        return f"  {self._tfm.get('contrast', 1.0):.2f}×"
