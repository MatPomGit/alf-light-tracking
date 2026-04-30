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

<!--
[AI-CHANGE | 2026-04-25 11:18 UTC | v0.202]
CO ZMIENIONO: Dodano twardą macierz środowisk (HARD ENV MATRIX) z jednoznaczną polityką ALLOW/BLOCK, profilem referencyjnym i regułami blokady release.
DLACZEGO: Wdrożenia wymagały sztywnego kontraktu środowiskowego, aby ograniczyć dryf zależności i skrócić diagnozę awarii po rolloutach.
JAK TO DZIAŁA: Pipeline dopuszcza publikację artefaktu tylko dla profilu referencyjnego; każde odchylenie od hard floor skutkuje natychmiastowym NO-GO i brakiem wydania.
TODO: Zautomatyzować walidację hard matrix w CI jako osobny job `env-hard-gate` blokujący merge przy statusie BLOCK.
-->

## Twarda macierz środowisk (HARD ENV MATRIX)

### Polityka nadrzędna
- Do produkcyjnego deploymentu dopuszczony jest wyłącznie profil oznaczony `ALLOW`.
- Każdy profil `BLOCK` powoduje przerwanie rolloutu bez publikacji artefaktu.
- Nie istnieje ścieżka „warunkowa produkcyjnie” — wątpliwa zgodność oznacza `BLOCK`.

### Profil referencyjny (jedyny ALLOW)

| Pole | Wymagana wartość (hard requirement) |
|---|---|
| OS | Ubuntu 24.04 LTS |
| ROS 2 | Jazzy Jalisco |
| Python | 3.12.x |
| Runtime UI | PySide6 6.7.x |
| Build toolchain | colcon + ament + pip (zgodne z lockfile) |
| Czas systemowy | NTP/PTP aktywne, offset <= 100 ms |
| Zasoby hosta | min. 4 vCPU, 16 GB RAM, 80 GB free, SSD NVMe |

### Macierz ALLOW/BLOCK

| ID | OS | ROS 2 | Python | Status | Powód decyzji |
|---|---|---|---|---|---|
| H1 | Ubuntu 24.04 LTS | Jazzy | 3.12.x | **ALLOW** | Profil referencyjny zgodny z testami Stage 0. |
| H2 | Ubuntu 22.04 LTS | Humble | 3.10.x | **BLOCK** | Inna linia ABI/zależności runtime; brak gwarancji przewidywalności rolloutu. |
| H3 | Debian 12 | Jazzy | 3.11.x | **BLOCK** | Dryf pakietów systemowych względem środowiska referencyjnego. |
| H4 | Windows 11 + WSL2 | Jazzy | 3.12.x | **BLOCK** | Brak wsparcia dla operatorskiego deploymentu czasu rzeczywistego. |
| H5 | Ubuntu 24.04 LTS | Jazzy | 3.13.x | **BLOCK** | Niezatwierdzona wersja Pythona poza profilem walidowanym. |

### Hard gates przed wydaniem
1. `env_profile == H1` (dokładne dopasowanie OS/ROS/Python/UI).
2. `colcon build --packages-select g1_light_tracking robot_mission_control` kończy się sukcesem.
3. Smoke launch obu stosów kończy się sukcesem bez alarmów krytycznych.
4. Dependency audit nie wykrywa konfliktów ani braków krytycznych.

Niespełnienie dowolnej bramki => wynik release `NO-GO` i brak publikacji artefaktu.

### Zasada audytu i odstępstw
- Odstępstwa od hard matrix są niedozwolone dla produkcji.
- Dopuszczalne są wyłącznie w środowiskach laboratoryjnych z etykietą `NON-PROD`.
- Artefakt zbudowany poza profilem `H1` musi być oznaczony jako nieprodukcyjny i nie może trafić na stanowisko operatorskie.
