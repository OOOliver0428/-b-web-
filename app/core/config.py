"""配置文件"""
import os
import sys
from pydantic_settings import BaseSettings
from typing import List, Optional


def get_external_path():
    """获取外部文件目录（EXE同级目录或项目根目录）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包环境: 返回 EXE 所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境: 返回项目根目录
        return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


# 尝试加载.env文件
try:
    from dotenv import load_dotenv
    
    EXTERNAL_BASE = get_external_path()
    
    # 尝试多个可能的.env路径
    possible_paths = [
        os.path.join(EXTERNAL_BASE, '.env'),  # 外部配置优先
        '.env',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'),
        os.path.join(os.getcwd(), '.env'),
    ]
    
    loaded = False
    for path in possible_paths:
        if os.path.exists(path):
            load_dotenv(path, encoding='utf-8')
            print(f"已加载配置文件: {path}")
            loaded = True
            break
    
    if not loaded:
        print("警告: 未找到 .env 配置文件")
        
except ImportError:
    pass


class Settings(BaseSettings):
    """应用配置"""
    # B站Cookie
    SESSDATA: str = ""
    BILI_JCT: str = ""
    BUVID3: Optional[str] = None
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    
    # Redis
    REDIS_URL: Optional[str] = None
    
    # 敏感词
    SENSITIVE_WORDS: str = ""
    
    @property
    def cookies(self) -> dict:
        """获取Cookie字典"""
        cookies = {
            "SESSDATA": self.SESSDATA,
            "bili_jct": self.BILI_JCT,
        }
        if self.BUVID3:
            cookies["buvid3"] = self.BUVID3
        return cookies
    
    @property
    def sensitive_words_list(self) -> List[str]:
        """获取敏感词列表"""
        if not self.SENSITIVE_WORDS:
            return []
        return [w.strip() for w in self.SENSITIVE_WORDS.split(",") if w.strip()]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
