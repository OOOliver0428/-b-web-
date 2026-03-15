#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
"""
B站房管工具 - 打包脚本

使用方式:
    python package.py              # 打包为zip
    python package.py exe          # 打包为exe (需要pyinstaller)
    python package.py all          # 全部打包
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist"

def clean_dist():
    """清理dist目录"""
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(exist_ok=True)

def get_version():
    """从代码获取版本号"""
    return "1.0.0"

def create_zip_package():
    """创建ZIP源码包"""
    print("[*] 正在创建ZIP源码包...")
    
    version = get_version()
    package_name = f"bilibili-mod-tool-v{version}"
    package_dir = DIST_DIR / package_name
    
    # 复制文件
    shutil.copytree(ROOT_DIR / "app", package_dir / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT_DIR / "sensitive_words", package_dir / "sensitive_words", ignore=shutil.ignore_patterns("*.txt"))
    
    # 复制必要文件
    files_to_copy = [
        "requirements.txt",
        "run.py",
        "README.md",
        ".env.example"
    ]
    for f in files_to_copy:
        src = ROOT_DIR / f
        if src.exists():
            shutil.copy2(src, package_dir / f)
    
    # 创建启动脚本
    with open(package_dir / "start.bat", "w", encoding="utf-8") as f:
        f.write("""@echo off
echo 正在启动B站房管工具...
python -m pip install -r requirements.txt -q
python run.py
pause
""")
    
    with open(package_dir / "start.sh", "w", encoding="utf-8") as f:
        f.write("""#!/bin/bash
echo "正在启动B站房管工具..."
pip install -r requirements.txt -q
python run.py
""")
    
    # 创建部署说明
    with open(package_dir / "部署说明.txt", "w", encoding="utf-8") as f:
        f.write("""===== B站房管工具部署说明 =====

【快速开始】

1. 安装Python 3.10或更高版本
   https://www.python.org/downloads/

2. 配置Cookie
   - 复制 .env.example 为 .env
   - 填写你的 SESSDATA 和 BILI_JCT

3. 启动服务
   Windows: 双击 start.bat
   Linux/Mac: 运行 ./start.sh

4. 浏览器访问 http://127.0.0.1:8000

【详细说明】
请阅读 README.md 获取完整使用指南

【常见问题】

Q: 提示缺少依赖？
A: 运行 pip install -r requirements.txt

Q: 无法连接直播间？
A: 检查Cookie是否有效，是否过期

Q: 无法禁言用户？
A: 必须是你管理/房管的直播间

【目录说明】
- app/           程序代码
- sensitive_words/ 敏感词文件目录
- 部署说明.txt    本文档
- README.md      详细使用说明
""")
    
    # 压缩
    zip_path = DIST_DIR / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in package_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)
    
    # 清理临时目录
    shutil.rmtree(package_dir)
    
    print(f"[OK] ZIP源码包已创建: {zip_path}")
    return zip_path

def create_exe_package():
    """使用PyInstaller打包为exe"""
    print("[*] 正在创建EXE可执行文件...")
    
    try:
        import PyInstaller.__main__
    except ImportError:
        print("[ERR] 请先安装 pyinstaller: pip install pyinstaller")
        return None
    
    version = get_version()
    
    # 创建spec文件内容
    spec_content = f'''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[r'{ROOT_DIR}'],
    binaries=[],
    datas=[
        (r'{ROOT_DIR}/app/static', 'app/static'),
        (r'{ROOT_DIR}/sensitive_words', 'sensitive_words'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.lifespan.off',
        'uvicorn.lifespan.on',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.http.auto',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='bilibili-mod-tool-v{version}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    
    spec_path = DIST_DIR / "build.spec"
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    # 执行打包
    PyInstaller.__main__.run([
        str(spec_path),
        "--distpath", str(DIST_DIR / "exe"),
        "--workpath", str(DIST_DIR / "build"),
        "--specpath", str(DIST_DIR),
        "--clean",
        "-y",
    ])
    
    exe_path = DIST_DIR / "exe" / f"bilibili-mod-tool-v{version}.exe"
    print(f"[OK] EXE可执行文件已创建: {exe_path}")
    return exe_path

def main():
    """主函数"""
    if len(sys.argv) < 2:
        cmd = "zip"
    else:
        cmd = sys.argv[1].lower()
    
    clean_dist()
    
    if cmd == "zip":
        create_zip_package()
    elif cmd == "exe":
        create_exe_package()
    elif cmd == "all":
        create_zip_package()
        create_exe_package()
    else:
        print(__doc__)
        return 1
    
    print(f"\n[*] 输出目录: {DIST_DIR}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
