# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Install dependencies
pip install -r requirements.txt

# Run the application
.\run.ps1
# OR
python app.py
```

`run.ps1` sets `TCL_LIBRARY` and `TK_LIBRARY` environment variables required for tkinter to work correctly in the virtualenv on Windows. Always use it (or replicate those env vars) when running the app.

There are no tests or linting configuration in this project.

## Architecture

Three main modules cooperate to produce a tkinter desktop app for generating student ID cards from an Excel sheet and a template image.

### `card_generator.py` — Core Logic
`CardGenerator` is the processing engine. It is UI-agnostic and owns all image/data operations:
- Loads Excel via `pandas` + `openpyxl`; loads template images via `Pillow`
- Auto-detects text field positions with Tesseract OCR (`auto_detect_fields`, `auto_detect_from_mapping_template`)
- Auto-detects circular or rectangular photo regions via OpenCV contour analysis and `HoughCircles` (`detect_photo_region`)
- Composites a single card (`generate_card`): places text fields and a cropped/masked photo onto the template
- Batch-generates all student cards to JPG (`generate_all`)
- Creates A4 print sheets at configurable DPI (`create_print_sheet`)

Photo pipeline: `extract_face` (Haar cascade) → `apply_photo_transform` (user pan/zoom/rotate) → `fit_photo_to_circle` (resize + circular mask).

### `app.py` — GUI (tkinter)
`IDCardApp` is the main window. Layout: left panel = searchable student list, right panel = card preview canvas. Key dialogs:
- `ColumnMapDialog` — maps Excel columns to card roles (name, class, photo path, DOB, blood group, etc.)
- `FieldConfigDialog` — click-to-position editor where the user clicks the template image to place each text field and photo region
- `PrintSheetDialog` — DPI and cards-per-row settings for batch print sheets

Typical user workflow: Load Excel → confirm column mappings → load template → configure field positions → optionally edit per-student photos → generate cards.

### `photo_editor.py` — Interactive Photo Editor
`PhotoEditorDialog` is a modal dialog for per-student photo adjustment (drag to pan, scroll to zoom, slider to rotate). Persists transform as `{x, y, scale, rotation}` back to the caller.

### `config/default_config.json`
Default configuration for ICC Middle School. Contains `column_map`, `photo_column`, `photo_region` (position + shape), and `fields` (array of text field definitions with position, font, color, alignment, and optional text transforms). Loaded as the starting config for new sessions.
