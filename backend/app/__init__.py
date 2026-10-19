import os

# O OpenBLAS do numpy com várias threads, rodando ao mesmo tempo que o
# onnxruntime (voz) e o CTranslate2 (Whisper), derruba o processo com access
# violation no Windows. A álgebra do numpy aqui é pequena; uma thread basta.
# Precisa vir antes do primeiro `import numpy`.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

__version__ = "2.2.2"
