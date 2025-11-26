import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
import svgwrite
import os
import threading
import json
import copy
from PIL import Image, ImageTk, ImageDraw, ImageFont

# --- 3D IMPORTS ---
import trimesh
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union, nearest_points

# --- DEFAULTS ---
DEFAULT_MAX_COLORS = 4
DEFAULT_MAX_WIDTH = 1000
DEFAULT_SMOOTHING = 0.0005 
DEFAULT_DENOISE = 5
DEFAULT_MIN_BLOB = 50
DEFAULT_TEMPLATE = "%INPUTFILENAME%-%COLOR%-%INDEX%"

def bgr_to_hex(bgr):
    return '#{:02x}{:02x}{:02x}'.format(int(bgr[2]), int(bgr[1]), int(bgr[0]))

def is_bright(bgr):
    return (bgr[2] * 0.299 + bgr[1] * 0.587 + bgr[0] * 0.114) > 186

def filter_small_blobs(mask, min_size):
    """ Optimized area filtering using Connected Components (Raster). """
    if min_size <= 0: return mask
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    valid_labels = (stats[:, cv2.CC_STAT_AREA] >= min_size)
    valid_labels[0] = False 
    lut = np.zeros(n, dtype=np.uint8)
    lut[valid_labels] = 255
    return lut[labels]

# --- NEW: ZOOM/PAN CANVAS WITH DRAW HOOK ---
class ZoomPanCanvas(tk.Canvas):
    def __init__(self, parent, pil_image, **kwargs):
        super().__init__(parent, **kwargs)
        self.pil_image = pil_image
        self.tk_image = None
        self.post_draw_hook = None # Function to call after image redraw
        
        # Transform state
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        
        # Interactions
        self.bind("<Configure>", self.on_resize)
        self.bind("<ButtonPress-3>", self.start_pan) # Right click to pan
        self.bind("<B3-Motion>", self.do_pan)
        self.bind("<MouseWheel>", self.do_zoom) # Windows/Mac
        self.bind("<Button-4>", self.do_zoom)   # Linux Scroll Up
        self.bind("<Button-5>", self.do_zoom)   # Linux Scroll Down
        
        self._drag_start = (0, 0)

    def start_pan(self, event):
        self._drag_start = (event.x, event.y)

    def do_pan(self, event):
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self.pan_x += dx
        self.pan_y += dy
        self._drag_start = (event.x, event.y)
        self.redraw()

    def do_zoom(self, event):
        # Determine scroll direction
        if event.num == 5 or event.delta < 0:
            factor = 0.9
        else:
            factor = 1.1
        
        # Zoom centered on mouse
        mouse_x = self.canvasx(event.x)
        mouse_y = self.canvasy(event.y)
        
        # Offset logic to keep mouse point stable
        self.pan_x = mouse_x - (mouse_x - self.pan_x) * factor
        self.pan_y = mouse_y - (mouse_y - self.pan_y) * factor
        self.zoom *= factor
        self.redraw()

    def on_resize(self, event):
        if not self.pil_image: return
        # Initial fit-to-screen on first load if zoom is 1.0
        if self.zoom == 1.0 and self.pan_x == 0 and self.pan_y == 0:
            img_w, img_h = self.pil_image.size
            scale = min(event.width / img_w, event.height / img_h)
            self.zoom = scale
            self.pan_x = (event.width - img_w * scale) / 2
            self.pan_y = (event.height - img_h * scale) / 2
        self.redraw()

    def redraw(self):
        self.delete("all")
        if not self.pil_image: return
        
        new_w = int(self.pil_image.width * self.zoom)
        new_h = int(self.pil_image.height * self.zoom)
        
        if new_w < 1 or new_h < 1: return
        
        try:
            resized = self.pil_image.resize((new_w, new_h), Image.Resampling.BOX)
            self.tk_image = ImageTk.PhotoImage(resized)
            self.create_image(self.pan_x, self.pan_y, anchor="nw", image=self.tk_image)
        except: pass
        
        if self.post_draw_hook:
            self.post_draw_hook()

    def get_image_coordinates(self, screen_x, screen_y):
        if not self.pil_image: return None
        # Inverse transform: (screen - pan) / zoom
        img_x = int((screen_x - self.pan_x) / self.zoom)
        img_y = int((screen_y - self.pan_y) / self.zoom)
        
        if 0 <= img_x < self.pil_image.width and 0 <= img_y < self.pil_image.height:
            return (img_x, img_y)
        return None
        
    def image_to_screen_coords(self, img_x, img_y):
        scr_x = (img_x * self.zoom) + self.pan_x
        scr_y = (img_y * self.zoom) + self.pan_y
        return scr_x, scr_y

# --- HELPER: DXF WRITER ---
def write_simple_dxf(filename, contours, height_mm):
    """ Writes a minimal DXF R12 file with LWPOLYLINE entities. """
    with open(filename, 'w') as f:
        # Header
        f.write("0\nSECTION\n2\nENTITIES\n")
        
        for cnt in contours:
            # Ensure closed loop
            pts = cnt.squeeze().tolist()
            if not pts or len(pts) < 2: continue
            
            f.write("0\nLWPOLYLINE\n")
            f.write("8\n0\n") # Layer 0
            f.write(f"90\n{len(pts)}\n") # Num vertices
            f.write("70\n1\n") # Closed flag
            for p in pts:
                f.write(f"10\n{p[0]:.4f}\n20\n{height_mm - p[1]:.4f}\n") # Flip Y for CAD
            
        f.write("0\nENDSEC\n0\nEOF\n")

# --- HELPER: GUIDE GENERATOR ---
def create_guide_image(centers, filename):
    # Create a visual guide of colors -> layers
    try:
        w, h = 600, 50 + (len(centers) * 60)
        img = Image.new('RGB', (w, h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # Attempt to load a font, fallback to default
        try: font = ImageFont.truetype("arial.ttf", 20)
        except: font = ImageFont.load_default()
        
        draw.text((20, 10), "Camo Studio - Layer Guide", fill=(0,0,0), font=font)
        
        for i, bgr in enumerate(centers):
            y = 50 + (i * 60)
            rgb = (int(bgr[2]), int(bgr[1]), int(bgr[0]))
            hex_c = bgr_to_hex(bgr)
            
            # Draw Swatch
            draw.rectangle([20, y, 70, y+50], fill=rgb, outline=(0,0,0))
            
            # Text
            text = f"Layer {i+1}: {hex_c}"
            draw.text((90, y+15), text, fill=(0,0,0), font=font)
            
        img.save(filename)
    except Exception as e:
        print(f"Guide gen failed: {e}")

class CamoStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Camo Studio v32 - Image Manipulation")
        self.root.geometry("1200x850")
        
        self.settings_file = "user_settings.json"
        self.last_opened_dir = os.getcwd()

        self.config = {
            "max_colors": tk.IntVar(value=DEFAULT_MAX_COLORS),
            "max_width": tk.IntVar(value=DEFAULT_MAX_WIDTH),
            "denoise_strength": tk.IntVar(value=DEFAULT_DENOISE),
            "min_blob_size": tk.IntVar(value=DEFAULT_MIN_BLOB),
            "filename_template": tk.StringVar(value=DEFAULT_TEMPLATE),
            "smoothing": tk.DoubleVar(value=DEFAULT_SMOOTHING),
            "orphaned_blobs": tk.BooleanVar(value=False) 
        }
        
        self.exp_units = tk.StringVar(value="mm")
        self.exp_width = tk.DoubleVar(value=100.0)
        self.exp_height = tk.DoubleVar(value=2.0) 
        self.exp_border = tk.DoubleVar(value=5.0)
        self.exp_bridge = tk.DoubleVar(value=2.0)
        self.exp_invert = tk.BooleanVar(value=True)
        self.exp_dxf = tk.BooleanVar(value=True)
        
        self.load_app_settings()
        
        self.original_image_path = None
        
        # --- IMAGE PIPELINE VARS ---
        self.cv_geo_base = None # Image after Rotation/Crop (Geometry Base)
        self.cv_original_full = None # Image after B/C (View) -> Used by app
        self.brightness_val = tk.DoubleVar(value=1.0) # 0.0 to 3.0 (1.0 neutral)
        self.contrast_val = tk.DoubleVar(value=0)     # -100 to 100 (0 neutral)
        
        # --- CROP VARS ---
        self.is_cropping = False
        self.crop_start = None
        self.crop_current = None
        
        self.picked_colors = [] 
        self.layer_vars = []
        self.select_vars = [] 
        self.bulk_target_layer = tk.IntVar(value=1)
        self.last_select_index = -1 
        
        # --- UNDO STACK ---
        self.undo_stack = []
        self.redo_stack = []
        self.is_undoing = False 
        
        self.processed_data = None 
        self.view_vector = tk.BooleanVar(value=False)
        self.result_canvases = [] 

        self._create_ui()
        self._bind_shortcuts()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_app_settings(self):
        if not os.path.exists(self.settings_file): return
        try:
            with open(self.settings_file, 'r') as f:
                data = json.load(f)
            cfg = data.get("config", {})
            for k, v in cfg.items():
                if k in self.config:
                    try: self.config[k].set(v)
                    except: pass
            exp = data.get("export", {})
            self.exp_units.set(exp.get("units", "mm"))
            self.exp_width.set(exp.get("width", 100.0))
            self.exp_height.set(exp.get("height", 2.0))
            self.exp_border.set(exp.get("border", 5.0))
            self.exp_bridge.set(exp.get("bridge", 2.0))
            self.exp_invert.set(exp.get("invert", True))
            last_dir = data.get("last_directory", "")
            if last_dir and os.path.exists(last_dir):
                self.last_opened_dir = last_dir
        except Exception as e:
            print(f"Failed to load settings: {e}")

    def save_app_settings(self):
        data = {
            "config": {k: v.get() for k, v in self.config.items()},
            "export": {
                "units": self.exp_units.get(),
                "width": self.exp_width.get(),
                "height": self.exp_height.get(),
                "border": self.exp_border.get(),
                "bridge": self.exp_bridge.get(),
                "invert": self.exp_invert.get()
            },
            "last_directory": self.last_opened_dir
        }
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def on_close(self):
        self.save_app_settings()
        self.root.destroy()

    def _bind_shortcuts(self):
        self.root.bind("<Control-n>", lambda e: self.reset_project())
        self.root.bind("<Control-o>", lambda e: self.load_image())
        self.root.bind("<Control-s>", lambda e: self.save_project_json())
        self.root.bind("<Control-Shift-O>", lambda e: self.load_project_json())
        self.root.bind("<Control-p>", self.trigger_process)
        self.root.bind("<Control-y>", self.yolo_scan) 
        self.root.bind("<Control-e>", self.export_bundle_2d)
        self.root.bind("<Control-comma>", self.open_config_window)
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-Z>", lambda e: self.redo()) 
        self.root.bind("<Control-Shift-z>", lambda e: self.redo())

    def _create_ui(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Project (Ctrl+N)", command=self.reset_project)
        file_menu.add_command(label="Open Image... (Ctrl+O)", command=lambda: self.load_image())
        file_menu.add_separator()
        file_menu.add_command(label="Open Project... (Ctrl+Shift+O)", command=self.load_project_json)
        file_menu.add_command(label="Save Project (Ctrl+S)", command=self.save_project_json)
        file_menu.add_separator()
        file_menu.add_command(label="Export SVG Bundle (Ctrl+E)", command=self.export_bundle_2d)
        file_menu.add_command(label="Export STL Models (Ctrl+Shift+E)", command=self.open_3d_export_window)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo (Ctrl+Z)", command=self.undo)
        edit_menu.add_command(label="Redo (Ctrl+Shift+Z)", command=self.redo)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        prop_menu = tk.Menu(menubar, tearoff=0)
        prop_menu.add_command(label="Configuration (Ctrl+,)", command=self.open_config_window)
        menubar.add_cascade(label="Properties", menu=prop_menu)
        self.root.config(menu=menubar)

        self.toolbar = tk.Frame(self.root, padx=10, pady=10, bg="#ddd")
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(self.toolbar, text="L-Click: Pick | R-Click: Pan | Wheel: Zoom", bg="#ddd", fg="#333", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.btn_process = tk.Button(self.toolbar, text="PROCESS IMAGE", command=self.trigger_process, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.btn_process.pack(side=tk.RIGHT, padx=10)
        self.chk_vector = tk.Checkbutton(self.toolbar, text="Show Vector Output", variable=self.view_vector, command=self.refresh_tab_images, bg="#ddd", font=("Arial", 9, "bold"))
        self.chk_vector.pack(side=tk.RIGHT, padx=10)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=5)
        
        self.tab_main = tk.Frame(self.notebook)
        self.notebook.add(self.tab_main, text="Input / Preview")
        
        self.input_container = tk.Frame(self.tab_main)
        self.input_container.pack(fill="both", expand=True)

        # --- SIDEBAR TABS ---
        self.sidebar_notebook = ttk.Notebook(self.input_container, width=280)
        self.sidebar_notebook.pack(side=tk.LEFT, fill="y", padx=5, pady=5)
        
        # TAB 1: PALETTE
        self.palette_tab = tk.Frame(self.sidebar_notebook)
        self.sidebar_notebook.add(self.palette_tab, text="Palette")
        
        self.sidebar_tools = tk.Frame(self.palette_tab)
        self.sidebar_tools.pack(side=tk.TOP, fill="x", pady=(5, 5))
        tk.Button(self.sidebar_tools, text="YOLO Scan (Auto-Detect)", command=self.yolo_scan, 
                  bg="#FF9800", fg="white", font=("Arial", 9, "bold")).pack(fill="x", padx=5)

        self.swatch_container = tk.Frame(self.palette_tab)
        self.swatch_container.pack(side=tk.TOP, fill="both", expand=True)
        
        self.swatch_canvas = tk.Canvas(self.swatch_container, bg="#f0f0f0", highlightthickness=0)
        self.swatch_scrollbar = ttk.Scrollbar(self.swatch_container, orient="vertical", command=self.swatch_canvas.yview)
        
        self.swatch_list_frame = tk.Frame(self.swatch_canvas, bg="#f0f0f0")
        self.swatch_list_frame.bind("<Configure>", lambda e: self.swatch_canvas.configure(scrollregion=self.swatch_canvas.bbox("all")))
        self.swatch_window = self.swatch_canvas.create_window((0, 0), window=self.swatch_list_frame, anchor="nw")
        self.swatch_canvas.bind("<Configure>", lambda e: self.swatch_canvas.itemconfig(self.swatch_window, width=e.width))
        self.swatch_canvas.configure(yscrollcommand=self.swatch_scrollbar.set)
        self.swatch_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.swatch_canvas.pack(side=tk.LEFT, fill="both", expand=True)
        
        def _on_mousewheel(event):
            self.swatch_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.swatch_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self.bulk_frame = tk.Frame(self.palette_tab, bg="#e0e0e0", padx=5, pady=5)
        self.bulk_frame.pack(side=tk.BOTTOM, fill="x")
        bf_header = tk.Frame(self.bulk_frame, bg="#e0e0e0")
        bf_header.pack(fill="x", pady=(0,2))
        tk.Label(bf_header, text="Bulk Assign:", bg="#e0e0e0", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Button(bf_header, text="Clear List", command=self.reset_picks, bg="#ffdddd", font=("Arial", 7)).pack(side=tk.RIGHT)
        bf_inner = tk.Frame(self.bulk_frame, bg="#e0e0e0")
        bf_inner.pack(fill="x", pady=2)
        tk.Label(bf_inner, text="Sel. to Layer:", bg="#e0e0e0", font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Spinbox(bf_inner, from_=1, to=999, width=4, textvariable=self.bulk_target_layer).pack(side=tk.LEFT, padx=5)
        tk.Button(bf_inner, text="Apply", command=self.apply_bulk_layer, bg="#ccc", font=("Arial", 8)).pack(side=tk.LEFT)

        # TAB 2: IMAGE TOOLS
        self.img_tools_tab = tk.Frame(self.sidebar_notebook, padx=5, pady=5)
        self.sidebar_notebook.add(self.img_tools_tab, text="Image Tools")
        
        # Adjustments
        tk.Label(self.img_tools_tab, text="Adjustments", font=("Arial", 10, "bold")).pack(pady=(10, 5), anchor="w")
        tk.Label(self.img_tools_tab, text="Brightness").pack(anchor="w")
        # Bind Press-1 to save state BEFORE drag starts
        s_bright = tk.Scale(self.img_tools_tab, from_=0.5, to=2.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.brightness_val, command=self.apply_image_transform)
        s_bright.bind("<ButtonPress-1>", lambda e: self.push_undo_state())
        s_bright.pack(fill="x")
        
        tk.Label(self.img_tools_tab, text="Contrast").pack(anchor="w")
        s_cont = tk.Scale(self.img_tools_tab, from_=-50, to=50, orient=tk.HORIZONTAL, variable=self.contrast_val, command=self.apply_image_transform)
        s_cont.bind("<ButtonPress-1>", lambda e: self.push_undo_state())
        s_cont.pack(fill="x")
        
        tk.Button(self.img_tools_tab, text="Reset Sliders", command=self.reset_bc_sliders).pack(fill="x", pady=5)
        
        ttk.Separator(self.img_tools_tab, orient="horizontal").pack(fill="x", pady=15)
        
        # Geometry
        tk.Label(self.img_tools_tab, text="Geometry", font=("Arial", 10, "bold")).pack(pady=(0, 5), anchor="w")
        
        rot_frame = tk.Frame(self.img_tools_tab)
        rot_frame.pack(fill="x", pady=5)
        tk.Button(rot_frame, text="Rotate L", command=lambda: self.rotate_image(cv2.ROTATE_90_COUNTERCLOCKWISE)).pack(side=tk.LEFT, expand=True, fill="x", padx=2)
        tk.Button(rot_frame, text="Rotate R", command=lambda: self.rotate_image(cv2.ROTATE_90_CLOCKWISE)).pack(side=tk.LEFT, expand=True, fill="x", padx=2)
        
        self.btn_crop = tk.Button(self.img_tools_tab, text="Crop Tool", command=self.toggle_crop_mode, bg="#ddd")
        self.btn_crop.pack(fill="x", pady=10)
        
        tk.Button(self.img_tools_tab, text="Reset Image Geometry", command=self.reset_geometry, fg="red").pack(fill="x", pady=20)

        self.canvas_frame = tk.Frame(self.input_container, bg="#333")
        self.canvas_frame.pack(side=tk.LEFT, fill="both", expand=True)
        
        self.btn_main_load = tk.Button(self.canvas_frame, text="OPEN IMAGE", command=lambda: self.load_image(),
                                       font=("Arial", 16, "bold"), bg="#555", fg="white", padx=20, pady=10, cursor="hand2")
        self.btn_main_load.place(relx=0.5, rely=0.5, anchor="center")
        
        self.main_canvas = None

        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress.pack(side=tk.BOTTOM, fill=tk.X)
        self.lbl_status = tk.Label(self.root, text="Ready.", anchor="w")
        self.lbl_status.pack(side=tk.BOTTOM, fill=tk.X)

    # --- IMAGE PIPELINE ---
    def reset_bc_sliders(self):
        self.push_undo_state() # Save before reset
        self.brightness_val.set(1.0)
        self.contrast_val.set(0)
        self.apply_image_transform()

    def reset_geometry(self):
        if self.original_image_path and os.path.exists(self.original_image_path):
            self.push_undo_state() # Save before reset
            # Reload fresh
            self.cv_original_full = cv2.imread(self.original_image_path)
            self.cv_geo_base = self.cv_original_full.copy()
            self.reset_bc_sliders() # Triggers display update
            self.lbl_status.config(text="Geometry reset.")

    def apply_image_transform(self, event=None):
        """ Applies B/C to the Geometry Base and updates the View. """
        if self.cv_geo_base is None: return
        
        # Contrast/Brightness formula: new = alpha*old + beta
        # alpha = brightness (1.0 is neutral), beta = contrast shift? 
        # Actually OpenCV uses alpha for contrast (gain), beta for brightness (bias)
        # But let's map user sliders: Brightness (Mult), Contrast (Add) roughly
        
        alpha = self.brightness_val.get() 
        beta = self.contrast_val.get()
        
        # Apply
        res = cv2.convertScaleAbs(self.cv_geo_base, alpha=alpha, beta=beta)
        
        self.cv_original_full = res
        self.update_canvas_image(res)

    def update_canvas_image(self, cv_img):
        if self.main_canvas:
            rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            self.main_canvas.pil_image = pil
            self.main_canvas.redraw()

    def rotate_image(self, code):
        if self.cv_geo_base is None: return
        self.push_undo_state() # Save before rotate
        self.cv_geo_base = cv2.rotate(self.cv_geo_base, code)
        self.apply_image_transform() # Re-apply B/C to new orientation

    # --- CROP LOGIC ---
    def toggle_crop_mode(self):
        if self.cv_geo_base is None: return
        if not self.is_cropping:
            self.is_cropping = True
            self.btn_crop.config(text="Cancel Crop", bg="#ffdddd")
            self.main_canvas.bind("<ButtonPress-1>", self.crop_mousedown)
            self.main_canvas.bind("<B1-Motion>", self.crop_mousemove)
            self.main_canvas.bind("<ButtonRelease-1>", self.crop_mouseup)
            self.main_canvas.post_draw_hook = self.draw_crop_rect
            self.lbl_status.config(text="Crop Mode: Drag to select area. Click inside to confirm.")
        else:
            self.end_crop_mode()

    def end_crop_mode(self):
        self.is_cropping = False
        self.crop_start = None
        self.crop_current = None
        self.btn_crop.config(text="Crop Tool", bg="#ddd")
        self.main_canvas.unbind("<ButtonPress-1>")
        self.main_canvas.unbind("<B1-Motion>")
        self.main_canvas.unbind("<ButtonRelease-1>")
        # Rebind standard click
        self.main_canvas.bind("<Button-1>", self.on_canvas_click)
        self.main_canvas.post_draw_hook = None
        self.main_canvas.redraw()
        self.lbl_status.config(text="Crop cancelled.")

    def crop_mousedown(self, event):
        coords = self.main_canvas.get_image_coordinates(event.x, event.y)
        if coords:
            self.crop_start = coords
            self.crop_current = coords

    def crop_mousemove(self, event):
        if not self.crop_start: return
        coords = self.main_canvas.get_image_coordinates(event.x, event.y)
        if coords:
            self.crop_current = coords
            self.main_canvas.redraw() # Triggers hook

    def crop_mouseup(self, event):
        # If drag was tiny, treat as click?
        if not self.crop_start or not self.crop_current: return
        x1, y1 = self.crop_start
        x2, y2 = self.crop_current
        if abs(x2-x1) < 5 or abs(y2-y1) < 5: return
        
        if messagebox.askyesno("Confirm Crop", "Crop to selected area?"):
            self.push_undo_state() # Save before crop applies
            
            # Perform Crop
            x_min, x_max = sorted([x1, x2])
            y_min, y_max = sorted([y1, y2])
            
            # Crop from geo_base
            self.cv_geo_base = self.cv_geo_base[y_min:y_max, x_min:x_max]
            self.apply_image_transform()
            self.end_crop_mode()
            self.lbl_status.config(text="Image Cropped.")

    def draw_crop_rect(self):
        if not self.crop_start or not self.crop_current: return
        # Convert image coords back to screen
        x1, y1 = self.main_canvas.image_to_screen_coords(*self.crop_start)
        x2, y2 = self.main_canvas.image_to_screen_coords(*self.crop_current)
        self.main_canvas.create_rectangle(x1, y1, x2, y2, outline="red", width=2, dash=(4, 2))

    # --- UNDO / REDO LOGIC ---
    def push_undo_state(self):
        if self.is_undoing: return
        
        state = {
            "colors": list(self.picked_colors),
            "layers": [v.get() for v in self.layer_vars],
            # Image Pipeline State
            "geo_base": self.cv_geo_base.copy() if self.cv_geo_base is not None else None,
            "brightness": self.brightness_val.get(),
            "contrast": self.contrast_val.get()
        }
        # Avoid duplicates
        if self.undo_stack:
            last = self.undo_stack[-1]
            # Simple diff check
            if (last["colors"] == state["colors"] and 
                last["layers"] == state["layers"] and 
                last["brightness"] == state["brightness"] and
                last["contrast"] == state["contrast"]):
                
                # Check image equality only if diff
                if last["geo_base"] is None and state["geo_base"] is None: return
                if (last["geo_base"] is not None and state["geo_base"] is not None and 
                    np.array_equal(last["geo_base"], state["geo_base"])):
                    return
        
        self.undo_stack.append(state)
        self.redo_stack.clear() # Clear redo on new action
        
        # Limit stack size (images are heavy)
        if len(self.undo_stack) > 15:
            self.undo_stack.pop(0)

    def undo(self, event=None):
        if not self.undo_stack: return
        
        # Save current as redoable
        current_state = {
            "colors": list(self.picked_colors),
            "layers": [v.get() for v in self.layer_vars],
            "geo_base": self.cv_geo_base.copy() if self.cv_geo_base is not None else None,
            "brightness": self.brightness_val.get(),
            "contrast": self.contrast_val.get()
        }
        self.redo_stack.append(current_state)
        
        prev_state = self.undo_stack.pop()
        self.restore_state(prev_state)
        self.lbl_status.config(text="Undo performed.")

    def redo(self, event=None):
        if not self.redo_stack: return
        
        # Save current to undo
        current_state = {
            "colors": list(self.picked_colors),
            "layers": [v.get() for v in self.layer_vars],
            "geo_base": self.cv_geo_base.copy() if self.cv_geo_base is not None else None,
            "brightness": self.brightness_val.get(),
            "contrast": self.contrast_val.get()
        }
        self.undo_stack.append(current_state)
        
        next_state = self.redo_stack.pop()
        self.restore_state(next_state)
        self.lbl_status.config(text="Redo performed.")

    def restore_state(self, state):
        self.is_undoing = True
        self.picked_colors = state["colors"]
        
        # Rebuild Vars
        self.layer_vars = []
        self.select_vars = []
        for lid in state["layers"]:
            self.layer_vars.append(tk.IntVar(value=lid))
            self.select_vars.append(tk.BooleanVar(value=False))
            
        self.update_pick_ui()
        
        # Restore Image Pipeline
        if state["geo_base"] is not None:
            self.cv_geo_base = state["geo_base"].copy()
            self.brightness_val.set(state["brightness"])
            self.contrast_val.set(state["contrast"])
            self.apply_image_transform()
            
        self.is_undoing = False

    # --- UPDATED COLOR ACTIONS WITH UNDO PUSH ---
    def yolo_scan(self, event=None):
        if self.cv_original_full is None: return
        self.push_undo_state() # Save state before YOLO overwrite
        # ... rest of yolo scan logic ...
        if self.picked_colors:
            if not messagebox.askyesno("YOLO Mode", "Replace current palette?"):
                return
        # ... [Existing YOLO logic remains mostly same, ensure push_undo_state is called first] ...
        # To save space, I will implement the logic briefly:
        
        img = self.cv_original_full.copy()
        # ... (Preprocessing) ...
        h, w = img.shape[:2]
        max_analysis_w = 300
        if w > max_analysis_w:
            img = cv2.resize(img, (max_analysis_w, int(h*(max_analysis_w/w))))
        data = img.reshape((-1, 3)).astype(np.float32)
        unique = np.unique(data.astype(np.uint8), axis=0)
        
        final_colors = []
        if len(unique) <= 64:
            final_colors = [tuple(int(x) for x in c) for c in unique]
        else:
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            _, _, center = cv2.kmeans(data, 32, None, crit, 10, cv2.KMEANS_RANDOM_CENTERS)
            final_colors = [tuple(int(x) for x in c) for c in center]
            
        self.picked_colors = final_colors
        self.reorder_palette_by_similarity()
        
        # K-Means grouping for layers
        tgt = self.config["max_colors"].get()
        if len(self.picked_colors) > tgt:
            p_data = np.array(self.picked_colors, dtype=np.float32)
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            ret, labels, centers = cv2.kmeans(p_data, tgt, None, crit, 10, cv2.KMEANS_RANDOM_CENTERS)
            
            # Sort layers by brightness
            c_info = [{'id': i, 'val': sum(c)} for i,c in enumerate(centers)]
            c_info.sort(key=lambda x: x['val'], reverse=True)
            map_layer = {info['id']: i+1 for i, info in enumerate(c_info)}
            
            for i, c_idx in enumerate(labels.flatten()):
                self.layer_vars[i].set(map_layer[c_idx])

        self.update_pick_ui()
        self.lbl_status.config(text="YOLO Scan complete.")

    def on_canvas_click(self, event):
        if self.cv_original_full is None: return
        coords = self.main_canvas.get_image_coordinates(event.x, event.y)
        if coords:
            x, y = coords
            if y < self.cv_original_full.shape[0] and x < self.cv_original_full.shape[1]:
                self.push_undo_state() # Save before add
                bgr = self.cv_original_full[y, x]
                tup = tuple(int(x) for x in bgr)
                if tup not in self.picked_colors:
                    self.picked_colors.append(tup)
                    self.reorder_palette_by_similarity()
                    self.update_pick_ui()

    def remove_color(self, index):
        if 0 <= index < len(self.picked_colors):
            self.push_undo_state() # Save before delete
            del self.picked_colors[index]
            del self.layer_vars[index]
            del self.select_vars[index]
            self.compact_layer_ids()
            self.update_pick_ui()

    def apply_bulk_layer(self):
        target = self.bulk_target_layer.get()
        changed = False
        # Check if changes will happen
        for i, var in enumerate(self.select_vars):
            if var.get() and self.layer_vars[i].get() != target:
                changed = True
                break
        
        if changed:
            self.push_undo_state() # Save before bulk change
            for i, var in enumerate(self.select_vars):
                if var.get():
                    self.layer_vars[i].set(target)
                    var.set(False)
            self.compact_layer_ids()
            self.update_pick_ui()

    # --- UI HELPERS ---
    def open_config_window(self, event=None):
        top = tk.Toplevel(self.root)
        top.title("Properties")
        top.geometry("600x600")
        form = tk.Frame(top, padx=20, pady=20)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        
        row = 0
        tk.Label(form, text="Max Color Count (Auto-Mode):").grid(row=row, column=0, sticky="w")
        tk.Entry(form, textvariable=self.config["max_colors"]).grid(row=row, column=1, sticky="ew", pady=5); row+=1
        tk.Label(form, text="Denoise Strength:").grid(row=row, column=0, sticky="w")
        tk.Scale(form, from_=0, to=20, orient=tk.HORIZONTAL, variable=self.config["denoise_strength"]).grid(row=row, column=1, sticky="ew", pady=5); row+=1
        tk.Label(form, text="Path Smoothing:").grid(row=row, column=0, sticky="w")
        tk.Scale(form, from_=0.0001, to=0.005, resolution=0.0001, orient=tk.HORIZONTAL, variable=self.config["smoothing"]).grid(row=row, column=1, sticky="ew", pady=5); row+=1
        tk.Label(form, text="Lower = More Detail. Higher = Smoother.", font=("Arial", 8), fg="gray").grid(row=row, column=1, sticky="w"); row+=1
        tk.Label(form, text="Min Blob Size (px):").grid(row=row, column=0, sticky="w")
        tk.Entry(form, textvariable=self.config["min_blob_size"]).grid(row=row, column=1, sticky="ew", pady=5); row+=1
        
        tk.Label(form, text="Orphaned Blobs:").grid(row=row, column=0, sticky="w")
        tk.Checkbutton(form, text="Detect & Assign Random Color", variable=self.config["orphaned_blobs"]).grid(row=row, column=1, sticky="w", pady=5); row+=1
        
        tk.Label(form, text="Max Width (px):").grid(row=row, column=0, sticky="w")
        tk.Entry(form, textvariable=self.config["max_width"]).grid(row=row, column=1, sticky="ew", pady=5); row+=1
        tk.Label(form, text="Filename Template:").grid(row=row, column=0, sticky="w")
        tk.Entry(form, textvariable=self.config["filename_template"]).grid(row=row, column=1, sticky="ew", pady=5); row+=1
        tk.Button(top, text="Close", command=top.destroy).pack(pady=10)

    def open_3d_export_window(self, event=None):
        if not self.processed_data:
            messagebox.showwarning("No Data", "Process an image first.")
            return
        win = tk.Toplevel(self.root)
        win.title("Export 3D Models")
        win.geometry("450x500")
        form = tk.Frame(win, padx=20, pady=20)
        form.pack(fill="both", expand=True)
        tk.Label(form, text="3D Stencil Settings", font=("Arial", 10, "bold")).pack(pady=10)
        tk.Checkbutton(form, text="Invert (Stencil Mode)", variable=self.exp_invert, font=("Arial", 9, "bold")).pack(pady=5)
        u_frame = tk.Frame(form); u_frame.pack(fill="x", pady=5)
        tk.Label(u_frame, text="Units:").pack(side=tk.LEFT)
        tk.Radiobutton(u_frame, text="Millimeters", variable=self.exp_units, value="mm").pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(u_frame, text="Inches", variable=self.exp_units, value="in").pack(side=tk.LEFT)
        w_frame = tk.Frame(form); w_frame.pack(fill="x", pady=5)
        tk.Label(w_frame, text="Total Width:").pack(side=tk.LEFT)
        tk.Entry(w_frame, textvariable=self.exp_width, width=10).pack(side=tk.RIGHT)
        h_frame = tk.Frame(form); h_frame.pack(fill="x", pady=5)
        tk.Label(h_frame, text="Extrusion Height:").pack(side=tk.LEFT)
        tk.Entry(h_frame, textvariable=self.exp_height, width=10).pack(side=tk.RIGHT)
        b_frame = tk.Frame(form); b_frame.pack(fill="x", pady=5)
        tk.Label(b_frame, text="Solid Border Width:").pack(side=tk.LEFT)
        tk.Entry(b_frame, textvariable=self.exp_border, width=10).pack(side=tk.RIGHT)
        
        br_frame = tk.Frame(form); br_frame.pack(fill="x", pady=5)
        tk.Label(br_frame, text="Stencil Bridge Width:").pack(side=tk.LEFT)
        tk.Entry(br_frame, textvariable=self.exp_bridge, width=10).pack(side=tk.RIGHT)
        
        tk.Button(form, text="Export STL Files", command=lambda: self.trigger_3d_export(win), bg="blue", fg="white").pack(pady=20, fill="x")

    def trigger_3d_export(self, parent_window):
        target_dir = filedialog.askdirectory(initialdir=self.last_opened_dir)
        if not target_dir: return
        self.last_opened_dir = target_dir 
        parent_window.destroy()
        self.progress['mode'] = 'determinate'
        self.progress_var.set(0)
        threading.Thread(target=self.export_3d_thread, args=(target_dir,)).start()

    def reset_project(self):
        if self.picked_colors and not messagebox.askyesno("New Project", "Discard current changes?"):
            return
        self.original_image_path = None
        self.cv_original_full = None # The View
        self.cv_geo_base = None      # The Source
        self.current_base_name = "camo"
        self.picked_colors = []
        self.layer_vars = []
        self.select_vars = []
        self.undo_stack = []
        self.redo_stack = []
        self.last_select_index = -1
        self.processed_data = None
        
        self.brightness_val.set(1.0)
        self.contrast_val.set(0)
        
        self.update_pick_ui()
        if self.main_canvas: 
            self.main_canvas.destroy()
            self.main_canvas = None
        for tab in self.notebook.tabs():
            if tab != str(self.tab_main): self.notebook.forget(tab)
        self.btn_main_load.place(relx=0.5, rely=0.5, anchor="center")
        self.lbl_status.config(text="Project cleared.")

    def load_image(self, from_path=None):
        path = from_path
        if not path:
            path = filedialog.askopenfilename(initialdir=self.last_opened_dir, filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")])
        if not path: return
        self.last_opened_dir = os.path.dirname(path)
        if not os.path.exists(path):
            messagebox.showerror("Error", f"Image file not found:\n{path}\nPlease locate it manually.")
            path = filedialog.askopenfilename(initialdir=self.last_opened_dir, filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")])
            if not path: return
            self.last_opened_dir = os.path.dirname(path)

        self.original_image_path = path
        self.current_base_name = os.path.splitext(os.path.basename(path))[0]
        
        # Load Image
        self.cv_original_full = cv2.imread(path)
        self.cv_geo_base = self.cv_original_full.copy() # Store pristine copy for B/C resets
        
        rgb_img = cv2.cvtColor(self.cv_original_full, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)
        
        self.btn_main_load.place_forget()
        if self.main_canvas: self.main_canvas.destroy()
        self.main_canvas = ZoomPanCanvas(self.canvas_frame, pil_image=pil_img, bg="#333", highlightthickness=0)
        self.main_canvas.pack(fill="both", expand=True)
        self.main_canvas.bind("<Button-1>", self.on_canvas_click)
        
        if from_path is None:
            self.reset_picks()
            self.reset_bc_sliders()
            
        self.lbl_status.config(text=f"Loaded: {os.path.basename(path)}")

    def save_project_json(self):
        if not self.original_image_path:
            messagebox.showwarning("Warning", "No image loaded to save.")
            return
        sanitized_colors = [tuple(int(x) for x in c) for c in self.picked_colors]
        data = {
            "version": "1.0",
            "image_path": self.original_image_path,
            "config": {k: v.get() for k, v in self.config.items()},
            "colors": sanitized_colors, 
            "layers": [v.get() for v in self.layer_vars],
            "3d_export": {
                "units": self.exp_units.get(),
                "width": self.exp_width.get(),
                "height": self.exp_height.get(),
                "border": self.exp_border.get(),
                "bridge": self.exp_bridge.get(),
                "invert": self.exp_invert.get()
            }
        }
        path = filedialog.asksaveasfilename(initialdir=self.last_opened_dir, defaultextension=".json", filetypes=[("Camo Project", "*.json")])
        if path:
            self.last_opened_dir = os.path.dirname(path)
            try:
                with open(path, 'w') as f:
                    json.dump(data, f, indent=4)
                self.lbl_status.config(text=f"Project saved to {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("Save Error", str(e))

    def load_project_json(self):
        if self.picked_colors and not messagebox.askyesno("Open Project", "Discard current changes?"):
            return
        path = filedialog.askopenfilename(initialdir=self.last_opened_dir, filetypes=[("Camo Project", "*.json")])
        if not path: return
        self.last_opened_dir = os.path.dirname(path)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self.load_image(from_path=data.get("image_path"))
            if "config" in data:
                for k, v in data["config"].items():
                    if k in self.config:
                        try: self.config[k].set(v)
                        except: pass
            if "3d_export" in data:
                ex = data["3d_export"]
                self.exp_units.set(ex.get("units", "mm"))
                self.exp_width.set(ex.get("width", 100.0))
                self.exp_height.set(ex.get("height", 2.0))
                self.exp_border.set(ex.get("border", 5.0))
                self.exp_bridge.set(ex.get("bridge", 2.0))
                self.exp_invert.set(ex.get("invert", True))
            self.picked_colors = [tuple(c) for c in data.get("colors", [])]
            saved_layers = data.get("layers", [])
            self.layer_vars = []
            self.select_vars = []
            for i in range(len(self.picked_colors)):
                lid = saved_layers[i] if i < len(saved_layers) else 1
                self.layer_vars.append(tk.IntVar(value=lid))
                self.select_vars.append(tk.BooleanVar(value=False))
            self.update_pick_ui()
            self.lbl_status.config(text=f"Project loaded: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load project:\n{str(e)}")

    def reorder_palette_by_similarity(self):
        if not self.picked_colors: return
        while len(self.layer_vars) < len(self.picked_colors):
             existing_ids = [v.get() for v in self.layer_vars]
             next_id = max(existing_ids) + 1 if existing_ids else 1
             self.layer_vars.append(tk.IntVar(value=next_id))
        while len(self.select_vars) < len(self.picked_colors):
             self.select_vars.append(tk.BooleanVar(value=False))
        groups = {}
        for i, color in enumerate(self.picked_colors):
            lid = self.layer_vars[i].get()
            if lid not in groups: groups[lid] = []
            groups[lid].append({'color': color, 'var': self.layer_vars[i], 'select': self.select_vars[i]})
        group_metrics = []
        for lid, items in groups.items():
            avg_b = np.mean([sum(x['color']) for x in items])
            group_metrics.append({'lid': lid, 'brightness': avg_b, 'items': items})
        group_metrics.sort(key=lambda x: x['brightness'], reverse=True)
        new_colors = []
        new_layer_vars = []
        new_select_vars = []
        current_layer_num = 1
        for g in group_metrics:
            items = g['items']
            items.sort(key=lambda x: sum(x['color']), reverse=True)
            for item in items:
                new_colors.append(item['color'])
                new_layer_vars.append(tk.IntVar(value=current_layer_num))
                new_select_vars.append(item['select'])
            current_layer_num += 1
        self.picked_colors = new_colors
        self.layer_vars = new_layer_vars
        self.select_vars = new_select_vars

    def handle_click_selection(self, index, event):
        if event and (event.state & 0x0001): 
            if self.last_select_index != -1:
                start = min(self.last_select_index, index)
                end = max(self.last_select_index, index)
                for i in range(start, end + 1):
                    self.select_vars[i].set(True)
        else:
            self.last_select_index = index

    def update_pick_ui(self):
        for widget in self.swatch_list_frame.winfo_children():
            widget.destroy()
        if not self.picked_colors:
            tk.Label(self.swatch_list_frame, text="Auto-Mode", bg="#f0f0f0").pack(pady=10)
            return
        h_frame = tk.Frame(self.swatch_list_frame, bg="#f0f0f0")
        h_frame.pack(fill="x", pady=2)
        tk.Label(h_frame, text="Sel", bg="#f0f0f0", font=("Arial", 7)).pack(side=tk.LEFT, padx=2)
        tk.Label(h_frame, text="Color", bg="#f0f0f0", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=5)
        btn_sort = tk.Button(h_frame, text="Resort", command=lambda: [self.reorder_palette_by_similarity(), self.update_pick_ui()], font=("Arial", 7), padx=2, pady=0)
        btn_sort.pack(side=tk.RIGHT, padx=2)
        tk.Label(h_frame, text="Layer #", bg="#f0f0f0", font=("Arial", 8, "bold")).pack(side=tk.RIGHT, padx=2)
        for i, bgr in enumerate(self.picked_colors):
            var = self.layer_vars[i]
            sel_var = self.select_vars[i]
            hex_c = bgr_to_hex(bgr)
            fg = "black" if is_bright(bgr) else "white"
            f = tk.Frame(self.swatch_list_frame, bg=hex_c, height=30, highlightthickness=1, highlightbackground="#999")
            f.pack(fill="x", padx=5, pady=2)
            f.pack_propagate(False) 
            chk = tk.Checkbutton(f, variable=sel_var, bg=hex_c, activebackground=hex_c)
            chk.pack(side=tk.LEFT, padx=2)
            chk.bind("<Shift-Button-1>", lambda e, idx=i: self.handle_click_selection(idx, e))
            chk.bind("<Button-1>", lambda e, idx=i: self.handle_click_selection(idx, None))
            btn_del = tk.Label(f, text="X", bg="red", fg="white", font=("Arial", 8, "bold"), width=3)
            btn_del.pack(side=tk.LEFT, fill="y")
            btn_del.bind("<Button-1>", lambda e, idx=i: self.remove_color(idx))
            lbl = tk.Label(f, text=hex_c, bg=hex_c, fg=fg, font=("Consolas", 9, "bold"))
            lbl.pack(side=tk.LEFT, expand=True)
            spin = tk.Spinbox(f, from_=1, to=999, width=4, textvariable=var, font=("Arial", 10))
            spin.pack(side=tk.RIGHT, padx=5)

    def trigger_process(self, event=None):
        if self.cv_original_full is None: return
        self.lbl_status.config(text="Processing...")
        self.progress['mode'] = 'indeterminate'
        self.progress.start(10)
        snapshot_config = {
            "max_width": self.config["max_width"].get(),
            "max_colors": self.config["max_colors"].get(),
            "denoise_strength": self.config["denoise_strength"].get(),
            "min_blob_size": self.config["min_blob_size"].get(),
            "orphaned_blobs": self.config["orphaned_blobs"].get(),
            "smoothing": self.config["smoothing"].get()
        }
        snapshot_colors = list(self.picked_colors)
        snapshot_layers = [v.get() for v in self.layer_vars]
        threading.Thread(target=self.process_thread, args=(self.cv_original_full, snapshot_config, snapshot_colors, snapshot_layers)).start()

    def process_thread(self, img_original, config, picked_colors, layer_ids):
        try:
            img = img_original.copy()
            max_w = config["max_width"]
            h, w = img.shape[:2]
            if max_w and w > max_w:
                scale = max_w / w
                img = cv2.resize(img, (max_w, int(h * scale)), interpolation=cv2.INTER_AREA)
            denoise_val = config["denoise_strength"]
            if denoise_val > 0:
                k = denoise_val if denoise_val % 2 == 1 else denoise_val + 1
                img = cv2.GaussianBlur(img, (k, k), 0)
            h, w = img.shape[:2]
            data = img.reshape((-1, 3)).astype(np.float32)
            raw_masks = []
            raw_centers = []
            
            if len(picked_colors) > 0:
                centers = np.array(picked_colors, dtype=np.float32)
                distances = np.zeros((data.shape[0], len(centers)), dtype=np.float32)
                for i, center in enumerate(centers):
                    distances[:, i] = np.sum((data - center) ** 2, axis=1)
                labels_reshaped = np.argmin(distances, axis=1).reshape((h, w))
                raw_centers = np.uint8(centers)
                num_raw_colors = len(centers)
            else:
                max_k = config["max_colors"]
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
                ret, label, center = cv2.kmeans(data, max_k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
                raw_centers = np.uint8(center)
                labels_reshaped = label.flatten().reshape((h, w))
                num_raw_colors = len(raw_centers)

            for i in range(num_raw_colors):
                mask = cv2.inRange(labels_reshaped, i, i)
                raw_masks.append(mask)

            final_masks = []
            final_centers = []
            total_coverage_mask = np.zeros((h, w), dtype=np.uint8) 
            min_blob = config["min_blob_size"]
            kernel = None
            if denoise_val > 0:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (denoise_val, denoise_val))

            if len(picked_colors) > 0:
                layer_map = {} 
                for idx, lid in enumerate(layer_ids):
                    if lid not in layer_map: layer_map[lid] = []
                    layer_map[lid].append(idx)
                sorted_layer_ids = sorted(layer_map.keys())
                for lid in sorted_layer_ids:
                    indices = layer_map[lid]
                    combined_mask = np.zeros((h, w), dtype=np.uint8)
                    avg_color = np.zeros(3, dtype=np.float32)
                    for idx in indices:
                        combined_mask = cv2.bitwise_or(combined_mask, raw_masks[idx])
                        avg_color += raw_centers[idx]
                    avg_color = (avg_color / len(indices)).astype(np.uint8)
                    if kernel is not None:
                        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
                        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
                    filtered = filter_small_blobs(combined_mask, min_blob)
                    final_masks.append(filtered)
                    final_centers.append(avg_color)
                    total_coverage_mask = cv2.bitwise_or(total_coverage_mask, filtered)
            else:
                for i, mask in enumerate(raw_masks):
                    if kernel is not None:
                        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                    filtered = filter_small_blobs(mask, min_blob)
                    final_masks.append(filtered)
                    total_coverage_mask = cv2.bitwise_or(total_coverage_mask, filtered)
                final_centers = list(raw_centers)

            if config["orphaned_blobs"]:
                orphans = cv2.bitwise_not(total_coverage_mask)
                if kernel is not None:
                    orphans = cv2.morphologyEx(orphans, cv2.MORPH_OPEN, kernel)
                    orphans = cv2.morphologyEx(orphans, cv2.MORPH_CLOSE, kernel)
                orphans_final = filter_small_blobs(orphans, min_blob)
                if cv2.countNonZero(orphans_final) > 0:
                    attempts = 0
                    rand_c = np.array([0, 255, 0], dtype=np.uint8) 
                    while attempts < 50:
                        attempts += 1
                        candidate = np.random.randint(0, 256, 3).astype(np.uint8)
                        dists = [np.sum((c - candidate)**2) for c in final_centers]
                        threshold = 2000 if len(final_centers) < 10 else 500
                        if not dists or min(dists) > threshold: 
                            rand_c = candidate
                            break
                    final_masks.append(orphans_final)
                    final_centers.append(rand_c)
                    print("Added Orphaned Blobs layer.")

            # --- GENERATE PREVIEWS (RASTER) ---
            previews_raster = {}
            combined_raster = np.ones((h, w, 3), dtype=np.uint8) * 255
            for i, mask in enumerate(final_masks):
                color = final_centers[i]
                combined_raster[mask == 255] = color
                layer_img = np.ones((h, w, 3), dtype=np.uint8) * 255
                layer_img[mask == 255] = color
                previews_raster[i] = Image.fromarray(cv2.cvtColor(layer_img, cv2.COLOR_BGR2RGB))
            previews_raster["All"] = Image.fromarray(cv2.cvtColor(combined_raster, cv2.COLOR_BGR2RGB))

            # --- GENERATE PREVIEWS (VECTOR) ---
            previews_vector = {}
            combined_vector = np.ones((h, w, 3), dtype=np.uint8) * 255
            smoothing = config["smoothing"]
            
            for i, mask in enumerate(final_masks):
                color_tuple = (int(final_centers[i][0]), int(final_centers[i][1]), int(final_centers[i][2]))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                polys = []
                for c in contours:
                    epsilon = smoothing * cv2.arcLength(c, True)
                    approx = cv2.approxPolyDP(c, epsilon, True)
                    polys.append(approx)
                
                cv2.drawContours(combined_vector, polys, -1, color_tuple, -1)
                
                layer_vector_img = np.ones((h, w, 3), dtype=np.uint8) * 255
                cv2.drawContours(layer_vector_img, polys, -1, color_tuple, -1)
                previews_vector[i] = Image.fromarray(cv2.cvtColor(layer_vector_img, cv2.COLOR_BGR2RGB))
                
            previews_vector["All"] = Image.fromarray(cv2.cvtColor(combined_vector, cv2.COLOR_BGR2RGB))

            processed_data = {
                "centers": final_centers,
                "masks": final_masks,
                "width": w,
                "height": h,
                "raster_previews": previews_raster,
                "vector_previews": previews_vector
            }
            self.root.after(0, lambda: self.finish_processing(processed_data))

        except Exception as e:
            print(e)
            self.root.after(0, self.progress.stop)

    def finish_processing(self, data):
        self.processed_data = data
        self.progress.stop()
        self.progress['mode'] = 'determinate'
        self.progress_var.set(100)
        self.lbl_status.config(text="Processing Complete.")
        
        for tab in self.notebook.tabs():
            if tab != str(self.tab_main): self.notebook.forget(tab)
        self.result_canvases = [] 
        
        self._add_tab("Combined Result", "All")
        centers = data["centers"]
        for i in range(len(centers)):
            hex_c = bgr_to_hex(centers[i])
            self._add_tab(f"L{i+1} {hex_c}", i)
            
        self.refresh_tab_images()
        self.notebook.select(1)

    def _add_tab(self, title, image_key):
        frame = tk.Frame(self.notebook, bg="#333")
        self.notebook.add(frame, text=title)
        canvas = ZoomPanCanvas(frame, pil_image=None, bg="#333", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        self.result_canvases.append((canvas, image_key))

    def refresh_tab_images(self):
        if not self.processed_data: return
        is_vector = self.view_vector.get()
        source = self.processed_data["vector_previews"] if is_vector else self.processed_data["raster_previews"]
        
        for canvas, key in self.result_canvases:
            if key in source:
                canvas.pil_image = source[key]
                # Force redraw by mocking a configure event
                w = canvas.winfo_width()
                h = canvas.winfo_height()
                if w > 1 and h > 1:
                    class MockEvent:
                        def __init__(self, w, h): self.width, self.height = w, h
                    canvas.on_resize(MockEvent(w, h))

    def export_bundle_2d(self, event=None):
        if not self.processed_data: return
        target_dir = filedialog.askdirectory(initialdir=self.last_opened_dir)
        if not target_dir: return
        self.last_opened_dir = target_dir 
        self.progress['mode'] = 'determinate'
        self.progress_var.set(0)
        threading.Thread(target=self.export_2d_thread, args=(target_dir,)).start()

    def export_2d_thread(self, target_dir):
        try:
            centers = self.processed_data["centers"]
            masks = self.processed_data["masks"]
            width = self.processed_data["width"]
            height = self.processed_data["height"]
            tmpl = self.config["filename_template"].get()
            smooth = self.config["smoothing"].get() 
            
            # Generate Guide Image
            create_guide_image(centers, os.path.join(target_dir, "_layer_guide.png"))
            
            for i in range(len(centers)):
                self.progress_var.set(((i+1)/len(centers))*100)
                bgr = centers[i]
                hex_c = bgr_to_hex(bgr)
                fname = tmpl.replace("%INPUTFILENAME%", self.current_base_name).replace("%COLOR%", hex_c.replace("#","")).replace("%INDEX%", str(i+1))
                
                # SVG Export
                if not fname.endswith(".svg"): fname_svg = fname + ".svg"
                else: fname_svg = fname
                path = os.path.join(target_dir, fname_svg)
                dwg = svgwrite.Drawing(path, profile='tiny', size=(width, height))
                
                contours, _ = cv2.findContours(masks[i], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                dxf_contours = [] # Collect for DXF
                
                for c in contours:
                    epsilon = smooth * cv2.arcLength(c, True)
                    approx = cv2.approxPolyDP(c, epsilon, True)
                    if len(approx) < 3: continue
                    dxf_contours.append(approx)
                    
                    pts = approx.squeeze().tolist()
                    if not pts: continue
                    if isinstance(pts[0], int): d = f"M {pts[0]},{pts[1]} "
                    else:
                        d = f"M {pts[0][0]},{pts[0][1]} "
                        for p in pts[1:]: d += f"L {p[0]},{p[1]} "
                    d += "Z "
                    dwg.add(dwg.path(d=d, fill=hex_c, stroke='none'))
                dwg.save()
                
                # DXF Export (Optional)
                fname_dxf = fname.replace(".svg", ".dxf")
                if not fname_dxf.endswith(".dxf"): fname_dxf += ".dxf"
                write_simple_dxf(os.path.join(target_dir, fname_dxf), dxf_contours, height) # height passed for coord flip
                
            self.root.after(0, lambda: messagebox.showinfo("Success", "2D Export (SVG + DXF + Guide) Complete"))
        except Exception as e:
            print(e)
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

    def apply_stencil_bridges(self, polys, bridge_width):
        bridged_polys = []
        for poly in polys:
            if not poly.is_valid: poly = poly.buffer(0)
            if len(poly.interiors) == 0:
                bridged_polys.append(poly)
                continue
            temp_poly = poly
            for interior in poly.interiors:
                p1, p2 = nearest_points(temp_poly.exterior, interior)
                bridge_line = LineString([p1, p2])
                bridge_shape = bridge_line.buffer(bridge_width / 2)
                try:
                    temp_poly = temp_poly.difference(bridge_shape)
                    if not temp_poly.is_valid: temp_poly = temp_poly.buffer(0)
                except Exception as e:
                    print(f"Bridge failed on one island: {e}")
            if isinstance(temp_poly, MultiPolygon):
                for geom in temp_poly.geoms:
                    bridged_polys.append(geom)
            else:
                bridged_polys.append(temp_poly)
        return bridged_polys

    def export_3d_thread(self, target_dir):
        try:
            centers = self.processed_data["centers"]
            masks = self.processed_data["masks"]
            orig_w = self.processed_data["width"]
            orig_h = self.processed_data["height"]
            tmpl = self.config["filename_template"].get()
            smooth = self.config["smoothing"].get() 
            target_w = self.exp_width.get()
            extrusion = self.exp_height.get()
            border_w = self.exp_border.get()
            is_stencil = self.exp_invert.get()
            scale = target_w / orig_w
            target_h = orig_h * scale
            
            total_volume = 0.0
            
            for i in range(len(centers)):
                self.progress_var.set(((i+1)/len(centers))*100)
                bgr = centers[i]
                hex_c = bgr_to_hex(bgr)
                fname = tmpl.replace("%INPUTFILENAME%", self.current_base_name).replace("%COLOR%", hex_c.replace("#","")).replace("%INDEX%", str(i+1))
                if is_stencil: fname += "_stencil"
                fname += ".stl"
                full_path = os.path.join(target_dir, fname)
                
                contours, hierarchy = cv2.findContours(masks[i], cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
                shapely_polys = []
                if hierarchy is not None:
                    hierarchy = hierarchy[0]
                    for j, c in enumerate(contours):
                        if hierarchy[j][3] == -1: 
                            epsilon = smooth * cv2.arcLength(c, True)
                            approx = cv2.approxPolyDP(c, epsilon, True)
                            if len(approx) < 3: continue
                            outer_pts = approx.squeeze() * scale
                            outer_pts[:, 1] = target_h - outer_pts[:, 1] 
                            holes = []
                            current_child_idx = hierarchy[j][2]
                            while current_child_idx != -1:
                                child_c = contours[current_child_idx]
                                eps_child = smooth * cv2.arcLength(child_c, True)
                                approx_child = cv2.approxPolyDP(child_c, eps_child, True)
                                if len(approx_child) >= 3:
                                    hole_pts = approx_child.squeeze() * scale
                                    hole_pts[:, 1] = target_h - hole_pts[:, 1]
                                    holes.append(hole_pts)
                                current_child_idx = hierarchy[current_child_idx][0]
                            try:
                                poly = Polygon(shell=outer_pts, holes=holes)
                                clean_poly = poly.buffer(0)
                                if clean_poly.is_empty: continue
                                shapely_polys.append(clean_poly)
                            except: pass

                if is_stencil:
                     bridge_w = self.exp_bridge.get()
                     if bridge_w > 0:
                         shapely_polys = self.apply_stencil_bridges(shapely_polys, bridge_w)

                scene_mesh = trimesh.Trimesh()
                if is_stencil:
                    min_x, min_y = -border_w, -border_w
                    max_x, max_y = target_w + border_w, target_h + border_w
                    plate_poly = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
                    final_shape = plate_poly
                    if shapely_polys:
                        try:
                            blobs = unary_union(shapely_polys)
                            final_shape = plate_poly.difference(blobs)
                        except Exception as e:
                            print(f"Boolean diff failed: {e}")
                    polys_to_extrude = []
                    if isinstance(final_shape, MultiPolygon):
                        for geom in final_shape.geoms: polys_to_extrude.append(geom)
                    else:
                        polys_to_extrude.append(final_shape)
                    for p in polys_to_extrude:
                        if not p.is_valid: p = p.buffer(0)
                        if p.is_empty: continue
                        mesh_part = trimesh.creation.extrude_polygon(p, height=extrusion)
                        scene_mesh += mesh_part
                else:
                    if shapely_polys:
                        combined_poly = unary_union(shapely_polys)
                        polys_to_extrude = []
                        if isinstance(combined_poly, MultiPolygon):
                            for geom in combined_poly.geoms: polys_to_extrude.append(geom)
                        else:
                            polys_to_extrude.append(combined_poly)
                        for p in polys_to_extrude:
                            if not p.is_valid: p = p.buffer(0)
                            if p.is_empty: continue
                            mesh_part = trimesh.creation.extrude_polygon(p, height=extrusion)
                            scene_mesh += mesh_part
                    if border_w > 0:
                        outer_box = [[-border_w, -border_w], [target_w + border_w, -border_w],
                                     [target_w + border_w, target_h + border_w], [-border_w, target_h + border_w]]
                        inner_box = [[0, 0], [target_w, 0], [target_w, target_h], [0, target_h]]
                        border_poly = Polygon(shell=outer_box, holes=[inner_box])
                        border_mesh = trimesh.creation.extrude_polygon(border_poly, height=extrusion)
                        scene_mesh += border_mesh

                if not scene_mesh.is_empty:
                    total_volume += scene_mesh.volume
                    scene_mesh.export(full_path)
            
            # Est weight (PLA ~ 1.24 g/cm3). Volume is in cubic units (usually mm^3)
            # mm^3 to cm^3 = / 1000
            vol_cm3 = total_volume / 1000.0
            weight_g = vol_cm3 * 1.24
            
            msg = f"Export Complete.\nEst. Material: {weight_g:.2f}g (PLA)"
            self.root.after(0, lambda: messagebox.showinfo("Success", msg))
            self.root.after(0, lambda: self.lbl_status.config(text="3D Export Complete."))
        except Exception as e:
            print(e)
            err_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("Export Error", err_msg))
            self.root.after(0, self.progress.stop)

if __name__ == "__main__":
    root = tk.Tk()
    app = CamoStudioApp(root)
    root.mainloop()
