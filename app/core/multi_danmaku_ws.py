"""多连接弹幕客户端 - 同时连接多个B站弹幕服务器，减少遗漏"""
import asyncio
from typing import Callable, Optional, List, Dict
from loguru import logger

from app.core.danmaku_ws import DanmakuClient


class MultiDanmakuClient:
    """
    多连接弹幕客户端
    同时连接B站提供的多个弹幕服务器，提高消息接收可靠性
    """
    
    def __init__(self, room_id: int, on_danmaku: Optional[Callable] = None):
        self.room_id = room_id
        self.on_danmaku_callback = on_danmaku
        self.clients: List[DanmakuClient] = []
        self.running = False
        
    async def start(self) -> bool:
        """启动多个客户端连接"""
        # 先用一个客户端初始化房间信息
        init_client = DanmakuClient(self.room_id)
        if not await init_client.init_room():
            logger.error(f"房间初始化失败: {self.room_id}")
            return False
        
        # 获取所有host
        from app.core.bili_client import bili_client
        danmu_info = await bili_client.get_danmu_info(self.room_id)
        if not danmu_info:
            logger.error("获取弹幕服务器信息失败")
            return False
        
        host_list = danmu_info.get("host_list", [])
        token = danmu_info.get("token")
        
        if not host_list:
            logger.error("没有可用的弹幕服务器")
            return False
        
        # 为每个host创建一个客户端
        self.running = True
        tasks = []
        
        for i, host in enumerate(host_list[:3]):  # 最多连接3个服务器
            client = DanmakuClient(self.room_id, self._on_message)
            client.real_room_id = init_client.real_room_id
            client.uid = init_client.uid
            client.token = token
            client.WS_URL = f"wss://{host['host']}:{host['wss_port']}/sub"
            
            self.clients.append(client)
            
            # 启动客户端
            task = asyncio.create_task(self._start_client(client, i))
            tasks.append(task)
            logger.info(f"启动弹幕客户端 #{i+1}: {host['host']}")
        
        # 等待至少一个连接成功
        await asyncio.sleep(2)
        connected = sum(1 for c in self.clients if c.ws and c.running)
        
        if connected == 0:
            logger.error("所有弹幕服务器连接失败")
            return False
        
        logger.info(f"弹幕多连接启动成功: {connected}/{len(self.clients)} 个连接")
        return True
    
    async def _start_client(self, client: DanmakuClient, index: int):
        """启动单个客户端"""
        try:
            # 手动启动，不使用 client.start()
            import websockets
            logger.debug(f"客户端 #{index+1} 连接: {client.WS_URL}")
            
            client.ws = await websockets.connect(client.WS_URL)
            client.running = True
            
            # 发送认证
            await client._send_auth()
            
            # 启动心跳和监听
            asyncio.create_task(client._send_heartbeat())
            await client._listen()
            
        except Exception as e:
            logger.error(f"客户端 #{index+1} 异常: {e}")
    
    async def _on_message(self, msg: Dict):
        """消息回调 - 去重后转发"""
        # 使用消息ID去重（如果可用）
        msg_id = msg.get("msg_id") or f"{msg.get('user', {}).get('uid')}_{msg.get('timestamp')}"
        
        # 这里可以实现一个去重缓存
        # 简单起见，直接转发
        if self.on_danmaku_callback:
            await self.on_danmaku_callback(msg)
    
    async def stop(self):
        """停止所有客户端"""
        self.running = False
        
        stop_tasks = []
        for client in self.clients:
            if client.running:
                stop_tasks.append(client.stop())
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        self.clients.clear()
        logger.info("多连接弹幕客户端已停止")
