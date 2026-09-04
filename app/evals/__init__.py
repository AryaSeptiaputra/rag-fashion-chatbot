"""Penilaian mutu retrieval.

Submodul retrieval.py memakai DeepEval, yang hanya terpasang di venv eval
(requirements-eval.txt). Import pustaka itu sengaja ditahan di dalam submodul,
bukan di sini, supaya venv utama tetap bisa meng-import app tanpa memasangnya.

Variabel telemetri diset di sini, sebelum submodul mana pun sempat meng-import
pustaka penilai: DeepEval membaca env var tersebut saat import, jadi
menyetelnya belakangan tidak berpengaruh sama sekali.
"""

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
