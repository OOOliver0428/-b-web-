#!/usr/bin/env python3
"""启动脚本"""
import subprocess
import time
import sys
import signal
import asyncio
import uvicorn
from app.core.config import settings
# 直接导入 FastAPI 应用对象，确保 PyInstaller 能正确打包
from app.main import app as fastapi_app

def open_browser():
    """自动打开浏览器"""
    url = f"http://{settings.HOST}:{settings.PORT}"
    try:
        # Windows
        if sys.platform == 'win32':
            subprocess.Popen(['start', '', url], shell=True)
        # macOS
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', url])
        # Linux
        else:
            subprocess.Popen(['xdg-open', url])
        print(f"\n✓ 已自动打开浏览器: {url}")
    except Exception as e:
        print(f"\n! 无法自动打开浏览器，请手动访问: {url}")

async def shutdown(server, tasks):
    """优雅关闭"""
    print("\n\n正在关闭服务...")
    server.should_exit = True
    # 取消所有任务
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    print("服务已关闭")

async def main():
    url = f"http://{settings.HOST}:{settings.PORT}"
    
    print(f"""
╔══════════════════════════════════════════════════╗
║          B站房管工具 - 启动中...                  ║
╠══════════════════════════════════════════════════╣
║  服务地址: {url:<35}  ║
║  API文档: {url + '/docs':<35}  ║
╚══════════════════════════════════════════════════╝
""")
    
    # 延迟打开浏览器
    browser_timer = None
    if settings.DEBUG:
        browser_timer = threading.Timer(2.0, open_browser)
        browser_timer.daemon = True
        browser_timer.start()
    
    # 创建 uvicorn 服务器
    # 注意：使用 fastapi_app 对象而不是字符串，确保 PyInstaller 能正确打包
    config = uvicorn.Config(
        fastapi_app,
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # 打包后不能使用 reload
        log_level="info",
        lifespan="on"
    )
    server = uvicorn.Server(config)
    
    # 设置信号处理
    tasks = []
    
    def signal_handler(sig, frame):
        if browser_timer:
            browser_timer.cancel()
        # 直接退出，让 lifespan 处理清理
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动服务
    await server.serve()

if __name__ == "__main__":
    import threading
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务已停止")
        sys.exit(0)
