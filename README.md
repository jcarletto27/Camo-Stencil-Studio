# Camo-Stencil-Studio

**Camo-Stencil-Studio** is a powerful Python-based desktop application designed to convert standard images into professional camouflage patterns, vector stencils, and 3D printable models.

It bridges the gap between 2D image processing and physical fabrication, allowing users to create multi-layer spray paint stencils or solid 3D camouflage geometry from photographs or reference images.

## Key Features

### Color & Palette Management


- **YOLO Mode (Auto-Detect):** One-click scanning that intelligently detects all dominant colors in an image and sorts them by visual similarity for you.


- **Hybrid Color Detection:** Use automatic K-Means quantization to find dominant colors, or manually click the canvas to pick specific target colors.


- **Smart Palette Sorting:** Colors are automatically sorted by visual similarity (Nearest Neighbor algorithm), creating smooth gradients in your list to make layer organization easier.


- **Bulk Layer Management:** Use checkboxes to select multiple colors and assign them to a single layer instantly.


- **Auto-Renumbering:** The app automatically compacts layer numbers (e.g., 1, 3, 5 → 1, 2, 3) to ensure a clean, sequential output without gaps.


- **Duplicate Prevention:** Automatically detects and prevents adding the same color twice.



### Image Processing


- **Smart Denoising:** Configurable Gaussian blur and Morphological operations to smooth out jagged pixel noise before vectorization.


- **Area Filtering:** "Min Blob Size" setting automatically removes tiny, isolated islands or speckles that are too small to cut or print.


- **Auto-Resizing:** Large images are automatically downscaled for performance while maintaining aspect ratio.



### 2D Export (Vector)


- **SVG Bundles:** Exports each color layer as a separate, clean SVG file.


- **Optimized Paths:** Uses polygon simplification (Ramer-Douglas-Peucker algorithm) to create smooth vector curves suitable for vinyl cutters (Cricut/Silhouette) and laser cutters.



### 3D Export (STL)


- **Computational Geometry:** Converts 2D contours into 3D meshes using triangulation.


- **Stencil Mode (Inverted):** Generates a solid plate with "holes" cut out where the pattern exists (for spray painting).


- **Solid Mode (Positive):** Generates extruded blocks of the pattern (for physical textures or inlays).


- **Custom Dimensions:** Define exact width (mm/in), extrusion height, and solid border width.



## Installation & Setup

This project includes automated setup scripts to handle Python Virtual Environments and dependencies.

### Windows


1. Double-click **`setup_windows.bat`**.


- This will create a virtual environment, upgrade pip, and install all required libraries.




1. Once complete, double-click **`run.bat`** to launch the application.



### Linux


1. Open a terminal in the project folder.


1. Make the scripts executable:

```
chmod +x setup_linux.sh run.sh   

```


1. Run the setup:

```
./setup_linux.sh   

```


1. Launch the application:

```
./run.sh   

```



## Usage Guide

### 1. Load & Pick


- Go to **File > Load Base Image** and select a reference image (JPG, PNG, BMP).


- **YOLO Mode (Recommended):** Click the orange **YOLO Scan** button. It will find the best colors, sort them by similarity, and assign them layer numbers automatically.


- **Manual Mode:** Click anywhere on the image to add that color to your Palette Sidebar.


- **Auto Mode:** If you don't pick any colors (and don't use YOLO), the app will automatically calculate the average dominant colors based on the "Max Colors" setting.



### 2. Configure Layers


- Look at the **Palette Sidebar** on the left.


- **Single Edit:** Use the spinner next to any color to change its **Layer #**.


- **Bulk Edit:**


1. Check the boxes next to the colors you want to group (e.g., three shades of green).


1. Look at the **Bulk Assign** panel at the bottom of the sidebar.


1. Set the target layer number and click **Apply**.




- **Resort:** Click the **Resort** button to re-organize the list by visual similarity if things get messy.



### 3. Process


- Click the green **PROCESS IMAGE** button.


- The app will calculate the masks, clean up noise, and generate a preview.


- Use the tabs at the top to view the "Combined Result" or individual Layers.



### 4. Export


- **2D:** Go to **File > Export SVG Bundle**. Select a folder, and it will generate `layer_1.svg`, `layer_2.svg`, etc.


- **3D:** Go to **File > Export STL Models**.


- **Invert (Stencil Mode):** Check this if you want a spray paint stencil (holes). Uncheck it for solid objects.


- **Dimensions:** Set your desired physical width and thickness.





### Keyboard Shortcuts

Action

Shortcut

Load Image

Ctrl + O`

Process Image

Ctrl + P`

YOLO Scan

Ctrl + Y`

Export SVG (2D)

Ctrl + E`

Export STL (3D)

Ctrl + Shift + E`

Clear Palette

Ctrl + R`

Resort Palette

Ctrl + S`

Configuration

Ctrl + ,`

## Configuration Settings

Access these via **Properties > Configuration**:

Setting

Description

**Max Color Count**

Used only in Auto-Mode. How many dominant colors to find.

**Denoise Strength**

(1-20) Higher values blur the image more before processing, resulting in rounder, smoother blobs. Lower values keep sharp details.

**Min Blob Size**

(Pixels) Any shape smaller than this will be deleted. Essential for removing "dust" from stencils.

**Max Width**

Downscales input images to this width to speed up processing. Default is 1000px.

**Filename Template**

customize output names. Variables: `%INPUTFILENAME%`, `%COLOR%`, `%INDEX%`.

## Requirements

If installing manually (without the scripts), these are the required Python libraries:

```
opencv-python numpy svgwrite Pillow trimesh shapely scipy mapbox_earcut   

```

You can install them via:

```
pip install opencv-python numpy svgwrite Pillow trimesh shapely scipy mapbox_earcut   

```

## License

This project is provided as-is for personal and educational use.