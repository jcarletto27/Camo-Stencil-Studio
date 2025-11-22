# Camo-Stencil-Studio

**Camo-Stencil-Studio** is a powerful Python-based desktop application designed to convert standard images into professional camouflage patterns, vector stencils, and 3D printable models.

It bridges the gap between 2D image processing and physical fabrication, allowing users to create multi-layer spray paint stencils or solid 3D camouflage geometry from photographs or reference images.

## 🌟 Key Features

### 🎨 Color & Palette Management


- **Hybrid Color Detection:** Use automatic K-Means quantization to find dominant colors, or manually click the canvas to pick specific target colors.


- **Layer Merging:** Assign multiple distinct colors to a single "Layer ID". This allows you to merge different shades (e.g., "Forest Green" and "Dark Green") into a single physical stencil layer.


- **Smart Palette Sidebar:**


- Visual swatches with Hex codes.


- Duplicate prevention (prevents adding the same color twice).


- Manual sorting and removing of colors.





### 🛠 Image Processing


- **Smart Denoising:** Configurable Gaussian blur and Morphological operations to smooth out jagged pixel noise before vectorization.


- **Area Filtering:** "Min Blob Size" setting automatically removes tiny, isolated islands or speckles that are too small to cut or print.


- **Auto-Resizing:** Large images are automatically downscaled for performance while maintaining aspect ratio.



### 📂 2D Export (Vector)


- **SVG Bundles:** Exports each color layer as a separate, clean SVG file.


- **Optimized Paths:** Uses polygon simplification (Ramer-Douglas-Peucker algorithm) to create smooth vector curves suitable for vinyl cutters (Cricut/Silhouette) and laser cutters.



### 🧊 3D Export (STL)


- **Computational Geometry:** Converts 2D contours into 3D meshes using triangulation.


- **Stencil Mode (Inverted):** Generates a solid plate with "holes" cut out where the pattern exists (for spray painting).


- **Solid Mode (Positive):** Generates extruded blocks of the pattern (for physical textures or inlays).


- **Custom Dimensions:** Define exact width (mm/in), extrusion height, and solid border width.



## 🚀 Installation & Setup

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



## 📖 Usage Guide

### 1. Load & Pick


- Go to **File > Load Base Image** and select a reference image (JPG, PNG, BMP).


- **Manual Mode:** Click anywhere on the image to add that color to your Palette Sidebar.


- **Auto Mode:** If you don't pick any colors, the app will automatically calculate the average dominant colors based on the "Max Colors" setting.



### 2. Configure Layers


- Look at the **Palette Sidebar** on the left.


- Each color has a **Layer #**.


- If you want two different colors to end up on the same stencil, change their Layer # to match (e.g., set both Brown and Tan to Layer 1).


- Click the **Sort** button to organize the list.



### 3. Process


- Click the green **PROCESS IMAGE** button.


- The app will calculate the masks, clean up noise, and generate a preview.


- Use the tabs at the top to view the "Combined Result" or individual Layers.



### 4. Export


- **2D:** Go to **File > Export SVG Bundle**. Select a folder, and it will generate `layer_1.svg`, `layer_2.svg`, etc.


- **3D:** Go to **File > Export STL Models**.


- **Invert (Stencil Mode):** Check this if you want a spray paint stencil (holes). Uncheck it for solid objects.


- **Dimensions:** Set your desired physical width and thickness.





## ⚙️ Configuration Settings

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

## 📦 Requirements

If installing manually (without the scripts), these are the required Python libraries:

```
opencv-python numpy svgwrite Pillow trimesh shapely scipy mapbox_earcut   

```

You can install them via:

```
pip install opencv-python numpy svgwrite Pillow trimesh shapely scipy mapbox_earcut   

```
