"""PyInstaller 图形界面打包入口（等价于 python -m yijing_agent.gui）。"""

import sys

from yijing_agent.gui import main

if __name__ == "__main__":
    sys.exit(main())
