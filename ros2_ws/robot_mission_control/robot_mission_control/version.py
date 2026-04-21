"""Generated build version artifact for robot mission control."""

# [AI-CHANGE | 2026-04-21 05:27 UTC | v0.164]
# CO ZMIENIONO: Plik artefaktu wersji zawiera teraz metadane commit_count/SHA/czas oraz pole źródła.
# DLACZEGO: Runtime ma akceptować fallback tylko wtedy, gdy artefakt jednoznacznie deklaruje,
#           że numer pochodzi z `git rev-list --count HEAD`.
# JAK TO DZIAŁA: Resolver odrzuca artefakt bez `ARTIFACT_SOURCE`, dzięki czemu brak `.git` nie
#                skutkuje pokazaniem przypadkowego numeru wersji.
# TODO: Dodać sumę kontrolną sekcji metadanych i jej automatyczną weryfikację przy starcie.
COMMIT_COUNT = 164
SHORT_SHA = "59a1a3a"
BUILD_TIME_UTC = "2026-04-21T05:28:20+00:00"
ARTIFACT_SOURCE = "git_rev_list_count"
