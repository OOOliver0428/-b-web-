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
    
    async def get_room_init(self, room_id: int) -> Optional[Dict[str, Any]]:
        """
        获取房间初始化信息（支持短号翻译）
        API: https://api.live.bilibili.com/room/v1/Room/room_init
        返回数据包含: room_id(真实房间号), short_id(短号), uid(主播ID) 等
        """
        url = f"{self.BASE_URL}/room/v1/Room/room_init"
        params = {"id": room_id}
        
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data")
            logger.warning(f"获取房间初始化信息失败: {data}")
        except Exception as e:
            logger.error(f"获取房间初始化信息异常: {e}")
        return None
    
    async def get_room_info(self, room_id: int) -> Optional[Dict[str, Any]]:
        """获取直播间详细信息（包含标题、主播名等）"""
        url = f"{self.BASE_URL}/room/v1/Room/get_info"
        params = {"room_id": room_id}
        
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json()
            if data.get("code") == 0:
                room_data = data.get("data", {})
                # get_info 接口不返回主播名称，需要额外获取
                uname = await self._get_anchor_name(room_id)
                if uname:
                    room_data["uname"] = uname
                return room_data
            logger.warning(f"获取房间信息失败: {data}")
        except Exception as e:
            logger.error(f"获取房间信息异常: {e}")
        return None
    
    async def _get_anchor_name(self, room_id: int) -> Optional[str]:
        """
        获取主播名称
        使用 get_info_by_id 接口，该接口返回 uname 字段
        """
        url = f"{self.BASE_URL}/room/v1/Room/get_info_by_id"
        params = {"ids[]": room_id}
        
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json()
            if data.get("code") == 0:
                rooms_data = data.get("data", {})
                # 返回的数据格式: {"room_id": {...}}
                for room_data in rooms_data.values():
                    uname = room_data.get("uname")
                    if uname:
                        logger.debug(f"获取主播名称成功: {uname}")
                        return uname
            logger.debug(f"获取主播名称失败: {data}")
        except Exception as e:
            logger.error(f"获取主播名称异常: {e}")
        return None
    
    async def resolve_room_id(self, input_room_id: int) -> Optional[Dict[str, Any]]:
        """
        解析房间号（支持短号翻译）
        优先尝试作为真实房间号获取信息，如果失败则尝试作为短号翻译
        
        返回: {
            "room_id": 真实房间号,
            "short_id": 短号(如果有),
            "uid": 主播ID,
            "title": 直播标题,
            "uname": 主播名称,
            "live_status": 直播状态,
            ...
        }
        """
        # 首先尝试作为真实房间号获取详细信息
        room_info = await self.get_room_info(input_room_id)
        
        if room_info and room_info.get("room_id"):
            # 输入的是真实房间号，获取 room_init 补充信息
            logger.info(f"房间号 {input_room_id} 识别为真实房间号")
            room_init = await self.get_room_init(input_room_id)
            if room_init:
                # 合并信息
                # 主播名称可能来自不同的字段，统一为 uname
                anchor_name = room_info.get("anchor_name") or room_info.get("uname", "")
                return {
                    **room_info,
                    "uid": room_init.get("uid"),
                    "short_id": room_init.get("short_id", 0),
                    "is_short_id": False,
                    "uname": anchor_name,
                }
            return room_info
        
        # 尝试作为短号翻译
        logger.info(f"房间号 {input_room_id} 可能为短号，尝试翻译...")
        room_init = await self.get_room_init(input_room_id)
        
        if room_init and room_init.get("room_id"):
            real_room_id = room_init.get("room_id")
            logger.info(f"短号 {input_room_id} 翻译为真实房间号: {real_room_id}")
            
            # 获取详细信息
            room_info = await self.get_room_info(real_room_id)
            
            if room_info:
                # 主播名称可能来自不同的字段，统一为 uname
                anchor_name = room_info.get("anchor_name") or room_info.get("uname", "")
                return {
                    **room_info,
                    "uid": room_init.get("uid"),
                    "short_id": room_init.get("short_id", 0),
                    "is_short_id": True,
                    "input_id": input_room_id,
                    "uname": anchor_name,
                }
            else:
                # 只有 room_init 信息
                return {
                    "room_id": real_room_id,
                    "uid": room_init.get("uid"),
                    "short_id": room_init.get("short_id", 0),
                    "live_status": room_init.get("live_status", 0),
                    "is_short_id": True,
                    "input_id": input_room_id,
                    "uname": "",
                }
        
        logger.error(f"无法解析房间号: {input_room_id}")
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
    
    async def get_ban_list(self, room_id: int, page: int = 1, page_size: int = 50) -> List[Dict[str, Any]]:
        """获取禁言列表
        参考: https://socialsisteryi.github.io/bilibili-API-collect/docs/live/silent_user_manage.html
        
        注意: B站API使用 'ps' 作为页码参数名（不是 pn）
        """
        url = f"{self.BASE_URL}/xlive/web-ucenter/v1/banned/GetSilentUserList"

        # 根据文档，ps 是页码参数（虽然命名容易混淆）
        data = {
            "room_id": str(room_id),
            "ps": str(page),  # 页码（从1开始）
            "csrf": settings.BILI_JCT,
            "csrf_token": settings.BILI_JCT,
            "visit_id": "",
        }
        
        logger.debug(f"获取禁言列表请求: room_id={room_id}, page={page}")
        
        try:
            resp = await self.client.post(url, data=data)
            text = resp.text
            logger.debug(f"禁言列表原始响应: {text[:500]}")
            
            if not text:
                logger.warning("禁言列表返回空响应")
                return []
            
            result = resp.json()
            logger.debug(f"禁言列表解析结果: code={result.get('code')}")
            
            if result.get("code") == 0:
                ban_data = result.get("data", {}).get("data", [])
                total = result.get("data", {}).get("total", 0)
                logger.info(f"获取禁言列表成功: 共 {len(ban_data)} 条, 总计 {total} 条")
                return ban_data
            else:
                logger.warning(f"获取禁言列表失败: code={result.get('code')}, message={result.get('message')}")
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

        注意：B站直播弹幕不支持单条删除。房管只能禁言用户来阻止后续弹幕。
        此方法记录操作日志并返回 False。
        """
        logger.warning(
            f"B站直播弹幕不支持单条删除。"
            f"如需阻止用户发言，请使用禁言功能。"
            f"room={room_id}, msg={msg_id}, user={user_id}"
        )
        return False


# 全局客户端实例
bili_client = BilibiliClient()
