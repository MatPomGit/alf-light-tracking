"""
[AI-CHANGE | 2026-04-25 08:51 UTC | v0.202]
CO ZMIENIONO: Dodano moduł `e2e` grupujący narzędzia uruchomień end-to-end.
DLACZEGO: Potrzebujemy stabilnej przestrzeni nazw dla entrypointów pomocniczych ROS2 używanych w testach runtime.
JAK TO DZIAŁA: Pakiet eksportuje moduły E2E i pozwala rejestrować je przez `setup.py` jako `console_scripts`.
TODO: Uzupełnić `__all__` po dodaniu kolejnych scenariuszy E2E (np. abort/timeout).
"""
