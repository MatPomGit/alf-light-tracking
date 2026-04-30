# [CHANGE | 2026-04-20 14:12 UTC | v0.141]
# CO ZMIENIONO: Dodano lokalne zasady pracy dla poddrzewa robot_mission_control.
# DLACZEGO: Chcemy utrzymać spójność stylu i bezpieczne zachowanie UI w obszarze aplikacji desktopowej.
# JAK TO DZIAŁA: Instrukcje poniżej obowiązują dla wszystkich plików w tym katalogu i niżej.
# TODO: Doprecyzować reguły testów integracyjnych Qt+ROS po przygotowaniu pipeline CI.

## Zasady lokalne

1. Komentarze techniczne zapisuj po polsku.
2. Kod źródłowy (identyfikatory) zapisuj po angielsku.
3. W logice mostu ROS preferuj bezpieczny fallback: gdy dane są niepewne lub brak połączenia, zwracaj stan `BRAK DANYCH`.
4. Niegotowe elementy UI muszą być disabled i mieć etykietę `NIEDOSTĘPNE W TEJ WERSJI`.
