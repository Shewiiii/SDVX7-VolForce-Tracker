from collections import Counter
from colorsys import rgb_to_hsv
from io import BytesIO

from PIL import Image


def get_accent_color(image_bytes: bytes, threshold: int = 50) -> tuple[int, int, int]:
    """Extract an accent color from image bytes."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image = image.resize((50, 50))
    pixels = list(image.getdata())

    color_counts = Counter(pixels)
    dominant_color = color_counts.most_common(1)[0][0]

    def color_distance(c1, c2):
        return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5

    accent_color = dominant_color
    max_priority = -1

    for color, count in color_counts.items():
        if color_distance(dominant_color, color) > threshold:
            _, saturation, brightness = rgb_to_hsv(
                color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
            )
            priority = saturation * brightness * count

            if priority > max_priority:
                max_priority = priority
                accent_color = color

    return accent_color
