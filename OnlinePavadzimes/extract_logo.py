from PIL import Image
import sys

def extract_logo(image_path, output_path):
    try:
        img = Image.open(image_path)
        img = img.convert("RGBA")
        
        # We assume the logo is in the top left.
        # Let's crop a safe area first to analyze
        # The image is 552x786. The logo is in the top left corner.
        scan_width = 200
        scan_height = 150
        
        cropped = img.crop((0, 0, scan_width, scan_height))
        
        # Find bounding box of non-white pixels
        bbox = cropped.getbbox()
        
        if bbox:
            # Add some padding
            left, top, right, bottom = bbox
            # Adjust padding if needed, but getbbox is usually tight to non-transparent/black
            # Since the background is likely white, we might need to be careful.
            # getbbox works on the alpha channel usually or black/white.
            # If the image is scanned, the white background might not be perfectly (255, 255, 255).
            
            # Let's try to convert to grayscale and threshold to find "ink"
            gray = cropped.convert("L")
            # Invert so ink is white (high value) and paper is black (low value) for getbbox which looks for non-zero
            from PIL import ImageOps
            inverted = ImageOps.invert(gray)
            
            # Threshold to remove noise (paper grain)
            # Anything lighter than 200 (in original) becomes 0 (in inverted)
            # Original: 0=Black, 255=White.
            # Inverted: 255=Black, 0=White.
            # Wait, ImageOps.invert(0) -> 255.
            # So ink (dark) becomes light (high value). Paper (light) becomes dark (low value).
            # We want to zero out the low values (paper).
            
            threshold = 30 # Threshold for noise
            inverted = inverted.point(lambda p: p if p > threshold else 0)
            
            bbox = inverted.getbbox()
            
            if bbox:
                print(f"Found logo bbox: {bbox}")
                # Crop from the original image using this bbox
                logo = img.crop(bbox)
                logo.save(output_path)
                print(f"Saved logo to {output_path}")
            else:
                print("Could not find logo content (blank area).")
                # Fallback: just crop a fixed size
                img.crop((0, 0, 150, 150)).save(output_path)
        else:
            print("No content found in top-left.")
            img.crop((0, 0, 150, 150)).save(output_path)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract_logo("image.png", "logo.png")
