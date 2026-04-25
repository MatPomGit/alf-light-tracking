"""Współdzielone mapowanie komunikatów operatorskich dla kart UI."""

from __future__ import annotations

from dataclasses import dataclass


# [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
# CO ZMIENIONO: Dodano współdzielony moduł mapowania komunikatów operatorskich
#               (sekcje „co się stało” i „co zrobić”) oraz mapowanie statusu akcji na stan misji.
# DLACZEGO: Overview/Diagnostics/Controls/Rosbag muszą korzystać z jednej semantyki, aby operator
#           dostawał spójny komunikat niezależnie od zakładki i nie podejmował sprzecznych decyzji.
# JAK TO DZIAŁA: `resolve_operator_guidance` najpierw sprawdza `reason_code`, potem status domenowy;
#                gdy brak znanego mapowania, zwracany jest bezpieczny fallback z zaleceniem wstrzymania
#                ryzykownych działań (lepiej brak akcji niż działanie na błędnych danych).
# TODO: Przenieść mapy do pliku konfiguracyjnego YAML, aby zespół operacyjny mógł je aktualizować bez deployu.
@dataclass(frozen=True, slots=True)
class OperatorGuidance:
    meaning: str
    action: str


FALLBACK_GUIDANCE = OperatorGuidance(
    meaning="Kod lub status nie ma jeszcze opisu operatorskiego.",
    action="Wstrzymaj ryzykowne działania, zapisz kontekst i eskaluj do wsparcia technicznego.",
)

CODE_GUIDANCE_MAP: dict[str, OperatorGuidance] = {
    "stale_data": OperatorGuidance(
        meaning="Dane są przeterminowane i nie odzwierciedlają bieżącego stanu robota.",
        action="Wstrzymaj akcje zależne od tej telemetrii i sprawdź opóźnienia źródła danych.",
    ),
    "missing_data": OperatorGuidance(
        meaning="Brakuje wymaganej próbki telemetrycznej.",
        action="Zweryfikuj publisher; jeśli brak próbki się utrzymuje, wykonaj reconnect kanału.",
    ),
    "heartbeat_missing": OperatorGuidance(
        meaning="Brak heartbeat z warstwy ROS bridge.",
        action="Sprawdź procesy ROS2 i sieć; nie uruchamiaj nowych komend ruchu do czasu odzyskania heartbeat.",
    ),
    "heartbeat_stale": OperatorGuidance(
        meaning="Heartbeat dociera zbyt rzadko i stan może być nieaktualny.",
        action="Przejdź w tryb bezpieczny i sprawdź obciążenie CPU/sieci po stronie ROS.",
    ),
    "ros_unavailable": OperatorGuidance(
        meaning="Warstwa ROS jest niedostępna dla aplikacji operatorskiej.",
        action="Zweryfikuj ROS_DOMAIN_ID oraz node managera; po naprawie odśwież status.",
    ),
    "reconnect_failed": OperatorGuidance(
        meaning="Automatyczna próba ponownego połączenia nie powiodła się.",
        action="Wykonaj kontrolowany restart bridge ROS i potwierdź powrót statusu CONNECTED.",
    ),
    "node_not_initialized": OperatorGuidance(
        meaning="Node manager nie został poprawnie zainicjalizowany.",
        action="Sprawdź konfigurację startową i uruchom Mission Control ponownie.",
    ),
    "dependency_report_empty": OperatorGuidance(
        meaning="Raport zależności jest pusty, więc gotowość środowiska jest niepewna.",
        action="Zweryfikuj źródło dependency audit i traktuj system jako niegotowy operacyjnie.",
    ),
    "action_contract_missing": OperatorGuidance(
        meaning="Brakuje kontraktu Action wymaganego do sterowania misją.",
        action="Napraw konfigurację backendu Action i dopiero potem uruchamiaj misję.",
    ),
    "action_backend_unavailable": OperatorGuidance(
        meaning="Backend akcji jest niedostępny, więc komendy operatorskie nie zostaną wysłane.",
        action="Nie zaczynaj nowej misji; sprawdź log backendu i przywróć kanał Action.",
    ),
    "MC_CFG_001": OperatorGuidance(
        meaning="Brakuje wymaganego pola w konfiguracji.",
        action="Uzupełnij brakujący klucz w pliku konfiguracyjnym zgodnie z dokumentacją wdrożeniową.",
    ),
    "MC_CFG_002": OperatorGuidance(
        meaning="Pole konfiguracji ma nieprawidłowy typ.",
        action="Popraw typ wartości w YAML/JSON i uruchom walidację konfiguracji.",
    ),
    "MC_CFG_003": OperatorGuidance(
        meaning="Pole konfiguracji ma nieprawidłową wartość.",
        action="Przywróć wartość z dozwolonego zakresu; nie uruchamiaj misji na niezweryfikowanej konfiguracji.",
    ),
    "MC_CFG_004": OperatorGuidance(
        meaning="Plik konfiguracji nie daje się sparsować.",
        action="Sprawdź składnię pliku i ponów start aplikacji.",
    ),
    "MC_UI_001": OperatorGuidance(
        meaning="Operacja UI została zatrzymana przez mechanizm bezpieczeństwa.",
        action="Traktuj komendę jako niewykonaną; usuń przyczynę i dopiero wtedy ponów akcję.",
    ),
}

STATUS_GUIDANCE_MAP: dict[str, OperatorGuidance] = {
    "RUNNING": OperatorGuidance(
        meaning="Misja jest wykonywana.",
        action="Monitoruj postęp; anuluj tylko gdy pojawi się alert krytyczny.",
    ),
    "EXECUTING": OperatorGuidance(
        meaning="Akcja jest wykonywana przez backend.",
        action="Utrzymuj nadzór i czekaj na wynik lub sygnał błędu.",
    ),
    "SUCCEEDED": OperatorGuidance(
        meaning="Akcja zakończyła się sukcesem.",
        action="Zweryfikuj rezultat i przejdź do kolejnego kroku planu misji.",
    ),
    "COMPLETED": OperatorGuidance(
        meaning="Misja została ukończona.",
        action="Potwierdź końcowy stan i przygotuj następne zadanie.",
    ),
    "FAILED": OperatorGuidance(
        meaning="Akcja zakończyła się błędem.",
        action="Nie powtarzaj komendy automatycznie; sprawdź przyczynę i przejdź do diagnostyki.",
    ),
    "ABORTED": OperatorGuidance(
        meaning="Akcja została przerwana przez system.",
        action="Ustal przyczynę przerwania i dopiero po weryfikacji podejmij kolejną próbę.",
    ),
    "CANCELED": OperatorGuidance(
        meaning="Akcja została anulowana.",
        action="Zweryfikuj, czy anulowanie było zamierzone i czy robot jest w stanie bezpiecznym.",
    ),
    "IDLE": OperatorGuidance(
        meaning="System jest bez aktywnej akcji.",
        action="Możesz wysłać nowy goal tylko jeśli telemetria i łączność są wiarygodne.",
    ),
    "READY": OperatorGuidance(
        meaning="System jest gotowy do przyjęcia nowej akcji.",
        action="Uruchom kolejną akcję zgodnie z procedurą operacyjną.",
    ),
    "RECORDING": OperatorGuidance(
        meaning="Nagrywanie rosbag trwa.",
        action="Nie uruchamiaj playbacku; zakończ nagrywanie przed zmianą trybu.",
    ),
    "PLAYING": OperatorGuidance(
        meaning="Odtwarzanie rosbag trwa.",
        action="Nie uruchamiaj nagrywania równolegle i monitoruj integralność danych.",
    ),
}

MISSION_STATE_MAP: dict[str, str] = {
    "RUNNING": "MISJA W TOKU",
    "EXECUTING": "MISJA W TOKU",
    "SUCCEEDED": "MISJA ZAKOŃCZONA",
    "COMPLETED": "MISJA ZAKOŃCZONA",
    "CANCELED": "MISJA PRZERWANA",
    "FAILED": "MISJA PRZERWANA",
    "ABORTED": "MISJA PRZERWANA",
    "IDLE": "MISJA GOTOWA",
    "READY": "MISJA GOTOWA",
}


def resolve_operator_guidance(*, reason_code: str | None = None, status: str | None = None) -> OperatorGuidance:
    normalized_code = (reason_code or "").strip()
    if normalized_code:
        guidance = CODE_GUIDANCE_MAP.get(normalized_code)
        if guidance is not None:
            return guidance

    normalized_status = (status or "").strip().upper()
    if normalized_status:
        guidance = STATUS_GUIDANCE_MAP.get(normalized_status)
        if guidance is not None:
            return guidance
    return FALLBACK_GUIDANCE


def map_action_status_to_mission_state(status: str | None) -> str:
    normalized_status = (status or "").strip().upper()
    if not normalized_status:
        return "STAN MISJI NIEZNANY"
    return MISSION_STATE_MAP.get(normalized_status, "STAN MISJI NIEZNANY")
