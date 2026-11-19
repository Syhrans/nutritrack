
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# NutriTrack existing dashboard logo colours
BACKGROUND = "#C9F36B"
N_COLOUR = "#192314"
PLUS_COLOUR = "#5E7B31"

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "frontend" / "public"

# Look for Manrope first, then use a Windows bold font.
FONT_CANDIDATES = [
    PROJECT_DIR / "frontend" / "public" / "fonts" / "Manrope-ExtraBold.ttf",
    PROJECT_DIR / "frontend" / "public" / "fonts" / "Manrope-Bold.ttf",
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\seguisb.ttf"),
]

FONT_PATH = next(
    (path for path in FONT_CANDIDATES if path.exists()),
    None
)

if FONT_PATH is None:
    raise FileNotFoundError(
        "Could not find a suitable bold font on this computer."
    )

def create_icon(size):
    # Draw at a large resolution for smooth edges.
    canvas_size = 1024
    image = Image.new(
        "RGBA",
        (canvas_size, canvas_size),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(image)

    # Rounded lime-green background.
    radius = 342
    draw.rounded_rectangle(
        (0, 0, canvas_size - 1, canvas_size - 1),
        radius=radius,
        fill=BACKGROUND
    )

    # Existing dashboard N+ logo typography.
    font = ImageFont.truetype(str(FONT_PATH), 465)

    n_width = draw.textlength("N", font=font)
    plus_width = draw.textlength("+", font=font)

    total_width = n_width + plus_width

    start_x = (canvas_size - total_width) / 2

    # Draw N and + separately to preserve their colours.
    draw.text(
        (start_x, canvas_size / 2),
        "N",
        font=font,
        fill=N_COLOUR,
        anchor="lm"
    )

    draw.text(
        (start_x + n_width, canvas_size / 2),
        "+",
        font=font,
        fill=PLUS_COLOUR,
        anchor="lm"
    )

    # Resize with high-quality antialiasing.
    image = image.resize(
        (size, size),
        Image.Resampling.LANCZOS
    )

    return image

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    icons = {
        "icon-192.png": 192,
        "icon-512.png": 512,
        "apple-touch-icon.png": 180,
        "favicon-32.png": 32,
    }

    print(f"Using font: {FONT_PATH}")
    print("Generating NutriTrack N+ icons...")

    for filename, size in icons.items():
        image = create_icon(size)
        output_path = OUTPUT_DIR / filename
        image.save(output_path, "PNG")
        print(f"Created: {output_path}")

    print("\nAll NutriTrack icons generated successfully!")

if __name__ == "__main__":
    main()
