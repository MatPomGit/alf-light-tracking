#!/usr/bin/env python3
"""
Offline camera calibration from a folder of chessboard images.

Outputs:
1. ROS-compatible YAML calibration file
2. Human-readable text report with:
   - what was processed
   - how many images were accepted/rejected
   - estimated calibration accuracy
   - likely weaknesses in the dataset
   - recommendations for improving future calibration sessions

Example:
    python calibrate_from_folder.py \
        --image-folder calibration/images \
        --board-cols 9 \
        --board-rows 6 \
        --square-size-m 0.024 \
        --output-yaml calibration/camera_intrinsics.yaml \
        --output-report calibration/camera_intrinsics_report.txt
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import glob

import cv2
import numpy as np


@dataclass
class FrameStats:
    path: Path
    accepted: bool
    reason: str
    width: int
    height: int
    center_u: Optional[float] = None
    center_v: Optional[float] = None
    bbox_w: Optional[float] = None
    bbox_h: Optional[float] = None
    mean_corner_shift_px: Optional[float] = None


@dataclass
class CalibrationResult:
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    mean_reprojection_error: float
    per_image_errors: List[float]
    image_size: Tuple[int, int]
    num_samples: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate camera intrinsics from a folder of images.")
    parser.add_argument("--image-folder", required=True, help="Folder with calibration images.")
    parser.add_argument("--image-globs", nargs="+", default=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"])
    parser.add_argument("--recursive", action="store_true", help="Search subdirectories recursively.")
    parser.add_argument("--board-cols", type=int, default=9)
    parser.add_argument("--board-rows", type=int, default=6)
    parser.add_argument("--square-size-m", type=float, default=0.024)
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--min-corner-shift-px", type=float, default=8.0)
    parser.add_argument("--camera-name", default="g1_camera")
    parser.add_argument("--distortion-model", default="plumb_bob")
    parser.add_argument("--output-yaml", required=True)
    parser.add_argument("--output-report", required=True)
    parser.add_argument("--preview-output-dir", default="")
    parser.add_argument("--save-previews", action="store_true")
    parser.add_argument("--adaptive-threshold", action="store_true", default=True)
    parser.add_argument("--normalize-image", action="store_true", default=True)
    parser.add_argument("--fast-check", action="store_true", default=False)
    parser.add_argument("--filter-quads", action="store_true", default=True)
    return parser.parse_args()


def find_images(folder: Path, patterns: List[str], recursive: bool) -> List[Path]:
    paths: List[Path] = []
    for pattern in patterns:
        if recursive:
            paths.extend(Path(p) for p in glob.glob(str(folder / "**" / pattern), recursive=True))
        else:
            paths.extend(Path(p) for p in glob.glob(str(folder / pattern)))
    uniq = sorted({p.resolve() for p in paths if p.is_file()})
    return [Path(p) for p in uniq]


def chessboard_flags(args: argparse.Namespace) -> int:
    flags = 0
    if args.adaptive_threshold:
        flags |= cv2.CALIB_CB_ADAPTIVE_THRESH
    if args.normalize_image:
        flags |= cv2.CALIB_CB_NORMALIZE_IMAGE
    if args.fast_check:
        flags |= cv2.CALIB_CB_FAST_CHECK
    if args.filter_quads:
        flags |= cv2.CALIB_CB_FILTER_QUADS
    return flags


def make_object_points(board_cols: int, board_rows: int, square_size_m: float) -> np.ndarray:
    objp = np.zeros((board_rows * board_cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_cols, 0:board_rows].T.reshape(-1, 2)
    objp *= square_size_m
    return objp


def should_add_sample(previous_corners: Optional[np.ndarray], new_corners: np.ndarray, min_shift_px: float) -> Tuple[bool, Optional[float]]:
    if previous_corners is None:
        return True, None
    mean_dist = float(np.linalg.norm(
        new_corners.reshape(-1, 2) - previous_corners.reshape(-1, 2), axis=1
    ).mean())
    return mean_dist > min_shift_px, mean_dist


def detect_chessboard(
    frame: np.ndarray,
    pattern_size: Tuple[int, int],
    criteria,
    flags: int,
) -> Tuple[bool, Optional[np.ndarray], np.ndarray]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, pattern_size, flags)
    preview = frame.copy()
    if not found or corners is None:
        return False, None, preview
    refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    cv2.drawChessboardCorners(preview, pattern_size, refined, found)
    return True, refined, preview


def corner_distribution_metrics(frame_stats: List[FrameStats], image_size: Tuple[int, int]) -> dict:
    width, height = image_size
    centers = [(fs.center_u, fs.center_v) for fs in frame_stats if fs.accepted and fs.center_u is not None and fs.center_v is not None]
    if not centers:
        return {"coverage_x": 0.0, "coverage_y": 0.0, "center_bias": 1.0}

    xs = [c[0] for c in centers]
    ys = [c[1] for c in centers]
    coverage_x = (max(xs) - min(xs)) / max(width, 1)
    coverage_y = (max(ys) - min(ys)) / max(height, 1)

    img_center = np.array([width / 2.0, height / 2.0], dtype=np.float32)
    dists = [float(np.linalg.norm(np.array([x, y], dtype=np.float32) - img_center)) for x, y in centers]
    max_dist = math.sqrt((width / 2.0) ** 2 + (height / 2.0) ** 2)
    center_bias = float(np.mean(dists) / max(max_dist, 1e-6))
    return {
        "coverage_x": float(coverage_x),
        "coverage_y": float(coverage_y),
        "center_bias": float(center_bias),
    }


def scale_variation_metrics(frame_stats: List[FrameStats]) -> dict:
    sizes = [max(fs.bbox_w or 0.0, fs.bbox_h or 0.0) for fs in frame_stats if fs.accepted and fs.bbox_w and fs.bbox_h]
    if len(sizes) < 2:
        return {"relative_std": 0.0, "min_size": sizes[0] if sizes else 0.0, "max_size": sizes[0] if sizes else 0.0}
    arr = np.array(sizes, dtype=np.float32)
    rel_std = float(arr.std() / max(arr.mean(), 1e-6))
    return {
        "relative_std": rel_std,
        "min_size": float(arr.min()),
        "max_size": float(arr.max()),
    }


def calibrate(
    objpoints: List[np.ndarray],
    imgpoints: List[np.ndarray],
    image_size: Tuple[int, int],
) -> CalibrationResult:
    ok, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        objpoints,
        imgpoints,
        image_size,
        None,
        None,
    )
    if not ok:
        raise RuntimeError("cv2.calibrateCamera returned failure")

    per_image_errors: List[float] = []
    mean_error = 0.0
    for i in range(len(objpoints)):
        imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], camera_matrix, dist_coeffs)
        error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
        per_image_errors.append(float(error))
        mean_error += float(error)
    mean_error /= max(1, len(objpoints))

    return CalibrationResult(
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        mean_reprojection_error=float(mean_error),
        per_image_errors=per_image_errors,
        image_size=image_size,
        num_samples=len(imgpoints),
    )


def write_yaml(
    output_yaml: Path,
    image_size: Tuple[int, int],
    camera_name: str,
    distortion_model: str,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    mean_error: float,
    num_samples: int,
) -> None:
    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "image_width: %d\n"
        "image_height: %d\n"
        "camera_name: %s\n"
        "camera_matrix:\n"
        "  rows: 3\n"
        "  cols: 3\n"
        "  data: [%s]\n"
        "distortion_model: %s\n"
        "distortion_coefficients:\n"
        "  rows: 1\n"
        "  cols: %d\n"
        "  data: [%s]\n"
        "mean_reprojection_error: %.8f\n"
        "num_samples: %d\n"
    ) % (
        image_size[0],
        image_size[1],
        camera_name,
        ", ".join(f"{float(v):.10f}" for v in camera_matrix.reshape(-1)),
        distortion_model,
        int(dist_coeffs.reshape(-1).shape[0]),
        ", ".join(f"{float(v):.10f}" for v in dist_coeffs.reshape(-1)),
        float(mean_error),
        int(num_samples),
    )
    output_yaml.write_text(text, encoding="utf-8")


def quality_label(mean_error: float) -> str:
    if mean_error < 0.20:
        return "excellent"
    if mean_error < 0.35:
        return "good"
    if mean_error < 0.60:
        return "acceptable"
    if mean_error < 1.00:
        return "weak"
    return "poor"


def make_recommendations(
    total_images: int,
    accepted_images: int,
    min_samples: int,
    coverage: dict,
    scale_metrics: dict,
    mean_error: float,
) -> List[str]:
    recs: List[str] = []

    if accepted_images < min_samples:
        recs.append(
            f"Za mało zaakceptowanych zdjęć: {accepted_images}/{min_samples}. "
            "Zbierz więcej ujęć szachownicy z różnych pozycji."
        )

    if coverage["coverage_x"] < 0.45:
        recs.append(
            "Szachownica była zbyt słabo rozłożona poziomo w kadrze. "
            "Na przyszłość wykonaj więcej zdjęć przy lewej i prawej krawędzi obrazu."
        )
    if coverage["coverage_y"] < 0.45:
        recs.append(
            "Szachownica była zbyt słabo rozłożona pionowo w kadrze. "
            "Dodaj ujęcia przy górnej i dolnej części obrazu."
        )
    if coverage["center_bias"] < 0.22:
        recs.append(
            "Ujęcia były zbyt mocno skupione wokół środka obrazu. "
            "To osłabia estymację dystorsji brzegowej."
        )

    if scale_metrics["relative_std"] < 0.18:
        recs.append(
            "Za mała zmienność skali wzorca między zdjęciami. "
            "Dodaj ujęcia z bliska i z daleka."
        )

    if mean_error >= 0.60:
        recs.append(
            "Błąd reprojekcji jest wysoki. Sprawdź ostrość zdjęć, poprawność rozmiaru pól "
            "szachownicy oraz czy wzorzec był płaski i dobrze widoczny."
        )

    if total_images > 0 and accepted_images / total_images < 0.5:
        recs.append(
            "Duża część zdjęć została odrzucona. Warto poprawić oświetlenie, kontrast wzorca "
            "albo sprawdzić, czy liczba kolumn/wierszy szachownicy jest ustawiona poprawnie."
        )

    if not recs:
        recs.append(
            "Zestaw wygląda sensownie. Na przyszłość nadal warto dodawać kilka ujęć przy skrajach "
            "kadru oraz w większym zakresie odległości, żeby zwiększyć odporność kalibracji."
        )

    return recs


def write_report(
    output_report: Path,
    image_folder: Path,
    total_images: int,
    frame_stats: List[FrameStats],
    result: Optional[CalibrationResult],
    board_cols: int,
    board_rows: int,
    square_size_m: float,
    min_samples: int,
) -> None:
    output_report.parent.mkdir(parents=True, exist_ok=True)

    accepted = [fs for fs in frame_stats if fs.accepted]
    rejected = [fs for fs in frame_stats if not fs.accepted]
    accepted_images = len(accepted)

    lines: List[str] = []
    lines.append("RAPORT KALIBRACJI KAMERY")
    lines.append("")
    lines.append("1. Co zostało zrobione")
    lines.append(
        f"- Przetworzono zdjęcia z folderu: {image_folder}"
    )
    lines.append(
        f"- Użyto wzorca szachownicy {board_cols}x{board_rows} o rozmiarze pola {square_size_m:.6f} m"
    )
    lines.append(
        f"- Łączna liczba znalezionych plików: {total_images}"
    )
    lines.append(
        f"- Liczba zaakceptowanych próbek: {accepted_images}"
    )
    lines.append(
        f"- Minimalna wymagana liczba próbek: {min_samples}"
    )
    lines.append("")

    reason_counts = {}
    for fs in rejected:
        reason_counts[fs.reason] = reason_counts.get(fs.reason, 0) + 1

    lines.append("2. Co się udało, a co nie")
    lines.append(f"- Zaakceptowane zdjęcia: {accepted_images}")
    lines.append(f"- Odrzucone zdjęcia: {len(rejected)}")
    if reason_counts:
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"  - Odrzucone z powodu '{reason}': {count}")
    lines.append("")

    if result is None:
        lines.append("3. Wynik")
        lines.append("- Kalibracja NIE została wykonana.")
        lines.append("- Powód: za mało poprawnych próbek lub nie udało się policzyć modelu kamery.")
        lines.append("")
        recs = make_recommendations(
            total_images=total_images,
            accepted_images=accepted_images,
            min_samples=min_samples,
            coverage={"coverage_x": 0.0, "coverage_y": 0.0, "center_bias": 1.0},
            scale_metrics={"relative_std": 0.0},
            mean_error=999.0,
        )
        lines.append("4. Czego brakowało")
        lines.append(
            "- Brak wystarczającej liczby poprawnych, zróżnicowanych ujęć wzorca."
        )
        lines.append("")
        lines.append("5. Co poprawić na przyszłość")
        for rec in recs:
            lines.append(f"- {rec}")
        output_report.write_text("\n".join(lines), encoding="utf-8")
        return

    coverage = corner_distribution_metrics(frame_stats, result.image_size)
    scale_metrics = scale_variation_metrics(frame_stats)
    qlabel = quality_label(result.mean_reprojection_error)
    recs = make_recommendations(
        total_images=total_images,
        accepted_images=accepted_images,
        min_samples=min_samples,
        coverage=coverage,
        scale_metrics=scale_metrics,
        mean_error=result.mean_reprojection_error,
    )

    lines.append("3. Wynik kalibracji")
    lines.append(f"- Rozdzielczość obrazów: {result.image_size[0]}x{result.image_size[1]}")
    lines.append(f"- Liczba próbek użytych do estymacji: {result.num_samples}")
    lines.append(f"- Średni błąd reprojekcji: {result.mean_reprojection_error:.6f} px")
    lines.append(f"- Jakość wyniku: {qlabel}")
    lines.append(f"- Błąd minimalny na obraz: {min(result.per_image_errors):.6f} px")
    lines.append(f"- Błąd maksymalny na obraz: {max(result.per_image_errors):.6f} px")
    lines.append("")

    lines.append("4. Ocena kompletności danych")
    lines.append(f"- Pokrycie poziome kadru przez wzorzec: {coverage['coverage_x']:.3f}")
    lines.append(f"- Pokrycie pionowe kadru przez wzorzec: {coverage['coverage_y']:.3f}")
    lines.append(f"- Bias do środka kadru (niżej = bardziej centralnie): {coverage['center_bias']:.3f}")
    lines.append(f"- Zmienność skali wzorca: {scale_metrics['relative_std']:.3f}")
    lines.append("")

    lines.append("5. Czego brakowało / słabe strony zestawu")
    found_any = False
    if coverage["coverage_x"] < 0.45:
        lines.append("- Za mało ujęć przy bocznych krawędziach obrazu.")
        found_any = True
    if coverage["coverage_y"] < 0.45:
        lines.append("- Za mało ujęć przy górnych i dolnych krawędziach obrazu.")
        found_any = True
    if coverage["center_bias"] < 0.22:
        lines.append("- Zbyt dużo zdjęć było wykonanych blisko środka kadru.")
        found_any = True
    if scale_metrics["relative_std"] < 0.18:
        lines.append("- Za mała różnorodność odległości wzorca od kamery.")
        found_any = True
    if result.mean_reprojection_error >= 0.60:
        lines.append("- Dokładność wyniku jest słaba lub graniczna.")
        found_any = True
    if not found_any:
        lines.append("- Nie wykryto oczywistych braków w rozkładzie próbek.")
    lines.append("")

    lines.append("6. Co naprawić na przyszłość")
    for rec in recs:
        lines.append(f"- {rec}")
    lines.append("")

    lines.append("7. Uwagi operacyjne")
    lines.append("- Najlepiej zbierać zdjęcia ostre, dobrze oświetlone, bez poruszenia.")
    lines.append("- Wzorzec powinien być płaski i widoczny w całości.")
    lines.append("- Warto robić zdjęcia pod różnymi kątami, z różnej odległości i przy krawędziach kadru.")
    lines.append("- Jeżeli wynik jest słaby, sprawdź czy board_cols/board_rows odpowiadają realnemu wzorcowi.")
    lines.append("")

    output_report.write_text("\n".join(lines), encoding="utf-8")


def save_preview(preview_dir: Path, frame_path: Path, preview: np.ndarray, accepted: bool) -> None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    prefix = "accepted" if accepted else "rejected"
    out_path = preview_dir / f"{prefix}_{frame_path.stem}.png"
    cv2.imwrite(str(out_path), preview)


def main() -> int:
    args = parse_args()

    image_folder = Path(args.image_folder)
    if not image_folder.is_absolute():
        image_folder = (Path.cwd() / image_folder).resolve()
    if not image_folder.exists() or not image_folder.is_dir():
        print(f"ERROR: image folder does not exist: {image_folder}")
        return 2

    output_yaml = Path(args.output_yaml)
    if not output_yaml.is_absolute():
        output_yaml = (Path.cwd() / output_yaml).resolve()

    output_report = Path(args.output_report)
    if not output_report.is_absolute():
        output_report = (Path.cwd() / output_report).resolve()

    preview_dir = None
    if args.save_previews:
        preview_dir = Path(args.preview_output_dir) if args.preview_output_dir else output_yaml.parent / "previews"
        if not preview_dir.is_absolute():
            preview_dir = (Path.cwd() / preview_dir).resolve()

    image_paths = find_images(image_folder, args.image_globs, args.recursive)
    if not image_paths:
        print(f"ERROR: no images found in {image_folder}")
        return 3

    pattern_size = (args.board_cols, args.board_rows)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    flags = chessboard_flags(args)
    objp = make_object_points(args.board_cols, args.board_rows, args.square_size_m)

    objpoints: List[np.ndarray] = []
    imgpoints: List[np.ndarray] = []
    frame_stats: List[FrameStats] = []

    previous_corners: Optional[np.ndarray] = None
    image_size: Optional[Tuple[int, int]] = None

    for path in image_paths:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            frame_stats.append(FrameStats(path=path, accepted=False, reason="read_failed", width=0, height=0))
            continue

        h, w = frame.shape[:2]
        image_size = (w, h) if image_size is None else image_size

        found, corners, preview = detect_chessboard(frame, pattern_size, criteria, flags)
        if not found or corners is None:
            frame_stats.append(FrameStats(path=path, accepted=False, reason="not_found", width=w, height=h))
            if preview_dir is not None:
                save_preview(preview_dir, path, preview, accepted=False)
            continue

        corners_2d = corners.reshape(-1, 2)
        min_xy = corners_2d.min(axis=0)
        max_xy = corners_2d.max(axis=0)
        bbox_w = float(max_xy[0] - min_xy[0])
        bbox_h = float(max_xy[1] - min_xy[1])
        center = corners_2d.mean(axis=0)

        accept, shift = should_add_sample(previous_corners, corners, args.min_corner_shift_px)
        if accept:
            objpoints.append(objp.copy())
            imgpoints.append(corners)
            previous_corners = corners
            frame_stats.append(
                FrameStats(
                    path=path,
                    accepted=True,
                    reason="accepted",
                    width=w,
                    height=h,
                    center_u=float(center[0]),
                    center_v=float(center[1]),
                    bbox_w=bbox_w,
                    bbox_h=bbox_h,
                    mean_corner_shift_px=shift,
                )
            )
            label = f"accepted {len(imgpoints)}/{args.min_samples}"
            color = (0, 255, 0)
        else:
            frame_stats.append(
                FrameStats(
                    path=path,
                    accepted=False,
                    reason="too_similar",
                    width=w,
                    height=h,
                    center_u=float(center[0]),
                    center_v=float(center[1]),
                    bbox_w=bbox_w,
                    bbox_h=bbox_h,
                    mean_corner_shift_px=shift,
                )
            )
            label = "rejected: too_similar"
            color = (0, 165, 255)

        cv2.putText(preview, label, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        if preview_dir is not None:
            save_preview(preview_dir, path, preview, accepted=accept)

    result: Optional[CalibrationResult] = None
    if image_size is not None and len(imgpoints) >= args.min_samples:
        result = calibrate(objpoints, imgpoints, image_size)
        write_yaml(
            output_yaml=output_yaml,
            image_size=result.image_size,
            camera_name=args.camera_name,
            distortion_model=args.distortion_model,
            camera_matrix=result.camera_matrix,
            dist_coeffs=result.dist_coeffs,
            mean_error=result.mean_reprojection_error,
            num_samples=result.num_samples,
        )

    write_report(
        output_report=output_report,
        image_folder=image_folder,
        total_images=len(image_paths),
        frame_stats=frame_stats,
        result=result,
        board_cols=args.board_cols,
        board_rows=args.board_rows,
        square_size_m=args.square_size_m,
        min_samples=args.min_samples,
    )

    if result is None:
        print(f"Calibration report written to: {output_report}")
        print("Calibration YAML not produced.")
        return 4

    print(f"Calibration YAML written to:   {output_yaml}")
    print(f"Calibration report written to: {output_report}")
    print(f"Mean reprojection error:       {result.mean_reprojection_error:.6f} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
