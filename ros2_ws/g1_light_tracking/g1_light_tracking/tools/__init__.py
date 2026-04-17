"""Narzędzia CLI pakietu g1_light_tracking."""

# [AI-CHANGE | 2026-04-17 13:32 UTC | v0.109]
# CO ZMIENIONO: Dodano pakiet `g1_light_tracking.tools`, aby udostępnić entry pointy CLI przez setuptools.
# DLACZEGO: Bez dedykowanego pakietu nie da się stabilnie mapować komend `console_scripts` na moduły dystrybuowane wraz z pakietem.
# JAK TO DZIAŁA: Samo istnienie pliku `__init__.py` oznacza katalog jako pakiet Pythona i pozwala importować moduły narzędziowe.
# TODO: Uzupełnić ten moduł o wspólne helpery CLI (np. walidacja ścieżek i logger konsolowy).
