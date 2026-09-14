# XPZ Image Extractor

A Windows desktop tool for inspecting image assets in supported original Xbox XPZ/XPR containers. Select individual files or a folder, queue a batch, and export textures as PNGs with transparency.

Built for game-development research, interface asset inspection, and preservation workflows. It extracts the images used by a menu; it does **not** reconstruct menu layouts, positioning, scripts, or behavior.

## Download and run

**[Download the latest Windows release](https://github.com/JonAlexInc/xpz-image-extractor/releases/latest).**

1. Download and unpack `XPZ-Image-Extractor-Windows-x64.zip`.
2. Double-click **XPZ Image Extractor.exe**.
3. Choose **Add files…** for one or more files, or **Add folder…** for a batch. Use **Include subfolders** to search nested folders.
4. Use **Browse…** to choose the output location.
5. Click **Extract all queued files**, then **Open output folder**.

The Windows x64 executable includes Python, Tk, Pillow, and the required runtime components. Python and Codex do not need to be installed separately. No administrator access or network connection is required by the app. The initial release is unsigned.

Each extraction run creates a new dated folder with a separate subfolder for each input. Duplicate filenames from different locations remain separate. Source files and previous extraction runs are not overwritten.

## Features

- File picker with multiple selection and a folder picker with optional recursion.
- Batch queue, progress display, and cancellation between textures or files.
- PNG export preserving decoded dimensions and alpha transparency.
- Per-file reports with dimensions, formats, skipped resources, and source SHA-256; a batch report summarizes the run.
- Unsupported files do not stop the remaining batch.
- No uploads, telemetry, game downloads, or bundled game assets.

## Format support

**The `.xpz` extension is not a universal format.** This tool identifies supported Xbox resource structures by their file headers. Other games may use different containers, compression, resource tables, or texture formats with the same extension.

| Area | Implemented support |
| --- | --- |
| Containers | XPR1 named-resource tables with offsets relative to byte 12; single-texture XPR0 |
| Payloads | zlib-compressed or uncompressed |
| Block-compressed textures | DXT1, DXT3, DXT5 |
| Common linear/swizzled textures | ARGB8888, XRGB8888, ABGR8888, RGB565, ARGB1555, XRGB1555, ARGB4444, L8, A8, A8L8 |
| Export | 2D PNG, largest mip level only |
| Limits | 256 MB input/expanded payload; 4096 pixels per axis |

Not implemented: cube maps, volume textures, palette-based textures, multi-resource XPR0 variants, other compression schemes, unrelated XPZ formats, or menu layout reconstruction. DXT2/4 cannot be distinguished from the corresponding DXT3/5 Xbox format identifiers; premultiplied-alpha correction is not applied.

### Texture row layout

Keep **Auto** selected initially. Some games store tightly packed pixel rows while others include GPU row padding. If the report says the layout is ambiguous, retry with **Tight rows** or **GPU pitch**. The wrong manual choice may distort an image; previous runs remain available for comparison.

## Validation and current limits

The initial real-file test used one `meter_files.xpz` sample containing ten textures. All ten exported PNGs matched a previously visually verified extraction pixel for pixel, including transparency. No game sample or extracted images are included here.

Synthetic tests cover additional formats, arbitrary resource names, path-safe filenames, rectangular swizzling, row padding, truncated data, cancellation, and bulk extraction with duplicate filenames and a failed input. These tests do not establish compatibility with every game.

The release executable initialized its bundled GUI and extracted the sample from a separate folder with Python-related environment settings removed. It has not been tested on a separate clean Windows machine. Windows x64 is the supported release target.

## Run from source

Use Python 3.12 with Tkinter available (included with the usual Windows Python installer).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe xpz_app.py
```

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_extractor
```

An optional local regression test uses `XPZ_TEST_SAMPLE` and `XPZ_TEST_REFERENCE` environment variables for the original ten-texture sample and its reference PNG folder. Without them, that test is skipped; the synthetic tests run normally.

## Build a standalone executable

On Windows x64 with Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --noupx --name "XPZ Image Extractor" xpz_app.py
```

The result is `dist/XPZ Image Extractor.exe`. For redistribution, include `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `third_party_licenses/` alongside it. Re-check bundled dependency notices if changing runtime or dependency versions. The repository's Windows workflow also tests and packages a downloadable build artifact.

## Reporting unsupported files

Open an issue with the game/platform, the error from `report.json`, expected asset type, and a small header description if available. Avoid uploading full game archives, copyrighted image packs, or private local paths. A report helps identify the next format to support; support is not guaranteed from an extension alone.

## License and references

New application code is released under the [MIT License](LICENSE). Bundled components retain their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).

See [development references](DEVELOPMENT.md) for the source material consulted during investigation. Neither XboxToolkit nor XPRXpress is bundled. This is an independent project maintained by JonAlexInc, not an official Xbox or Microsoft product.
