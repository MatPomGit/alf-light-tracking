#!/usr/bin/env bash
set -euo pipefail

# [AI-CHANGE | 2026-04-25 08:51 UTC | v0.202]
# CO ZMIENIONO: Dodano skrypt E2E uruchamiający realny przepływ ROS2: launch aplikacji,
#               `ros2 run` serwera testowego oraz sekwencję goal -> feedback -> result -> cancel.
# DLACZEGO: Umożliwia to powtarzalne potwierdzenie działania integracji Action poza mockami,
#           zgodnie z wymaganiem operatorskim dla walidacji runtime.
# JAK TO DZIAŁA: Skrypt buduje workspace, startuje procesy w tle, wysyła goal z feedbackiem,
#                a następnie uruchamia drugi goal i anuluje go; logi zapisuje do `logs/e2e_real_flow/`.
# TODO: Zastąpić parsowanie tekstowe logów przez asercje w `launch_testing` i eksport raportu JUnit.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WS_DIR="$(cd "${PKG_DIR}/.." && pwd)"
LOG_DIR="${PKG_DIR}/logs/e2e_real_flow"

mkdir -p "${LOG_DIR}"

if ! command -v ros2 >/dev/null 2>&1; then
  echo "[E2E][ERROR] Brak komendy 'ros2' w PATH. Test E2E nie może zostać uruchomiony." >&2
  exit 2
fi

cleanup() {
  local exit_code=$?
  set +e
  for pid_var in APP_PID SERVER_PID CANCEL_PID; do
    local pid_value="${!pid_var:-}"
    if [[ -n "${pid_value}" ]]; then
      kill "${pid_value}" >/dev/null 2>&1 || true
    fi
  done
  wait >/dev/null 2>&1 || true
  exit "${exit_code}"
}
trap cleanup EXIT

pushd "${WS_DIR}" >/dev/null
# [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
# CO ZMIENIONO: Build E2E wybiera tylko pakiet `robot_mission_control`.
# DLACZEGO: Kontrakt `MissionStep` jest częścią tego samego pakietu, więc wybór usuniętego pakietu
#           `robot_mission_control_interfaces` kończyłby scenariusz błędem przed testem runtime.
# JAK TO DZIAŁA: `colcon build --packages-select robot_mission_control` buduje aplikację, skrypty oraz lokalny typ Action.
# TODO: Dodać wariant skryptu z czystym `build/ install/ log/`, aby wykrywać zależności ukryte w poprzednich artefaktach.
colcon build --packages-select robot_mission_control >"${LOG_DIR}/colcon_build.log" 2>&1
source install/setup.bash

ros2 run robot_mission_control mission_step_action_test_server >"${LOG_DIR}/action_server.log" 2>&1 &
SERVER_PID=$!

ros2 launch robot_mission_control mission_control.launch.py >"${LOG_DIR}/mission_control_launch.log" 2>&1 &
APP_PID=$!

sleep 3

echo "[E2E] Wysyłam goal (scenariusz result + feedback)."
ros2 action send_goal --feedback /mission_control/execute_step \
  robot_mission_control/action/MissionStep \
  '{goal: start_patrol, correlation_id: e2e-success, parameters_json: "{}"}' \
  >"${LOG_DIR}/goal_success.log" 2>&1

echo "[E2E] Wysyłam goal do anulowania."
ros2 action send_goal --feedback /mission_control/execute_step \
  robot_mission_control/action/MissionStep \
  '{goal: return_to_base, correlation_id: e2e-cancel, parameters_json: "{}"}' \
  >"${LOG_DIR}/goal_cancel.log" 2>&1 &
CANCEL_PID=$!

sleep 1
ros2 action cancel /mission_control/execute_step >"${LOG_DIR}/cancel.log" 2>&1
wait "${CANCEL_PID}"

echo "[E2E] Zakończono. Sprawdź logi w ${LOG_DIR}."
popd >/dev/null
