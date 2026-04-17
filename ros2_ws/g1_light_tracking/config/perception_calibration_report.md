# Raport kalibracji percepcji

## Metadane uruchomienia

- Data UTC: 2026-04-17T14:23:25.814652+00:00
- Input video: `C:\Users\matpo\repo\alf-light-tracking\ros2_ws\g1_light_tracking\tools\video.mp4`
- Input frame count: **734**
- Sampled frames: **734**
- Analyzed frames: **245**
- Status kalibracji: **⚠️ brak wiarygodnych parametrów**
- Powód odrzucenia: **Niestabilne statystyki detekcji między próbkami**
- Fallback do domyślnych: **tak**
- Powód fallbacku: **Kalibracja oznaczona jako niewiarygodna przez analizę statystyk.**
- Detection ratio: **0.102** (25/245)
- Mediana confidence: **0.607**
- Mediana score_proxy: **0.592**

## Parametry i reguły wyliczenia

| Parameter | Value | Source metric | Reguła wyliczenia |
|---|---:|---|---|
| `min_detection_confidence` | `0.0000` | `confidence` | fallback bezpieczeństwa: wartość domyślna z DetectorConfig (0 próbek estymacji) |
| `min_detection_score` | `0.0000` | `score_proxy` | fallback bezpieczeństwa: wartość domyślna z DetectorConfig (0 próbek estymacji) |
| `min_area` | `10.0000` | `area` | fallback bezpieczeństwa: wartość domyślna z DetectorConfig (0 próbek estymacji) |
| `min_mean_contrast` | `4.0000` | `mean_contrast` | fallback bezpieczeństwa: wartość domyślna z DetectorConfig (0 próbek estymacji) |
| `min_peak_sharpness` | `6.0000` | `peak_sharpness` | fallback bezpieczeństwa: wartość domyślna z DetectorConfig (0 próbek estymacji) |
| `max_saturated_ratio` | `0.3500` | `saturated_ratio` | fallback bezpieczeństwa: wartość domyślna z DetectorConfig (0 próbek estymacji) |

## Wagi confidence (znormalizowane do sumy 1.0)

| Parameter | Value | Source metric | Reguła wyliczenia |
|---|---:|---|---|
| `confidence_weight_shape` | `0.3200` | `scene_statistics` | Scena ma podwyższoną saturację, więc zwiększamy wpływ kary saturacji i sygnałów kształtu. |
| `confidence_weight_brightness` | `0.2200` | `scene_statistics` | Jasność opisuje siłę sygnału, ale nie może dominować nad geometrią plamki. |
| `confidence_weight_contrast` | `0.2400` | `scene_statistics` | Niski kontrast lokalny wymaga premiowania cechy kontrastu, aby odsiać tło. |
| `confidence_weight_sharpness` | `0.2200` | `scene_statistics` | Niska ostrość piku wymaga ostrożności i utrzymania istotnej wagi cechy sharpness. |

## Odrzucone klatki i powody

| Powód odrzucenia | Liczba klatek | Przykładowe indeksy klatek |
|---|---:|---|
| `brak_detekcji` | 220 | 0, 3, 6, 9, 12, 15, 18, 21 |
| `peak_sharpness<min_peak_sharpness` | 2 | 705, 711 |

## Ryzyka i ograniczenia

- Kalibracja bazuje na pojedynczym materiale wejściowym; zmiana ekspozycji kamery lub tła może wymagać ponownego strojenia.
- Reguły percentylowe (P10/P15/P90) zakładają reprezentatywność próbek; przy biasie sceny mogą zaniżać lub zawyżać progi.
- Odrzucanie outlierów IQR poprawia stabilność, ale może usunąć rzadkie, poprawne przypadki graniczne.
- Zgodnie z polityką bezpieczeństwa przy niskiej wiarygodności pozostawiane są wartości domyślne, co może zmniejszyć czułość.

## Rekomendacje dalszego strojenia

- Przygotować osobne profile `indoor` i `outdoor` oraz przełączać je na podstawie metryk `mean_contrast` i `saturated_ratio`.
- Dodać walidację krzyżową na kilku klipach referencyjnych (różne pory dnia) i raportować rozrzut progów między klipami.
- Rozważyć adaptacyjne `min_detection_score` zależne od stabilności `peak_sharpness` w oknie czasowym.

## Wynik

- Plik konfiguracji: `ros2_ws\g1_light_tracking\config\perception.yaml`
- Polityka bezpieczeństwa: przy niestabilnych danych pozostawiono bezpieczne ustawienia bazowe.
