# Head display – instrukcja operatora

Node `head_display_state_node` wizualizuje status robota na diodach LED głowy.
Priorytet efektów jest stały: **E-STOP > safety warning > mission effect > idle/fallback**.

## Jak czytać sygnały

- **Niebieski pulse (delikatny)** → `idle`.
- **Turkus↔fiolet scan** → `search` lub `navigate` (robot aktywnie szuka / jedzie do celu).
- **Bursztynowy pulse (coraz szybszy przy mniejszym dystansie)** → `approach`.
- **Biało-cyjanowy „oddech”** → `align`.
- **Zielony solid** → `drop`.
- **Złoty solid** → `handover_ready`.
- **Czerwony blink** → `terminal` / `error` lub ostrzeżenie safety.
- **Czerwony strobe** → aktywny **E-STOP** (najwyższy priorytet).

## Fallback diagnostyczny

Jeżeli node nie otrzymuje świeżych danych z `/mission/state`, przełącza się
na neutralny wzorzec diagnostyczny (szary pulse). Dzięki temu operator widzi,
że sam sterownik LED działa, ale brak danych wejściowych z modułu misji.

## Transport wyjściowy

Node ma adapter wyjścia wybierany parametrem `output_mode`:

- `ros_topic` – publikuje JSON na `/head_display/command`,
- `vendor_bridge` – publikuje JSON na `/unitree/head_display/command`
  (placeholder pod natywny bridge vendorowy).

To pozwala rozwijać logikę efektów niezależnie od docelowego sterownika LED.
