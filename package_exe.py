#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站房管工具 - PyInstaller 打包脚本

生成单文件 EXE，用户只需配置：
- .env (Cookie配置)
- sensitive_words/ (敏感词文件)

使用方法:
    python package_exe.py
"""

import os
import sys
import io
import shutil
import subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"

def clean():
    """清理构建目录"""
    print("[*] 清理构建目录...")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    DIST_DIR.mkdir(exist_ok=True)

def check_pyinstaller():
    """检查 PyInstaller"""
    try:
        import PyInstaller
        return True
    except ImportError:
        print("[ERR] 未安装 PyInstaller，请先运行: pip install pyinstaller")
        return False

def create_hook():
    """创建运行时钩子，用于处理外部文件路径"""
    hook_content = '''
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
'''
    hook_path = BUILD_DIR / "runtime_hook.py"
    hook_path.parent.mkdir(exist_ok=True)
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(hook_content)
    return str(hook_path)

def build_exe():
    """使用 PyInstaller 构建 EXE"""
    print("[*] 开始构建 EXE...")
    
    # 创建运行时钩子
    hook_file = create_hook()
    
    # PyInstaller 参数
    args = [
        "run.py",                          # 入口文件
        "--name=B站房管工具",               # 程序名
        "--onefile",                        # 单文件
        "--console",                        # 显示控制台
        "--clean",                          # 清理临时文件
        "--noconfirm",                      # 不确认覆盖
        "--distpath", str(DIST_DIR),        # 输出目录
        "--workpath", str(BUILD_DIR / "work"),
        "--specpath", str(BUILD_DIR),
        "--runtime-hook", hook_file,        # 运行时钩子
        # 静态文件打包进 EXE
        "--add-data", f"{ROOT_DIR}/app/static{os.pathsep}app/static",
        # 图标（如果有的话）
        # "--icon", "icon.ico",
    ]
    
    # 执行打包
    subprocess.run([sys.executable, "-m", "PyInstaller"] + args, check=True)
    
    print("[OK] EXE 构建完成")

def create_dist_package():
    """创建分发包"""
    print("[*] 创建分发包...")
    
    package_dir = DIST_DIR / "B站房管工具"
    package_dir.mkdir(exist_ok=True)
    
    # 移动 EXE
    exe_name = "B站房管工具.exe"
    exe_src = DIST_DIR / exe_name
    exe_dst = package_dir / exe_name
    if exe_src.exists():
        shutil.move(str(exe_src), str(exe_dst))
    
    # 复制配置文件模板
    shutil.copy2(ROOT_DIR / ".env.example", package_dir / ".env.example")
    
    # 创建敏感词目录并复制默认文件
    sw_dir = package_dir / "sensitive_words"
    sw_dir.mkdir(exist_ok=True)
    for md_file in (ROOT_DIR / "sensitive_words").glob("*.md"):
        shutil.copy2(md_file, sw_dir / md_file.name)
    
    # 创建使用说明
    with open(package_dir / "使用说明.txt", "w", encoding="utf-8") as f:
        f.write("""========================================
        B站房管工具 - 使用说明
========================================

【快速开始】

1. 配置Cookie
   - 将 .env.example 复制为 .env
   - 打开 .env 文件，填写你的 SESSDATA 和 BILI_JCT
   - 获取方式：登录B站网页版 → F12 → Application → Cookies

2. （可选）配置敏感词
   - 编辑 sensitive_words/ 目录下的 .md 文件
   - 或创建新的 .md 文件
   - 每行一个敏感词

3. 启动程序
   - 双击 "B站房管工具.exe"
   - 等待显示 "Uvicorn running on http://0.0.0.0:8000"
   - 浏览器自动打开，或手动访问 http://127.0.0.1:8000

【注意事项】

- 首次运行会弹出防火墙提示，请允许
- .env 文件中的 Cookie 是登录凭证，请勿泄露
- 敏感词文件支持热更新，修改后刷新页面即可生效
- 必须是直播间的房管才能禁言用户

【文件说明】

B站房管工具.exe    - 主程序（不要改名）
.env              - Cookie 配置文件（需自行创建）
.env.example      - 配置模板（参考用）
sensitive_words/  - 敏感词文件目录
使用说明.txt       - 本文档

【技术支持】
Bilibili: 江边砍柴
""")
    
    # 创建压缩包
    zip_path = DIST_DIR / "B站房管工具-v1.0.0.zip"
    shutil.make_archive(
        str(DIST_DIR / "B站房管工具-v1.0.0"),
        'zip',
        str(package_dir)
    )
    
    print(f"[OK] 分发包已创建: {zip_path}")
    print(f"[*] 目录结构:")
    for item in sorted(package_dir.rglob("*")):
        rel_path = item.relative_to(package_dir)
        if item.is_file():
            print(f"    {rel_path}")

def main():
    if not check_pyinstaller():
        return 1
    
    clean()
    build_exe()
    create_dist_package()
    
    print("\n" + "="*50)
    print("打包完成！")
    print("="*50)
    print(f"输出目录: {DIST_DIR}")
    print("\n用户使用步骤:")
    print("1. 解压 B站房管工具-v1.0.0.zip")
    print("2. 复制 .env.example 为 .env，填写 Cookie")
    print("3. 双击 B站房管工具.exe 启动")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
