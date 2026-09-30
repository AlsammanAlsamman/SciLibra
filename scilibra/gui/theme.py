"""Colours and shapes shared by the KV layout and widgets built in Python (Material 3 inspired).

Two palettes are available, "light" (default) and "dark". `apply()` must be called before layout.kv is
loaded, because the KV rules read these module attributes when widgets are created.
"""

import os

# white rounded rectangle, used as a 9-slice background (tinted by background_color) for dialogs
ROUNDED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "rounded.png")
ROUNDED_BORDER = (27, 27, 27, 27)

PALETTES = {
    "light": dict(
        BG=(0.957, 0.953, 0.980, 1),             # window background
        PANEL=(1, 1, 1, 1),                      # cards, dialogs, menus
        ROW=(0.965, 0.961, 0.988, 1),            # list items
        ROW_GROUP=(0.941, 0.945, 0.992, 1),
        ROW_SELECTED=(0.886, 0.871, 1, 1),       # primary container
        BUTTON=(0.918, 0.910, 0.965, 1),         # tonal buttons
        ACCENT=(0.357, 0.298, 0.878, 1),         # primary
        ACCENT_CONTAINER=(0.886, 0.871, 1, 1),
        DANGER=(0.851, 0.231, 0.251, 1),
        DANGER_CONTAINER=(0.992, 0.906, 0.910, 1),
        SUCCESS=(0.118, 0.557, 0.306, 1),
        INPUT=(0.945, 0.937, 0.973, 1),
        OUTLINE=(0.843, 0.831, 0.902, 1),
        TEXT=(0.110, 0.106, 0.133, 1),
        MUTED=(0.392, 0.376, 0.451, 1),
        WARN=(0.718, 0.380, 0.0, 1),
        ERROR=(0.776, 0.157, 0.157, 1),
        SHADOW=(0.180, 0.130, 0.420, 0.16),
        ON_BAR=(1, 1, 1, 1),                      # text on the gradient app bar
        BAR_1=(0.357, 0.298, 0.878, 1),           # app bar gradient
        BAR_2=(0.557, 0.345, 0.953, 1),
    ),
    "dark": dict(
        BG=(0.078, 0.071, 0.094, 1),
        PANEL=(0.114, 0.106, 0.133, 1),
        ROW=(0.145, 0.137, 0.169, 1),
        ROW_GROUP=(0.141, 0.141, 0.188, 1),
        ROW_SELECTED=(0.263, 0.227, 0.478, 1),
        BUTTON=(0.192, 0.180, 0.235, 1),
        ACCENT=(0.639, 0.588, 1, 1),
        ACCENT_CONTAINER=(0.263, 0.227, 0.478, 1),
        DANGER=(0.949, 0.431, 0.431, 1),
        DANGER_CONTAINER=(0.353, 0.133, 0.145, 1),
        SUCCESS=(0.314, 0.769, 0.475, 1),
        INPUT=(0.169, 0.161, 0.200, 1),
        OUTLINE=(0.271, 0.259, 0.325, 1),
        TEXT=(0.925, 0.918, 0.957, 1),
        MUTED=(0.647, 0.635, 0.710, 1),
        WARN=(1, 0.718, 0.412, 1),
        ERROR=(1, 0.557, 0.557, 1),
        SHADOW=(0, 0, 0, 0.45),
        ON_BAR=(1, 1, 1, 1),
        BAR_1=(0.259, 0.196, 0.588, 1),
        BAR_2=(0.408, 0.255, 0.702, 1),
    ),
}

NAME = "light"
globals().update(PALETTES[NAME])

# avatar colours for list items (picked from the item's title)
AVATARS = [(0.357, 0.298, 0.878, 1), (0.063, 0.529, 0.608, 1), (0.804, 0.341, 0.176, 1),
           (0.188, 0.573, 0.318, 1), (0.741, 0.231, 0.494, 1), (0.216, 0.435, 0.851, 1),
           (0.620, 0.447, 0.086, 1), (0.459, 0.337, 0.643, 1)]


def apply(name):
    """Switch palette ("light" or "dark"). Call before layout.kv is loaded."""
    global NAME
    NAME = name if name in PALETTES else "light"
    globals().update(PALETTES[NAME])
    _gradients.clear()


def darker(color, amount=0.06):
    """Pressed-state colour: darker in the light theme, lighter in the dark theme."""
    sign = 1 if NAME == "light" else -1.4
    return tuple(min(1.0, max(0.0, c - amount * sign)) for c in color[:3]) + (color[3],)


def hover(color):
    return darker(color, 0.03)


def on(color):
    """Readable text colour on top of `color` (white on strong colours, TEXT on light ones)."""
    r, g, b = color[:3]
    if len(color) > 3 and color[3] < 0.5:
        return TEXT
    return (1, 1, 1, 1) if 0.299 * r + 0.587 * g + 0.114 * b < 0.6 else (0.110, 0.106, 0.133, 1)


def alpha(color, a):
    return tuple(color[:3]) + (a,)


def avatar(text):
    return AVATARS[sum(ord(c) for c in (text or "?")[:12]) % len(AVATARS)]


def initials(text):
    words = [w for w in (text or "").replace("-", " ").split() if w[:1].isalnum()]
    return (words[0][0] if words else "?").upper()


_gradients = {}


def gradient(c1=None, c2=None):
    """Horizontal gradient texture (needs the window / GL context, so call it from KV)."""
    from kivy.graphics.texture import Texture
    c1, c2 = c1 or BAR_1, c2 or BAR_2
    key = (tuple(c1), tuple(c2))
    if key not in _gradients:
        steps = 64
        buf = bytearray()
        for i in range(steps):
            t = i / (steps - 1)
            buf += bytes(int(255 * (a + (b - a) * t)) for a, b in zip(c1[:3], c2[:3])) + b"\xff"
        tex = Texture.create(size=(steps, 1), colorfmt="rgba")
        tex.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
        tex.wrap = "clamp_to_edge"
        _gradients[key] = tex
    return _gradients[key]
