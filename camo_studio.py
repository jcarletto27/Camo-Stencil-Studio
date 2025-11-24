import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
import svgwrite
import os
import threading
from PIL import Image, ImageTk

# --- 3D IMPORTS ---
import trimesh
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

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

class AutoResizingCanvas(tk.Canvas):
    def __init__(self, parent, pil_image, **kwargs):
        super().__init__(parent, **kwargs)
        self.pil_image = pil_image
        self.displayed_image = None 
        self.scale_ratio = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.bind("<Configure>", self.on_resize)

    def on_resize(self, event):
        if not self.pil_image: return
        canvas_width = event.width
        canvas_height = event.height
        if canvas_width < 10 or canvas_height < 10: return

        img_w, img_h = self.pil_image.size
        self.scale_ratio = min(canvas_width / img_w, canvas_height / img_h)
        
        new_w = int(img_w * self.scale_ratio)
        new_h = int(img_h * self.scale_ratio)
        
        resized_pil = self.pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.displayed_image = ImageTk.PhotoImage(resized_pil)
        
        self.delete("all")
        self.offset_x = (canvas_width - new_w) // 2
        self.offset_y = (canvas_height - new_h) // 2
        self.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.displayed_image)

    def get_image_coordinates(self, screen_x, screen_y):
        if not self.pil_image: return None
        rel_x = screen_x - self.offset_x
        rel_y = screen_y - self.offset_y
        img_x = int(rel_x / self.scale_ratio)
        img_y = int(rel_y / self.scale_ratio)
        w, h = self.pil_image.size
        if 0 <= img_x < w and 0 <= img_y < h:
            return (img_x, img_y)
        return None

class CamoStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Camo Studio v22 - Orphaned Blobs")
        self.root.geometry("1200x850")

        self.config = {
            "max_colors": tk.IntVar(value=DEFAULT_MAX_COLORS),
            "max_width": tk.IntVar(value=DEFAULT_MAX_WIDTH),
            "denoise_strength": tk.IntVar(value=DEFAULT_DENOISE),
            "min_blob_size": tk.IntVar(value=DEFAULT_MIN_BLOB),
            "filename_template": tk.StringVar(value=DEFAULT_TEMPLATE),
            "smoothing": tk.DoubleVar(value=DEFAULT_SMOOTHING),
            "orphaned_blobs": tk.BooleanVar(value=False) # New Config
        }
        
        # 3D Export Vars
        self.exp_units = tk.StringVar(value="mm")
        self.exp_width = tk.DoubleVar(value=100.0)
        self.exp_height = tk.DoubleVar(value=2.0) 
        self.exp_border = tk.DoubleVar(value=5.0)
        self.exp_invert = tk.BooleanVar(value=True)
        
        self.original_image_path = None
        self.cv_original_full = None 
        self.current_base_name = "camo"
        
        # State
        self.picked_colors = [] 
        self.layer_vars = []
        self.select_vars = [] 
        self.bulk_target_layer = tk.IntVar(value=1)
        
        # Selection state for Shift+Click
        self.last_select_index = -1 
        
        self.processed_data = None 
        self.preview_images = {}

        self._create_ui()
        self._bind_shortcuts()

    def _bind_shortcuts(self):
        self.root.bind("<Control-o>", self.load_image)
        self.root.bind("<Control-p>", self.trigger_process)
        self.root.bind("<Control-y>", self.yolo_scan)
        self.root.bind("<Control-e>", self.export_bundle_2d)
        self.root.bind("<Control-E>", self.open_3d_export_window) 
        self.root.bind("<Control-r>", self.reset_picks)
        self.root.bind("<Control-s>", lambda e: [self.reorder_palette_by_similarity(), self.update_pick_ui()])
        self.root.bind("<Control-comma>", self.open_config_window)

    def _create_ui(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Base Image (Ctrl+O)", command=self.load_image)
        file_menu.add_command(label="Export SVG Bundle (Ctrl+E)", command=self.export_bundle_2d)
        file_menu.add_command(label="Export STL Models (Ctrl+Shift+E)", command=self.open_3d_export_window)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        prop_menu = tk.Menu(menubar, tearoff=0)
        prop_menu.add_command(label="Configuration (Ctrl+,)", command=self.open_config_window)
        menubar.add_cascade(label="Properties", menu=prop_menu)
        self.root.config(menu=menubar)

        self.toolbar = tk.Frame(self.root, padx=10, pady=10, bg="#ddd")
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(self.toolbar, text="Pick Colors -> Assign Layers -> Process -> Export", bg="#ddd", fg="#555").pack(side=tk.LEFT)
        self.btn_process = tk.Button(self.toolbar, text="PROCESS IMAGE", command=self.trigger_process, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.btn_process.pack(side=tk.RIGHT, padx=10)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=5)
        
        self.tab_main = tk.Frame(self.notebook)
        self.notebook.add(self.tab_main, text="Input / Preview")
        
        self.input_container = tk.Frame(self.tab_main)
        self.input_container.pack(fill="both", expand=True)

        self.swatch_sidebar = tk.Frame(self.input_container, width=280, bg="#f0f0f0", padx=5, pady=5)
        self.swatch_sidebar.pack(side=tk.LEFT, fill="y")
        self.swatch_sidebar.pack_propagate(False) 
        
        self.sidebar_tools = tk.Frame(self.swatch_sidebar, bg="#f0f0f0")
        self.sidebar_tools.pack(side=tk.TOP, fill="x", pady=(0, 5))
        tk.Button(self.sidebar_tools, text="YOLO Scan (Auto-Detect)", command=self.yolo_scan, 
                  bg="#FF9800", fg="white", font=("Arial", 9, "bold")).pack(fill="x", padx=5)

        self.bulk_frame = tk.Frame(self.swatch_sidebar, bg="#e0e0e0", padx=5, pady=5)
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

        self.swatch_container = tk.Frame(self.swatch_sidebar, bg="#f0f0f0")
        self.swatch_container.pack(side=tk.LEFT, fill="both", expand=True)
        
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

        self.canvas_frame = tk.Frame(self.input_container, bg="#333")
        self.canvas_frame.pack(side=tk.LEFT, fill="both", expand=True)
        
        self.lbl_placeholder = tk.Label(self.canvas_frame, text="Load an image to start.", font=("Arial", 14), fg="#555")
        self.lbl_placeholder.pack(expand=True)
        self.main_canvas = None

        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress.pack(side=tk.BOTTOM, fill=tk.X)
        self.lbl_status = tk.Label(self.root, text="Ready.", anchor="w")
        self.lbl_status.pack(side=tk.BOTTOM, fill=tk.X)

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
        
        # New Orphaned Blobs Feature
        tk.Label(form, text="Orphaned Blobs:").grid(row=row, column=0, sticky="w")
        tk.Checkbutton(form, text="Detect & Assign Random Color", variable=self.config["orphaned_blobs"]).grid(row=row, column=1, sticky="w", pady=5); row+=1
        tk.Label(form, text="(Captures white space/background as a new layer)", font=("Arial", 8), fg="gray").grid(row=row, column=1, sticky="w"); row+=1

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
        win.geometry("450x400")
        form = tk.Frame(win, padx=20, pady=20)
        form.pack(fill="both", expand=True)
        tk.Label(form, text="3D Stencil Settings", font=("Arial", 10, "bold")).pack(pady=10)
        tk.Checkbutton(form, text="Invert (Stencil Mode)", variable=self.exp_invert, font=("Arial", 9, "bold")).pack(pady=5)
        tk.Label(form, text="Checked: Blobs are holes.\nUnchecked: Blobs are solid.", font=("Arial", 8), fg="gray").pack(pady=(0, 10))
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
        tk.Button(form, text="Export STL Files", command=lambda: self.trigger_3d_export(win), bg="blue", fg="white").pack(pady=20, fill="x")

    def trigger_3d_export(self, parent_window):
        target_dir = filedialog.askdirectory()
        if not target_dir: return
        parent_window.destroy()
        self.progress['mode'] = 'determinate'
        self.progress_var.set(0)
        threading.Thread(target=self.export_3d_thread, args=(target_dir,)).start()

    def load_image(self, event=None):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")])
        if not path: return
        self.original_image_path = path
        self.current_base_name = os.path.splitext(os.path.basename(path))[0]
        self.cv_original_full = cv2.imread(path)
        rgb_img = cv2.cvtColor(self.cv_original_full, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)
        if self.lbl_placeholder: self.lbl_placeholder.destroy()
        if self.main_canvas: self.main_canvas.destroy()
        self.main_canvas = AutoResizingCanvas(self.canvas_frame, pil_image=pil_img, bg="#333", highlightthickness=0)
        self.main_canvas.pack(fill="both", expand=True)
        self.main_canvas.bind("<Button-1>", self.on_canvas_click)
        self.reset_picks()
        self.lbl_status.config(text="Image loaded.")

    # --- YOLO MODE (UPDATED) ---
    def yolo_scan(self, event=None):
        if self.cv_original_full is None: 
            messagebox.showinfo("Info", "Load an image first.")
            return
            
        if self.picked_colors:
            if not messagebox.askyesno("YOLO Mode", "This will replace your current palette. Continue?"):
                return

        self.picked_colors = []
        self.layer_vars = []
        self.select_vars = []
        
        img = self.cv_original_full.copy()
        max_analysis_w = 300 
        h, w = img.shape[:2]
        if w > max_analysis_w:
            scale = max_analysis_w / w
            img = cv2.resize(img, (max_analysis_w, int(h * scale)), interpolation=cv2.INTER_AREA)
            
        data = img.reshape((-1, 3)).astype(np.float32)
        
        unique_colors = np.unique(data.astype(np.uint8), axis=0)
        final_colors = []
        
        # 1. Get Raw Colors
        if len(unique_colors) <= 64:
            print(f"YOLO: Found {len(unique_colors)} unique colors. Using Exact.")
            final_colors = [tuple(c) for c in unique_colors]
        else:
            print(f"YOLO: Too many colors. Quantizing to 32.")
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            ret, label, center = cv2.kmeans(data, 32, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
            center = np.uint8(center)
            final_colors = [tuple(c) for c in center]
            
        self.picked_colors = final_colors
        
        # 2. Initial Sort & Variable Creation (Assigns 1..N layers)
        self.reorder_palette_by_similarity()
        
        # 3. SMART GROUPING (NEW)
        target_layers = self.config["max_colors"].get()
        
        # Only apply grouping if we have more colors than target layers
        if len(self.picked_colors) > target_layers:
            print(f"YOLO: Grouping {len(self.picked_colors)} colors into {target_layers} layers.")
            
            # A. Cluster the Palette itself
            palette_data = np.array(self.picked_colors, dtype=np.float32)
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            ret, labels, centers = cv2.kmeans(palette_data, target_layers, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
            
            # B. Sort the Centers by Brightness (Lightest -> Darkest)
            # This ensures Layer 1 is always the lightest group, Layer N is darkest
            centers_info = []
            for i, center in enumerate(centers):
                centers_info.append( {'id': i, 'val': sum(center)} )
            centers_info.sort(key=lambda x: x['val'], reverse=True)
            
            # Map: Old Cluster ID -> New Sequential Layer Number (1..N)
            cluster_to_layer_map = {}
            for new_layer_num, info in enumerate(centers_info):
                cluster_to_layer_map[info['id']] = new_layer_num + 1
            
            # C. Assign Layers to Colors
            # labels[i] tells us which center picked_colors[i] belongs to
            for i, cluster_idx in enumerate(labels.flatten()):
                new_layer_id = cluster_to_layer_map[cluster_idx]
                self.layer_vars[i].set(new_layer_id)

        self.update_pick_ui()
        self.lbl_status.config(text=f"YOLO Mode: {len(self.picked_colors)} colors grouped into {target_layers} layers.")

    def on_canvas_click(self, event):
        if self.cv_original_full is None: return
        coords = self.main_canvas.get_image_coordinates(event.x, event.y)
        if coords:
            x, y = coords
            if y < self.cv_original_full.shape[0] and x < self.cv_original_full.shape[1]:
                bgr_color = self.cv_original_full[y, x]
                bgr_tuple = tuple(bgr_color)
                if bgr_tuple in self.picked_colors:
                    self.lbl_status.config(text="Color already in palette.")
                    return
                self.picked_colors.append(bgr_tuple)
                self.reorder_palette_by_similarity()
                self.update_pick_ui()
                self.lbl_status.config(text=f"Color added & sorted. Total: {len(self.picked_colors)}")

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

    def remove_color(self, index):
        if 0 <= index < len(self.picked_colors):
            del self.picked_colors[index]
            del self.layer_vars[index] 
            del self.select_vars[index]
            self.compact_layer_ids()
            self.update_pick_ui()
            self.lbl_status.config(text=f"Color removed. Total: {len(self.picked_colors)}")

    def reset_picks(self, event=None):
        self.picked_colors = []
        self.layer_vars = []
        self.select_vars = []
        self.last_select_index = -1
        self.update_pick_ui()
        if self.cv_original_full is not None:
            for tab in self.notebook.tabs():
                if tab != str(self.tab_main): self.notebook.forget(tab)

    # --- BULK ACTIONS ---
    def apply_bulk_layer(self):
        target = self.bulk_target_layer.get()
        changed = False
        for i, var in enumerate(self.select_vars):
            if var.get():
                self.layer_vars[i].set(target)
                changed = True
                var.set(False) 
        
        if changed:
            self.compact_layer_ids()
            self.update_pick_ui()
            self.lbl_status.config(text="Bulk assignment complete. Layers re-numbered.")
        else:
            messagebox.showinfo("Info", "No colors selected.")

    def compact_layer_ids(self):
        current_ids = sorted(list(set(v.get() for v in self.layer_vars)))
        id_map = {old: new+1 for new, old in enumerate(current_ids)}
        for var in self.layer_vars:
            var.set(id_map[var.get()])

    # --- SELECTION LOGIC ---
    def handle_click_selection(self, index, event):
        """Handles click and Shift+Click logic for the checkbox range"""
        if event and (event.state & 0x0001): # Shift Key Held
            if self.last_select_index != -1:
                start = min(self.last_select_index, index)
                end = max(self.last_select_index, index)
                # Set range to True
                for i in range(start, end + 1):
                    self.select_vars[i].set(True)
        else:
            # Normal click logic is handled by Checkbutton naturally toggling.
            # We just need to track this as the anchor for the next shift click.
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
            # Bind Shift+Click to the Checkbutton
            chk.bind("<Shift-Button-1>", lambda e, idx=i: self.handle_click_selection(idx, e))
            # Also bind normal click to update anchor
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
        threading.Thread(target=self.process_thread).start()

    def process_thread(self):
        try:
            img = self.cv_original_full.copy()
            max_w = self.config["max_width"].get()
            h, w = img.shape[:2]
            if max_w and w > max_w:
                scale = max_w / w
                img = cv2.resize(img, (max_w, int(h * scale)), interpolation=cv2.INTER_AREA)

            denoise_val = self.config["denoise_strength"].get()
            if denoise_val > 0:
                k = denoise_val if denoise_val % 2 == 1 else denoise_val + 1
                img = cv2.GaussianBlur(img, (k, k), 0)

            h, w = img.shape[:2]
            data = img.reshape((-1, 3)).astype(np.float32)

            raw_masks = []
            raw_centers = []
            
            if len(self.picked_colors) > 0:
                centers = np.array(self.picked_colors, dtype=np.float32)
                distances = np.zeros((data.shape[0], len(centers)), dtype=np.float32)
                for i, center in enumerate(centers):
                    distances[:, i] = np.sum((data - center) ** 2, axis=1)
                labels_reshaped = np.argmin(distances, axis=1).reshape((h, w))
                raw_centers = np.uint8(centers)
                num_raw_colors = len(centers)
            else:
                max_k = self.config["max_colors"].get()
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
            
            min_blob = self.config["min_blob_size"].get()
            kernel = None
            if denoise_val > 0:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (denoise_val, denoise_val))

            if len(self.picked_colors) > 0:
                layer_map = {} 
                for idx, var in enumerate(self.layer_vars):
                    lid = var.get()
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
                    
                    if min_blob > 0:
                        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        filtered = np.zeros_like(combined_mask)
                        valid = [c for c in contours if cv2.contourArea(c) >= min_blob]
                        if valid: cv2.drawContours(filtered, valid, -1, 255, -1)
                        final_masks.append(filtered)
                    else:
                        final_masks.append(combined_mask)
                        
                    final_centers.append(avg_color)

            else:
                for i, mask in enumerate(raw_masks):
                    if kernel is not None:
                        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                    
                    if min_blob > 0:
                        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        filtered = np.zeros_like(mask)
                        valid = [c for c in contours if cv2.contourArea(c) >= min_blob]
                        if valid: cv2.drawContours(filtered, valid, -1, 255, -1)
                        final_masks.append(filtered)
                    else:
                        final_masks.append(mask)
                final_centers = raw_centers

            # --- ORPHANED BLOBS FEATURE ---
            if self.config["orphaned_blobs"].get():
                # 1. Calculate total coverage
                full_mask = np.zeros((h, w), dtype=np.uint8)
                for m in final_masks:
                    full_mask = cv2.bitwise_or(full_mask, m)
                
                # 2. Find empty space (where full_mask is 0)
                orphans = cv2.bitwise_not(full_mask)
                
                # 3. Filter orphans
                if kernel is not None:
                    orphans = cv2.morphologyEx(orphans, cv2.MORPH_OPEN, kernel)
                    orphans = cv2.morphologyEx(orphans, cv2.MORPH_CLOSE, kernel)

                if min_blob > 0:
                    contours, _ = cv2.findContours(orphans, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    filtered_orphans = np.zeros_like(orphans)
                    valid = [c for c in contours if cv2.contourArea(c) >= min_blob]
                    if valid:
                        cv2.drawContours(filtered_orphans, valid, -1, 255, -1)
                    orphans_final = filtered_orphans
                else:
                    orphans_final = orphans

                # 4. Add if significant content exists
                if cv2.countNonZero(orphans_final) > 0:
                    while True:
                        rand_c = np.random.randint(0, 256, 3).astype(np.uint8)
                        dists = [np.sum((c - rand_c)**2) for c in final_centers]
                        if not dists or min(dists) > 2000: # Ensure reasonable contrast
                            break
                    
                    final_masks.append(orphans_final)
                    final_centers.append(rand_c)
                    print("Added Orphaned Blobs layer.")

            self.processed_data = {
                "centers": final_centers,
                "masks": final_masks,
                "width": w,
                "height": h
            }
            self._generate_previews(final_centers, final_masks, w, h)
            self.root.after(0, self.update_ui_after_process)

        except Exception as e:
            print(e)
            self.root.after(0, self.progress.stop)

    def _generate_previews(self, centers, masks, w, h):
        combined = np.ones((h, w, 3), dtype=np.uint8) * 255
        for i, mask in enumerate(masks):
            combined[mask == 255] = centers[i]
        self.preview_images["All"] = Image.fromarray(cv2.cvtColor(combined, cv2.COLOR_BGR2RGB))
        for i, mask in enumerate(masks):
            layer = np.ones((h, w, 3), dtype=np.uint8) * 255
            layer[mask == 255] = centers[i]
            self.preview_images[i] = Image.fromarray(cv2.cvtColor(layer, cv2.COLOR_BGR2RGB))

    def update_ui_after_process(self):
        self.progress.stop()
        self.progress['mode'] = 'determinate'
        self.progress_var.set(100)
        self.lbl_status.config(text="Processing Complete.")
        for tab in self.notebook.tabs():
            if tab != str(self.tab_main): self.notebook.forget(tab)
        self._add_tab("Combined Result", self.preview_images["All"])
        centers = self.processed_data["centers"]
        for i in range(len(centers)):
            hex_c = bgr_to_hex(centers[i])
            self._add_tab(f"L{i+1} {hex_c}", self.preview_images[i])
        self.notebook.select(1)

    def _add_tab(self, title, pil_image):
        frame = tk.Frame(self.notebook, bg="#333")
        self.notebook.add(frame, text=title)
        canvas = AutoResizingCanvas(frame, pil_image=pil_image, bg="#333", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

    def export_bundle_2d(self, event=None):
        if not self.processed_data: return
        target_dir = filedialog.askdirectory()
        if not target_dir: return
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
            
            for i in range(len(centers)):
                self.progress_var.set(((i+1)/len(centers))*100)
                bgr = centers[i]
                hex_c = bgr_to_hex(bgr)
                fname = tmpl.replace("%INPUTFILENAME%", self.current_base_name).replace("%COLOR%", hex_c.replace("#","")).replace("%INDEX%", str(i+1))
                if not fname.endswith(".svg"): fname += ".svg"
                path = os.path.join(target_dir, fname)
                
                dwg = svgwrite.Drawing(path, profile='tiny', size=(width, height))
                contours, _ = cv2.findContours(masks[i], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for c in contours:
                    epsilon = smooth * cv2.arcLength(c, True)
                    approx = cv2.approxPolyDP(c, epsilon, True)
                    if len(approx) < 3: continue
                    pts = approx.squeeze().tolist()
                    if not pts: continue
                    if isinstance(pts[0], int): d = f"M {pts[0]},{pts[1]} "
                    else:
                        d = f"M {pts[0][0]},{pts[0][1]} "
                        for p in pts[1:]: d += f"L {p[0]},{p[1]} "
                    d += "Z "
                    dwg.add(dwg.path(d=d, fill=hex_c, stroke='none'))
                dwg.save()
            self.root.after(0, lambda: messagebox.showinfo("Success", "2D Export Complete"))
        except Exception as e:
            print(e)
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

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
                                if not poly.is_valid: poly = poly.buffer(0)
                                shapely_polys.append(poly)
                            except: pass

                scene_mesh = trimesh.Trimesh()

                if is_stencil:
                    min_x, min_y = -border_w, -border_w
                    max_x, max_y = target_w + border_w, target_h + border_w
                    plate_poly = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
                    
                    final_shape = plate_poly
                    if shapely_polys:
                        blobs = unary_union(shapely_polys)
                        final_shape = plate_poly.difference(blobs)
                    
                    polys_to_extrude = []
                    if isinstance(final_shape, MultiPolygon):
                        for geom in final_shape.geoms: polys_to_extrude.append(geom)
                    else:
                        polys_to_extrude.append(final_shape)
                        
                    for p in polys_to_extrude:
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
                    scene_mesh.export(full_path)
            
            self.root.after(0, lambda: messagebox.showinfo("Success", f"Exported 3D models to {target_dir}"))
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
