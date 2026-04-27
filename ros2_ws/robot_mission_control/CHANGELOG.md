<!-- [AI-CHANGE | 2026-04-20 14:12 UTC | v0.141] -->
<!-- CO ZMIENIONO: Dodano dziennik zmian dla nowego modułu robot_mission_control. -->
<!-- DLACZEGO: Potrzebna jest ścieżka audytowa dla kolejnych iteracji i decyzji architektonicznych. -->
<!-- JAK TO DZIAŁA: Sekcja wersji zapisuje zakres zmian i poziom gotowości komponentów. -->
<!-- TODO: Zintegrować changelog z automatycznym generowaniem release notes w CI/CD. -->

# Changelog

<!--
[AI-CHANGE | 2026-04-27 12:03 UTC | v0.203]
CO ZMIENIONO: Uporządkowano strukturę CHANGELOG.md tak, aby przechowywał wyłącznie fakty releasowe bez szczegółów commitowych.
DLACZEGO: Ten sam fakt nie może występować równolegle w wielu plikach, a szczegóły techniczne należą do COMMIT_LOG.md.
JAK TO DZIAŁA: Każdy wpis wersji zawiera tylko datę wydania, poziom gotowości i wpływ produktowy; implementacyjne detale są referencją do COMMIT_LOG.md.
TODO: Dodać sekcję "Breaking changes" i automatyczną walidację semver podczas tworzenia release.
-->
## Zakres dokumentu
- Ten plik opisuje wyłącznie historię wersji/release.
- Szczegóły techniczne commitów i PR utrzymujemy tylko w `COMMIT_LOG.md`.
- Statusy zadań backlogu utrzymujemy tylko w `TASKS.md`.

## 0.1.0 - 2026-04-20

- Pierwsze wydanie modułu `robot_mission_control` do użytku operatorskiego (status: `INITIAL RELEASE`).
- Udostępniono bezpieczny tryb pracy: preferencja `BRAK DANYCH`/`UNAVAILABLE` zamiast ryzyka błędnej prezentacji danych.
