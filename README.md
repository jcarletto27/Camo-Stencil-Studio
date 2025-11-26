# Camo Stencil Studio v2.0

**Camo Stencil Studio** is a professional-grade desktop application designed to bridge the gap between 2D image processing and physical fabrication. It converts standard photographs or reference images into multi-layer camouflage patterns, vector stencils for vinyl cutters, and robust 3D models for printing.

**Version 2.0** introduces a fully persistent workspace, advanced 3D geometry processing (auto-bridging), and a project management system.

##  New in v2.0
* **Project Files (`.json`):** Save your work—including the source image, palette, and layer mappings—and resume exactly where you left off.
* **Smart Memory:** The app now remembers your global settings (Denoise strength, Dimensions, etc.) and your last opened folder between sessions.
* **3D Auto-Bridging:** Automatically detects "floating islands" (e.g., the center of a donut shape) in stencil mode and cuts structural bridges to anchor them to the frame.
* **Stability:** Fixed JSON serialization crashes and optimized thread handling.

## Key Features

###  Workspace & Management
* **Persistent Configuration:** Set your preferred export units, smoothing levels, and bridge widths once; the app remembers them automatically.
* **New Project Workflow:** Dedicated controls to clear the workspace or load previous projects instantly.
* **Center-Stage UI:** Clean interface with a drag-and-drop style "Open Image" workflow and tabbed result previews.

###  Color & Layering
* **YOLO Mode (Auto-Scan):** One-click analysis that detects dominant colors, sorts them by visual similarity (brightness/hue), and assigns layer numbers automatically.
* **Hybrid Selection:** Combine auto-detection with manual color picking by clicking anywhere on the canvas.
* **Bulk Assignment:** Select multiple color swatches via checkboxes and assign them to a single output layer in one click.
* **Orphan Detection:** Optional mode to capture background "white space" or unassigned pixels to ensure 100% surface coverage.

###  Processing Engine
* **Smart Denoising:** Configurable Gaussian blur and morphological operations to smooth out pixel noise before vectorization.
* **Min Blob Filtering:** Automatically removes tiny, isolated speckles ("dust") that are too small to cut or print.
* **Vector Smoothing:** Adjustable Ramer-Douglas-Peucker simplification for organic or angular aesthetic styles.

###  Export Capabilities
* **2D Vector (SVG):** Exports clean, layered SVG bundles compatible with Laser Cutters, Cricut, and Silhouette machines.
* **3D Model (STL):**
    * **Stencil Mode:** Inverted plates with holes (for spray painting). Includes **Auto-Bridging** logic to make stencils physically viable.
    * **Solid Mode:** Positive extrusions for texture mapping or physical inlays.
    * **Precision:** Define exact physical width (mm/in), extrusion height, and border width.

## Installation

### Prerequisites
Ensure you have Python 3.x, venv, and pip installed. The application relies on the following libraries:

```bash
pip install opencv-python numpy svgwrite Pillow trimesh shapely
```

### Quick Start (Windows)
1.  Double-click **`setup_windows.bat`** (if provided) to install dependencies.
2.  Double-click **`run.bat`** to launch.

### Quick Start (Linux)
1.  Open a terminal in the directory.
2.  Run setup: `chmod +x setup_linux.sh && ./setup_linux.sh`
3.  Launch: `./run.sh`

## Workflow Guide

### 1. Import
Click the central **OPEN IMAGE** button (or `Ctrl+O`). Supported formats: JPG, PNG, BMP.

### 2. Define Colors
* **Auto:** Click **YOLO Scan** to let the app decide.
* **Manual:** Click on the image to pick colors.
* **Refine:** Use the sidebar to merge similar colors into the same **Layer #**. Grouping 3 shades of green into "Layer 1" creates a complex, organic pattern.

### 3. Process
Click **PROCESS IMAGE** (`Ctrl+P`). The app will generate masks, apply smoothing, and create a preview. Switch between tabs to see individual layers.

### 4. Export
* **2D:** File > Export SVG Bundle (`Ctrl+E`).
* **3D:** File > Export STL Models (`Ctrl+Shift+E`).
    * *Tip:* For spray stencils, ensure **Invert** is checked and **Bridge Width** is set to at least 2.0mm.

## Keyboard Shortcuts

| Action | Shortcut |
| :--- | :--- |
| **New Project** | `Ctrl + N` |
| **Open Image** | `Ctrl + O` |
| **Open Project** | `Ctrl + Shift + O` |
| **Save Project** | `Ctrl + S` |
| **Process** | `Ctrl + P` |
| **YOLO Scan** | `Ctrl + Y` |
| **Export 2D** | `Ctrl + E` |
| **Export 3D** | `Ctrl + Shift + E` |
| **Config** | `Ctrl + ,` |

## Configuration Details

Settings are accessed via **Properties > Configuration** and are auto-saved on exit.

| Setting | Description |
| :--- | :--- |
| **Max Color Count** | (Auto-Mode only) How many clusters K-Means should look for. |
| **Denoise Strength** | Higher values blur the input more, resulting in smoother, rounder blobs. |
| **Path Smoothing** | Lower (0.0001) = High detail/organic. Higher (0.005) = Low poly/angular. |
| **Min Blob Size** | Filters out small islands (noise) in pixels. |
| **Orphaned Blobs** | Forces the app to create a layer for any pixels not covered by selected colors. |
| **Filename Template** | Naming convention for exports (e.g., `%INPUTFILENAME%-%COLOR%`). |

