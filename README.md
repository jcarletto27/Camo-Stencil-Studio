# Camo-Stencil-Studio

**Camo-Stencil-Studio** is a powerful, Python-based desktop application designed to convert standard images into professional camouflage patterns, vector stencils, and 3D printable models.

It bridges the gap between 2D image processing and physical fabrication, allowing users to create multi-layer spray paint stencils or solid 3D camouflage geometry from photographs or reference images.

## Key Features

### 📂 Project Workspace (New in v27)
- **Save & Resume:** Save your entire workspace—including the image, color palette, layer assignments, and export settings—to a `.json` file and pick up exactly where you left off later.
- **Project Management:** Easily start fresh with a "New Project" option or reload previous configurations instantly.
- **Intuitive UI:** Clean interface with a central "Open Image" workflow and organized tabbed previews.

### 🎨 Color & Palette Management
- **YOLO Mode (Auto-Detect):** One-click scanning that intelligently detects all dominant colors in an image, sorts them by visual similarity, and assigns layer numbers automatically.
- **Hybrid Color Detection:** Use automatic K-Means quantization to find dominant colors, or manually click the canvas to pick specific target colors.
- **Smart Palette Sorting:** Colors are sorted by brightness (Lightest to Darkest) and visual similarity, creating smooth gradients to streamline layer organization.
- **Bulk Layer Management:** Select multiple colors via checkboxes and assign them to a single layer instantly.
- **Orphaned Blob Detection:** Optional setting to detect background "white space" or unassigned areas and group them into a randomly colored layer to ensure full coverage.

### 🖼️ Image Processing
- **Smart Denoising:** Configurable Gaussian blur and Morphological operations to smooth out jagged pixel noise before vectorization.
- **Area Filtering:** "Min Blob Size" setting automatically removes tiny, isolated islands or speckles that are too small to cut or print.
- **Auto-Resizing:** Large images are automatically downscaled for performance while maintaining aspect ratio.

### ✂️ 2D Export (Vector)
- **SVG Bundles:** Exports each color layer as a separate, clean SVG file.
- **Optimized Paths:** Uses polygon simplification to create smooth vector curves suitable for vinyl cutters (Cricut/Silhouette) and laser cutters. Adjustable smoothing factor allows for high-detail organic curves or low-poly angular styles.

### 🧊 3D Export (STL)
- **Stencil Mode (Inverted):** Generates a solid plate with "holes" cut out where the pattern exists (for spray painting).
- **Auto-Bridging (Island Fix):** Automatically detects "floating islands" (e.g., the center of a donut shape) inside stencil layers and cuts small structural bridges to anchor them to the frame. This ensures stencils are printable and physically stable.
- **Solid Mode (Positive):** Generates extruded blocks of the pattern (for physical textures or inlays).
- **Custom Dimensions:** Define exact width (mm/in), extrusion height, solid border width, and bridge thickness.

## Installation & Setup

### Requirements
The software requires `Python 3.13.0` or higher,  `venv`, and `pip`
The software relies on the following Python libraries:
```bash
pip install opencv-python numpy svgwrite Pillow trimesh shapely
```

### Windows
1. Double-click **`setup_windows.bat`**.
   - This will create a virtual environment, upgrade pip, and install all required libraries.
2. Once complete, double-click **`run.bat`** to launch the application.

### Linux
1. Open a terminal in the project folder.
2. Make the scripts executable:
   ```bash
   chmod +x setup_linux.sh run.sh
   ```
3. Run the setup:
   ```bash
   ./setup_linux.sh
   ```
4. Launch the application:
   ```bash
   ./run.sh
   ```

## Usage Guide

### 1. Load & Pick
- Click the central **OPEN IMAGE** button or use **File > Load Base Image**.
- **YOLO Mode (Recommended):** Click the orange **YOLO Scan** button. It will find the best colors, sort them by similarity, and assign them layer numbers automatically.
- **Manual Mode:** Click anywhere on the image to add that color to your Palette Sidebar.

### 2. Configure Layers
- **Palette Sidebar:** Use the spinner next to any color to change its **Layer #**.
- **Bulk Edit:** Check the boxes next to multiple colors, set the target layer in the **Bulk Assign** panel, and click **Apply**.
- **Resort:** Click the **Resort** button in the list header to re-organize the list by visual similarity.

### 3. Process
- Click the green **PROCESS IMAGE** button.
- The app will calculate the masks, clean up noise, fix orphaned pixels, and generate a preview.
- Use the tabs at the top to view the "Combined Result" or individual Layers.

### 4. Export
- **2D:** Go to **File > Export SVG Bundle**.
- **3D:** Go to **File > Export STL Models**.
  - **Invert:** Check for spray stencils, uncheck for solid models.
  - **Bridge Width:** Set a value > 0 (e.g., 2.0mm) to automatically connect floating islands to the frame.

## Keyboard Shortcuts

| Action | Shortcut |
| :--- | :--- |
| **New Project** | `Ctrl + N` |
| **Load Image** | `Ctrl + O` |
| **Open Project** | `Ctrl + Shift + O` |
| **Save Project** | `Ctrl + S` |
| **Process Image** | `Ctrl + P` |
| **YOLO Scan** | `Ctrl + Y` |
| **Export SVG (2D)** | `Ctrl + E` |
| **Export STL (3D)** | `Ctrl + Shift + E` |
| **Clear Palette** | `Ctrl + R` |
| **Configuration** | `Ctrl + ,` |

## Configuration Settings

Access these via **Properties > Configuration**:

| Setting | Description |
| :--- | :--- |
| **Max Color Count** | Used only in Auto-Mode. How many dominant colors to find. |
| **Denoise Strength** | (1-20) Higher values blur the image more before processing, resulting in rounder, smoother blobs. Lower values keep sharp details. |
| **Path Smoothing** | Controls vector detail. Lower values (left) create complex, organic curves. Higher values (right) create simpler, smoother, or more angular shapes. |
| **Min Blob Size** | (Pixels) Any shape smaller than this will be deleted. Essential for removing "dust" from stencils. |
| **Orphaned Blobs** | If checked, the app finds all pixels *not* covered by your selected colors (backgrounds) and assigns them to a new layer. |
| **Filename Template** | Customize output names. Variables: `%INPUTFILENAME%`, `%COLOR%`, `%INDEX%`. |
