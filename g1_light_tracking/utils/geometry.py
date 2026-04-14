import cv2
import numpy as np

def solve_square_pnp(image_points, camera_matrix, dist_coeffs, size_m: float):
    half = size_m / 2.0
    object_points = np.array([
        [-half, -half, 0.0],
        [ half, -half, 0.0],
        [ half,  half, 0.0],
        [-half,  half, 0.0],
    ], dtype=np.float32)
    image_points = np.array(image_points, dtype=np.float32)
    if image_points.shape != (4, 2):
        return None
    ok, rvec, tvec = cv2.solvePnP(
        object_points,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_IPPE_SQUARE,
    )
    if not ok:
        return None
    return rvec, tvec

def dominant_color_bgr(roi):
    if roi is None or roi.size == 0:
        return "unknown"
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mean_h = float(hsv[..., 0].mean())
    mean_s = float(hsv[..., 1].mean())
    mean_v = float(hsv[..., 2].mean())
    if mean_v < 40:
        return "unknown"
    if mean_s < 30 and mean_v > 180:
        return "white"
    if mean_h < 10 or mean_h >= 170:
        return "red"
    if 10 <= mean_h < 35:
        return "yellow"
    if 35 <= mean_h < 85:
        return "green"
    if 85 <= mean_h < 135:
        return "blue"
    return "unknown"

def pixel_to_floor_plane(u, v, camera_matrix, floor_z=0.0):
    fx = camera_matrix[0, 0]
    fy = camera_matrix[1, 1]
    cx = camera_matrix[0, 2]
    cy = camera_matrix[1, 2]
    if fx == 0 or fy == 0:
        return None
    x = (u - cx) / fx
    y = (v - cy) / fy
    if abs(y) < 1e-6:
        return None
    scale = max(0.1, abs((1.0 - floor_z) / y))
    return (float(x * scale), float(scale), float(floor_z))

def bbox_center(x1, y1, x2, y2):
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

def estimate_depth_from_known_width(pixel_width: float, focal_x: float, real_width_m: float):
    if pixel_width <= 1.0 or focal_x <= 1.0 or real_width_m <= 0.0:
        return None
    return float((focal_x * real_width_m) / pixel_width)
