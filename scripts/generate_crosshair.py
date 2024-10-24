from PIL import Image, ImageDraw

def create_crosshair(size=400, color=(0, 255, 0)):
    # Create a transparent image
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Calculate dimensions
    center = size // 2
    radius = int(size * 0.48)  # Outer circle radius
    gap = size // 10          # Gap in the center
    line_width = max(2, size // 50)  # Line width scaled with image size
    tick_width = line_width * 2      # Tick marks are thicker
    
    # Draw outer circle
    draw.ellipse(
        [center - radius, center - radius, center + radius, center + radius],
        outline=color,
        width=line_width
    )
    
    # Draw center dot
    dot_radius = max(1, size // 50)
    draw.ellipse(
        [center - dot_radius, center - dot_radius, 
         center + dot_radius, center + dot_radius],
        fill=color
    )
    
    # Draw crosshair lines
    # Vertical lines (top and bottom)
    draw.line([center, size//10, center, center-gap], fill=color, width=line_width)  # Top
    draw.line([center, center+gap, center, size-size//10], fill=color, width=line_width)  # Bottom
    
    # Horizontal lines (left and right)
    draw.line([size//10, center, center-gap, center], fill=color, width=line_width)  # Left
    draw.line([center+gap, center, size-size//10, center], fill=color, width=line_width)  # Right
    
    # Draw tick marks
    tick_length = size // 10
    # Top
    draw.line([center, size*0.15, center, size*0.25], fill=color, width=tick_width)
    # Bottom
    draw.line([center, size*0.75, center, size*0.85], fill=color, width=tick_width)
    # Left
    draw.line([size*0.15, center, size*0.25, center], fill=color, width=tick_width)
    # Right
    draw.line([size*0.75, center, size*0.85, center], fill=color, width=tick_width)
    
    return image

if __name__ == "__main__":
    # Create crosshair image
    crosshair = create_crosshair(400)  # 400x400 pixels
    
    # Save the image
    crosshair.save("crosshair.png")
    print("Crosshair image saved as 'crosshair.png'")