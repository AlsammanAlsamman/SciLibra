"""Colours shared by the KV layout and widgets built in Python."""

BG = (0.105, 0.115, 0.135, 1)
PANEL = (0.145, 0.157, 0.184, 1)
ROW = (0.18, 0.192, 0.225, 1)
ROW_GROUP = (0.16, 0.24, 0.22, 1)
ROW_SELECTED = (0.2, 0.38, 0.66, 1)
BUTTON = (0.23, 0.245, 0.285, 1)
ACCENT = (0.26, 0.52, 0.96, 1)
DANGER = (0.78, 0.27, 0.27, 1)
INPUT = (0.2, 0.212, 0.248, 1)
TEXT = (0.93, 0.94, 0.96, 1)
MUTED = (0.62, 0.65, 0.71, 1)
WARN = (1, 0.69, 0.38, 1)
ERROR = (1, 0.5, 0.5, 1)


def darker(color, amount=0.06):
    return tuple(max(0.0, c - amount) for c in color[:3]) + (color[3],)
