import cv2
import numpy as np
from filterpy.kalman import KalmanFilter
from typing import Optional, Tuple

class LightSpotDetector:
    def __init__(self, config: dict):
        # Parametry konfiguracyjne (z YAML / ROS params)
        self.blob_params = cv2.SimpleBlobDetector_Params()
        self.blob_params.filterByArea = True
        self.blob_params.minArea = config.get('min_spot_area', 3)      # małe plamki lasera
        self.blob_params.maxArea = config.get('max_spot_area', 500)
        self.blob_params.filterByCircularity = True
        self.blob_params.minCircularity = config.get('min_circularity', 0.5)  # odróżnia od refleksów
        self.blob_params.filterByConvexity = True
        self.blob_params.minConvexity = 0.7
        self.blob_params.filterByInertia = True
        self.blob_params.minInertiaRatio = 0.3
        self.blob_params.filterByColor = True
        self.blob_params.blobColor = 255  # szukamy jasnych blobów

        self.blob_detector = cv2.SimpleBlobDetector_create(self.blob_params)

        # Filtr Kalmana (pozycja x,y)
        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        self.kf.F = np.array([[1,0,1,0],
                              [0,1,0,1],
                              [0,0,1,0],
                              [0,0,0,1]])
        self.kf.H = np.array([[1,0,0,0],
                              [0,1,0,0]])
        self.kf.P *= 1000
        self.kf.R = np.diag([config.get('measurement_noise', 25)]*2)
        self.kf.Q = np.diag([1,1,10,10])  # większa niepewność prędkości
        self.kf.x = np.array([[0],[0],[0],[0]])

        self.last_measurement_time = None
        self.timeout_ms = config.get('tracking_timeout_ms', 200)

    def preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """Adaptacyjne zwiększenie kontrastu i redukcja szumu."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape)==3 else img
        # CLAHE – wydobywa słabe plamki na nierównym tle
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        # Delikatne wygładzenie – nie niszczy małych szczegółów
        blurred = cv2.medianBlur(enhanced, 3)
        return blurred

    def detect_blobs(self, preprocessed: np.ndarray) -> list:
        """Wykrywa bloby o różnych jasnościach (łączy kilka progów)."""
        # Metoda 1: Binaryzacja Otsu – dobra dla średnich plamek
        _, otsu = cv2.threshold(preprocessed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        keypoints_otsu = self.blob_detector.detect(otsu)

        # Metoda 2: Adaptacyjne progowanie – lepsze dla małych plamek na jasnym tle
        adaptive = cv2.adaptiveThreshold(preprocessed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                         cv2.THRESH_BINARY, 11, 2)
        keypoints_adapt = self.blob_detector.detect(adaptive)

        # Metoda 3: Proste progowanie wysoką wartością – dla bardzo intensywnych plamek (laser)
        _, high = cv2.threshold(preprocessed, 240, 255, cv2.THRESH_BINARY)
        keypoints_high = self.blob_detector.detect(high)

        # Połącz i deduplikuj (wg odległości)
        all_kp = keypoints_otsu + keypoints_adapt + keypoints_high
        return self.merge_close_keypoints(all_kp, min_distance=5)

    def merge_close_keypoints(self, kp_list, min_distance=5):
        """Łączy bloby oddalone o mniej niż min_distance – wybiera najjaśniejszy."""
        merged = []
        for kp in kp_list:
            close = False
            for m in merged:
                if np.hypot(kp.pt[0]-m.pt[0], kp.pt[1]-m.pt[1]) < min_distance:
                    # Zostaw ten z większą odpowiedzią (intensywność)
                    if kp.response > m.response:
                        m.pt = kp.pt
                        m.response = kp.response
                    close = True
                    break
            if not close:
                merged.append(kp)
        return merged

    def select_best_spot(self, keypoints, full_image: np.ndarray) -> Optional[Tuple[float, float]]:
        """Spośród wykrytych blobów wybiera najlepszego kandydata."""
        if not keypoints:
            return None

        # Dodatkowe kryteria: jasność w oryginalnym obrazie, okrągłość, kontrast brzegowy
        best_kp = None
        best_score = -1
        gray = cv2.cvtColor(full_image, cv2.COLOR_BGR2GRAY) if len(full_image.shape)==3 else full_image

        for kp in keypoints:
            x, y = int(kp.pt[0]), int(kp.pt[1])
            r = int(kp.size / 2)
            # ROI wokół plamki
            x1, y1 = max(0, x-r), max(0, y-r)
            x2, y2 = min(gray.shape[1], x+r), min(gray.shape[0], y+r)
            roi = gray[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            # Kryterium 1: średnia jasność w ROI (wyższa = lepsza)
            brightness = np.mean(roi)
            # Kryterium 2: kontrast (odchylenie standardowe)
            contrast = np.std(roi)
            # Kryterium 3: okrągłość (pole powierzchni do pola bounding box)
            area = np.pi * (kp.size/2)**2
            bbox_area = (x2-x1)*(y2-y1)
            circularity = area / max(bbox_area, 1)
            # Łączny wynik
            score = brightness * 0.5 + contrast * 0.3 + circularity * 0.2
            if score > best_score:
                best_score = score
                best_kp = kp

        if best_kp is not None:
            return (best_kp.pt[0], best_kp.pt[1])
        return None

    def kalman_update(self, measurement: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
        """Aktualizuje filtr Kalmana i zwraca stabilizowaną pozycję."""
        current_time = cv2.getTickCount() / cv2.getTickFrequency()
        if self.last_measurement_time is not None:
            dt = current_time - self.last_measurement_time
            # Adaptacja macierzy przejścia dla zmiennego dt
            self.kf.F[0,2] = dt
            self.kf.F[1,3] = dt

        if measurement is not None:
            # Pomiar dostępny
            z = np.array([[measurement[0]], [measurement[1]]])
            self.kf.update(z)
            self.last_measurement_time = current_time
        else:
            # Brak pomiaru – predykcja, ale tylko jeśli nie przekroczono timeoutu
            if self.last_measurement_time and (current_time - self.last_measurement_time) > self.timeout_ms/1000.0:
                return None
        # Predykcja zawsze (dla aktualizacji pozycji)
        self.kf.predict()
        return (self.kf.x[0,0], self.kf.x[1,0])

    def process_frame(self, bgr_image: np.ndarray) -> Optional[Tuple[float, float]]:
        """Główna metoda przetwarzania pojedynczej klatki."""
        preprocessed = self.preprocess_image(bgr_image)
        blobs = self.detect_blobs(preprocessed)
        measurement = self.select_best_spot(blobs, bgr_image)
        stabilized = self.kalman_update(measurement)
        return stabilized