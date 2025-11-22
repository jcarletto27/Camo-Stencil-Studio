import cv2
import numpy as np
import svgwrite
import os

def rgb_to_hex(rgb):
    """Converts an RGB tuple to a hex string."""
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]), int(rgb[1]), int(rgb[2]))

def create_camouflage_templates(image_path, max_colors=3, smooth_factor=0.002, generate_preview=True, max_width=800):
    """
    Process an image to create separated SVG layers based on averaged colors.
    
    :param max_width: Downscales image to this width before processing to speed up K-Means. 
                      (Set to None to disable resizing).
    """
    
    # 1. Load Image
    print(f"Loading {image_path}...")
    img = cv2.imread(image_path)
    if img is None:
        print("Error: Could not load image.")
        return

    # --- NEW STEP: Resize for Performance ---
    height, width = img.shape[:2]
    
    if max_width and width > max_width:
        print(f"Original size: {width}x{height}")
        scaling_factor = max_width / float(width)
        new_height = int(height * scaling_factor)
        
        # INTER_AREA is best for downscaling (reduces noise/aliasing)
        img = cv2.resize(img, (max_width, new_height), interpolation=cv2.INTER_AREA)
        print(f"Resized to: {max_width}x{new_height} for faster processing.")
        
        # Update dimensions for SVG generation later
        height, width = new_height, max_width

    # 2. Breakdown Colors (Quantization via K-Means)
    data = img.reshape((-1, 3))
    data = np.float32(data)
    
    # Criteria: (Stop when epsilon is reached OR max iterations occurs)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    
    print(f"Processing colors (reducing to {max_colors} dominant tones)...")
    ret, label, center = cv2.kmeans(data, max_colors, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    center = np.uint8(center)

    # Create output directory
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    output_dir = f"{base_name}_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 2.5 Generate Preview Image
    if generate_preview:
        print("Generating preview image...")
        res = center[label.flatten()]
        res2 = res.reshape((img.shape))
        preview_filename = f"{output_dir}/_PREVIEW_combined.jpg"
        cv2.imwrite(preview_filename, res2)
        print(f"Preview saved: {preview_filename}")

    # 3 & 4. Split and Convert to SVG
    labels_reshaped = label.flatten().reshape((height, width))
    
    print("Generating SVGs...")
    
    for i in range(max_colors):
        bgr_color = center[i]
        rgb_color = (bgr_color[2], bgr_color[1], bgr_color[0])
        hex_color = rgb_to_hex(rgb_color)
        
        mask = cv2.inRange(labels_reshaped, i, i)
        
        # Find Contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        svg_filename = f"{output_dir}/layer_{i}_{hex_color}.svg"
        dwg = svgwrite.Drawing(svg_filename, profile='tiny', size=(width, height))
        
        # Add a comment in the SVG file about the color
        dwg.add(dwg.text(f"Color Layer: {hex_color}", insert=(10, 20), fill='black'))
        
        for contour in contours:
            epsilon = smooth_factor * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            
            # Filter noise (tiny blobs)
            if len(approx) < 3: continue
            
            points = approx.squeeze().tolist()
            if not points: continue
            
            # Build Path String
            if isinstance(points[0], int): 
                 d_str = f"M {points[0]},{points[1]} "
            else:
                 d_str = f"M {points[0][0]},{points[0][1]} "
                 for p in points[1:]:
                     d_str += f"L {p[0]},{p[1]} "
            
            d_str += "Z " 
            dwg.add(dwg.path(d=d_str, fill=hex_color, stroke='none'))

        dwg.save()
        print(f"Saved Layer: {svg_filename}")

    print(f"Done! Files located in folder: {output_dir}")

if __name__ == "__main__":
    INPUT_IMAGE = "input.jpg" 
    
    # Tip: A width of 800-1000 is usually perfect for stencils. 
    # It is high enough to keep detail, but low enough to smooth out jagged pixel edges.
    create_camouflage_templates(INPUT_IMAGE, max_colors=4, max_width=800)