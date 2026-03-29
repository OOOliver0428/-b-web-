"""API路由"""
import os
import sys
import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from loguru import logger

from app.core.room_manager import room_manager
from app.services.moderation import moderation_service, ActionType
from app.core.bili_client import bili_client
from app.core.config import get_external_path


router = APIRouter()


# ============ 数据模型 ============

class RoomCreate(BaseModel):
    room_id: int


class BanUserRequest(BaseModel):
    room_id: int
    user_id: int
    hour: int = 1  # -1=永久, 0=本场, 其他=小时
    reason: str = ""


class UnbanUserRequest(BaseModel):
    room_id: int
    block_id: int


class SensitiveWordRequest(BaseModel):
    word: str


class DeleteDanmakuRequest(BaseModel):
    room_id: int
    msg_id: str = ""
    user_id: int


class AutoModerationConfig(BaseModel):
    enabled: bool = True
    ban_on_sensitive: bool = True
    ban_on_advertisement: bool = True
    block_on_spam: bool = True


# ============ 直播间管理接口 ============

@router.post("/rooms/start")
async def start_room(data: RoomCreate):
    """启动直播间监听（支持短号自动翻译）"""
    result = await room_manager.start_room(data.room_id)
    if result.get("success"):
        return {
            "code": 0, 
            "message": result.get("message", "启动成功"),
            "data": {
                "room_id": result.get("room_id"),
                "input_id": result.get("input_id"),
                "title": result.get("title"),
                "anchor_id": result.get("anchor_id"),
                "anchor_name": result.get("anchor_name"),
                "live_status": result.get("live_status"),
            }
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("message", "启动失败"))


@router.post("/rooms/stop")
async def stop_room(data: RoomCreate):
    """停止直播间监听"""
    await room_manager.stop_room(data.room_id)
    return {"code": 0, "message": "已停止"}


@router.get("/rooms")
async def list_rooms():
    """获取所有监听的房间"""
    rooms = room_manager.get_all_rooms()
    return {"code": 0, "data": rooms}


@router.get("/rooms/{room_id}/history")
async def get_room_history(room_id: int, limit: int = 100):
    """获取房间弹幕历史"""
    room = room_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")
    
    history = room.danmaku_history[-limit:] if room.danmaku_history else []
    return {"code": 0, "data": history}


# ============ 房管操作接口 ============

@router.post("/moderation/ban")
async def ban_user(data: BanUserRequest):
    """禁言用户"""
    success = await room_manager.ban_user(
        data.room_id, data.user_id, data.hour, data.reason
    )
    if success:
        return {"code": 0, "message": "禁言成功"}
    else:
        raise HTTPException(status_code=400, detail="禁言失败，请检查权限")


@router.post("/moderation/unban")
async def unban_user(data: UnbanUserRequest):
    """解除禁言"""
    success = await room_manager.unban_user(data.room_id, data.block_id)
    if success:
        return {"code": 0, "message": "解除禁言成功"}
    else:
        raise HTTPException(status_code=400, detail="解除禁言失败")


@router.get("/moderation/ban-list/{room_id}")
async def get_ban_list(room_id: int):
    """获取禁言列表"""
    ban_list = await room_manager.get_ban_list(room_id)
    return {"code": 0, "data": ban_list}


@router.post("/moderation/delete-danmaku")
async def delete_danmaku(data: DeleteDanmakuRequest):
    """删除弹幕（B站不支持单条删除，此接口会禁言用户）"""
    success = await bili_client.delete_danmaku(data.room_id, data.msg_id, data.user_id)
    if success:
        return {"code": 0, "message": "操作成功"}
    else:
        # B站不支持单条删除弹幕，提示用户使用禁言功能
        return {"code": -1, "message": "B站直播不支持删除单条弹幕，请使用禁言功能阻止用户发言"}


# ============ 敏感词管理接口 ============

# 敏感词文件目录（优先使用外部目录，方便用户配置）
SENSITIVE_WORDS_DIR = os.path.join(get_external_path(), "sensitive_words")

def load_sensitive_words_from_file(filename: str) -> List[str]:
    """从 .md 文件加载敏感词"""
    filepath = os.path.join(SENSITIVE_WORDS_DIR, filename)
    if not os.path.exists(filepath):
        return []
    
    words = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释行
                if not line or line.startswith("#"):
                    continue
                words.append(line)
    except Exception as e:
        logger.error(f"加载敏感词文件失败: {e}")
    
    return words

@router.get("/moderation/sensitive-word-files")
async def get_sensitive_word_files():
    """获取可用的敏感词文件列表"""
    try:
        if not os.path.exists(SENSITIVE_WORDS_DIR):
            return {"code": 0, "data": []}
        
        files = [f for f in os.listdir(SENSITIVE_WORDS_DIR) if f.endswith(".md")]
        return {"code": 0, "data": files}
    except Exception as e:
        logger.error(f"获取敏感词文件列表失败: {e}")
        return {"code": -1, "message": str(e), "data": []}

@router.post("/moderation/sensitive-words/load")
async def load_sensitive_words(data: dict):
    """加载指定文件的敏感词（替换当前列表）"""
    filename = data.get("filename", "")
    if not filename:
        return {"code": -1, "message": "文件名不能为空"}
    
    # 安全检查：只允许 .md 文件
    if not filename.endswith(".md"):
        return {"code": -1, "message": "只能加载 .md 文件"}
    
    count = moderation_service.load_file(filename)
    if count == 0 and not os.path.exists(os.path.join(SENSITIVE_WORDS_DIR, filename)):
        return {"code": -1, "message": f"文件 {filename} 不存在"}
    
    return {"code": 0, "message": f"已加载 {count} 个敏感词", "data": moderation_service.sensitive_words}


@router.post("/moderation/sensitive-words/load-merge")
async def load_sensitive_words_merge(data: dict):
    """加载指定文件的敏感词（合并到当前列表）"""
    filename = data.get("filename", "")
    if not filename:
        return {"code": -1, "message": "文件名不能为空"}
    if not filename.endswith(".md"):
        return {"code": -1, "message": "只能加载 .md 文件"}
    
    added = moderation_service.load_file_merge(filename)
    return {
        "code": 0,
        "message": f"合并加载完成，新增 {added} 个词",
        "data": moderation_service.sensitive_words
    }


@router.get("/moderation/sensitive-words")
async def get_sensitive_words():
    """获取当前加载的敏感词列表"""
    return {
        "code": 0, 
        "data": moderation_service.sensitive_words,
        "loaded_files": moderation_service.loaded_files,
    }


@router.post("/moderation/sensitive-words/add")
async def add_sensitive_word(data: dict):
    """添加敏感词并持久化到文件"""
    word = data.get("word", "").strip()
    filename = data.get("filename", "default.md").strip()
    if not word:
        return {"code": -1, "message": "敏感词不能为空"}
    if not filename.endswith(".md"):
        return {"code": -1, "message": "只能写入 .md 文件"}
    
    if word in moderation_service.sensitive_words:
        return {"code": -1, "message": "该敏感词已存在"}
    
    success = moderation_service.add_sensitive_word(word, filename)
    if success:
        return {"code": 0, "message": "添加成功", "data": moderation_service.sensitive_words}
    else:
        return {"code": -1, "message": "添加失败，文件写入异常"}


@router.post("/moderation/sensitive-words/remove")
async def remove_sensitive_word(data: dict):
    """移除敏感词并持久化到文件"""
    word = data.get("word", "").strip()
    filename = data.get("filename", "default.md").strip()
    if not word:
        return {"code": -1, "message": "敏感词不能为空"}
    if not filename.endswith(".md"):
        return {"code": -1, "message": "只能写入 .md 文件"}
    
    success = moderation_service.remove_sensitive_word(word, filename)
    if success:
        return {"code": 0, "message": "移除成功", "data": moderation_service.sensitive_words}
    else:
        return {"code": -1, "message": "该敏感词不存在"}


@router.get("/moderation/stats")
async def get_moderation_stats():
    """获取审核触发统计"""
    return {"code": 0, "data": moderation_service.get_stats()}


# ============ WebSocket接口（实时弹幕） ============

@router.websocket("/ws/danmaku/{room_id}")
async def danmaku_websocket(websocket: WebSocket, room_id: int):
    """
    WebSocket实时弹幕推送
    连接后自动订阅指定房间的弹幕
    """
    await websocket.accept()
    logger.info(f"WebSocket 客户端已连接: room={room_id}")
    
    room = room_manager.get_room(room_id)
    if not room:
        await websocket.send_json({"type": "error", "message": "房间未启动"})
        await websocket.close()
        return
    
    # 创建消息队列
    message_queue = asyncio.Queue()
    
    # 定义回调函数 - 将消息放入队列
    async def on_danmaku(msg: Dict):
        await message_queue.put(msg)
    
    # 添加回调
    room.add_callback(on_danmaku)
    
    async def send_messages():
        """持续发送消息给客户端"""
        while True:
            try:
                msg = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
                break
    
    async def receive_commands():
        """接收客户端命令"""
        while True:
            try:
                data = await websocket.receive_json()
                cmd = data.get("cmd")
                if cmd == "ban":
                    user_id = data.get("user_id")
                    hour = data.get("hour", 1)
                    await room_manager.ban_user(room_id, user_id, hour)
                    await websocket.send_json({"type": "success", "message": f"已禁言用户 {user_id}"})
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"接收命令失败: {e}")
                break
    
    try:
        # 发送历史弹幕
        history = room.danmaku_history[-50:] if room.danmaku_history else []
        await websocket.send_json({"type": "history", "data": history})
        logger.info(f"已发送历史弹幕: {len(history)} 条")
        
        # 同时运行发送和接收任务
        send_task = asyncio.create_task(send_messages())
        receive_task = asyncio.create_task(receive_commands())
        
        # 等待任意一个任务结束
        done, pending = await asyncio.wait(
            [send_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # 取消剩余任务
        for task in pending:
            task.cancel()
            
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
    finally:
        room.remove_callback(on_danmaku)
        logger.info(f"WebSocket 客户端已断开: room={room_id}")


# ============ 系统状态接口 ============

@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "code": 0,
        "status": "ok",
        "rooms": len(room_manager.rooms),
        "moderation": moderation_service.get_stats()
    }


@router.get("/debug/danmaku/{room_id}")
async def debug_danmaku(room_id: int):
    """调试：获取原始弹幕数据"""
    room = room_manager.get_room(room_id)
    if not room:
        return {"code": -1, "message": "房间未启动"}
    
    # 返回最近的10条弹幕
    recent = room.danmaku_history[-10:] if room.danmaku_history else []
    return {
        "code": 0,
        "data": {
            "room_status": room.status,
            "total_danmaku": len(room.danmaku_history),
            "recent_danmaku": recent
        }
    }
