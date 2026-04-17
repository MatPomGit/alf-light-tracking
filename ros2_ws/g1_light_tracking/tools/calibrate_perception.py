#!/usr/bin/env python3
"""
Narzędzie CLI do kalibracji progów percepcji na podstawie nagrania wideo.

Wejścia:
- `--video`: ścieżka do pliku wideo z wzorcową plamką świetlną.
- `--output-config`: ścieżka pliku YAML z wynikową konfiguracją percepcji.
- `--output-report`: ścieżka raportu Markdown z metrykami i decyzją kalibracji.
- `--sample-step`: co ile klatek wykonywać analizę (np. 3 = co trzecia klatka).
- `--max-frames`: maksymalna liczba przeanalizowanych klatek wejściowych.
- `--debug-dir`: opcjonalny katalog na obrazy diagnostyczne.

Wyjścia:
- Plik konfiguracyjny YAML z parametrami sekcji `light_spot_detector_node.ros__parameters`.
- Raport Markdown opisujący próbkę, statystyki i powód ewentualnego odrzucenia kalibracji.
- Kod zakończenia 0 dla poprawnego przebiegu (również gdy wynik to "brak wiarygodnych parametrów").

Założenie bezpieczeństwa:
- Jeżeli próbka jest zbyt mała albo statystyki są niestabilne, narzędzie kończy kalibrację
  stanem "brak wiarygodnych parametrów" i nie zaostrza progów (preferujemy brak wyniku
  nad ryzykiem błędnej detekcji).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


# [AI-CHANGE | 2026-04-17 13:13 UTC | v0.99]
# CO ZMIENIONO: Dodano jawne dołączenie katalogu pakietu ROS2 do `sys.path`, aby
# narzędzie uruchamiane przez `python ...` mogło importować pipeline detekcji bez noda ROS.
# DLACZEGO: Skrypt działa poza środowiskiem ROS launch i bez tej ścieżki import mógłby się nie udać.
# JAK TO DZIAŁA: Ścieżka repozytorium `ros2_ws/g1_light_tracking` jest dopinana do `sys.path`
# tylko gdy nie występuje jeszcze na liście, co zachowuje deterministyczne rozwiązywanie modułów.
# TODO: Zastąpić manipulację `sys.path` przez instalowalny entry-point w `setup.py` (console_scripts).
REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "ros2_ws" / "g1_light_tracking"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from g1_light_tracking.vision.detector_interfaces import DetectorConfig
from g1_light_tracking.vision.detectors import detect_spots_with_config


@dataclass
class FrameMetrics:
    """Pojedynczy zestaw metryk detekcji wyliczony dla jednej klatki."""

    frame_index: int
    detected: bool
    confidence: float
    score_proxy: float
    area: float
    circularity: float
    mean_contrast: float
    peak_sharpness: float
    saturated_ratio: float


@dataclass
class CalibrationStats:
    """Zbiorcze statystyki analizy klipu potrzebne do wyznaczania progów."""

    sampled_frames: int
    analyzed_frames: int
    detection_count: int
    detection_ratio: float
    stable: bool
    reliable: bool
    rejection_reason: Optional[str]
    metrics: List[FrameMetrics]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kalibracja progów percepcji na podstawie nagrania wideo.")
    parser.add_argument("--video", required=True, help="Ścieżka do nagrania wzorcowej plamki.")
    parser.add_argument(
        "--output-config",
        default="ros2_ws/g1_light_tracking/config/perception.yaml",
        help="Ścieżka wyjściowego pliku YAML z konfiguracją percepcji.",
    )
    parser.add_argument(
        "--output-report",
        default="calibration_report.md",
        help="Ścieżka wyjściowego raportu Markdown.",
    )
    parser.add_argument(
        "--sample-step",
        type=int,
        default=3,
        help="Co ile klatek wykonywać analizę (>=1).",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=900,
        help="Limit przetwarzanych klatek wejściowych (>=1).",
    )
    parser.add_argument(
        "--debug-dir",
        default=None,
        help="Opcjonalny katalog na obrazy diagnostyczne.",
    )
    return parser


def _score_proxy(confidence: float, circularity: float, mean_contrast: float, peak_sharpness: float, saturated_ratio: float) -> float:
    """Liczy przybliżony wynik jakości kandydata na podstawie kluczowych metryk fotometrycznych."""
    contrast_norm = float(np.clip((mean_contrast + 64.0) / 128.0, 0.0, 1.0))
    sharpness_norm = float(np.clip((peak_sharpness + 32.0) / 128.0, 0.0, 1.0))
    return float(
        np.clip(
            (0.45 * confidence)
            + (0.20 * float(np.clip(circularity, 0.0, 1.0)))
            + (0.20 * contrast_norm)
            + (0.15 * sharpness_norm)
            - (0.20 * float(np.clip(saturated_ratio, 0.0, 1.0))),
            0.0,
            1.0,
        )
    )


def _estimate_intensity_metrics(frame_bgr: np.ndarray, detection: Any) -> tuple[float, float, float]:
    """Szacuje metryki kontrastu/ostrości/saturacji lokalnie wokół detekcji."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x = int(round(float(detection.x)))
    y = int(round(float(detection.y)))
    radius = max(3, int(round(float(detection.radius))))

    inner_r = radius
    ring_inner = radius + 2
    ring_outer = radius + 6

    yy, xx = np.ogrid[:h, :w]
    dist2 = (xx - x) ** 2 + (yy - y) ** 2
    inner_mask = dist2 <= (inner_r * inner_r)
    ring_mask = (dist2 >= (ring_inner * ring_inner)) & (dist2 <= (ring_outer * ring_outer))

    inside = gray[inner_mask]
    ring = gray[ring_mask]
    if inside.size < 8 or ring.size < 8:
        return 0.0, 0.0, 1.0

    mean_contrast = float(np.mean(inside) - np.mean(ring))
    peak_sharpness = float(np.percentile(inside, 95) - np.percentile(ring, 95))
    saturated_ratio = float(np.mean(inside >= 250))
    return mean_contrast, peak_sharpness, saturated_ratio


def analyze_video(
    video_path: Path,
    sample_step: int,
    max_frames: int,
    debug_dir: Optional[Path],
) -> CalibrationStats:
    """Analizuje klip i zbiera metryki jakości detekcji dla próbek klatek.

    Args:
        video_path: Ścieżka do pliku z nagraniem wzorcowej plamki.
        sample_step: Co ile klatek wykonywać inferencję detektora (wartość >= 1).
        max_frames: Maksymalna liczba kolejnych klatek pobrana z wejścia (>= 1).
        debug_dir: Opcjonalna ścieżka do katalogu z obrazami diagnostycznymi.

    Returns:
        CalibrationStats: Zbiorcze statystyki procesu (liczność próbek, stabilność,
        wiarygodność i lista metryk per-klatka) potrzebne do wyznaczenia progów.
    """

    # [AI-CHANGE | 2026-04-17 13:13 UTC | v0.99]
    # CO ZMIENIONO: Dodano pętlę analizy klipu korzystającą z istniejącego pipeline
    # `detect_spots_with_config` i rejestrującą metryki jakości każdej detekcji.
    # DLACZEGO: Kalibracja ma bazować na realnych danych z modułu produkcyjnego,
    # aby strojenie odpowiadało zachowaniu używanemu podczas pracy robota.
    # JAK TO DZIAŁA: Dla próbkowanych klatek uruchamiany jest detektor, a potem
    # zapisujemy confidence, score_proxy, area, circularity, mean_contrast,
    # peak_sharpness i saturated_ratio; brak detekcji zapisujemy jako `detected=False`.
    # TODO: Dodać alternatywę z odczytem surowych kandydatów przed filtrem rankingu,
    # aby raportować także statystyki odrzuceń top1-vs-top2.
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Nie udało się otworzyć pliku wideo: {video_path}")

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)

    config = DetectorConfig(track_mode="brightness", max_spots=1)
    frame_idx = 0
    sampled_frames = 0
    analyzed_frames = 0
    metrics: List[FrameMetrics] = []

    while frame_idx < max_frames:
        ok, frame = cap.read()
        if not ok:
            break

        sampled_frames += 1
        if frame_idx % sample_step != 0:
            frame_idx += 1
            continue

        analyzed_frames += 1
        detections, mask, _roi, _diagnostics = detect_spots_with_config(frame, config)

        if detections:
            det = detections[0]
            mean_contrast, peak_sharpness, saturated_ratio = _estimate_intensity_metrics(frame, det)
            score = _score_proxy(
                confidence=float(det.confidence),
                circularity=float(det.circularity),
                mean_contrast=mean_contrast,
                peak_sharpness=peak_sharpness,
                saturated_ratio=saturated_ratio,
            )
            metrics.append(
                FrameMetrics(
                    frame_index=frame_idx,
                    detected=True,
                    confidence=float(det.confidence),
                    score_proxy=score,
                    area=float(det.area),
                    circularity=float(det.circularity),
                    mean_contrast=float(mean_contrast),
                    peak_sharpness=float(peak_sharpness),
                    saturated_ratio=float(saturated_ratio),
                )
            )

            if debug_dir is not None:
                debug = frame.copy()
                cv2.circle(debug, (int(round(det.x)), int(round(det.y))), int(max(2, round(det.radius))), (0, 255, 0), 2)
                cv2.putText(debug, f"c={det.confidence:.2f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.imwrite(str(debug_dir / f"frame_{frame_idx:06d}.png"), debug)
                cv2.imwrite(str(debug_dir / f"mask_{frame_idx:06d}.png"), mask)
        else:
            metrics.append(
                FrameMetrics(
                    frame_index=frame_idx,
                    detected=False,
                    confidence=0.0,
                    score_proxy=0.0,
                    area=0.0,
                    circularity=0.0,
                    mean_contrast=0.0,
                    peak_sharpness=0.0,
                    saturated_ratio=1.0,
                )
            )

        frame_idx += 1

    cap.release()

    detection_count = sum(1 for item in metrics if item.detected)
    detection_ratio = (detection_count / analyzed_frames) if analyzed_frames > 0 else 0.0

    detected_metrics = [m for m in metrics if m.detected]
    stable = True
    rejection_reason: Optional[str] = None

    if analyzed_frames < 10 or detection_count < 8:
        stable = False
        rejection_reason = "Zbyt mała próbka do wiarygodnej estymacji"
    else:
        confidence_values = np.array([m.confidence for m in detected_metrics], dtype=float)
        contrast_values = np.array([m.mean_contrast for m in detected_metrics], dtype=float)
        sharpness_values = np.array([m.peak_sharpness for m in detected_metrics], dtype=float)
        if confidence_values.size == 0:
            stable = False
            rejection_reason = "Brak detekcji po analizie próbek"
        else:
            conf_std = float(np.std(confidence_values))
            contrast_std = float(np.std(contrast_values))
            sharpness_std = float(np.std(sharpness_values))
            if conf_std > 0.18 or contrast_std > 20.0 or sharpness_std > 25.0 or detection_ratio < 0.35:
                stable = False
                rejection_reason = "Niestabilne statystyki detekcji między próbkami"

    reliable = stable and rejection_reason is None
    return CalibrationStats(
        sampled_frames=sampled_frames,
        analyzed_frames=analyzed_frames,
        detection_count=detection_count,
        detection_ratio=detection_ratio,
        stable=stable,
        reliable=reliable,
        rejection_reason=rejection_reason,
        metrics=metrics,
    )


def derive_thresholds(stats: CalibrationStats) -> Dict[str, Optional[float]]:
    """Wyprowadza bezpieczne progi detekcji z danych statystycznych.

    Args:
        stats: Wynik `analyze_video(...)` zawierający listę metryk i ocenę wiarygodności.

    Returns:
        Słownik progów. Jeśli kalibracja nie jest wiarygodna, wartości progów są `None`.
    """

    # [AI-CHANGE | 2026-04-17 13:13 UTC | v0.99]
    # CO ZMIENIONO: Dodano etap wyznaczania progów z konserwatywnymi kwantylami
    # oraz twardym warunkiem odrzucenia kalibracji przy niestabilnych danych.
    # DLACZEGO: Projekt wymaga polityki bezpieczeństwa „lepiej brak niż błędna detekcja”,
    # więc nie wolno produkować agresywnych progów przy słabej próbce.
    # JAK TO DZIAŁA: Dla wiarygodnych danych stosujemy percentyle odporne na outliery;
    # dla niewiarygodnych zwracamy `None`, co blokuje automatyczne zaostrzenie progów.
    # TODO: Rozszerzyć stabilność o test driftu czasowego (początek vs koniec nagrania).
    if not stats.reliable:
        return {
            "min_detection_confidence": None,
            "min_detection_score": None,
            "min_area": None,
            "min_mean_contrast": None,
            "min_peak_sharpness": None,
            "max_saturated_ratio": None,
        }

    detected = [m for m in stats.metrics if m.detected]
    conf = np.array([m.confidence for m in detected], dtype=float)
    score = np.array([m.score_proxy for m in detected], dtype=float)
    area = np.array([m.area for m in detected], dtype=float)
    contrast = np.array([m.mean_contrast for m in detected], dtype=float)
    sharpness = np.array([m.peak_sharpness for m in detected], dtype=float)
    sat = np.array([m.saturated_ratio for m in detected], dtype=float)

    return {
        "min_detection_confidence": float(max(0.0, min(0.95, np.percentile(conf, 15)))),
        "min_detection_score": float(max(0.0, min(0.95, np.percentile(score, 15)))),
        "min_area": float(max(3.0, np.percentile(area, 10))),
        "min_mean_contrast": float(max(0.0, np.percentile(contrast, 20))),
        "min_peak_sharpness": float(max(0.0, np.percentile(sharpness, 20))),
        "max_saturated_ratio": float(max(0.05, min(0.98, np.percentile(sat, 85)))),
    }


def build_perception_config(thresholds: Dict[str, Optional[float]], stats: CalibrationStats) -> Dict[str, Any]:
    """Buduje strukturę wynikowej konfiguracji percepcji do zapisu w YAML.

    Args:
        thresholds: Progi zwrócone przez `derive_thresholds(...)`.
        stats: Statystyki analizy, używane do decyzji czy stosować wartości kalibracji.

    Returns:
        Słownik reprezentujący sekcję YAML dla `light_spot_detector_node`.
    """

    params: Dict[str, Any] = {
        "camera_topic": "/camera/image_raw",
        "detection_topic": "/light_tracking/detection_json",
        "camera_frame": "camera_link",
        "brightness_threshold": 245,
        "min_area": 6.0,
        "min_detection_confidence": 0.62,
        "min_detection_score": 0.0,
        "min_top1_top2_margin": 0.0,
        "min_mean_contrast": 4.0,
        "min_peak_sharpness": 6.0,
        "max_saturated_ratio": 0.35,
        "min_persistence_frames": 1,
        "blur_kernel": 5,
        "morph_kernel": 3,
        "legacy_mode": False,
    }

    # [AI-CHANGE | 2026-04-17 13:13 UTC | v0.99]
    # CO ZMIENIONO: Dodano bezpieczne budowanie konfiguracji wynikowej zależnie od
    # wiarygodności kalibracji, z zachowaniem konserwatywnych wartości bazowych.
    # DLACZEGO: Przy niestabilnej próbce nie wolno wymuszać agresywnych progów,
    # które mogłyby powodować błędne detekcje w runtime.
    # JAK TO DZIAŁA: Gdy `stats.reliable=False`, zwracane są wyłącznie bazowe parametry.
    # Gdy `True`, nadpisujemy tylko wybrane progi wartościami z kalibracji.
    # TODO: Dodać merge z istniejącym plikiem YAML, aby zachować ustawienia specyficzne dla robota.
    if stats.reliable:
        for key, value in thresholds.items():
            if value is not None:
                params[key] = float(value)

    return {"light_spot_detector_node": {"ros__parameters": params}}


def _to_yaml_text(config: Dict[str, Any]) -> str:
    """Konwertuje słownik konfiguracji do prostego tekstu YAML bez zależności zewnętrznych."""
    params = config["light_spot_detector_node"]["ros__parameters"]
    lines = ["light_spot_detector_node:", "  ros__parameters:"]
    for key, value in params.items():
        if isinstance(value, bool):
            val = "true" if value else "false"
        elif isinstance(value, str):
            val = value
        else:
            val = f"{value}"
        lines.append(f"    {key}: {val}")
    return "\n".join(lines) + "\n"


def write_report(report_path: Path, stats: CalibrationStats, thresholds: Dict[str, Optional[float]], config_path: Path) -> None:
    """Zapisuje raport Markdown z przebiegu kalibracji i końcową decyzją bezpieczeństwa.

    Args:
        report_path: Docelowa ścieżka pliku raportu.
        stats: Statystyki zwrócone przez `analyze_video(...)`.
        thresholds: Progi zwrócone przez `derive_thresholds(...)`.
        config_path: Ścieżka pliku YAML zapisanego po kalibracji.

    Returns:
        None. Funkcja tworzy raport na dysku.
    """

    detected = [m for m in stats.metrics if m.detected]
    med_conf = median([m.confidence for m in detected]) if detected else 0.0
    med_score = median([m.score_proxy for m in detected]) if detected else 0.0

    status = "✅ wiarygodna" if stats.reliable else "⚠️ brak wiarygodnych parametrów"
    reason = stats.rejection_reason or "brak"

    lines = [
        "# Raport kalibracji percepcji",
        "",
        f"- Data UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Status kalibracji: **{status}**",
        f"- Powód odrzucenia: **{reason}**",
        f"- Przeanalizowane klatki: **{stats.analyzed_frames}** / próbkowane: **{stats.sampled_frames}**",
        f"- Liczba detekcji: **{stats.detection_count}** (ratio={stats.detection_ratio:.3f})",
        f"- Mediana confidence: **{med_conf:.3f}**",
        f"- Mediana score_proxy: **{med_score:.3f}**",
        "",
        "## Wyznaczone progi",
        "",
    ]
    for key, value in thresholds.items():
        shown = "BRAK (kalibracja odrzucona)" if value is None else f"{value:.4f}"
        lines.append(f"- `{key}`: {shown}")

    lines.extend(
        [
            "",
            "## Wynik",
            "",
            f"- Plik konfiguracji: `{config_path}`",
            "- Polityka bezpieczeństwa: przy niestabilnych danych pozostawiono bezpieczne ustawienia bazowe.",
        ]
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.sample_step < 1:
        parser.error("--sample-step musi być >= 1")
    if args.max_frames < 1:
        parser.error("--max-frames musi być >= 1")

    video_path = Path(args.video).expanduser().resolve()
    output_config = Path(args.output_config).expanduser()
    output_report = Path(args.output_report).expanduser()
    debug_dir = Path(args.debug_dir).expanduser() if args.debug_dir else None

    stats = analyze_video(
        video_path=video_path,
        sample_step=int(args.sample_step),
        max_frames=int(args.max_frames),
        debug_dir=debug_dir,
    )
    thresholds = derive_thresholds(stats)
    config = build_perception_config(thresholds, stats)

    output_config.parent.mkdir(parents=True, exist_ok=True)
    output_config.write_text(_to_yaml_text(config), encoding="utf-8")

    write_report(
        report_path=output_report,
        stats=stats,
        thresholds=thresholds,
        config_path=output_config,
    )

    if stats.reliable:
        print(f"Kalibracja zakończona sukcesem. Zapisano: {output_config} oraz {output_report}")
    else:
        print(
            "Kalibracja zakończona bez wiarygodnych parametrów. "
            f"Pozostawiono bezpieczne ustawienia bazowe w: {output_config}. Raport: {output_report}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
