<!--
[AI-CHANGE | 2026-04-20 20:39 UTC | v0.153]
CO ZMIENIONO: Utworzono nowy dokument specyfikacyjny/architektoniczny/użytkowy dla etapu Stage 0.
DLACZEGO: Uporządkowanie wymagań i procedur operacyjnych projektu oraz formalizacja kryteriów jakości.
JAK TO DZIAŁA: Dokument stanowi źródło referencyjne; definiuje zasady, zakres i wymagane działania dla zespołu.
TODO: Uzupełnić dokument o referencje do konkretnych modułów i artefaktów CI po ich wdrożeniu.
-->

# Wersjonowanie i build

## Model wersjonowania
- SemVer dla artefaktów aplikacyjnych.
- Numer build zawiera hash commita i znacznik czasu UTC.

## Wymagania pipeline build
1. Build reprodukowalny z lockfile.
2. Artefakty podpisane i śledzone w rejestrze.
3. Raport kompatybilności kontraktów danych przy każdej zmianie minor/major.

## Polityka jakości
- Wydanie nie może włączać trybu domyślnego, który maskuje błędne detekcje.
- Gdy test jakości nie przechodzi, release jest blokowany: **lepszy brak wyniku niż błędny wynik**.
- **Brak danych fikcyjnych** w testach akceptacyjnych bez oznaczenia `synthetic=true`.


<!--
[AI-CHANGE | 2026-04-24 12:20 UTC | v0.203]
CO ZMIENIONO: Dodano listę wspieranych kombinacji środowiska (OS/ROS/Python) oraz minimalne wymagania hosta dla przewidywalnego deploymentu.
DLACZEGO: Celem jest ograniczenie niespodzianek zależnościowych i jednoznaczne określenie, które konfiguracje są dopuszczone do wdrożenia.
JAK TO DZIAŁA: Deployment jest dozwolony wyłącznie dla kombinacji oznaczonych jako SUPPORTED, a pre-flight musi przejść walidację wymagań hosta i narzędzi.
TODO: Dodać automatyczny skrypt pre-flight (CLI) który zablokuje rollout przy wykryciu konfiguracji spoza tabeli SUPPORTED.
-->

## Wspierane kombinacje środowiska (Stage 0)

> Statusy:
> - `SUPPORTED` — konfiguracja dopuszczona do deploymentu produkcyjnego.
> - `CONDITIONAL` — tylko testy bench/pilotaż, bez rolloutu na wszystkie stanowiska.
> - `UNSUPPORTED` — brak wsparcia, deployment zablokowany.

| ID | OS hosta | ROS 2 | Python | Runtime UI | Status | Uwagi operacyjne |
|---|---|---|---|---|---|---|
| C1 | Ubuntu 24.04 LTS | Jazzy Jalisco | 3.12.x | PySide6 6.7.x | SUPPORTED | Bazowa kombinacja dla wdrożeń Stage 0. |
| C2 | Ubuntu 22.04 LTS | Humble Hawksbill | 3.10.x | PySide6 6.5.x | CONDITIONAL | Tylko środowiska przejściowe; wymaga dodatkowego smoke testu UI+ROS po każdym update. |
| C3 | Debian 12 | Jazzy Jalisco | 3.11.x | PySide6 6.6.x | UNSUPPORTED | Niezgodność z docelową bazą pakietów i brak gwarancji kompatybilności launch/runtime. |
| C4 | Windows 11 + WSL2 | Jazzy Jalisco | 3.12.x | PySide6 6.7.x | UNSUPPORTED | Dopuszczalne lokalnie do developmentu, niedopuszczalne do deploymentu operatorskiego. |

### Zasada decyzyjna deploymentu
- Jeżeli wykryta kombinacja nie jest `SUPPORTED`, deployment kończy się wynikiem NO-GO.
- Dla `CONDITIONAL` wymagane jest formalne odstępstwo release managera i udokumentowany rollback.
- Dla `UNSUPPORTED` pipeline ma zwrócić brak artefaktu produkcyjnego (fail-safe zamiast ryzykownego wdrożenia).

## Minimalne wymagania hosta (per stanowisko operatorskie)

### Sprzęt i system
- CPU: min. `4 vCPU` (zalecane 8 vCPU dla równoległego rosbag + UI).
- RAM: min. `16 GB` (hard floor), zalecane `32 GB`.
- Dysk: min. `80 GB` wolnego miejsca, w tym min. `40 GB` buforu na rosbag.
- Storage: SSD NVMe (SATA HDD niedopuszczalne dla środowiska produkcyjnego).
- GPU: opcjonalnie; gdy brak GPU, konfiguracja musi utrzymać SLA opóźnień na CPU.

### Narzędzia i zależności
- `python3 --version` zgodne z tabelą kombinacji (`major.minor` musi się zgadzać).
- `ros2 --version` i dystrybucja ROS zgodna z tabelą kombinacji.
- `colcon`, `ament`, `pip` dostępne w `PATH` użytkownika wdrożeniowego.
- Lockfile zależności (`requirements*.txt`) musi instalować się bez konfliktów resolvera.

### Parametry operacyjne i bezpieczeństwo
- Czas systemowy synchronizowany przez NTP (odchylenie <= 100 ms).
- Lokalizacja logów i rosbag na partycji z monitoringiem wolnego miejsca.
- Host musi uruchamiać pre-flight check przed każdym rolloutem (`build`, `launch`, `dependency audit`).
- Gdy którykolwiek warunek minimalny nie jest spełniony, proces wdrożenia ma zwrócić NO-GO i nie publikować artefaktu.

## Minimalny pre-flight gate (checklista)
1. Walidacja kombinacji (`OS`, `ROS`, `Python`) = `SUPPORTED`.
2. Walidacja zasobów hosta (`CPU`, `RAM`, `disk_free`) >= minimum.
3. `colcon build --packages-select g1_light_tracking robot_mission_control` bez błędów.
4. Smoke launch: `ros2 launch robot_mission_control mission_control.launch.py` oraz `ros2 launch g1_light_tracking light_tracking_stack.launch.py`.
5. Jeżeli którykolwiek krok kończy się błędem lub statusem niepewnym, wynik pre-flight = NO-GO (brak wdrożenia).
