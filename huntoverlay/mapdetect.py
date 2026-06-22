# On-screen map recognition.
#
# Given the four reference map images in the maps/ folder (named by their
# data.json index, e.g. 1.webp), this module identifies which map is currently
# shown on screen by comparing a captured screen region against each reference.
#
# The match is a grayscale, downscaled, zero-normalized cross correlation (ZNCC).
# Each reference is compared at four rotations because the in-game map is drawn
# rotated relative to the reference art (see helpers.rotate90cw_norm). This makes
# the matcher tolerant of orientation without needing to know the exact rotation.
import os
import math

from PySide6 import QtCore, QtGui

from .paths import bd

# Side length of the square the images are reduced to before comparison.
# Small enough to be fast and to wash out the overlay dots, large enough to
# keep each map distinguishable.
GRID = 32

# Minimum correlation for a match to be considered confident. Below this the
# caller may still use the best guess but should warn the user.
MATCH_THRESHOLD = 0.15


def maps_dir() -> str:
    return os.path.join(bd(), "maps")


def _vec_from_qimage(qimg: QtGui.QImage):
    """
    Reduce an image to a zero-mean, unit-length grayscale feature vector.
    Returns None if the image is empty.
    """
    if qimg is None or qimg.isNull():
        return None

    img = qimg.convertToFormat(QtGui.QImage.Format_Grayscale8).scaled(
        GRID, GRID, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation
    )

    vals = []
    for y in range(GRID):
        for x in range(GRID):
            vals.append(float(QtGui.qGray(img.pixel(x, y))))

    n = len(vals)
    if n == 0:
        return None

    mean = sum(vals) / n
    centered = [v - mean for v in vals]
    norm = math.sqrt(sum(c * c for c in centered))
    if norm <= 0.0:
        return None

    return [c / norm for c in centered]


def _rotation_vectors(qimg: QtGui.QImage):
    """Feature vectors for the image at 0, 90, 180 and 270 degrees."""
    out = []
    for ang in (0, 90, 180, 270):
        rotated = qimg if ang == 0 else qimg.transformed(QtGui.QTransform().rotate(ang))
        vec = _vec_from_qimage(rotated)
        if vec is not None:
            out.append(vec)
    return out


class MapMatcher:
    """
    Holds the reference feature vectors and matches a captured region against them.
    index_to_name maps a data.json map index (e.g. 1) to its map name.
    """
    def __init__(self, index_to_name: dict):
        self.refs = []  # list of (name, [rotation_vectors])
        d = maps_dir()
        for idx, name in index_to_name.items():
            path = os.path.join(d, f"{idx}.webp")
            if not os.path.isfile(path):
                continue
            img = QtGui.QImage(path)
            if img.isNull():
                continue
            vecs = _rotation_vectors(img)
            if vecs:
                self.refs.append((str(name), vecs))

    def available(self) -> bool:
        return len(self.refs) > 0

    def detect(self, region: QtGui.QImage):
        """
        Returns (best_map_name, score). score is a correlation in [-1, 1].
        Returns (None, 0.0) when no reference or region is usable.
        """
        cap = _vec_from_qimage(region)
        if cap is None or not self.refs:
            return None, 0.0

        best_name, best_score = None, -2.0
        for name, rot_vecs in self.refs:
            for rv in rot_vecs:
                s = 0.0
                for a, b in zip(cap, rv):
                    s += a * b
                if s > best_score:
                    best_score = s
                    best_name = name

        return best_name, best_score
