
import os
import sys

# 获取 EXE 所在目录
if getattr(sys, 'frozen', False):
    # 打包后的运行环境
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 设置环境变量，让程序知道外部文件位置
os.environ['BILIBILI_MOD_TOOL_BASE'] = BASE_DIR
