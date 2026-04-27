<!--
[AI-CHANGE | 2026-04-27 09:05 UTC | v0.203]
CO ZMIENIONO: Dodano sekcję formalnej akceptacji operacyjnej dla twardej macierzy środowisk wraz z datą i właścicielem.
DLACZEGO: Backlog OPS-002 wymagał jawnego potwierdzenia, że macierz została przyjęta jako obowiązujący kontrakt release.
JAK TO DZIAŁA: Sekcja „Akceptacja operacyjna” pełni rolę bramki decyzyjnej i jest źródłem prawdy dla statusu `DONE` w `TASKS.md`.
TODO: Zintegrować status akceptacji z automatycznym gate w CI (`env-hard-gate`) i raportowaniem do release notes.
-->
<!--
[AI-CHANGE | 2026-04-25 16:38 UTC | v0.202]
CO ZMIENIONO: Dodano osobny dokument „twardej macierzy środowisk” z jednoznaczną polityką ALLOW/BLOCK, profilem referencyjnym oraz bramkami release.
DLACZEGO: Przewidywalne wdrożenia wymagają sztywnego kontraktu środowiskowego eliminującego dryf zależności i niekontrolowane odstępstwa.
JAK TO DZIAŁA: Każdy rollout przechodzi przez hard gate; publikacja artefaktu jest możliwa wyłącznie dla profilu referencyjnego H1.
TODO: Dodać automatyczny walidator `env-hard-gate` uruchamiany w CI przed etapem publikacji artefaktów.
-->

# Twarda macierz środowisk (HARD ENV MATRIX)

## Akceptacja operacyjna
- Status: `ZATWIERDZONE`
- Data akceptacji (UTC): `2026-04-27`
- Właściciel akceptacji: `@release_mgmt`
- Zakres: Stage 0, decyzje `ALLOW/BLOCK` przed publikacją artefaktów.

## Cel
Dokument definiuje **nieprzekraczalne** wymagania środowiskowe dla Stage 0.
Jeśli profil środowiska nie spełnia warunków `ALLOW`, rollout musi zakończyć się `NO-GO`.

## Zasady nadrzędne
1. Produkcja akceptuje tylko profil `H1` (`ALLOW`).
2. Każdy inny profil oznacza `BLOCK` i brak publikacji artefaktu.
3. Nie ma wyjątków „na szybko” dla środowisk operatorskich.
4. Wątpliwość co do zgodności = decyzja `BLOCK` (fail-safe deployment).

## Profil referencyjny H1 (jedyny ALLOW)

| Parametr | Wymaganie |
|---|---|
| OS | Ubuntu 24.04 LTS |
| ROS 2 | Jazzy Jalisco |
| Python | 3.12.x |
| Runtime UI | PySide6 6.7.x |
| Build toolchain | colcon + ament + pip (zgodne z lockfile) |
| Synchronizacja czasu | NTP/PTP aktywne, offset <= 100 ms |
| Zasoby hosta | min. 4 vCPU, 16 GB RAM, 80 GB free, SSD NVMe |

## Macierz ALLOW/BLOCK

| ID | OS | ROS 2 | Python | Status | Uzasadnienie |
|---|---|---|---|---|---|
| H1 | Ubuntu 24.04 LTS | Jazzy | 3.12.x | **ALLOW** | Walidowany profil release Stage 0. |
| H2 | Ubuntu 22.04 LTS | Humble | 3.10.x | **BLOCK** | Inny stos ABI i wysoki dryf zależności runtime. |
| H3 | Debian 12 | Jazzy | 3.11.x | **BLOCK** | Niezgodna baza pakietów systemowych względem H1. |
| H4 | Windows 11 + WSL2 | Jazzy | 3.12.x | **BLOCK** | Brak wsparcia operatorskiego deploymentu czasu rzeczywistego. |
| H5 | Ubuntu 24.04 LTS | Jazzy | 3.13.x | **BLOCK** | Niezatwierdzona wersja Pythona poza profilem testowym. |

## Hard gates przed release
1. **Gate-ENV:** dokładne dopasowanie do `H1`.
2. **Gate-BUILD:**
   `colcon build --packages-select g1_light_tracking robot_mission_control` kończy się sukcesem.
3. **Gate-SMOKE:**
   oba launch-e (`mission_control` i `light_tracking_stack`) kończą się bez alarmów krytycznych.
4. **Gate-DEPENDENCY:**
   brak konfliktów krytycznych w audycie zależności.

Niespełnienie dowolnego gate = `NO-GO` i brak artefaktu produkcyjnego.

## Polityka odstępstw
- Odstępstwa są dopuszczalne wyłącznie dla `NON-PROD`.
- Artefakt spoza H1 musi być oznaczony jako nieprodukcyjny.
- Artefakt nieprodukcyjny nie może zostać wdrożony na stanowisko operatorskie.

## Wymagane metadane release
Każdy release musi zawierać:
- identyfikator profilu środowiska (`H1`),
- wynik gate-ów (`ENV/BUILD/SMOKE/DEPENDENCY`),
- hash commita i timestamp UTC,
- link do raportu audytu zależności.
