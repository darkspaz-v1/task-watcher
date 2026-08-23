from PIL import Image, ImageDraw

_SIZE = 128  # drawn at 2x and downsampled for crisp anti-aliased edges


def _rounded_badge(color_top, color_bottom, size=_SIZE):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * t)
        grad.putpixel((0, y), (r, g, b))
    grad = grad.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def app_icon():
    """Mint badge, stopwatch glyph."""
    img = _rounded_badge((61, 220, 151), (22, 170, 110))
    d = ImageDraw.Draw(img)
    w = (255, 255, 255, 255)
    d.rounded_rectangle((56, 16, 72, 26), radius=4, fill=w)
    d.ellipse((28, 30, 100, 102), outline=w, width=7)
    d.line((64, 66, 84, 48), fill=w, width=6)
    d.ellipse((60, 62, 68, 70), fill=w)
    return img.resize((64, 64), Image.LANCZOS)
