"""FastAPI应用入口"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from app.api.routes import router
from app.core.room_manager import room_manager
from app.core.bili_client import bili_client
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("=" * 50)
    logger.info("B站房管工具启动中...")
    logger.info("=" * 50)
    
    # 检查Cookie配置
    if not settings.SESSDATA or not settings.BILI_JCT:
        logger.warning("警告: 未配置SESSDATA或BILI_JCT，房管功能将不可用")
        logger.warning("请在.env文件中配置你的B站Cookie")
    else:
        logger.info("Cookie已配置")
    
    yield
    
    # 关闭时
    logger.info("正在关闭所有直播间连接...")
    await room_manager.stop_all()
    await bili_client.close()
    logger.info("已关闭")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="B站房管工具 API",
        description="B站直播弹幕监控和房管管理工具",
        version="1.3.0",
        lifespan=lifespan
    )
    
    # CORS配置 - 限制为本地访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            f"http://127.0.0.1:{settings.PORT}",
            f"http://localhost:{settings.PORT}",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册API路由
    app.include_router(router, prefix="/api")
    
    # 静态文件目录
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
        
        # 大航海背景图目录
        guard_bg_dir = os.path.join(static_dir, "guard_bg")
        if os.path.exists(guard_bg_dir):
            app.mount("/guard_bg", StaticFiles(directory=guard_bg_dir), name="guard_bg")
    
    # 根路由 - 返回前端页面
    @app.get("/")
    async def root():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "B站房管工具 API 服务运行中", "docs": "/docs"}
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
