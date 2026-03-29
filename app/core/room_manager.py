"""直播间管理器"""
import asyncio
from typing import Dict, Optional, List, Callable, Any, Set
from dataclasses import dataclass, field
from collections import deque
from loguru import logger

from app.core.danmaku_ws import DanmakuClient
from app.core.bili_client import bili_client
from app.services.moderation import moderation_service, ActionType


@dataclass
class Room:
    """直播间数据"""
    room_id: int  # 真实房间号
    input_room_id: int  # 用户输入的房间号（可能是短号）
    client: DanmakuClient
    status: str = "stopped"  # stopped, running, error
    danmaku_history: List[Dict] = field(default_factory=list)
    banned_users: Dict[int, Dict] = field(default_factory=dict)
    callbacks: List[Callable] = field(default_factory=list)
    # 全局消息去重（多连接时避免重复）
    _seen_msg_ids: deque = field(default_factory=lambda: deque(maxlen=5000))
    # 房间信息
    room_info: Dict[str, Any] = field(default_factory=dict)  # 包含主播ID、标题等
    
    def add_callback(self, callback: Callable):
        """添加消息回调"""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable):
        """移除消息回调"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def _is_duplicate(self, msg: Dict) -> bool:
        """检查消息是否重复"""
        # 使用 msg_id 或生成唯一标识
        msg_id = msg.get('msg_id') or msg.get('id')
        if msg_id:
            if msg_id in self._seen_msg_ids:
                return True
            self._seen_msg_ids.append(msg_id)
            return False
        
        # 没有ID时使用内容+时间戳生成标识
        msg_type = msg.get('type', 'unknown')
        user_id = msg.get('user', {}).get('uid', 0)
        timestamp = msg.get('timestamp') or msg.get('start_time', 0)
        content = msg.get('content') or msg.get('message', '')
        
        unique_key = f"{msg_type}:{user_id}:{timestamp}:{content[:20]}"
        if unique_key in self._seen_msg_ids:
            return True
        self._seen_msg_ids.append(unique_key)
        return False
    
    async def on_message(self, msg: Dict):
        """收到消息时调用"""
        # 全局去重（多连接时避免重复）
        if self._is_duplicate(msg):
            return
        
        # ===== 自动审核：对弹幕和 SC 进行审核 =====
        msg_type = msg.get("type", "")
        if msg_type in ("danmaku", "super_chat"):
            result = await moderation_service.check(msg)
            if result.action == ActionType.BAN:
                user = msg.get("user", {})
                uid = user.get("uid")
                if uid:
                    try:
                        await bili_client.ban_user(
                            self.room_id, uid, result.duration, result.reason
                        )
                        logger.info(f"[自动审核] 已禁言用户 {user.get('name')} ({uid}): {result.reason}")
                    except Exception as e:
                        logger.error(f"[自动审核] 禁言失败: {e}")
                # 审核拦截：不广播被禁言的消息
                return
            elif result.action == ActionType.BLOCK:
                logger.info(f"[自动审核] 屏蔽弹幕: {result.reason}")
                return
        
        # 保存历史记录（限制数量）
        self.danmaku_history.append(msg)
        if len(self.danmaku_history) > 1000:
            self.danmaku_history = self.danmaku_history[-500:]
        
        # 分发到所有回调
        for callback in self.callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(msg)
                else:
                    callback(msg)
            except Exception as e:
                logger.error(f"消息回调执行失败: {e}")


class RoomManager:
    """直播间管理器（单例）"""
    _instance: Optional['RoomManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.rooms: Dict[int, Room] = {}
        self._lock = asyncio.Lock()
    
    async def start_room(self, room_id: int) -> Dict[str, Any]:
        """
        启动直播间监听
        支持短号自动翻译
        
        返回: {
            "success": bool,
            "room_id": 真实房间号,
            "input_id": 用户输入的房间号,
            "title": 直播标题,
            "anchor_id": 主播ID,
            "anchor_name": 主播名称,
            "live_status": 直播状态,
            "message": 提示信息
        }
        """
        async with self._lock:
            # 1. 解析房间号（支持短号翻译）
            room_info = await bili_client.resolve_room_id(room_id)
            if not room_info:
                logger.error(f"无法解析房间号: {room_id}")
                return {
                    "success": False,
                    "message": "房间不存在或无法访问"
                }
            
            real_room_id = room_info.get("room_id")
            
            # 检查房间是否已在运行
            if real_room_id in self.rooms:
                room = self.rooms[real_room_id]
                if room.status == "running":
                    logger.info(f"房间已在运行: {real_room_id}")
                    return {
                        "success": True,
                        "room_id": real_room_id,
                        "input_id": room_id,
                        "title": room_info.get("title", ""),
                        "anchor_id": room_info.get("uid") or room_info.get("anchor_id"),
                        "anchor_name": room_info.get("uname", ""),
                        "live_status": room_info.get("live_status", 0),
                        "message": "房间已在运行"
                    }
            
            # 2. 创建客户端（使用真实房间号）
            client = DanmakuClient(
                room_id=real_room_id,
                on_danmaku=None  # 稍后在Room中设置
            )
            
            # 3. 创建房间对象
            room = Room(
                room_id=real_room_id,
                input_room_id=room_id,
                client=client,
                room_info=room_info
            )
            # 设置客户端回调为room的on_message
            client.on_danmaku_callback = room.on_message
            
            # 4. 启动客户端
            if await client.start():
                room.status = "running"
                self.rooms[real_room_id] = room
                
                # 构建成功响应
                result = {
                    "success": True,
                    "room_id": real_room_id,
                    "input_id": room_id,
                    "title": room_info.get("title", ""),
                    "anchor_id": room_info.get("uid") or room_info.get("anchor_id"),
                    "anchor_name": room_info.get("uname", ""),
                    "live_status": room_info.get("live_status", 0),
                    "message": f"房间启动成功{'(短号已翻译)' if room_info.get('is_short_id') else ''}"
                }
                
                if room_info.get("is_short_id"):
                    result["short_id"] = room_info.get("short_id", 0)
                
                logger.info(f"房间启动成功: {real_room_id} (输入: {room_id}), 标题: {result['title']}")
                return result
            else:
                room.status = "error"
                logger.error(f"房间启动失败: {real_room_id}")
                return {
                    "success": False,
                    "message": "连接弹幕服务器失败"
                }
    
    async def stop_room(self, room_id: int):
        """停止直播间监听"""
        async with self._lock:
            room = self.rooms.get(room_id)
            if room:
                await room.client.stop()
                room.status = "stopped"
                del self.rooms[room_id]
                logger.info(f"房间已停止: {room_id}")
    
    async def stop_all(self):
        """停止所有房间"""
        async with self._lock:
            room_ids = list(self.rooms.keys())
        
        # 在锁外逐个停止，避免死锁
        for room_id in room_ids:
            await self.stop_room(room_id)
    
    def get_room(self, room_id: int) -> Optional[Room]:
        """获取房间对象"""
        return self.rooms.get(room_id)
    
    def get_all_rooms(self) -> List[Dict]:
        """获取所有房间状态"""
        return [
            {
                "room_id": r.room_id,
                "input_room_id": r.input_room_id,
                "status": r.status,
                "danmaku_count": len(r.danmaku_history),
                "title": r.room_info.get("title", ""),
                "anchor_id": r.room_info.get("uid") or r.room_info.get("anchor_id"),
                "anchor_name": r.room_info.get("uname", ""),
                "live_status": r.room_info.get("live_status", 0),
            }
            for r in self.rooms.values()
        ]
    
    async def ban_user(self, room_id: int, user_id: int, hour: int, msg: str = "") -> bool:
        """禁言用户"""
        return await bili_client.ban_user(room_id, user_id, hour, msg)
    
    async def unban_user(self, room_id: int, block_id: int) -> bool:
        """解除禁言"""
        return await bili_client.unban_user(room_id, block_id)
    
    async def get_ban_list(self, room_id: int) -> List[Dict]:
        """获取禁言列表"""
        return await bili_client.get_ban_list(room_id)


# 全局实例
room_manager = RoomManager()
