from __future__ import annotations

import argparse
import cv2

from g1_light_tracking.standalone.pipeline import (
    PerceptionEngine,
    SimpleTracker,
    ParcelAggregator,
    draw_overlay,
    summarize_functions,
)
from g1_light_tracking.standalone.profiles import list_profiles, load_profile_dict, sanitize_flags, save_profile_dict

KEY_FLAG_MAP = {
    ord('1'): ('enable_yolo', 'YOLO'),
    ord('2'): ('enable_qr', 'QR'),
    ord('3'): ('enable_apriltag', 'AprilTag'),
    ord('4'): ('enable_light_spot', 'Plamka światła'),
    ord('5'): ('enable_tracking', 'Tracking'),
    ord('6'): ('enable_binding', 'Wiązanie QR->karton'),
}

PROFILE_KEYS = {
    ord('7'): 'full_logistics',
    ord('8'): 'debug_perception',
    ord('9'): 'light_only',
    ord('0'): 'qr_only',
}

HELP_LINES = [
    "Skroty:",
    "q - wyjscie",
    "s - zapis klatki",
    "w - zapisz profil custom_last",
    "h - panel statusu on/off",
    "m - legenda skrotow on/off",
    "1 - YOLO on/off",
    "2 - QR on/off",
    "3 - AprilTag on/off",
    "4 - Plamka swiatla on/off",
    "5 - Tracking on/off",
    "6 - Wiazanie QR->karton on/off",
    "7 - profil full_logistics",
    "8 - profil debug_perception",
    "9 - profil light_only",
    "0 - profil qr_only",
]

def current_flags_dict(perception: PerceptionEngine) -> dict:
    return {
        'enable_yolo': bool(perception.flags.enable_yolo),
        'enable_qr': bool(perception.flags.enable_qr),
        'enable_apriltag': bool(perception.flags.enable_apriltag),
        'enable_light_spot': bool(perception.flags.enable_light_spot),
        'enable_tracking': bool(perception.flags.enable_tracking),
        'enable_binding': bool(perception.flags.enable_binding),
    }


def apply_named_profile(perception: PerceptionEngine, profile_name: str):
    data, _ = load_profile_dict(profile_name)
    applied = perception.apply_profile(sanitize_flags(data))
    return applied


def run_gui(camera: int, model: str, profile: str = ''):
    cap = cv2.VideoCapture(camera)
    camera_open = cap.isOpened()
    if not camera_open:
        raise RuntimeError(f'Nie można otworzyć kamery: {camera}')

    perception = PerceptionEngine(model_path=model)
    tracker = SimpleTracker()
    aggregator = ParcelAggregator()

    if profile:
        apply_named_profile(perception, profile)

    status = perception.build_status(camera_open=True, gui_enabled=True, cli_enabled=False)

    print("Tryb GUI uruchomiony.")
    if profile:
        print(f"Profil startowy: {profile}")
    print("Aktywne funkcje:")
    for line in status.as_lines():
        print(f" - {line}")
    print("Klawisze: q - wyjście, s - zapis klatki, w - zapisz profil, h - panel statusu, m - legenda, 1..6 - przełączniki funkcji, 7..0 - profile.")

    frame_no = 0
    state_text = 'standalone_gui'
    show_status_panel = True
    show_help_panel = True

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Brak klatki z kamery. Kończenie.")
            break

        detections = perception.detect(frame)
        tracks = tracker.update(detections, enabled=perception.flags.enable_tracking)
        parcel_tracks = aggregator.build(tracks, enabled=perception.flags.enable_binding)
        status = perception.build_status(camera_open=True, gui_enabled=True, cli_enabled=False)

        if parcel_tracks:
            best = parcel_tracks[0]
            state_text = f"parcel={best.parcel_box_track_id} shipment={best.shipment_id or '-'} state={best.logistics_state}"
        else:
            state_text = f"tracks={len(tracks)}"

        status_lines = summarize_functions(status, detections, tracks, parcel_tracks) if show_status_panel else None
        help_lines = HELP_LINES if show_help_panel else None
        overlay = draw_overlay(frame, tracks, parcel_tracks, state_text, status_lines=status_lines, help_lines=help_lines)
        cv2.imshow("g1_light_tracking GUI", overlay)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        if key == ord('s'):
            out = f"g1_light_tracking_frame_{frame_no:06d}.png"
            cv2.imwrite(out, overlay)
            print(f"Zapisano: {out}")
        if key == ord('w'):
            try:
                path = save_profile_dict('custom_last', current_flags_dict(perception))
                print(f"Zapisano profil: {path.name}")
            except Exception as exc:
                print(f"Blad zapisu profilu: {exc}")
        if key == ord('h'):
            show_status_panel = not show_status_panel
            print(f"Panel statusu: {'WŁĄCZONY' if show_status_panel else 'WYŁĄCZONY'}")
        if key == ord('m'):
            show_help_panel = not show_help_panel
            print(f"Legenda skrótów: {'WŁĄCZONA' if show_help_panel else 'WYŁĄCZONA'}")
        if key in KEY_FLAG_MAP:
            flag_name, label = KEY_FLAG_MAP[key]
            new_value = perception.toggle_flag(flag_name)
            print(f"{label}: {'WŁĄCZONE' if new_value else 'WYŁĄCZONE'}")
        if key in PROFILE_KEYS:
            profile_name = PROFILE_KEYS[key]
            try:
                applied = apply_named_profile(perception, profile_name)
                print(f"Profil {profile_name}: {applied}")
            except Exception as exc:
                print(f"Blad ladowania profilu {profile_name}: {exc}")
        frame_no += 1

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description='Standalone GUI dla g1_light_tracking bez ROS 2 topiców.')
    parser.add_argument('--camera', type=int, default=0, help='Indeks kamery OpenCV.')
    parser.add_argument('--model', type=str, default='yolov8n.pt', help='Ścieżka do modelu YOLO.')
    parser.add_argument('--profile', type=str, default='', help='Nazwa profilu startowego, np. full_logistics.')
    args = parser.parse_args()
    run_gui(camera=args.camera, model=args.model, profile=args.profile)


if __name__ == '__main__':
    main()
