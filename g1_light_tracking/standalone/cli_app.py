from __future__ import annotations

import argparse
import threading
import queue
import time
import cv2

from g1_light_tracking.standalone.pipeline import (
    PerceptionEngine,
    SimpleTracker,
    ParcelAggregator,
    summarize_functions,
)
from g1_light_tracking.standalone.profiles import (
    list_profiles,
    load_profile_dict,
    sanitize_flags,
    save_profile_dict,
)

FLAG_MAP = {
    'yolo': 'enable_yolo',
    'qr': 'enable_qr',
    'apriltag': 'enable_apriltag',
    'light': 'enable_light_spot',
    'tracking': 'enable_tracking',
    'binding': 'enable_binding',
}


def current_flags_dict(perception: PerceptionEngine) -> dict:
    return {
        'enable_yolo': bool(perception.flags.enable_yolo),
        'enable_qr': bool(perception.flags.enable_qr),
        'enable_apriltag': bool(perception.flags.enable_apriltag),
        'enable_light_spot': bool(perception.flags.enable_light_spot),
        'enable_tracking': bool(perception.flags.enable_tracking),
        'enable_binding': bool(perception.flags.enable_binding),
    }


def print_help():
    print("Dostepne komendy:")
    print("  status")
    print("  help")
    print("  profiles")
    print("  profile <nazwa>")
    print("  saveprofile <nazwa>")
    print("  yolo on|off")
    print("  qr on|off")
    print("  apriltag on|off")
    print("  light on|off")
    print("  tracking on|off")
    print("  binding on|off")
    print("  quit")


def print_header(status):
    print("=" * 80)
    print("g1_light_tracking - tryb standalone CLI")
    print("- Aktywne funkcje i moduly:")
    for line in status.as_lines():
        print(f"  * {line}")
    print("- Wpisz 'help', aby zobaczyc komendy runtime.")
    print("=" * 80)


def input_worker(cmd_queue: "queue.Queue[str]"):
    while True:
        try:
            cmd = input().strip()
        except EOFError:
            break
        cmd_queue.put(cmd)
        if cmd == 'quit':
            break


def handle_command(cmd: str, perception: PerceptionEngine):
    parts = cmd.strip().split()
    parts_lower = [p.lower() for p in parts]
    if not parts_lower:
        return False
    if parts_lower[0] == 'help':
        print_help()
        return False
    if parts_lower[0] == 'status':
        return False
    if parts_lower[0] == 'profiles':
        profiles = list_profiles()
        print("Dostepne profile:")
        for name in profiles:
            print(f" - {name}")
        return False
    if parts_lower[0] == 'profile' and len(parts) == 2:
        try:
            data, path = load_profile_dict(parts[1])
            applied = perception.apply_profile(sanitize_flags(data))
            print(f"[MENU] Zaladowano profil: {parts[1]} ({path.name})")
            print(f"[MENU] Ustawienia: {applied}")
        except Exception as exc:
            print(f"[MENU] Blad ladowania profilu: {exc}")
        return False
    if parts_lower[0] == 'saveprofile' and len(parts) == 2:
        try:
            path = save_profile_dict(parts[1], current_flags_dict(perception))
            print(f"[MENU] Zapisano profil: {path.name}")
        except Exception as exc:
            print(f"[MENU] Blad zapisu profilu: {exc}")
        return False
    if parts_lower[0] == 'quit':
        return True
    if len(parts_lower) == 2 and parts_lower[0] in FLAG_MAP and parts_lower[1] in {'on', 'off'}:
        perception.set_flag(FLAG_MAP[parts_lower[0]], parts_lower[1] == 'on')
        print(f"[MENU] {parts_lower[0]} -> {parts_lower[1]}")
        return False
    print("[MENU] Nieznana komenda.")
    print_help()
    return False


def run_cli(camera: int, model: str, max_frames: int = 0, show_every: int = 10, profile: str = ''):
    cap = cv2.VideoCapture(camera)
    camera_open = cap.isOpened()
    if not camera_open:
        raise RuntimeError(f'Nie można otworzyć kamery: {camera}')

    perception = PerceptionEngine(model_path=model)
    tracker = SimpleTracker()
    aggregator = ParcelAggregator()

    if profile:
        data, _ = load_profile_dict(profile)
        perception.apply_profile(sanitize_flags(data))

    status = perception.build_status(camera_open=True, cli_enabled=True, gui_enabled=False)

    cmd_queue: "queue.Queue[str]" = queue.Queue()
    thread = threading.Thread(target=input_worker, args=(cmd_queue,), daemon=True)
    thread.start()

    frame_idx = 0
    started = time.time()
    print_header(status)
    if profile:
        print(f"[PROFILE] Aktywny profil startowy: {profile}")
    print("Tryb CLI uruchomiony. Naciśnij Ctrl+C lub wpisz 'quit', aby zakończyć.")

    while True:
        while not cmd_queue.empty():
            cmd = cmd_queue.get_nowait()
            should_quit = handle_command(cmd, perception)
            if should_quit:
                cap.release()
                elapsed = max(1e-6, time.time() - started)
                print(f"Zakończono. frames={frame_idx}, fps={frame_idx / elapsed:.2f}")
                return

        ok, frame = cap.read()
        if not ok:
            print("Brak klatki z kamery. Kończenie.")
            break

        detections = perception.detect(frame)
        tracks = tracker.update(detections, enabled=perception.flags.enable_tracking)
        parcel_tracks = aggregator.build(tracks, enabled=perception.flags.enable_binding)
        status = perception.build_status(camera_open=True, cli_enabled=True, gui_enabled=False)

        frame_idx += 1
        if frame_idx % max(1, show_every) == 0:
            print("=" * 80)
            print(f"Klatka={frame_idx}  detekcje={len(detections)}  tracki={len(tracks)}  przesylki={len(parcel_tracks)}")
            for line in summarize_functions(status, detections, tracks, parcel_tracks):
                print(f"[STATUS] {line}")
            for tr in tracks[:8]:
                print(f"[TRACK] id={tr.track_id} type={tr.target_type} cls={tr.class_name} conf={tr.confidence:.2f} "
                      f"uv=({tr.center_u:.1f},{tr.center_v:.1f}) payload={tr.payload[:40]}")
            for pt in parcel_tracks[:5]:
                print(f"[PARCEL] box={pt.parcel_box_track_id} qr={pt.qr_track_id} shipment={pt.shipment_id} "
                      f"pickup={pt.pickup_zone} dropoff={pt.dropoff_zone} state={pt.logistics_state}")
            print("[MENU] status | profiles | profile <nazwa> | saveprofile <nazwa> | yolo/qr/apriltag/light/tracking/binding on|off | help | quit")

        if max_frames > 0 and frame_idx >= max_frames:
            break

    elapsed = max(1e-6, time.time() - started)
    print(f"Zakończono. frames={frame_idx}, fps={frame_idx / elapsed:.2f}")
    cap.release()


def main():
    parser = argparse.ArgumentParser(description='Standalone CLI dla g1_light_tracking bez ROS 2 topiców.')
    parser.add_argument('--camera', type=int, default=0, help='Indeks kamery OpenCV.')
    parser.add_argument('--model', type=str, default='yolov8n.pt', help='Ścieżka do modelu YOLO.')
    parser.add_argument('--max-frames', type=int, default=0, help='0 = bez limitu.')
    parser.add_argument('--show-every', type=int, default=10, help='Co ile klatek wypisywać stan.')
    parser.add_argument('--profile', type=str, default='', help='Nazwa profilu startowego, np. full_logistics.')
    args = parser.parse_args()
    run_cli(camera=args.camera, model=args.model, max_frames=args.max_frames, show_every=args.show_every, profile=args.profile)


if __name__ == '__main__':
    main()
