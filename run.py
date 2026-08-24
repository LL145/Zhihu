"""PyInstaller 打包入口（等价于 python -m yijing_agent）。"""

import sys

from yijing_agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
