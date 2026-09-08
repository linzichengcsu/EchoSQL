"""pytest 根路径配置:保证 `pytest` 直接运行(非 python -m)时项目根可导入。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
