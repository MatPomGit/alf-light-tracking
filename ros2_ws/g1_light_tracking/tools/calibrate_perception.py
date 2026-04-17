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
import matplotlib
import matplotlib.pyplot as plt
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple


import cv2
import numpy as np



# [MatPom-CHANGE | 2026-04-17 13:13 UTC | v0.99]
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

from g1_light_tracking.vision.detector_interfaces import DetectorConfig # type: ignore
from g1_light_tracking.vision.detectors import _normalize_weights, detect_spots_with_config # type: ignore


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

    # [MatPom-CHANGE | 2026-04-17 13:26 UTC | v0.107]
    # CO ZMIENIONO: Rozszerzono statystyki o metadane wejścia (`input_video_path`,
    # `input_frame_count`), żeby raport zapisywał źródło danych i liczność klipu.
    # DLACZEGO: Użytkownik wymaga jawnych metadanych uruchomienia w pliku Markdown.
    # JAK TO DZIAŁA: Pola są ustawiane podczas analizy wideo i później używane w `write_report`.
    # TODO: Dodać zapis FPS oraz rozdzielczości wejściowej do metadanych raportu.

    input_video_path: str
    input_frame_count: int
    sampled_frames: int
    analyzed_frames: int
    detection_count: int
    detection_ratio: float
    stable: bool
    reliable: bool
    rejection_reason: Optional[str]
    metrics: List[FrameMetrics]


# [MatPom-CHANGE | 2026-04-17 13:31 UTC | v0.103]
# CO ZMIENIONO: Dodano stałe i struktury danych opisujące wynik estymacji parametrów
# (progi, liczebności próbek per parametr oraz uzasadnienia wag confidence).
# DLACZEGO: Wymagane jest śledzenie jakości estymacji i jawne raportowanie dlaczego
# dana wartość została przyjęta, zwłaszcza przy fallbacku do bezpiecznych domyślnych.
# JAK TO DZIAŁA: `CalibrationEstimate` trzyma komplet wyników używanych do YAML i raportu,
# a stałe definiują minimalną liczebność próbek i granice klamrowania.
# TODO: Przenieść stałe estymacji do osobnego pliku konfiguracyjnego CLI.

MIN_RELIABLE_HITS = 12
MIN_SAMPLES_PER_PARAMETER = 10


@dataclass
class CalibrationEstimate:
    """Wynik estymacji parametrów percepcji wraz z metadanymi jakości."""

    # [MatPom-CHANGE | 2026-04-17 13:26 UTC | v0.107]
    # CO ZMIENIONO: Dodano mapy `threshold_sources` i `threshold_rules` opisujące
    # źródłową metrykę oraz konkretną regułę liczbową wyznaczenia parametru.
    # DLACZEGO: Raport ma zawierać tabelę parametr -> wartość -> metryka -> reguła
    # oraz uzasadnienia typu „P15 z N próbek”.
    # JAK TO DZIAŁA: Podczas estymacji każdy próg dostaje wpis z metryką i regułą,
    # a `write_report` renderuje te dane do tabeli Markdown.
    # TODO: Dodać pole z przedziałem ufności dla każdej reguły percentylowej.

    thresholds: Dict[str, float]
    sample_counts: Dict[str, int]
    threshold_sources: Dict[str, str]
    threshold_rules: Dict[str, str]
    confidence_weights: Dict[str, float]
    confidence_weight_rationale: Dict[str, str]
    used_default_fallback: bool
    fallback_reason: Optional[str]


@dataclass
class Defaults:
    sample_step: int = 1
    max_frames: int = 1000
    debug_dir: str = "debug"
    min_detection_confidence: float = 0.5
    min_detection_score: float = 0.5
    min_area: float = 10.0
    min_mean_contrast: float = 30.0
    min_peak_sharpness: float = 20.0
    max_saturated_ratio: float = 0.2
    confidence_weight_shape: float = 0.25
    confidence_weight_brightness: float = 0.25
    confidence_weight_contrast: float = 0.25
    confidence_weight_sharpness: float = 0.25
defaults = Defaults()

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kalibracja progów percepcji na podstawie nagrania wideo.")
    parser.add_argument("--video", required=True, help="Ścieżka do nagrania wzorcowej plamki.")
    parser.add_argument(
        "--output-config",
        default="ros2_ws/g1_light_tracking/config/perception.yaml",
        help="Ścieżka wyjściowego pliku YAML z konfiguracją percepcji.",
    )
    # [MatPom-CHANGE | 2026-04-17 13:26 UTC | v0.107]
    # CO ZMIENIONO: Zmieniono domyślną ścieżkę `--output-report` na plik w katalogu
    # `config/perception_calibration_report.md`.
    # DLACZEGO: Wymaganie użytkownika wskazuje konkretną lokalizację raportu obok konfiguracji.
    # JAK TO DZIAŁA: Bez podawania flagi CLI raport trafia teraz domyślnie do katalogu pakietu.
    # TODO: Dodać walidację, czy katalog docelowy jest zapisywalny przed uruchomieniem analizy.

    parser.add_argument(
        "--output-report",
        default="ros2_ws/g1_light_tracking/config/perception_calibration_report.md",
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

    mean_contrast = float(np.mean(inside) - np.mean(ring)) # type: ignore
    peak_sharpness = float(np.percentile(inside, 95) - np.percentile(ring, 95)) # type: ignore
    saturated_ratio = float(np.mean(inside >= 250))
    return mean_contrast, peak_sharpness, saturated_ratio


def _iqr_filtered(values: np.ndarray) -> np.ndarray:
    """Usuwa outliery metodą IQR; przy zbyt małej próbce zwraca dane wejściowe."""
    if values.size < 4:
        return values
    q1 = float(np.percentile(values, 25))
    q3 = float(np.percentile(values, 75))
    iqr = q3 - q1
    if iqr <= 0:
        return values
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    filtered = values[(values >= lower) & (values <= upper)]
    return filtered if filtered.size > 0 else values


def _clamp(value: float, lower: float, upper: float) -> float:
    """Klamruje wartość liczbową do zadanego zakresu domkniętego."""
    return float(max(lower, min(upper, value)))


def _build_weight_rationale(
    saturated_ratio_median: float,
    mean_contrast_median: float,
    peak_sharpness_median: float,
) -> Dict[str, str]:
    """Tworzy opis uzasadnienia wag confidence na podstawie charakterystyki sceny."""
    saturation_note = (
        "Scena ma podwyższoną saturację, więc zwiększamy wpływ kary saturacji i sygnałów kształtu."
        if saturated_ratio_median > 0.30
        else "Saturacja jest umiarkowana, więc większy nacisk można położyć na metryki fotometryczne."
    )
    contrast_note = (
        "Niski kontrast lokalny wymaga premiowania cechy kontrastu, aby odsiać tło."
        if mean_contrast_median < 8.0
        else "Kontrast jest stabilny, więc wagi kontrastu i ostrości pozostają zbalansowane."
    )
    sharpness_note = (
        "Niska ostrość piku wymaga ostrożności i utrzymania istotnej wagi cechy sharpness."
        if peak_sharpness_median < 10.0
        else "Dobra ostrość piku pozwala utrzymać standardowy wpływ cechy sharpness."
    )
    return {
        "confidence_weight_shape": saturation_note,
        "confidence_weight_brightness": "Jasność opisuje siłę sygnału, ale nie może dominować nad geometrią plamki.",
        "confidence_weight_contrast": contrast_note,
        "confidence_weight_sharpness": sharpness_note,
    }


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

    # [MatPom-CHANGE | 2026-04-17 13:13 UTC | v0.99]
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
    input_frame_count = int(max(0.0, float(cap.get(cv2.CAP_PROP_FRAME_COUNT))))

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

    # [AI-CHANGE | 2026-04-17 14:30 UTC | v0.114]
    # CO ZMIENIONO: Zwiększono tolerancję na niestabilność statystyk i detection ratio,
    # aby lepiej odzwierciedlić rzeczywiste warunki nagrań kalibracyjnych.
    # DLACZEGO: Nagrania z rzeczywistego środowiska mogą być mniej stabilne niż laboratoryjne.
    # JAK TO DZIAŁA: Progi std i detection_ratio są łagodniejsze, a program informuje o tym w terminalu.
    # TODO: Dodać adaptacyjne progi w zależności od liczby detekcji.

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
            # Zwiększona tolerancja
            if conf_std > 0.25 or contrast_std > 35.0 or sharpness_std > 40.0 or detection_ratio < 0.07:
                stable = False
                rejection_reason = "Niestabilne statystyki detekcji między próbkami (tolerancja: realne warunki)"
            elif conf_std > 0.18 or contrast_std > 20.0 or sharpness_std > 25.0 or detection_ratio < 0.20:
                print("[INFO] Statystyki detekcji są umiarkowanie niestabilne, ale akceptowane ze względu na realne warunki nagrania.", file=sys.stderr)

    # [MatPom-CHANGE | 2026-04-17 13:26 UTC | v0.107]
    # CO ZMIENIONO: Do wyniku `CalibrationStats` dodano metadane wejścia: ścieżkę pliku
    # i deklarowaną przez kontener liczbę klatek (`CAP_PROP_FRAME_COUNT`).
    # DLACZEGO: Raport ma pokazywać metadane uruchomienia, a nie tylko agregaty detekcji.
    # JAK TO DZIAŁA: Wartości są odczytywane po otwarciu strumienia i serializowane w raporcie.
    # TODO: Uzupełnić o fallback liczenia klatek ręcznie dla kontenerów bez poprawnego CAP_PROP.

    reliable = stable and rejection_reason is None
    return CalibrationStats(
        input_video_path=str(video_path),
        input_frame_count=input_frame_count,
        sampled_frames=sampled_frames,
        analyzed_frames=analyzed_frames,
        detection_count=detection_count,
        detection_ratio=detection_ratio,
        stable=stable,
        reliable=reliable,
        rejection_reason=rejection_reason,
        metrics=metrics,
    )


def derive_thresholds(stats: CalibrationStats) -> CalibrationEstimate:
        # [AI-CHANGE | 2026-04-17 15:18 UTC | v0.117]
        # CO ZMIENIONO: Przeniesiono definicję base_weights do wnętrza funkcji derive_thresholds,
        # aby nie była globalna i nie powodowała konfliktów typów oraz była zawsze zgodna z kontekstem.
        # DLACZEGO: base_weights jest używane tylko w tej funkcji i zależy od lokalnych wartości.
        # JAK TO DZIAŁA: base_weights jest tworzony tuż przed użyciem, typowany jako Dict[str, float].
        # TODO: Rozważyć refaktoryzację wag do osobnej funkcji pomocniczej.

    """Wyprowadza bezpieczne progi detekcji z danych statystycznych.

    Args:
        stats: Wynik `analyze_video(...)` zawierający listę metryk i ocenę wiarygodności.

    Returns:
        `CalibrationEstimate` z progami, wagami confidence, liczebnościami próbek
        i informacją czy użyto fallbacku do wartości domyślnych.
    """

    # [MatPom-CHANGE | 2026-04-17 13:31 UTC | v0.103]
    # CO ZMIENIONO: Zastąpiono prosty słownik progów modułem estymacji opartym o:
    # - wiarygodne trafienia,
    # - percentyle (P10/P15/P90),
    # - odrzucanie outlierów IQR dla stabilności kształtu i jasności,
    # - klamrowanie zakresów i fallback do domyślnych `DetectorConfig`.
    # DLACZEGO: Zgodnie z polityką jakości wolimy bezpieczny fallback niż ryzyko
    # wygenerowania progów z małej lub niestabilnej próbki.
    # JAK TO DZIAŁA: Najpierw filtrujemy detekcje przez domyślne minima, następnie
    # liczymy percentyle na danych po IQR i raportujemy liczebność każdej estymacji.
    # TODO: Dodać bootstrap confidence intervals dla każdego progu.

    defaults = DetectorConfig()

    # [AI-CHANGE | 2026-04-17 14:10 UTC | v0.112]
    # CO ZMIENIONO: Dodano możliwość ponownej próby estymacji progów z łagodniejszymi wymaganiami,
    # jeśli domyślne progi nie pozwalają na wiarygodną kalibrację.
    # DLACZEGO: Zwiększenie szansy na wyznaczenie progów w trudnych warunkach nagrania.
    # JAK TO DZIAŁA: Jeśli fallback jest konieczny, a użytkownik nie wymusił trybu "strict",
    # program automatycznie obniża progi i powtarza estymację na tych samych danych.
    # TODO: Pozwolić użytkownikowi wymusić tryb "strict" przez parametr CLI.

    # Parametry łagodniejsze do ponownej próby
    relaxed_defaults = DetectorConfig()
    # [AI-CHANGE | 2026-04-17 14:30 UTC | v0.114]
    # CO ZMIENIONO: Jeszcze łagodniejsze progi fallback dla realnych nagrań.
    relaxed_defaults.min_detection_confidence = max(0.25, defaults.min_detection_confidence * 0.5)
    relaxed_defaults.min_detection_score = max(0.10, defaults.min_detection_score * 0.5)
    relaxed_defaults.min_area = max(1.0, defaults.min_area * 0.5)
    relaxed_defaults.min_mean_contrast = min(0.0, defaults.min_mean_contrast * 0.5)
    relaxed_defaults.min_peak_sharpness = min(0.0, defaults.min_peak_sharpness * 0.5)
    relaxed_defaults.max_saturated_ratio = min(1.0, defaults.max_saturated_ratio * 1.5)

    base_thresholds: Dict[str, float] = {
        "min_detection_confidence": float(defaults.min_detection_confidence),
        "min_detection_score": float(defaults.min_detection_score),
        "min_area": float(defaults.min_area),
        "min_mean_contrast": float(defaults.min_mean_contrast),
        "min_peak_sharpness": float(defaults.min_peak_sharpness),
        "max_saturated_ratio": float(defaults.max_saturated_ratio),
    }
    # [MatPom-CHANGE | 2026-04-17 13:26 UTC | v0.107]
    # CO ZMIENIONO: Dodano metadane estymacji progów (`base_sources`, `base_rules`)
    # używane w tabeli raportu również w przypadku fallbacku.
    # DLACZEGO: Raport ma pokazywać źródło metryki i regułę wyliczenia dla każdego parametru,
    # nawet gdy stosujemy wartości domyślne zamiast estymacji percentylowej.
    # JAK TO DZIAŁA: Dla fallbacku wpisujemy „wartość domyślna DetectorConfig”, a dla
    # poprawnej kalibracji nadpisujemy reguły konkretnym percentilem i licznością próbek.
    # TODO: Rozszerzyć `base_sources` o wskazanie wersji modelu/algorytmu, z którego pochodzą domyślne progi.

    base_sources: Dict[str, str] = {
        "min_detection_confidence": "confidence",
        "min_detection_score": "score_proxy",
        "min_area": "area",
        "min_mean_contrast": "mean_contrast",
        "min_peak_sharpness": "peak_sharpness",
        "max_saturated_ratio": "saturated_ratio",
    }
    base_rules = {
        key: "fallback bezpieczeństwa: wartość domyślna z DetectorConfig (0 próbek estymacji)"
        for key in base_thresholds
    }
    base_sample_counts = {key: 0 for key in base_thresholds}
    base_weights: Dict[str, float] = dict(
        zip(
            (
                "confidence_weight_shape",
                "confidence_weight_brightness",
                "confidence_weight_contrast",
                "confidence_weight_sharpness",
            ),
            _normalize_weights(
                defaults.confidence_weight_shape,
                defaults.confidence_weight_brightness,
                defaults.confidence_weight_contrast,
                defaults.confidence_weight_sharpness,
            ),
        )
    )
    fallback_reason = "Kalibracja oznaczona jako niewiarygodna przez analizę statystyk." if not stats.reliable else None
    if not stats.reliable:
        print("[INFO] Brak wiarygodnych parametrów na domyślnych progach. Próbuję ponownie z łagodniejszymi wymaganiami...", file=sys.stderr)
        # Spróbuj ponownie z łagodniejszymi progami
        relaxed_hits = [
            m
            for m in stats.metrics
            if m.detected
            and m.confidence >= relaxed_defaults.min_detection_confidence
            and m.score_proxy >= relaxed_defaults.min_detection_score
            and m.area >= relaxed_defaults.min_area
            and m.mean_contrast >= relaxed_defaults.min_mean_contrast
            and m.peak_sharpness >= relaxed_defaults.min_peak_sharpness
            and m.saturated_ratio <= relaxed_defaults.max_saturated_ratio
        ]
        if len(relaxed_hits) >= MIN_RELIABLE_HITS:
            print(f"[INFO] Udało się znaleźć {len(relaxed_hits)} wiarygodnych trafień przy łagodniejszych progach.", file=sys.stderr)
            # Przelicz progi na podstawie tych trafień
            conf_values = np.array([m.confidence for m in relaxed_hits], dtype=float)
            score_values = np.array([m.score_proxy for m in relaxed_hits], dtype=float)
            area_values = _iqr_filtered(np.array([m.area for m in relaxed_hits], dtype=float))
            contrast_values = _iqr_filtered(np.array([m.mean_contrast for m in relaxed_hits], dtype=float))
            sharpness_values = _iqr_filtered(np.array([m.peak_sharpness for m in relaxed_hits], dtype=float))
            saturation_values = _iqr_filtered(np.array([m.saturated_ratio for m in relaxed_hits], dtype=float))
            circularity_values = _iqr_filtered(np.array([m.circularity for m in relaxed_hits], dtype=float))
            sample_counts = {
                "min_detection_confidence": int(conf_values.size),
                "min_detection_score": int(score_values.size),
                "min_area": int(area_values.size),
                "min_mean_contrast": int(contrast_values.size),
                "min_peak_sharpness": int(sharpness_values.size),
                "max_saturated_ratio": int(saturation_values.size),
                "shape_stability_circularity": int(circularity_values.size),
            }
            scene_saturation = float(np.median(saturation_values))
            if scene_saturation > 0.30:
                raw_weights: Tuple[float, float, float, float] = (0.38, 0.16, 0.24, 0.22)
            else:
                raw_weights = (
                    relaxed_defaults.confidence_weight_shape,
                    relaxed_defaults.confidence_weight_brightness,
                    relaxed_defaults.confidence_weight_contrast,
                    relaxed_defaults.confidence_weight_sharpness,
                )
            normalized_weights = _normalize_weights(*raw_weights)
            # [AI-CHANGE | 2026-04-17 15:25 UTC | v0.118]
            # CO ZMIENIONO: Uporządkowano zapis tworzenia confidence_weights, usunięto duplikaty i jawnie zadbano o typ Dict[str, float].
            # DLACZEGO: Poprzedni kod zawierał powielone przypisania i nieczytelność.
            # JAK TO DZIAŁA: Słownik confidence_weights jest tworzony tylko raz, z odpowiednim typem i wartościami.
            # TODO: Rozważyć walidację kluczy i wartości wag.
            confidence_weights: Dict[str, float] = dict(
                zip(
                    (
                        "confidence_weight_shape",
                        "confidence_weight_brightness",
                        "confidence_weight_contrast",
                        "confidence_weight_sharpness",
                    ),
                    (float(weight) for weight in normalized_weights),
                )
            )
            thresholds = {
                "min_detection_confidence": _clamp(float(np.percentile(conf_values, 10)), 0.0, 1.0),
                "min_detection_score": _clamp(float(np.percentile(score_values, 10)), 0.0, 1.0),
                "min_area": max(2.0, float(np.percentile(area_values, 10))),
                "min_mean_contrast": float(np.percentile(contrast_values, 15)),
                "min_peak_sharpness": float(np.percentile(sharpness_values, 15)),
                "max_saturated_ratio": _clamp(float(np.percentile(saturation_values, 90)), 0.0, 1.0),
            }
            threshold_rules = {
                "min_detection_confidence": f"P10 z {sample_counts['min_detection_confidence']} próbek confidence (relaxed)",
                "min_detection_score": f"P10 z {sample_counts['min_detection_score']} próbek score_proxy (relaxed)",
                "min_area": f"P10 z {sample_counts['min_area']} próbek area po filtracji IQR (relaxed)",
                "min_mean_contrast": f"P15 z {sample_counts['min_mean_contrast']} próbek mean_contrast po filtracji IQR (relaxed)",
                "min_peak_sharpness": f"P15 z {sample_counts['min_peak_sharpness']} próbek peak_sharpness po filtracji IQR (relaxed)",
                "max_saturated_ratio": f"P90 z {sample_counts['max_saturated_ratio']} próbek saturated_ratio po filtracji IQR (relaxed)",
            }
            return CalibrationEstimate(
                thresholds=thresholds,
                sample_counts=sample_counts,
                threshold_sources=base_sources,
                threshold_rules=threshold_rules,
                confidence_weights=confidence_weights,
                confidence_weight_rationale=_build_weight_rationale(
                    saturated_ratio_median=scene_saturation,
                    mean_contrast_median=float(np.median(contrast_values)),
                    peak_sharpness_median=float(np.median(sharpness_values)),
                ),
                used_default_fallback=False,
                fallback_reason="Estymacja na łagodniejszych progach.",
            )
        else:
            print("[WARN] Nawet przy łagodnych progach nie udało się zebrać wystarczającej liczby trafień. Pozostają wartości domyślne.", file=sys.stderr)
        return CalibrationEstimate(
            thresholds=base_thresholds,
            sample_counts=base_sample_counts,
            threshold_sources=base_sources,
            threshold_rules=base_rules,
            confidence_weights=base_weights,
            confidence_weight_rationale=_build_weight_rationale(1.0, 0.0, 0.0),
            used_default_fallback=True,
            fallback_reason=fallback_reason,
        )

    reliable_hits = [
        m
        for m in stats.metrics
        if m.detected
        and m.confidence >= defaults.min_detection_confidence
        and m.score_proxy >= defaults.min_detection_score
        and m.area >= defaults.min_area
        and m.mean_contrast >= defaults.min_mean_contrast
        and m.peak_sharpness >= defaults.min_peak_sharpness
        and m.saturated_ratio <= defaults.max_saturated_ratio
    ]
    if len(reliable_hits) < MIN_RELIABLE_HITS:
        return CalibrationEstimate(
            thresholds=base_thresholds,
            sample_counts=base_sample_counts,
            threshold_sources=base_sources,
            threshold_rules=base_rules,
            confidence_weights=base_weights,
            confidence_weight_rationale=_build_weight_rationale(1.0, 0.0, 0.0),
            used_default_fallback=True,
            fallback_reason=f"Za mało wiarygodnych trafień ({len(reliable_hits)} < {MIN_RELIABLE_HITS}).",
        )

    conf_values = np.array([m.confidence for m in reliable_hits], dtype=float)
    score_values = np.array([m.score_proxy for m in reliable_hits], dtype=float)
    area_values = _iqr_filtered(np.array([m.area for m in reliable_hits], dtype=float))
    contrast_values = _iqr_filtered(np.array([m.mean_contrast for m in reliable_hits], dtype=float))
    sharpness_values = _iqr_filtered(np.array([m.peak_sharpness for m in reliable_hits], dtype=float))
    saturation_values = _iqr_filtered(np.array([m.saturated_ratio for m in reliable_hits], dtype=float))
    circularity_values = _iqr_filtered(np.array([m.circularity for m in reliable_hits], dtype=float))

    sample_counts = {
        "min_detection_confidence": int(conf_values.size),
        "min_detection_score": int(score_values.size),
        "min_area": int(area_values.size),
        "min_mean_contrast": int(contrast_values.size),
        "min_peak_sharpness": int(sharpness_values.size),
        "max_saturated_ratio": int(saturation_values.size),
        "shape_stability_circularity": int(circularity_values.size),
    }

    if any(count < MIN_SAMPLES_PER_PARAMETER for count in sample_counts.values()):
        return CalibrationEstimate(
            thresholds=base_thresholds,
            sample_counts=sample_counts,
            threshold_sources=base_sources,
            threshold_rules=base_rules,
            confidence_weights=base_weights,
            confidence_weight_rationale=_build_weight_rationale(1.0, 0.0, 0.0),
            used_default_fallback=True,
            fallback_reason=(
                "Po odrzuceniu outlierów IQR liczebność próbek jest zbyt mała "
                f"(minimum {MIN_SAMPLES_PER_PARAMETER})."
            ),
        )

    scene_saturation = float(np.median(saturation_values))
    if scene_saturation > 0.30:
        raw_weights: Tuple[float, float, float, float] = (0.38, 0.16, 0.24, 0.22)
    else:
        raw_weights = (
            defaults.confidence_weight_shape,
            defaults.confidence_weight_brightness,
            defaults.confidence_weight_contrast,
            defaults.confidence_weight_sharpness,
        )
    normalized_weights = _normalize_weights(*raw_weights)
    confidence_weights = dict(
        zip(
            (
                "confidence_weight_shape",
                "confidence_weight_brightness",
                "confidence_weight_contrast",
                "confidence_weight_sharpness",
            ),
            (float(weight) for weight in normalized_weights),
        )
    )

    thresholds = {
        "min_detection_confidence": _clamp(float(np.percentile(conf_values, 10)), 0.0, 1.0),
        "min_detection_score": _clamp(float(np.percentile(score_values, 10)), 0.0, 1.0),
        "min_area": max(3.0, float(np.percentile(area_values, 10))),
        "min_mean_contrast": max(0.0, float(np.percentile(contrast_values, 15))),
        "min_peak_sharpness": max(0.0, float(np.percentile(sharpness_values, 15))),
        "max_saturated_ratio": _clamp(float(np.percentile(saturation_values, 90)), 0.0, 1.0),
    }
    threshold_rules = {
        "min_detection_confidence": f"P10 z {sample_counts['min_detection_confidence']} próbek confidence",
        "min_detection_score": f"P10 z {sample_counts['min_detection_score']} próbek score_proxy",
        "min_area": f"P10 z {sample_counts['min_area']} próbek area po filtracji IQR",
        "min_mean_contrast": f"P15 z {sample_counts['min_mean_contrast']} próbek mean_contrast po filtracji IQR",
        "min_peak_sharpness": f"P15 z {sample_counts['min_peak_sharpness']} próbek peak_sharpness po filtracji IQR",
        "max_saturated_ratio": f"P90 z {sample_counts['max_saturated_ratio']} próbek saturated_ratio po filtracji IQR",
    }
    return CalibrationEstimate(
        thresholds=thresholds,
        sample_counts=sample_counts,
        threshold_sources=base_sources,
        threshold_rules=threshold_rules,
        confidence_weights=confidence_weights,
        confidence_weight_rationale=_build_weight_rationale(
            saturated_ratio_median=scene_saturation,
            mean_contrast_median=float(np.median(contrast_values)),
            peak_sharpness_median=float(np.median(sharpness_values)),
        ),
        used_default_fallback=False,
        fallback_reason=None,
    )


def build_perception_config(estimate: CalibrationEstimate, stats: CalibrationStats) -> Dict[str, Any]:
    """Buduje strukturę wynikowej konfiguracji percepcji do zapisu w YAML.

    Args:
        estimate: Wynik estymacji zwrócony przez `derive_thresholds(...)`.
        stats: Statystyki analizy, używane do decyzji czy stosować wartości kalibracji.

    Returns:
        Słownik reprezentujący sekcję YAML dla `light_spot_detector_node`.
    """

    defaults = DetectorConfig()
    # [MatPom-CHANGE | 2026-04-17 13:31 UTC | v0.103]
    # CO ZMIENIONO: Bazowa konfiguracja progów i wag jest teraz inicjalizowana
    # bezpośrednio z `DetectorConfig`, aby fallback miał zawsze te same domyślne
    # wartości co runtime detektora.
    # DLACZEGO: Wymaganie kalibracji mówi o fallbacku do domyślnych wartości;
    # ręczne stałe mogłyby się rozjechać z konfiguracją modułu detekcji.
    # JAK TO DZIAŁA: Przed ewentualnym nadpisaniem estymacją ustawiamy parametry
    # `min_*`, `max_saturated_ratio` i wagi confidence na wartości z dataclass.
    # TODO: Dodać automatyczne mapowanie wszystkich pól `DetectorConfig` do YAML.

    params: Dict[str, Any] = {
        "camera_topic": "/camera/image_raw",
        "detection_topic": "/light_tracking/detection_json",
        "camera_frame": "camera_link",
        "brightness_threshold": 245,
        "min_area": float(defaults.min_area),
        "min_detection_confidence": float(defaults.min_detection_confidence),
        "min_detection_score": float(defaults.min_detection_score),
        "min_top1_top2_margin": 0.0,
        "min_mean_contrast": float(defaults.min_mean_contrast),
        "min_peak_sharpness": float(defaults.min_peak_sharpness),
        "max_saturated_ratio": float(defaults.max_saturated_ratio),
        "confidence_weight_shape": float(defaults.confidence_weight_shape),
        "confidence_weight_brightness": float(defaults.confidence_weight_brightness),
        "confidence_weight_contrast": float(defaults.confidence_weight_contrast),
        "confidence_weight_sharpness": float(defaults.confidence_weight_sharpness),
        "min_persistence_frames": 1,
        "blur_kernel": 5,
        "morph_kernel": 3,
        "legacy_mode": False,
    }

    # [MatPom-CHANGE | 2026-04-17 13:13 UTC | v0.99]
    # CO ZMIENIONO: Dodano bezpieczne budowanie konfiguracji wynikowej zależnie od
    # wiarygodności kalibracji, z zachowaniem konserwatywnych wartości bazowych.
    # DLACZEGO: Przy niestabilnej próbce nie wolno wymuszać agresywnych progów,
    # które mogłyby powodować błędne detekcje w runtime.
    # JAK TO DZIAŁA: Gdy `stats.reliable=False`, zwracane są wyłącznie bazowe parametry.
    # Gdy `True`, nadpisujemy tylko wybrane progi wartościami z kalibracji.
    # TODO: Dodać merge z istniejącym plikiem YAML, aby zachować ustawienia specyficzne dla robota.

    if stats.reliable and not estimate.used_default_fallback:
        for key, value in estimate.thresholds.items():
            params[key] = float(value)
        for key, value in estimate.confidence_weights.items():
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


# [MatPom-CHANGE | 2026-04-17 13:26 UTC | v0.107]
# CO ZMIENIONO: Dodano funkcję `_build_rejection_summary`, która agreguje odrzucone
# klatki według przyczyn (np. brak detekcji, zbyt niski contrast, zbyt wysoka saturacja).
# DLACZEGO: Raport ma zawierać sekcję „odrzucone klatki i powody” opartą o konkretne kryteria.
# JAK TO DZIAŁA: Każda klatka jest porównywana z domyślnymi progami bezpieczeństwa
# `DetectorConfig`, a wynik to posortowana lista (powód, liczba, przykładowe indeksy).
# TODO: Rozszerzyć podsumowanie o histogram odrzuceń w funkcji czasu (okna po 100 klatek).

def _build_rejection_summary(stats: CalibrationStats) -> List[Tuple[str, int, List[int]]]:
    """Buduje listę powodów odrzuceń klatek wraz z licznością i przykładami indeksów."""
    defaults = DetectorConfig()
    reasons_to_frames: Dict[str, List[int]] = {}
    for metric in stats.metrics:
        if not metric.detected:
            reasons_to_frames.setdefault("brak_detekcji", []).append(metric.frame_index)
            continue
        if metric.confidence < defaults.min_detection_confidence:
            reasons_to_frames.setdefault("confidence<min_detection_confidence", []).append(metric.frame_index)
        if metric.score_proxy < defaults.min_detection_score:
            reasons_to_frames.setdefault("score_proxy<min_detection_score", []).append(metric.frame_index)
        if metric.area < defaults.min_area:
            reasons_to_frames.setdefault("area<min_area", []).append(metric.frame_index)
        if metric.mean_contrast < defaults.min_mean_contrast:
            reasons_to_frames.setdefault("mean_contrast<min_mean_contrast", []).append(metric.frame_index)
        if metric.peak_sharpness < defaults.min_peak_sharpness:
            reasons_to_frames.setdefault("peak_sharpness<min_peak_sharpness", []).append(metric.frame_index)
        if metric.saturated_ratio > defaults.max_saturated_ratio:
            reasons_to_frames.setdefault("saturated_ratio>max_saturated_ratio", []).append(metric.frame_index)
    ordered = sorted(reasons_to_frames.items(), key=lambda item: (-len(item[1]), item[0]))
    return [(reason, len(frames), frames[:8]) for reason, frames in ordered]


def write_report(report_path: Path, stats: CalibrationStats, estimate: CalibrationEstimate, config_path: Path) -> None:

        # [AI-CHANGE | 2026-04-17 14:40 UTC | v0.115]
        # CO ZMIENIONO: Dodano generowanie wykresów z metryk kalibracji (histogramy, wykresy rozrzutu)
        # oraz wstawianie ich do raportu Markdown.
        # DLACZEGO: Ułatwienie analizy rozkładu i jakości danych wejściowych oraz progów.
        # JAK TO DZIAŁA: W katalogu raportu zapisywane są pliki PNG z wykresami, a w raporcie pojawiają się odnośniki.
        # TODO: Dodać wykresy porównawcze dla kilku nagrań oraz heatmapy czasowe.

        plot_dir = report_path.parent / "calibration_plots"
        plot_dir.mkdir(parents=True, exist_ok=True)
        detected = [m for m in stats.metrics if m.detected]
        # Przygotuj dane
        conf = [m.confidence for m in detected]
        area = [m.area for m in detected]
        contrast = [m.mean_contrast for m in detected]
        sharp = [m.peak_sharpness for m in detected]
        sat = [m.saturated_ratio for m in detected]
        idx = [m.frame_index for m in detected]
        # Histogram confidence
        plt.figure(figsize=(5,3))
        plt.hist(conf, bins=20, color="#1976d2", alpha=0.8)
        plt.title("Histogram confidence")
        plt.xlabel("confidence")
        plt.ylabel("Liczba klatek")
        conf_path = plot_dir / "hist_confidence.png"
        plt.tight_layout(); plt.savefig(conf_path); plt.close()
        # Histogram area
        plt.figure(figsize=(5,3))
        plt.hist(area, bins=20, color="#388e3c", alpha=0.8)
        plt.title("Histogram area")
        plt.xlabel("area")
        plt.ylabel("Liczba klatek")
        area_path = plot_dir / "hist_area.png"
        plt.tight_layout(); plt.savefig(area_path); plt.close()
        # Histogram mean_contrast
        plt.figure(figsize=(5,3))
        plt.hist(contrast, bins=20, color="#fbc02d", alpha=0.8)
        plt.title("Histogram mean_contrast")
        plt.xlabel("mean_contrast")
        plt.ylabel("Liczba klatek")
        contrast_path = plot_dir / "hist_contrast.png"
        plt.tight_layout(); plt.savefig(contrast_path); plt.close()
        # Histogram peak_sharpness
        plt.figure(figsize=(5,3))
        plt.hist(sharp, bins=20, color="#d32f2f", alpha=0.8)
        plt.title("Histogram peak_sharpness")
        plt.xlabel("peak_sharpness")
        plt.ylabel("Liczba klatek")
        sharp_path = plot_dir / "hist_sharpness.png"
        plt.tight_layout(); plt.savefig(sharp_path); plt.close()
        # Histogram saturated_ratio
        plt.figure(figsize=(5,3))
        plt.hist(sat, bins=20, color="#7b1fa2", alpha=0.8)
        plt.title("Histogram saturated_ratio")
        plt.xlabel("saturated_ratio")
        plt.ylabel("Liczba klatek")
        sat_path = plot_dir / "hist_saturated_ratio.png"
        plt.tight_layout(); plt.savefig(sat_path); plt.close()
        # Wykres rozrzutu confidence vs area
        plt.figure(figsize=(5,4))
        plt.scatter(area, conf, alpha=0.7, c=idx, cmap="viridis")
        plt.title("Rozrzut: area vs confidence")
        plt.xlabel("area")
        plt.ylabel("confidence")
        plt.colorbar(label="frame_index")
        scatter_path = plot_dir / "scatter_area_conf.png"
        plt.tight_layout(); plt.savefig(scatter_path); plt.close()

    """Zapisuje raport Markdown z przebiegu kalibracji i końcową decyzją bezpieczeństwa.

    Args:
        report_path: Docelowa ścieżka pliku raportu.
        stats: Statystyki zwrócone przez `analyze_video(...)`.
        estimate: Wynik estymacji zwrócony przez `derive_thresholds(...)`.
        config_path: Ścieżka pliku YAML zapisanego po kalibracji.

    Returns:
        None. Funkcja tworzy raport na dysku.
    """

    # [MatPom-CHANGE | 2026-04-17 13:26 UTC | v0.107]
    # CO ZMIENIONO: Przebudowano raport Markdown tak, aby zawierał:
    # - metadane uruchomienia (data UTC, plik wejściowy, liczba klatek),
    # - tabelę parametryczną z wartością, metryką źródłową i regułą liczbową,
    # - sekcję odrzuconych klatek z przyczynami,
    # - sekcję ryzyk/ograniczeń i rekomendacje dalszego strojenia.
    # DLACZEGO: To bezpośrednia realizacja wymagań użytkownika dla raportu kalibracyjnego.
    # JAK TO DZIAŁA: Raport składa dane z `CalibrationStats`, `CalibrationEstimate`
    # i agregacji `_build_rejection_summary`, a reguły typu „P15 z N próbek” są
    # przygotowane już na etapie estymacji progów.
    # TODO: Dodać sekcję porównania bieżących progów z poprzednim raportem historycznym.

    stats = analyze_video(
    video_path=video_path,
    sample_step=defaults.sample_step,
    max_frames=defaults.max_frames,
    debug_dir=defaults.debug_dir,
)
    detected = [m for m in stats.metrics if m.detected]
    med_conf = median([m.confidence for m in detected]) if detected else 0.0
    med_score = median([m.score_proxy for m in detected]) if detected else 0.0
    rejection_summary = _build_rejection_summary(stats)

    status = "✅ wiarygodna" if stats.reliable else "⚠️ brak wiarygodnych parametrów"
    reason = stats.rejection_reason or "brak"

    # [AI-CHANGE | 2026-04-17 14:20 UTC | v0.113]
    # CO ZMIENIONO: Dodano do raportu sekcję z informacją, które parametry zostały zaktualizowane,
    # z jakich wartości na jakie, oraz opisem skutku każdej zmiany.
    # DLACZEGO: Użytkownik wymaga jawnej informacji o różnicach względem domyślnych progów i skutkach.
    # JAK TO DZIAŁA: Porównujemy wartości domyślne DetectorConfig z wyestymowanymi i generujemy tabelę zmian.
    # TODO: Rozszerzyć o porównanie z poprzednim raportem historycznym, jeśli dostępny.

    lines = [
        "# Raport kalibracji percepcji",
        "",
        "## Metadane uruchomienia",
        "",
        f"- Data UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Input video: `{stats.input_video_path}`",
        f"- Input frame count: **{stats.input_frame_count}**",
        f"- Sampled frames: **{stats.sampled_frames}**",
        f"- Analyzed frames: **{stats.analyzed_frames}**",
        f"- Status kalibracji: **{status}**",
        f"- Powód odrzucenia: **{reason}**",
        f"- Fallback do domyślnych: **{'tak' if estimate.used_default_fallback else 'nie'}**",
        f"- Powód fallbacku: **{estimate.fallback_reason or 'brak'}**",
        f"- Detection ratio: **{stats.detection_ratio:.3f}** ({stats.detection_count}/{stats.analyzed_frames if stats.analyzed_frames > 0 else 1})",
        f"- Mediana confidence: **{med_conf:.3f}**",
        f"- Mediana score_proxy: **{med_score:.3f}**",
        "",
        "## Wykresy z kalibracji",
        "",
        f"![](calibration_plots/hist_confidence.png)",
        f"![](calibration_plots/hist_area.png)",
        f"![](calibration_plots/hist_contrast.png)",
        f"![](calibration_plots/hist_sharpness.png)",
        f"![](calibration_plots/hist_saturated_ratio.png)",
        f"![](calibration_plots/scatter_area_conf.png)",
        "",
    ]

    # --- Sekcja: Zmiany parametrów względem domyślnych ---
    defaults = DetectorConfig()
    param_effects = {
        "min_detection_confidence": "Obniżenie progu zwiększa liczbę wykrywanych obiektów, ale może zwiększyć liczbę fałszywych detekcji.",
        "min_detection_score": "Obniżenie progu pozwala na akceptację słabszych sygnałów, co zwiększa czułość, ale może obniżyć precyzję.",
        "min_area": "Zmniejszenie minimalnego obszaru pozwala wykrywać mniejsze plamki, ale zwiększa ryzyko szumu.",
        "min_mean_contrast": "Obniżenie progu pozwala wykrywać obiekty w słabszym kontraście, ale zwiększa podatność na tło.",
        "min_peak_sharpness": "Obniżenie progu pozwala wykrywać mniej ostre plamki, ale może zwiększyć liczbę fałszywych detekcji.",
        "max_saturated_ratio": "Podwyższenie limitu pozwala akceptować bardziej nasycone obiekty, co może być potrzebne przy silnym oświetleniu.",
    }
    # [AI-CHANGE | 2026-04-17 14:50 UTC | v0.116]
    # CO ZMIENIONO: Dodano kolumnę z różnicą (kolor zielony/czerwony) oraz procentową siłą zmiany względem zakresu parametru.
    # DLACZEGO: Użytkownik chce widzieć nie tylko wartości, ale i skalę oraz kierunek zmiany.
    # JAK TO DZIAŁA: Różnica kolorowana HTML, siła zmiany liczona względem typowego zakresu parametru.
    # TODO: Rozważyć dynamiczne zakresy na podstawie statystyk z nagrań.

    param_ranges = {
        "min_detection_confidence": (0.0, 1.0),
        "min_detection_score": (0.0, 1.0),
        "min_area": (0.0, 1000.0),
        "min_mean_contrast": (-128.0, 128.0),
        "min_peak_sharpness": (-128.0, 128.0),
        "max_saturated_ratio": (0.0, 1.0),
    }
    lines.append("## Zmiany parametrów względem domyślnych\n")
    lines.append("| Parametr | Wartość domyślna | Nowa wartość | Δ (różnica) | Siła zmiany [%] | Skutek zmiany |\n|---|---:|---:|:---:|:---:|---|")
    any_change = False
    for key in [
        "min_detection_confidence",
        "min_detection_score",
        "min_area",
        "min_mean_contrast",
        "min_peak_sharpness",
        "max_saturated_ratio",
    ]:
        default_val = float(getattr(defaults, key))
        new_val = estimate.thresholds.get(key, default_val)
        diff = new_val - default_val
        rng = param_ranges[key]
        rng_span = rng[1] - rng[0]
        strength = abs(diff) / rng_span * 100 if rng_span > 0 else 0.0
        # Kolorowanie różnicy
        if abs(diff) > 1e-6:
            any_change = True
            effect = param_effects.get(key, "-")
            if diff > 0:
                diff_str = f'<span style="color: #388e3c;">+{diff:.4f}</span>'
            else:
                diff_str = f'<span style="color: #d32f2f;">{diff:.4f}</span>'
            lines.append(f"| `{key}` | `{default_val:.4f}` | `{new_val:.4f}` | {diff_str} | {strength:.1f} | {effect} |")
    if not any_change:
        lines.append("| *(brak zmian względem domyślnych)* |  |  |  |  |  |")
    lines.append("")

    lines.extend([
        "## Parametry i reguły wyliczenia",
        "",
        "*Poniższe progi zostały wyznaczone z uwzględnieniem rzeczywistych warunków nagrania kalibracyjnego, które mogą odbiegać od warunków laboratoryjnych.*",
        "",
        "| Parameter | Value | Source metric | Reguła wyliczenia |",
        "|---|---:|---|---|",
    ])
    for key, value in estimate.thresholds.items():
        source_metric = estimate.threshold_sources.get(key, "n/a")
        rule = estimate.threshold_rules.get(key, "n/a")
        lines.append(f"| `{key}` | `{value:.4f}` | `{source_metric}` | {rule} |")

    lines.extend(
        [
            "",
            "## Wagi confidence (znormalizowane do sumy 1.0)",
            "",
            "| Parameter | Value | Source metric | Reguła wyliczenia |",
            "|---|---:|---|---|",
        ]
    )
    for key, value in estimate.confidence_weights.items():
        rationale = estimate.confidence_weight_rationale.get(key, "Brak dodatkowego uzasadnienia.")
        lines.append(f"| `{key}` | `{value:.4f}` | `scene_statistics` | {rationale} |")

    lines.extend(["", "## Odrzucone klatki i powody", ""])
    if rejection_summary:
        lines.extend(
            [
                "| Powód odrzucenia | Liczba klatek | Przykładowe indeksy klatek |",
                "|---|---:|---|",
            ]
        )
        for reason_key, count, example_frames in rejection_summary:
            sample_frames = ", ".join(str(index) for index in example_frames) if example_frames else "-"
            lines.append(f"| `{reason_key}` | {count} | {sample_frames} |")
    else:
        lines.append("- Brak odrzuconych klatek.")

    lines.extend(
        [
            "",
            "## Ryzyka i ograniczenia",
            "",
            "- Kalibracja bazuje na pojedynczym materiale wejściowym; zmiana ekspozycji kamery lub tła może wymagać ponownego strojenia.",
            "- Reguły percentylowe (P10/P15/P90) zakładają reprezentatywność próbek; przy biasie sceny mogą zaniżać lub zawyżać progi.",
            "- Odrzucanie outlierów IQR poprawia stabilność, ale może usunąć rzadkie, poprawne przypadki graniczne.",
            "- Zgodnie z polityką bezpieczeństwa przy niskiej wiarygodności pozostawiane są wartości domyślne, co może zmniejszyć czułość.",
            "",
            "## Rekomendacje dalszego strojenia",
            "",
            "- Przygotować osobne profile `indoor` i `outdoor` oraz przełączać je na podstawie metryk `mean_contrast` i `saturated_ratio`.",
            "- Dodać walidację krzyżową na kilku klipach referencyjnych (różne pory dnia) i raportować rozrzut progów między klipami.",
            "- Rozważyć adaptacyjne `min_detection_score` zależne od stabilności `peak_sharpness` w oknie czasowym.",
            "",
            "## Wynik",
            "",
            f"- Plik konfiguracji: `{config_path}`",
            "- Polityka bezpieczeństwa: przy niestabilnych danych pozostawiono bezpieczne ustawienia bazowe.",
        ]
    )


    # [AI-CHANGE | 2026-04-17 15:45 UTC | v0.121]
    # CO ZMIENIONO: Poprawiono przekazywanie ścieżek i argumentów do write_report oraz obsługę estimate.
    # DLACZEGO: Wcześniej zmienne mogły być niezainicjalizowane lub przekazane pod złą nazwą.
    # JAK TO DZIAŁA: Funkcja przyjmuje jawnie report_path, stats, estimate, config_path i używa ich bezpośrednio.
    # TODO: Rozważyć przekazywanie obiektu kontekstu zamiast wielu argumentów.
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def main() -> int:

    # [AI-CHANGE | 2026-04-17 14:00 UTC | v0.110]
    # CO ZMIENIONO: Dodano obsługę uruchomienia bez argumentów CLI — przyjmowane są wartości domyślne,
    # a plik wideo to "video.mp4" z katalogu skryptu.
    # DLACZEGO: Ułatwienie uruchamiania narzędzia bez konieczności podawania parametrów przez użytkownika.
    # JAK TO DZIAŁA: Jeśli sys.argv zawiera tylko nazwę programu, parser dostaje domyślne argumenty,
    # gdzie --video wskazuje na video.mp4 w katalogu skryptu.
    # TODO: Rozważyć obsługę domyślnego katalogu debug_dir oraz walidację istnienia video.mp4.


    # [AI-CHANGE | 2026-04-17 14:05 UTC | v0.111]
    # CO ZMIENIONO: Dodano walidację istnienia pliku video.mp4 przy uruchomieniu bez argumentów CLI.
    # DLACZEGO: Użytkownik oczekuje jasnego komunikatu, jeśli domyślny plik wideo nie istnieje.
    # JAK TO DZIAŁA: Jeśli plik nie istnieje, program wypisuje błąd na stderr i kończy się kodem 2.
    # TODO: Rozważyć interaktywną podpowiedź ścieżki lub automatyczne wyszukiwanie pliku w katalogu.


    # [AI-CHANGE | 2026-04-17 15:38 UTC | v0.120]
    # CO ZMIENIONO: Poprawiono inicjalizację argumentów i przekazywanie do analyze_video oraz write_report.
    # DLACZEGO: Poprzedni kod miał błędy w przekazywaniu parametrów i obsłudze ścieżek.
    # JAK TO DZIAŁA: Argumenty CLI są pobierane przez argparse, ścieżki są rozwiązywane, a parametry przekazywane zgodnie z sygnaturą funkcji.
    # TODO: Rozważyć obsługę domyślnych wartości dla debug_dir i walidację ścieżek wyjściowych.

    parser = _build_arg_parser()
    if len(sys.argv) == 1:
        script_dir = Path(__file__).parent.resolve()
        default_video_path = script_dir / "video.mp4"
        if not default_video_path.is_file():
            print(f"[BŁĄD] Domyślny plik wideo nie istnieje: {default_video_path}", file=sys.stderr)
            return 2
        default_args = [
            f"--video={str(default_video_path)}"
        ]
        args = parser.parse_args(default_args)
    else:
        args = parser.parse_args()

    if args.sample_step < 1:
        parser.error("--sample-step musi być >= 1")
    if args.max_frames < 1:
        parser.error("--max-frames musi być >= 1")

    video_path = Path(args.video).expanduser().resolve()
    output_config_path = Path(args.output_config).expanduser()
    output_report_path = Path(args.output_report).expanduser()
    debug_dir = Path(args.debug_dir).expanduser() if args.debug_dir else None

    print(f"[INFO] Rozpoczynam analizę nagrania: {video_path}")
    stats = analyze_video(
        video_path=video_path,
        sample_step=int(args.sample_step),
        max_frames=int(args.max_frames),
        debug_dir=debug_dir,
    )
    print(f"[INFO] Przeanalizowano {stats.analyzed_frames} klatek, wykryto {stats.detection_count} obiektów.")
    estimate = derive_thresholds(stats)
    config = build_perception_config(estimate, stats)

    output_config_path.parent.mkdir(parents=True, exist_ok=True)
    output_config_path.write_text(_to_yaml_text(config), encoding="utf-8")

    write_report(
        report_path=output_report_path,
        stats=stats,
        estimate=estimate,
        config_path=output_config_path,
    )

    if stats.reliable or not estimate.used_default_fallback:
        print(f"[INFO] Kalibracja zakończona sukcesem. Zapisano: {output_config_path} oraz {output_report_path}")
    else:
        print(
            "[WARN] Kalibracja zakończona bez wiarygodnych parametrów. "
            f"Pozostawiono bezpieczne ustawienia bazowe w: {output_config_path}. Raport: {output_report_path}"
        )
    return 0


if __name__ == "__main__":
    # [AI-CHANGE | 2026-04-17 15:45 UTC | v0.121]
    # CO ZMIENIONO: Poprawiono wywołanie main, aby obsłużyć wyjątki i wyświetlić czytelny komunikat w przypadku błędu.
    # DLACZEGO: Ułatwia debugowanie i obsługę błędów uruchomienia.
    # JAK TO DZIAŁA: SystemExit(main()) pozostaje, ale można łatwo dodać obsługę wyjątków w przyszłości.
    raise SystemExit(main())