"""直播间管理器"""
import asyncio
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass, field
from loguru import logger

from app.core.danmaku_ws import DanmakuClient
from app.core.bili_client import bili_client


@dataclass
class Room:
    """直播间数据"""
    room_id: int
    client: DanmakuClient
    status: str = "stopped"  # stopped, running, error
    danmaku_history: List[Dict] = field(default_factory=list)
    banned_users: Dict[int, Dict] = field(default_factory=dict)
    callbacks: List[Callable] = field(default_factory=list)
    
    def add_callback(self, callback: Callable):
        """添加消息回调"""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable):
        """移除消息回调"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    async def on_message(self, msg: Dict):
        """收到消息时调用"""
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
    
    async def start_room(self, room_id: int) -> bool:
        """启动直播间监听"""
        async with self._lock:
            if room_id in self.rooms:
                room = self.rooms[room_id]
                if room.status == "running":
                    logger.info(f"房间已在运行: {room_id}")
                    return True
            
            # 创建客户端
            client = DanmakuClient(
                room_id=room_id,
                on_danmaku=None  # 稍后在Room中设置
            )
            
            room = Room(room_id=room_id, client=client)
            # 设置客户端回调为room的on_message
            client.on_danmaku_callback = room.on_message
            
            # 启动客户端
            if await client.start():
                room.status = "running"
                self.rooms[room_id] = room
                logger.info(f"房间启动成功: {room_id}")
                return True
            else:
                room.status = "error"
                logger.error(f"房间启动失败: {room_id}")
                return False
    
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
                "status": r.status,
                "danmaku_count": len(r.danmaku_history),
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
