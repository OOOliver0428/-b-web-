"""B站API客户端"""
import httpx
import json
from typing import Optional, Dict, Any, List
from loguru import logger

from app.core.config import settings
from app.core.wbi import wbi_signer


class BilibiliClient:
    """B站HTTP API客户端"""
    
    BASE_URL = "https://api.live.bilibili.com"
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            cookies=settings.cookies,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://live.bilibili.com",
                "Origin": "https://live.bilibili.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "sec-ch-ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\", \"Google Chrome\";v=\"120\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\"",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            },
            timeout=30.0
        )
    
    async def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取当前登录用户信息"""
        url = "https://api.bilibili.com/x/web-interface/nav"
        
        try:
            resp = await self.client.get(url)
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data")
            logger.warning(f"获取用户信息失败: {data}")
        except Exception as e:
            logger.error(f"获取用户信息异常: {e}")
        return None
    
    async def close(self):
        await self.client.aclose()
    
    async def get_room_info(self, room_id: int) -> Optional[Dict[str, Any]]:
        """获取直播间信息"""
        url = f"{self.BASE_URL}/room/v1/Room/get_info"
        params = {"id": room_id}
        
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data")
            logger.warning(f"获取房间信息失败: {data}")
        except Exception as e:
            logger.error(f"获取房间信息异常: {e}")
        return None
    
    async def get_danmu_info(self, room_id: int) -> Optional[Dict[str, Any]]:
        """获取弹幕服务器配置信息（需要WBI签名）"""
        url = f"{self.BASE_URL}/xlive/web-room/v1/index/getDanmuInfo"
        
        try:
            # 获取带 WBI 签名的参数
            params = await wbi_signer.sign(self.client, {
                "id": str(room_id),
                "type": "0"
            })
            
            resp = await self.client.get(url, params=params)
            data = resp.json()
            logger.debug(f"getDanmuInfo 响应: {data}")
            
            if data.get("code") == 0:
                return data.get("data")
            
            # 如果是 -352 错误，可能是密钥过期，刷新重试
            if data.get("code") == -352:
                logger.warning("WBI 签名过期，刷新密钥重试...")
                wbi_signer.last_update = 0  # 强制刷新
                params = await wbi_signer.sign(self.client, {
                    "id": str(room_id),
                    "type": "0"
                })
                resp = await self.client.get(url, params=params)
                data = resp.json()
                if data.get("code") == 0:
                    return data.get("data")
            
            logger.warning(f"获取弹幕服务器信息失败: code={data.get('code')}, message={data.get('message')}")
        except Exception as e:
            logger.error(f"获取弹幕服务器信息异常: {e}")
        return None
    
    async def ban_user(
        self, 
        room_id: int, 
        user_id: int, 
        hour: int = 1, 
        msg: str = ""
    ) -> bool:
        """
        禁言用户
        hour: -1=永久, 0=本场直播, 其他=小时数
        """
        url = f"{self.BASE_URL}/xlive/web-ucenter/v1/banned/AddSilentUser"
        data = {
            "room_id": str(room_id),
            "tuid": str(user_id),
            "msg": msg,
            "mobile_app": "web",
            "hour": int(hour),  # 确保是整数
            "type": 1,  # 禁言类型
            "csrf_token": settings.BILI_JCT,
            "csrf": settings.BILI_JCT,
            "visit_id": "",
        }
        
        logger.info(f"禁言请求参数: room_id={room_id}, user_id={user_id}, hour={int(hour)}, msg={msg}")
        
        try:
            resp = await self.client.post(url, data=data)
            result = resp.json()
            logger.info(f"禁言响应: {result}")
            if result.get("code") == 0:
                logger.info(f"禁言用户成功: room={room_id}, user={user_id}, hour={hour}")
                return True
            else:
                logger.error(f"禁言用户失败: {result}")
        except Exception as e:
            logger.error(f"禁言用户异常: {e}")
        return False
    
    async def unban_user(self, room_id: int, block_id: int) -> bool:
        """
        解除禁言
        block_id: 禁言记录ID，从禁言列表接口获取
        """
        url = f"{self.BASE_URL}/banned_service/v1/Silent/del_room_block_user"
        data = {
            "roomid": str(room_id),
            "id": str(block_id),
            "csrf_token": settings.BILI_JCT,
            "csrf": settings.BILI_JCT,
            "visit_id": "",
        }
        
        try:
            resp = await self.client.post(url, data=data)
            result = resp.json()
            if result.get("code") == 0:
                logger.info(f"解除禁言成功: room={room_id}, block_id={block_id}")
                return True
            else:
                logger.error(f"解除禁言失败: {result}")
        except Exception as e:
            logger.error(f"解除禁言异常: {e}")
        return False
    
    async def get_ban_list(self, room_id: int, page: int = 1) -> List[Dict[str, Any]]:
        """获取禁言列表
        参考: https://socialsisteryi.github.io/bilibili-API-collect/docs/live/silent_user_manage.html
        """
        url = f"{self.BASE_URL}/xlive/web-ucenter/v1/banned/GetSilentUserList"
        
        # 使用 POST 请求，添加必要参数
        data = {
            "room_id": str(room_id),
            "ps": str(page),  # 注意参数名是 ps 不是 page
            "csrf": settings.BILI_JCT,
            "csrf_token": settings.BILI_JCT,
            "visit_id": "",
        }
        
        try:
            resp = await self.client.post(url, data=data)
            text = resp.text
            logger.debug(f"禁言列表响应: {text[:200]}")
            
            if not text:
                logger.warning("禁言列表返回空响应")
                return []
            
            result = resp.json()
            if result.get("code") == 0:
                ban_data = result.get("data", {}).get("data", [])
                logger.info(f"获取禁言列表成功: 共 {len(ban_data)} 条")
                return ban_data
            logger.warning(f"获取禁言列表失败: code={result.get('code')}, msg={result.get('message')}")
        except Exception as e:
            logger.error(f"获取禁言列表异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
        return []
    
    async def delete_danmaku(
        self, 
        room_id: int, 
        msg_id: str, 
        user_id: int
    ) -> bool:
        """
        删除弹幕（撤回）
        注意：B站直播弹幕删除接口经常变动，这里使用通用方法
        """
        # 最新接口可能有所不同，这里预留
        logger.info(f"删除弹幕: room={room_id}, msg={msg_id}, user={user_id}")
        # TODO: 根据实际接口实现
        return True


# 全局客户端实例
bili_client = BilibiliClient()
