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

# [AI-CHANGE | 2026-04-27 06:55 UTC | v0.203]
# CO ZMIENIONO: Dodano wspólną mapę krytycznych `reason_code` używanych przez aplikację,
#               aby wszystkie karty operatorskie (Overview/Diagnostics/Controls/Rosbag/VideoDepth)
#               renderowały identyczne komunikaty „co się stało / co zrobić”.
# DLACZEGO: DoD wymaga pełnej spójności instrukcji operatorskich dla kodów krytycznych;
#           fallback był bezpieczny, ale zbyt ogólny dla incydentów o znanej przyczynie.
# JAK TO DZIAŁA: `CRITICAL_REASON_CODE_GUIDANCE_MAP` jest scalana do `CODE_GUIDANCE_MAP`,
#                więc istniejące wywołania `resolve_operator_guidance(...)` automatycznie
#                korzystają z rozszerzonego słownika bez zmian interfejsu publicznego.
# TODO: Dodać walidator CI, który wykryje nowy `reason_code` bez wpisu w mapie operatorskiej.
CRITICAL_REASON_CODE_GUIDANCE_MAP: dict[str, OperatorGuidance] = {
    "transport_failure": OperatorGuidance(
        meaning="Transport danych przerwał się i stan systemu jest niewiarygodny.",
        action="Wstrzymaj sterowanie ruchem, sprawdź łącze i wznowienie transmisji przed kontynuacją.",
    ),
    "timeout": OperatorGuidance(
        meaning="Przekroczono limit czasu odpowiedzi komponentu krytycznego.",
        action="Nie ponawiaj komendy w pętli; zweryfikuj obciążenie i dostępność zależności.",
    ),
    "bridge_error": OperatorGuidance(
        meaning="Most komunikacyjny zgłosił błąd wykonania.",
        action="Przejdź do diagnostyki bridge, potwierdź stabilność i dopiero wtedy ponów akcję.",
    ),
    "node_manager_unavailable": OperatorGuidance(
        meaning="Menedżer węzłów ROS jest niedostępny.",
        action="Uruchom lub napraw node manager i potwierdź status CONNECTED przed kolejną komendą.",
    ),
    "waiting_for_topics": OperatorGuidance(
        meaning="System czeka na wymagane topiki ROS i nie ma pełnej gotowości.",
        action="Poczekaj na komplet topiców; jeśli stan trwa zbyt długo, sprawdź publishery i namespace.",
    ),
    "app_shutdown": OperatorGuidance(
        meaning="Aplikacja przechodzi procedurę zamknięcia.",
        action="Nie inicjuj nowych akcji; poczekaj na pełne zatrzymanie i uruchom ponownie, jeśli to konieczne.",
    ),
    "shutdown_failed": OperatorGuidance(
        meaning="Procedura zamknięcia komponentu zakończyła się błędem.",
        action="Wykonaj kontrolowany restart procesu i sprawdź logi zamykania przed wznowieniem pracy.",
    ),
    "node_shutdown": OperatorGuidance(
        meaning="Węzeł ROS został wyłączony.",
        action="Zweryfikuj, czy wyłączenie było planowane; przywróć węzeł przed wznowieniem misji.",
    ),
    "goal_already_running": OperatorGuidance(
        meaning="Nowa akcja została odrzucona, bo inny goal jest już aktywny.",
        action="Zakończ albo anuluj bieżący goal i dopiero potem uruchom kolejną akcję.",
    ),
    "unknown_quick_command": OperatorGuidance(
        meaning="Otrzymano nieobsługiwaną komendę szybkiej akcji.",
        action="Nie kontynuuj z nieznanym poleceniem; sprawdź mapowanie komend i konfigurację UI.",
    ),
    "no_active_goal": OperatorGuidance(
        meaning="Nie można wykonać operacji, bo brak aktywnego goalu.",
        action="Zweryfikuj status akcji; uruchom nowy goal tylko gdy dane i łączność są wiarygodne.",
    ),
    "goal_finished": OperatorGuidance(
        meaning="Goal został zakończony i nie jest już aktywny.",
        action="Potwierdź wynik końcowy i zdecyduj, czy uruchomić następny krok planu misji.",
    ),
    "not_initialized": OperatorGuidance(
        meaning="Komponent nie został poprawnie zainicjalizowany.",
        action="Przerwij operację, sprawdź sekwencję startową i inicjalizację zależności.",
    ),
}
CODE_GUIDANCE_MAP.update(CRITICAL_REASON_CODE_GUIDANCE_MAP)

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
        # [AI-CHANGE | 2026-04-28 10:14 UTC | v0.205]
        # CO ZMIENIONO: Wymuszono bezpośredni fallback dla nieznanego `reason_code`.
        # DLACZEGO: Nieznany kod błędu jest bardziej wiarygodnym sygnałem niepewności niż status ogólny;
        #           zgodnie z zasadą bezpieczeństwa lepiej zwrócić brak precyzyjnej diagnozy niż mylący opis.
        # JAK TO DZIAŁA: Gdy `reason_code` został podany, ale nie istnieje w mapie, funkcja zwraca
        #                `FALLBACK_GUIDANCE` i nie przechodzi do mapowania po `status`.
        # TODO: Dodać telemetrykę nieznanych `reason_code` z agregacją częstości do dalszego mapowania.
        return FALLBACK_GUIDANCE

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
