from __future__ import annotations

from pathlib import Path
import json
from typing import Dict, Tuple

PROFILE_KEYS = [
    'enable_yolo',
    'enable_qr',
    'enable_apriltag',
    'enable_light_spot',
    'enable_tracking',
    'enable_binding',
]


def get_profiles_dir() -> Path:
    return Path(__file__).resolve().parents[2] / 'profiles'


def list_profiles() -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    pdir = get_profiles_dir()
    if not pdir.exists():
        return out
    for path in sorted(pdir.glob('*.json')):
        out[path.stem] = path
    return out


def load_profile_dict(profile_name: str) -> Tuple[dict, Path]:
    profiles = list_profiles()
    if profile_name not in profiles:
        raise FileNotFoundError(f'Profil nie istnieje: {profile_name}')
    path = profiles[profile_name]
    data = json.loads(path.read_text(encoding='utf-8'))
    return data, path


def sanitize_flags(data: dict) -> dict:
    out = {}
    for key in PROFILE_KEYS:
        if key in data:
            out[key] = bool(data[key])
    return out


def save_profile_dict(profile_name: str, data: dict) -> Path:
    clean_name = profile_name.strip().replace(' ', '_')
    if not clean_name:
        raise ValueError('Nazwa profilu nie może być pusta')
    safe = []
    for ch in clean_name:
        if ch.isalnum() or ch in ('_', '-'):
            safe.append(ch)
    clean_name = ''.join(safe)
    if not clean_name:
        raise ValueError('Nazwa profilu po sanitizacji jest pusta')
    pdir = get_profiles_dir()
    pdir.mkdir(parents=True, exist_ok=True)
    path = pdir / f'{clean_name}.json'
    payload = sanitize_flags(data)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return path
