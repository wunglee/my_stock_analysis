import os
import sys

# Ensure src/ and tests/ are on sys.path for absolute imports like `from core.share...`
_HERE = os.path.dirname(__file__)
_SRC = os.path.abspath(os.path.join(_HERE, '..', 'src'))
_TESTS = os.path.abspath(_HERE)
for _p in (_SRC, _TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
