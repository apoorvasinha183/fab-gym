"""Geometry for the permit passes: boxes, carving a box around obstacles, and a walking grid with shortest walks.

The walking grid is 0.5 m cells, eight directions, no cutting a blocked corner; an 8-direction walk overestimates a
straight walk by at most 8.3% (1/cos 22.5 deg), so travel measured on it errs long, the safe side.
"""

import heapq
import math

import numpy as np

STEP = 0.5
SQ2 = math.sqrt(2.0)


def overlap(a, b):
    """Overlap volume of two boxes (x0, y0, z0, x1, y1, z1)."""
    dx = min(a[3], b[3]) - max(a[0], b[0])
    dy = min(a[4], b[4]) - max(a[1], b[1])
    dz = min(a[5], b[5]) - max(a[2], b[2])
    return dx * dy * dz if dx > 0 and dy > 0 and dz > 0 else 0.0


def overlap2(a, b, pad=0.0):
    """Do two boxes' plans overlap (with a gap of pad counted as overlap)?"""
    return min(a[3], b[3]) - max(a[0], b[0]) > -pad and min(a[4], b[4]) - max(a[1], b[1]) > -pad


def inside(a, b, tol=1e-6):
    return all(a[i] >= b[i] - tol for i in range(3)) and all(a[i] <= b[i] + tol for i in range(3, 6))


def carve(box, obstacles, gap=0.1, min_area=0.5):
    """Split a box into pieces that keep clear of every obstacle's plan by gap (where the z ranges meet)."""
    pieces = [box]
    for o in obstacles:
        if min(box[5], o[5]) - max(box[2], o[2]) <= 0:
            continue
        ox0, oy0, ox1, oy1 = o[0] - gap, o[1] - gap, o[3] + gap, o[4] + gap
        out = []
        for p in pieces:
            x0, y0, z0, x1, y1, z1 = p
            if ox1 <= x0 or ox0 >= x1 or oy1 <= y0 or oy0 >= y1:
                out.append(p)
                continue
            if ox0 > x0:
                out.append((x0, y0, z0, ox0, y1, z1))
            if ox1 < x1:
                out.append((ox1, y0, z0, x1, y1, z1))
            cx0, cx1 = max(x0, ox0), min(x1, ox1)
            if oy0 > y0:
                out.append((cx0, y0, z0, cx1, oy0, z1))
            if oy1 < y1:
                out.append((cx0, oy1, z0, cx1, y1, z1))
        pieces = [p for p in out if (p[3] - p[0]) * (p[4] - p[1]) >= min_area]
    return pieces


class Grid:
    """Free cells of one floor of one building, and walks over them."""

    def __init__(self, x0, y0, x1, y1, step=STEP):
        self.x0, self.y0, self.step = x0, y0, step
        self.nx = int(math.floor((x1 - x0) / step))
        self.ny = int(math.floor((y1 - y0) / step))
        self.free = np.ones((self.ny, self.nx), dtype=bool)

    def centre(self, i):
        iy, ix = divmod(i, self.nx)
        return self.x0 + (ix + 0.5) * self.step, self.y0 + (iy + 0.5) * self.step

    def block(self, box, pad=0.1):
        """Block every cell whose centre lies inside the box's plan grown by pad."""
        s = self.step
        ix0 = max(0, int(math.ceil((box[0] - pad - self.x0) / s - 0.5)))
        ix1 = min(self.nx - 1, int(math.floor((box[3] + pad - self.x0) / s - 0.5)))
        iy0 = max(0, int(math.ceil((box[1] - pad - self.y0) / s - 0.5)))
        iy1 = min(self.ny - 1, int(math.floor((box[4] + pad - self.y0) / s - 0.5)))
        if ix0 <= ix1 and iy0 <= iy1:
            self.free[iy0:iy1 + 1, ix0:ix1 + 1] = False

    def cell(self, x, y):
        """The free cell nearest a point (searching outward a few cells)."""
        s = self.step
        cx = min(max(int((x - self.x0) / s), 0), self.nx - 1)
        cy = min(max(int((y - self.y0) / s), 0), self.ny - 1)
        best = None
        for r in range(0, 8):
            for iy in range(cy - r, cy + r + 1):
                for ix in range(cx - r, cx + r + 1):
                    if 0 <= ix < self.nx and 0 <= iy < self.ny and self.free[iy, ix]:
                        d = (ix - cx) ** 2 + (iy - cy) ** 2
                        if best is None or d < best[0]:
                            best = (d, iy * self.nx + ix)
            if best:
                return best[1]
        raise ValueError(f"no free cell near ({x:.1f}, {y:.1f})")

    def prepare(self):
        self.flat = self.free.ravel().tolist()
        n = self.nx * self.ny
        self.dist = [math.inf] * n

    def walk(self, sources, dist=None):
        """Shortest walks from the sources (cell indices), lowering dist where a walk is shorter. Returns dist."""
        nx, ny, s = self.nx, self.ny, self.step
        free = self.flat
        dist = self.dist if dist is None else dist
        h = []
        for i in sources:
            if dist[i] > 0:
                dist[i] = 0.0
                h.append((0.0, i))
        heapq.heapify(h)
        d2 = s * SQ2
        while h:
            d, i = heapq.heappop(h)
            if d > dist[i]:
                continue
            iy, ix = divmod(i, nx)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < nx and 0 <= jy < ny:
                    j = jy * nx + jx
                    if free[j] and d + s < dist[j]:
                        dist[j] = d + s
                        heapq.heappush(h, (d + s, j))
            for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < nx and 0 <= jy < ny:
                    j = jy * nx + jx
                    if free[j] and free[iy * nx + jx] and free[jy * nx + ix] and d + d2 < dist[j]:
                        dist[j] = d + d2
                        heapq.heappush(h, (d + d2, j))
        return dist

    def component(self, seed):
        """Cells reachable from a seed cell (the floor people can stand on)."""
        d = self.walk([seed], [math.inf] * (self.nx * self.ny))
        return [x < math.inf for x in d]

    def farthest(self, reach):
        best, bi = -1.0, None
        for i, (r, d) in enumerate(zip(reach, self.dist)):
            if r and d > best:
                best, bi = d, i
        return best, bi

    def coarse(self, values, k=4):
        """Values on a grid k times coarser (the largest in each block), for drawing."""
        a = np.array([v if v < math.inf else -1.0 for v in values]).reshape(self.ny, self.nx)
        ny, nx = self.ny // k, self.nx // k
        a = a[:ny * k, :nx * k].reshape(ny, k, nx, k).max(axis=(1, 3))
        return a
