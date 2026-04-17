Uruchomienie przykładowe:

python calibrate_from_folder.py \
  --image-folder images \
  --board-cols 9 \
  --board-rows 6 \
  --square-size-m 0.024 \
  --min-samples 20 \
  --output-yaml camera_intrinsics.yaml \
  --output-report camera_intrinsics_report.txt \
  --save-previews \
  --preview-output-dir calibration/previews

Co wygeneruje:
- calibration/camera_intrinsics.yaml
- calibration/camera_intrinsics_report.txt
- calibration/previews/accepted_*.png i rejected_*.png

Najważniejsze argumenty:
- --image-folder: folder ze zdjęciami
- --board-cols / --board-rows: liczba narożników wewnętrznych szachownicy
- --square-size-m: rozmiar pola w metrach
- --min-samples: minimalna liczba zaakceptowanych ujęć
- --save-previews: zapis preview zaakceptowanych i odrzuconych klatek
