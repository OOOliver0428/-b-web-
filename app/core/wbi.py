"""WBI 签名算法
参考: https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md
"""
import re
import time
import hashlib
import urllib.parse
from typing import Dict, Optional, Tuple
import httpx
from loguru import logger


# WBI 签名用的字符映射表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]


def get_mixin_key(orig: str) -> str:
    """
    生成 mixin_key
    将 img_key 和 sub_key 拼接后，按 MIXIN_KEY_ENC_TAB 重排
    """
    return ''.join([orig[i] for i in MIXIN_KEY_ENC_TAB])[:32]


def enc_wbi(params: Dict[str, str], img_key: str, sub_key: str) -> Dict[str, str]:
    """
    给请求参数添加 WBI 签名
    
    Args:
        params: 原始请求参数
        img_key: WBI img_key
        sub_key: WBI sub_key
    
    Returns:
        添加了 w_rid 和 wts 的参数
    """
    # 添加时间戳
    params = dict(params)  # 复制一份，不修改原数据
    params['wts'] = str(int(time.time()))
    
    # 过滤值中的特殊字符
    filtered_params = {}
    for k, v in params.items():
        if v is not None:
            # 移除 !'()* 字符
            filtered_v = re.sub(r"[!'()*]", '', str(v))
            filtered_params[k] = filtered_v
    
    # 按 key 排序
    sorted_params = dict(sorted(filtered_params.items()))
    
    # URL 编码生成查询字符串
    query = urllib.parse.urlencode(sorted_params)
    
    # 生成 mixin_key
    mixin_key = get_mixin_key(img_key + sub_key)
    
    # MD5 哈希
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    
    # 添加签名到参数
    sorted_params['w_rid'] = w_rid
    
    return sorted_params


class WbiSigner:
    """WBI 签名管理器"""
    
    def __init__(self):
        self.img_key: Optional[str] = None
        self.sub_key: Optional[str] = None
        self.last_update: float = 0
        self.refresh_interval: int = 3600  # 1小时刷新一次密钥
    
    async def get_keys(self, client: httpx.AsyncClient) -> Tuple[str, str]:
        """
        从 B 站导航接口获取 WBI 密钥
        
        Returns:
            (img_key, sub_key)
        """
        # 检查是否需要刷新
        now = time.time()
        if self.img_key and self.sub_key and (now - self.last_update) < self.refresh_interval:
            return self.img_key, self.sub_key
        
        try:
            # 从导航接口获取
            resp = await client.get(
                "https://api.bilibili.com/x/web-interface/nav",
                timeout=10.0
            )
            data = resp.json()
            
            if data.get("code") == 0:
                wbi_img = data["data"]["wbi_img"]
                img_url = wbi_img["img_url"]
                sub_url = wbi_img["sub_url"]
                
                # 从 URL 中提取 key
                # URL 格式: https://i0.hdslb.com/bfs/wbi/7cd3...abc.png
                self.img_key = img_url.split('/')[-1].split('.')[0]
                self.sub_key = sub_url.split('/')[-1].split('.')[0]
                self.last_update = now
                
                logger.info(f"WBI 密钥已更新: img_key={self.img_key[:10]}..., sub_key={self.sub_key[:10]}...")
                return self.img_key, self.sub_key
            else:
                logger.error(f"获取 WBI 密钥失败: {data}")
        except Exception as e:
            logger.error(f"获取 WBI 密钥异常: {e}")
        
        # 如果获取失败但之前有密钥，使用旧的
        if self.img_key and self.sub_key:
            return self.img_key, self.sub_key
        
        raise Exception("无法获取 WBI 密钥")
    
    async def sign(self, client: httpx.AsyncClient, params: Dict[str, str]) -> Dict[str, str]:
        """
        对参数进行 WBI 签名
        
        Args:
            client: httpx 客户端
            params: 原始参数
        
        Returns:
            签名后的参数
        """
        img_key, sub_key = await self.get_keys(client)
        return enc_wbi(params, img_key, sub_key)


# 全局实例
wbi_signer = WbiSigner()
