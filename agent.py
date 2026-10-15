# 必须在任何 import 之前设置 —— numpy 在加载时就会读这个变量，
# 不加会报 "OpenBLAS error: Memory allocation still failed"
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from app.cli import startAgent

if __name__ == "__main__":
    startAgent()
