"""弹幕审核服务"""
import re
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from app.core.config import settings


class ActionType(Enum):
    """处理动作类型"""
    PASS = "pass"           # 通过
    BLOCK = "block"         # 屏蔽
    BAN = "ban"             # 禁言
    DELETE = "delete"       # 删除


@dataclass
class ModerationResult:
    """审核结果"""
    action: ActionType
    reason: str
    duration: int = 0  # 禁言时长（小时）


class ModerationService:
    """弹幕审核服务"""
    
    def __init__(self):
        self.sensitive_words: List[str] = []
        self.regex_patterns: List[re.Pattern] = []
        self.rules: List[Callable] = []
        
        self._load_default_rules()
        self._load_sensitive_words()
    
    def _load_sensitive_words(self):
        """加载敏感词"""
        words = settings.sensitive_words_list
        self.sensitive_words = words
        logger.info(f"加载了 {len(words)} 个敏感词")
    
    def _load_default_rules(self):
        """加载默认审核规则"""
        # 规则1: 敏感词检测
        self.rules.append(self._check_sensitive_words)
        
        # 规则2: 重复字符检测（刷屏）
        self.rules.append(self._check_spam)
        
        # 规则3: 广告检测
        self.rules.append(self._check_advertisement)
    
    def add_sensitive_word(self, word: str):
        """添加敏感词"""
        if word and word not in self.sensitive_words:
            self.sensitive_words.append(word)
    
    def remove_sensitive_word(self, word: str):
        """移除敏感词"""
        if word in self.sensitive_words:
            self.sensitive_words.remove(word)
    
    def _check_sensitive_words(self, danmaku: Dict) -> Optional[ModerationResult]:
        """检测敏感词"""
        content = danmaku.get("content", "")
        
        for word in self.sensitive_words:
            if word in content:
                return ModerationResult(
                    action=ActionType.BAN,
                    reason=f"包含敏感词: {word}",
                    duration=1  # 禁言1小时
                )
        return None
    
    def _check_spam(self, danmaku: Dict) -> Optional[ModerationResult]:
        """检测刷屏（重复字符）"""
        content = danmaku.get("content", "")
        
        # 检测重复字符超过10个
        for char in set(content):
            if content.count(char) > 10:
                return ModerationResult(
                    action=ActionType.BLOCK,
                    reason="刷屏/重复字符过多"
                )
        
        # 检测重复字符串
        if len(content) >= 6:
            for i in range(2, len(content) // 2):
                pattern = content[:i]
                if content == pattern * (len(content) // i) + pattern[:len(content) % i]:
                    return ModerationResult(
                        action=ActionType.BLOCK,
                        reason="刷屏/重复内容"
                    )
        
        return None
    
    def _check_advertisement(self, danmaku: Dict) -> Optional[ModerationResult]:
        """检测广告"""
        content = danmaku.get("content", "")
        
        # 广告关键词
        ad_keywords = ["加群", "qq群", "QQ群", "VX", "微信", "vx:", "微信:", 
                      " QQ", "qq:", "扫码", "二维码", "优惠券", "低价出", "出号"]
        
        # 检测联系方式
        patterns = [
            r"[\u4e00-\u9fa5]*[0-9a-zA-Z]{5,}@(?:qq|163|126|gmail)\.com",  # 邮箱
            r"(?:加|联系).*?(?:微|V|v|Q|q).*?(?:信|Q|q).*?(?:[:：]|是).*?\d+",  # 联系方式
            r"[\u4e00-\u9fa5]{0,3}[:：]\s*[a-zA-Z0-9]{6,}",  # 可能是微信号/QQ号
        ]
        
        for keyword in ad_keywords:
            if keyword in content:
                return ModerationResult(
                    action=ActionType.BAN,
                    reason=f"疑似广告: 包含 '{keyword}'",
                    duration=24  # 禁言24小时
                )
        
        for pattern in patterns:
            if re.search(pattern, content):
                return ModerationResult(
                    action=ActionType.BAN,
                    reason="疑似广告联系方式",
                    duration=24
                )
        
        return None
    
    async def check(self, danmaku: Dict) -> ModerationResult:
        """
        审核弹幕
        返回审核结果
        """
        for rule in self.rules:
            result = rule(danmaku)
            if result:
                logger.info(f"弹幕审核不通过: {result.reason}, 内容: {danmaku.get('content', '')}")
                return result
        
        return ModerationResult(action=ActionType.PASS, reason="")
    
    def get_stats(self) -> Dict:
        """获取审核服务统计"""
        return {
            "sensitive_words_count": len(self.sensitive_words),
            "rules_count": len(self.rules),
        }


# 全局实例
moderation_service = ModerationService()
