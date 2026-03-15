"""B站直播弹幕WebSocket客户端"""
import asyncio
import json
import struct
import zlib
import brotli
from typing import Callable, Optional, Dict, Any, Set
from loguru import logger
import websockets
from websockets.legacy.client import WebSocketClientProtocol

from app.core.bili_client import bili_client


class DanmakuClient:
    """
    B站直播弹幕WebSocket客户端
    协议说明：
    - 使用protobuf编码（简化处理，直接用JSON解析）
    - 心跳包每30秒发送一次
    - 认证包包含uid, roomid, protover, platform, type, key
    """
    
    # WebSocket地址
    WS_URL = "wss://broadcastlv.chat.bilibili.com/sub"
    
    # 协议版本
    PROTOCOL_VERSION = 3  # 使用zlib压缩
    
    # 数据包类型
    PACKET_TYPE_HEARTBEAT = 2
    PACKET_TYPE_HEARTBEAT_RSP = 3
    PACKET_TYPE_NORMAL = 5
    PACKET_TYPE_AUTH = 7
    PACKET_TYPE_AUTH_RSP = 8
    
    def __init__(self, room_id: int, on_danmaku: Optional[Callable] = None):
        self.room_id = room_id
        self.real_room_id: Optional[int] = None
        self.token: Optional[str] = None
        self.ws_list: List[WebSocketClientProtocol] = []  # 多个WebSocket连接
        self.host_list: List[Dict] = []  # 服务器列表
        self.on_danmaku_callback = on_danmaku
        self.running = False
        self.uid = 0  # 0表示匿名用户
        self._tasks: List[asyncio.Task] = []  # 所有任务
        
    async def init_room(self) -> bool:
        """初始化直播间信息"""
        # 获取真实房间ID
        room_info = await bili_client.get_room_info(self.room_id)
        if not room_info:
            logger.error(f"获取房间信息失败: {self.room_id}")
            return False
        
        self.real_room_id = room_info.get("room_id")
        
        # 获取当前用户信息（用于uid）
        user_info = await bili_client.get_user_info()
        if user_info:
            self.uid = user_info.get("mid", 0)
            logger.info(f"当前用户: {user_info.get('uname')}, uid={self.uid}")
        else:
            logger.warning("无法获取用户信息，使用匿名模式(uid=0)")
            self.uid = 0
        
        # 获取弹幕服务器信息
        danmu_info = await bili_client.get_danmu_info(self.room_id)
        if not danmu_info:
            logger.error(f"获取弹幕服务器信息失败: {self.room_id}")
            return False
        
        self.token = danmu_info.get("token")
        
        # 获取host_list（多个服务器）
        self.host_list = danmu_info.get("host_list", [])
        if not self.host_list:
            logger.error("没有可用的弹幕服务器")
            return False
        
        logger.info(f"房间初始化成功: {self.real_room_id}, uid={self.uid}, token={self.token[:20]}...")
        logger.info(f"获取到 {len(self.host_list)} 个弹幕服务器: {[h['host'] for h in self.host_list]}")
        return True
    
    def _pack_data(self, data: bytes, packet_type: int) -> bytes:
        """打包数据"""
        # 包头长度16字节
        # 4字节: 包总长度
        # 2字节: 包头长度 (固定16)
        # 2字节: 协议版本
        # 4字节: 包类型
        # 4字节: 序列号 (固定1)
        
        header = struct.pack(">IHHII", 
            len(data) + 16,  # 总长度
            16,               # 头部长度
            self.PROTOCOL_VERSION,  # 协议版本
            packet_type,      # 包类型
            1                 # 序列号
        )
        return header + data
    
    def _unpack_data(self, data: bytes) -> list:
        """解包数据，返回消息列表"""
        messages = []
        offset = 0
        
        while offset < len(data):
            if len(data) - offset < 16:
                break
                
            # 解析包头
            total_len, header_len, proto_ver, packet_type, seq = struct.unpack(">IHHII", data[offset:offset+16])
            
            logger.debug(f"解包: total_len={total_len}, header_len={header_len}, proto_ver={proto_ver}, packet_type={packet_type}")
            
            if total_len < 16:
                logger.debug(f"包长度太小: {total_len}")
                offset += 16
                continue
            
            if offset + total_len > len(data):
                logger.debug(f"包长度超出: total_len={total_len}, offset={offset}, data_len={len(data)}")
                # 可能是分包，尝试按剩余长度处理
                total_len = len(data) - offset
            
            payload = data[offset+header_len:offset+total_len]
            
            # 解压（如果需要）
            if proto_ver == 2:
                # zlib 压缩
                try:
                    payload = zlib.decompress(payload)
                    logger.debug(f"zlib 解压后 payload 长度: {len(payload)}")
                except Exception as e:
                    logger.debug(f"zlib 解压失败: {e}")
            elif proto_ver == 3:
                # brotli 压缩，但某些小包可能没有压缩
                try:
                    # 先尝试 brotli 解压
                    decompressed = brotli.decompress(payload)
                    payload = decompressed
                    logger.debug(f"brotli 解压后 payload 长度: {len(payload)}")
                except Exception as e:
                    # 解压失败，可能是未压缩的小包，尝试直接解析
                    logger.debug(f"brotli 解压失败，尝试直接解析: {e}")
                    # 如果 payload 看起来像 JSON，直接用它
                    try:
                        json.loads(payload.decode('utf-8'))
                        logger.debug("payload 是有效 JSON，无需解压")
                    except:
                        pass  # 不是 JSON，保持原样
            
            # 处理不同类型的包
            if packet_type == self.PACKET_TYPE_NORMAL:  # 普通消息
                try:
                    # 解压后的数据可能包含多个JSON消息，循环解析所有
                    parse_offset = 0
                    msg_count_in_payload = 0
                    
                    while parse_offset < len(payload):
                        # 跳过非JSON字符（零字节、填充等）
                        while parse_offset < len(payload) and payload[parse_offset] != ord('{'):
                            parse_offset += 1
                        
                        if parse_offset >= len(payload):
                            break
                        
                        remaining = payload[parse_offset:]
                        
                        # 查找完整的 JSON（括号匹配）
                        brace_depth = 0
                        json_end = -1
                        in_string = False
                        escape = False
                        
                        for i in range(len(remaining)):
                            c = remaining[i]
                            if escape:
                                escape = False
                                continue
                            if c == ord('\\'):
                                escape = True
                                continue
                            if c == ord('"'):
                                in_string = not in_string
                                continue
                            if not in_string:
                                if c == ord('{'):
                                    brace_depth += 1
                                elif c == ord('}'):
                                    brace_depth -= 1
                                    if brace_depth == 0:
                                        json_end = i + 1
                                        break
                        
                        if json_end <= 0:
                            break  # 找不到完整JSON
                        
                        try:
                            msg = json.loads(remaining[:json_end].decode('utf-8', errors='replace'))
                            messages.append(msg)
                            msg_count_in_payload += 1
                            parse_offset += json_end
                        except json.JSONDecodeError:
                            parse_offset += json_end  # 跳过这条，继续
                    
                    if msg_count_in_payload > 0:
                        logger.debug(f"从payload解析到 {msg_count_in_payload} 条消息")
                    
                except Exception as e:
                    logger.debug(f"解析消息失败: {e}")
            
            elif packet_type == self.PACKET_TYPE_AUTH_RSP:  # 认证响应
                try:
                    msg = json.loads(payload.decode('utf-8'))
                    messages.append({"cmd": "AUTH_REPLY", "data": msg})
                    logger.info(f"认证响应: {msg}")
                except Exception as e:
                    logger.debug(f"解析认证响应失败: {e}")
            
            elif packet_type == self.PACKET_TYPE_HEARTBEAT_RSP:  # 心跳响应
                # 心跳响应通常是一个整数（在线人数）
                try:
                    online_count = struct.unpack(">I", payload)[0]
                    logger.debug(f"心跳响应，在线人数: {online_count}")
                except:
                    pass
            
            offset += total_len
        
        return messages
    
    async def _send_auth(self, ws: WebSocketClientProtocol) -> bool:
        """发送认证包并等待响应"""
        auth_data = {
            "uid": self.uid,
            "roomid": self.real_room_id,
            "protover": self.PROTOCOL_VERSION,
            "platform": "web",
            "type": 2,
            "key": self.token,
        }
        data = json.dumps(auth_data).encode('utf-8')
        packet = self._pack_data(data, self.PACKET_TYPE_AUTH)
        await ws.send(packet)
        
        # 等待认证响应（5秒超时）
        try:
            resp_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
            messages = self._unpack_data(resp_data)
            
            # 检查是否有认证响应
            for msg in messages:
                if isinstance(msg, dict) and msg.get("cmd") == "AUTH_REPLY":
                    auth_data = msg.get("data", {})
                    if auth_data.get("code") == 0:
                        return True
                    else:
                        return False
            
            return True
            
        except asyncio.TimeoutError:
            return True  # 超时也继续，可能认证是静默的
    
    async def _send_heartbeat(self, ws: WebSocketClientProtocol):
        """发送心跳包 - 15秒间隔，避免连接被断开"""
        while self.running:
            try:
                packet = self._pack_data(b'[object Object]', self.PACKET_TYPE_HEARTBEAT)
                await ws.send(packet)
                await asyncio.sleep(15)
            except Exception as e:
                logger.debug(f"心跳发送失败: {e}")
                break
    
    async def _listen(self, ws: WebSocketClientProtocol):
        """监听消息 - 使用队列异步处理"""
        msg_count = 0
        
        try:
            while self.running:
                try:
                    data = await ws.recv()
                    msg_count += 1
                    
                    if isinstance(data, str):
                        continue
                    
                    messages = self._unpack_data(data)
                    
                    for msg in messages:
                        await self._handle_message(msg)
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.debug(f"WebSocket连接已关闭")
                    break
                except Exception as e:
                    logger.debug(f"接收消息异常: {e}")
                    break
        finally:
            logger.debug(f"监听结束，共接收 {msg_count} 条消息")
    async def _handle_message(self, msg: Dict[str, Any]):
        """处理消息"""
        cmd = msg.get("cmd", "")
        
        # 弹幕消息 (cmd 可能是 "DANMU_MSG" 或 "DANMU_MSG:4:0:2:2:2:0" 等格式)
        if cmd.startswith("DANMU_MSG"):
            info = msg.get("info", [])
            if len(info) >= 3:
                danmaku_data = {
                    "type": "danmaku",
                    "msg_id": msg.get("dm_v2", ""),  # 弹幕ID
                    "content": info[1],  # 弹幕内容
                    "timestamp": info[0][4],  # 发送时间
                    "user": {
                        "uid": info[2][0],  # 用户ID
                        "name": info[2][1],  # 用户名
                        "is_admin": info[2][2] == 1,  # 是否房管
                        "is_vip": info[2][3] == 1,  # 是否VIP
                        "guard_level": info[7] if len(info) > 7 else 0,  # 舰队等级
                    },
                    "medal": info[3] if len(info) > 3 and info[3] else None,  # 粉丝牌
                    "room_id": self.room_id,
                }
                if self.on_danmaku_callback:
                    await self.on_danmaku_callback(danmaku_data)
        
        # 礼物消息
        elif cmd == "SEND_GIFT":
            data = msg.get("data", {})
            gift_data = {
                "type": "gift",
                "user": {
                    "uid": data.get("uid"),
                    "name": data.get("uname"),
                },
                "gift_name": data.get("giftName"),
                "num": data.get("num"),
                "price": data.get("price"),
                "timestamp": data.get("timestamp"),
            }
            if self.on_danmaku_callback:
                await self.on_danmaku_callback(gift_data)
        
        # 进入直播间
        elif cmd == "INTERACT_WORD":
            data = msg.get("data", {})
            enter_data = {
                "type": "enter",
                "user": {
                    "uid": data.get("uid"),
                    "name": data.get("uname"),
                },
                "timestamp": data.get("timestamp"),
            }
            if self.on_danmaku_callback:
                await self.on_danmaku_callback(enter_data)
        
        # 其他消息类型可以根据需要添加
    
    async def start(self) -> bool:
        """启动客户端 - 同时连接多个服务器"""
        if not await self.init_room():
            return False
        
        self.running = True
        self._tasks = []
        
        # 同时连接所有服务器（最多3个）
        for i, host in enumerate(self.host_list[:3]):
            ws_url = f"wss://{host['host']}:{host['wss_port']}/sub"
            task = asyncio.create_task(self._connect_server(ws_url, i))
            self._tasks.append(task)
        
        # 等待一会儿看连接情况
        await asyncio.sleep(2)
        
        connected = len([ws for ws in self.ws_list if ws])
        if connected == 0:
            logger.error("所有弹幕服务器连接失败")
            return False
        
        logger.info(f"弹幕客户端启动成功: room={self.room_id}, 连接数={connected}/{len(self.host_list[:3])}")
        return True
    
    async def _connect_server(self, ws_url: str, index: int):
        """连接单个服务器"""
        try:
            logger.info(f"[连接{index+1}] 正在连接: {ws_url}")
            ws = await websockets.connect(
                ws_url,
                ping_interval=None,  # 我们自己发心跳
                max_size=None,  # 不限制消息大小
                compression=None  # 禁用WebSocket压缩，我们已经手动解压
            )
            self.ws_list.append(ws)
            logger.info(f"[连接{index+1}] WebSocket 已连接")
            
            # 发送认证
            await self._send_auth(ws)
            logger.info(f"[连接{index+1}] 认证成功")
            
            # 启动心跳和监听
            heartbeat_task = asyncio.create_task(self._send_heartbeat(ws))
            listen_task = asyncio.create_task(self._listen(ws))
            
            self._tasks.extend([heartbeat_task, listen_task])
            
            # 等待任务结束
            await asyncio.gather(heartbeat_task, listen_task)
            
        except Exception as e:
            logger.error(f"[连接{index+1}] 异常: {e}")
    
    async def stop(self):
        """停止客户端 - 关闭所有连接"""
        logger.info(f"正在停止弹幕客户端: room={self.room_id}")
        self.running = False
        
        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # 关闭所有 WebSocket
        for ws in self.ws_list:
            try:
                await ws.close()
            except:
                pass
        
        self.ws_list.clear()
        self._tasks.clear()
        
        logger.info(f"弹幕客户端已停止: room={self.room_id}")
