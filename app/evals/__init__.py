"""Penilaian mutu jawaban akhir dan mutu retrieval.

Submodul answer.py dan retrieval.py memakai RAGAS dan DeepEval, yang hanya
terpasang di venv eval (requirements-eval.txt). Import pustaka itu sengaja
ditahan di dalam submodul masing-masing, bukan di sini, supaya venv utama tetap
bisa meng-import app tanpa memasang keduanya.

Variabel telemetri diset di sini, sebelum submodul mana pun sempat meng-import
pustaka penilai: DeepEval dan RAGAS membaca env var tersebut saat import, jadi
menyetelnya belakangan tidak berpengaruh sama sekali.
"""

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
