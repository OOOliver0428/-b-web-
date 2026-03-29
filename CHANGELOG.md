# Changelog

## [1.3.0] - 2026-03-30

### New Features
- **短号翻译**: 支持自动翻译直播间短号到真实房间号，输入短号也能正确连接
- **直播信息展示**: 顶部栏新增显示主播名称、直播间标题、主播UID
- **大航海弹幕背景**: 根据用户舰队等级（总督/提督/舰长）显示对应背景图
- **禁言详情弹窗**: 优化禁言列表显示，点击详情可查看完整的禁言信息

### Improvements
- **主播名称获取**: 修复主播名称显示"未知"的问题，使用 get_info_by_id 接口获取
- **禁言到期时间**: 修复禁言列表中到期时间显示"未知"的问题，支持 block_end_time 字段
- **敏感词默认关闭**: 自动禁言功能默认关闭，需手动开启
- **静态文件路由**: 添加 /guard_bg 路由提供大航海背景图访问

### Bug Fixes
- **禁言列表参数**: 修复 get_ban_list API 调用参数错误（ps 应为页码）

## [1.2.0] - 2026-03-28

### Bug Fixes (Critical)
- **run.py**: 修复 `threading` 模块导入位置错误导致 `DEBUG=True` 时 `NameError` 的问题
- **multi_danmaku_ws.py**: 标记为废弃模块，添加弃用警告，委托给 DanmakuClient
- **敏感词同步**: 前端敏感词初始化改为从后端 API 加载，解决前后端敏感词不同步问题
- **.gitignore**: 移除对 `sensitive_words/` 的忽略，确保默认敏感词库可提交到仓库
- **后端 moderation 接入**: `Room.on_message()` 中接入 `moderation_service.check()`，弹幕和 SC 都会走自动审核
- **敏感词持久化**: 前端增删敏感词调用后端 API，后端写入 .md 文件，刷新不丢失

### Bug Fixes (Medium)
- **delete_danmaku**: 实现删除弹幕 API 端点，明确 B站不支持单条删除的限制
- **WebSocket 重连**: 前端添加指数退避自动重连机制（最多 5 次重连）
- **get_ban_list**: 修复 `ps` 参数误用为页码的问题，新增 `pn` 参数用于页码
- **双重审核**: 前端自动审核改用后端敏感词列表，减少前后端逻辑不一致
- **SC 自动审核**: 前端 `checkAutoModeration` 现在覆盖 danmaku 和 super_chat 两种类型
- **自动禁言静默**: `banUserDirect` 区分手动/自动禁言，自动禁言使用 console.log 代替 alert

### New Features
- **敏感词分类**: 前端增加词库文件选择器（替换/合并），后端新增 `load-merge` API
- **触发统计**: 新增 `GET /api/moderation/stats` 接口，记录敏感词触发次数
- **自动加载词库**: 后端启动时自动加载 `sensitive_words/default.md`
- **敏感词增删 API**: 新增 `POST /api/moderation/sensitive-words/add` 和 `/remove` 接口

### Improvements
- **CORS**: 限制为 localhost 来源，提升安全性
- **版本号**: 统一 `app/main.py` 和 `package_exe.py` 中的版本号为 1.2.0
- **依赖清理**: 移除 `requirements.txt` 中未使用的依赖（aiohttp, protobuf, python-socketio, aioredis, python-jose, requests）
- **用户列表**: 添加 500 条上限，防止长时间运行导致内存泄漏
- **安全提示**: `.env.example` 添加敏感凭证安全警告
- **代码清理**: 移除 routes.py 中重复的 `import asyncio`

### Skipped (风险过高)
- Cookie 加密存储：改动范围大，可能影响现有用户配置
- 前端构建化改造（Vite + TypeScript）：属于大版本变更，不在本次迭代范围
- API Token 认证：可能影响现有用户使用方式

## [1.1.0] - 2026-03-16
- 多服务器弹幕连接
- 消息去重和队列缓冲
- WBI 签名认证
- Super Chat 支持

## [1.0.0] - 2026-03-01
- 初始版本发布
- 基础弹幕监控
- 房管禁言/解禁功能
- 敏感词过滤
