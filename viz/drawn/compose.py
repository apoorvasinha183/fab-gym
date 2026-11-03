"""Stacking a frame (docs/DRAWN-FILM.md): each level's drawing, moved by the camera by its depth (multiplane), laid
over the ones behind it. Each drawing is prepared once however long it is held; frames go straight to ffmpeg."""

import subprocess

import numpy as np
from PIL import Image


def parallax(depth):
    """How much of the camera's move a level takes on screen: all of it for the nearest (depth 0), a third for the
    farthest (depth 1)."""
    return 1.0 / (1.0 + 2.0 * float(depth))


def offset(depth, cam):
    """The screen shift of a level at this depth for a camera at cam (x, y in world pixels)."""
    p = parallax(depth)
    return (-float(cam["x"]) * p, -float(cam["y"]) * p)


class Renderer:
    def __init__(self, drawings, size, anchors=None):
        self.src = drawings                  # name -> PIL image, or a callable name -> PIL image
        self.size = (int(size[0]), int(size[1]))
        self.anchors = anchors or {}         # name -> (x, y) in the drawing: the point the sheet places (its peg)
        self.cache = {}
        self.rendered = 0

    def drawing(self, name):
        if name not in self.cache:
            img = self.src(name) if callable(self.src) else self.src[name]
            self.cache[name] = img.convert("RGBA")
            self.rendered += 1
        return self.cache[name]

    def frame(self, sheet, f):
        W, H = self.size
        cx, cy = W / 2.0, H / 2.0
        cam = sheet.camera_at(f)
        out = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        for lv in sorted(sheet.levels, key=lambda lv: -lv.depth):
            name = lv.timeline[f] if f < len(lv.timeline) else None
            if name is None:
                continue
            img = self.drawing(name)
            p = parallax(lv.depth)
            z = 1.0 + (float(cam["zoom"]) - 1.0) * p
            ox, oy = float(cam["x"]) * p, float(cam["y"]) * p
            ax, ay = sheet.place(lv, f)
            if name in self.anchors:         # a pegged drawing is placed by its anchor, not by its corner
                ax -= float(self.anchors[name][0])
                ay -= float(self.anchors[name][1])
            # output pixel (X, Y) shows world point ((X - c) / z + c + camera); the drawing's pixel is that minus its place
            a, c = 1.0 / z, -cx / z + cx + ox - ax
            e, g = 1.0 / z, -cy / z + cy + oy - ay
            if abs(z - 1.0) < 1e-9 and abs(c - round(c)) < 1e-9 and abs(g - round(g)) < 1e-9:
                # whole-pixel place, no zoom: paste the visible part as it is
                dx, dy = int(round(-c)), int(round(-g))
                sx, sy = max(0, -dx), max(0, -dy)
                px, py = max(0, dx), max(0, dy)
                box = (sx, sy, min(img.width, sx + W - px), min(img.height, sy + H - py))
                if box[2] > box[0] and box[3] > box[1]:
                    out.alpha_composite(img.crop(box), dest=(px, py))
            else:
                t = img.transform((W, H), Image.AFFINE, data=(a, 0.0, c, 0.0, e, g), resample=Image.BILINEAR)
                out.alpha_composite(t)
        return np.asarray(out.convert("RGB"))

    def frames(self, sheet):
        for f in range(sheet.frames):
            yield self.frame(sheet, f)


def pops(frames, cuts=(), share=0.25, delta=8, spike=3.0):
    """Frames that jump (D5): more than `share` of their pixels differ by more than `delta` from the frame before, and
    that share is a spike, over `spike` times the usual change of the frames around it (so a steady pan over detailed
    paint is not a pop). A cut marked there is allowed."""
    moved, prev = [0.0], None
    for fr in frames:
        a = np.asarray(fr, dtype=np.int16)
        if prev is not None:
            moved.append(float((np.abs(a - prev).max(axis=-1) > delta).mean()))
        prev = a
    out = []
    for f in range(1, len(moved)):
        around = [moved[k] for k in range(max(1, f - 3), min(len(moved), f + 4)) if k != f]
        usual = sorted(around)[len(around) // 2] if around else 0.0
        if moved[f] > share and moved[f] > spike * usual + 0.02 and f not in set(cuts):
            out.append(f)
    return out


def encode(renderer, sheet, out, audio=None, crf=18):
    """Stream every frame to ffmpeg as raw pixels: only the video file is written (D7)."""
    W, H = renderer.size
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(sheet.fps), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for fr in renderer.frames(sheet):
            p.stdin.write(np.ascontiguousarray(fr, dtype=np.uint8).tobytes())
    finally:
        p.stdin.close()
        p.wait()
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode})")
    return out
