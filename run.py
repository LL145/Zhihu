"""PyInstaller 打包入口（等价于 python -m tianwen）。"""

import sys

from tianwen.cli import main

if __name__ == "__main__":
    sys.exit(main())
