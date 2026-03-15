const { createApp, ref, computed, onMounted, onUnmounted, nextTick, watch } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

// API 封装
class ApiClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 10000,
    });
  }

  async startRoom(roomId) {
    return this.client.post('/api/rooms/start', { room_id: roomId });
  }

  async stopRoom(roomId) {
    return this.client.post('/api/rooms/stop', { room_id: roomId });
  }

  async getRooms() {
    return this.client.get('/api/rooms');
  }

  async banUser(roomId, userId, hour, reason) {
    return this.client.post('/api/moderation/ban', {
      room_id: roomId,
      user_id: userId,
      hour,
      reason
    });
  }

  async unbanUser(roomId, blockId) {
    return this.client.post('/api/moderation/unban', {
      room_id: roomId,
      block_id: blockId
    });
  }

  async getBanList(roomId) {
    return this.client.get(`/api/moderation/ban-list/${roomId}`);
  }

  async getSensitiveWords() {
    return this.client.get('/api/moderation/sensitive-words');
  }

  async addSensitiveWord(word) {
    return this.client.post('/api/moderation/sensitive-words', { word });
  }

  async removeSensitiveWord(word) {
    return this.client.delete(`/api/moderation/sensitive-words/${encodeURIComponent(word)}`);
  }
}

// WebSocket 管理
class DanmakuWebSocket {
  constructor(roomId, url, callbacks) {
    this.roomId = roomId;
    this.url = url;
    this.callbacks = callbacks;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 3000;
  }

  connect() {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          if (this.callbacks.onConnect) this.callbacks.onConnect();
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (this.callbacks.onMessage) this.callbacks.onMessage(data);
          } catch (e) {
            console.error('Parse message error:', e);
          }
        };

        this.ws.onclose = () => {
          console.log('WebSocket closed');
          if (this.callbacks.onDisconnect) this.callbacks.onDisconnect();
          this.tryReconnect();
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          if (this.callbacks.onError) this.callbacks.onError(error);
          reject(error);
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  tryReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      setTimeout(() => this.connect(), this.reconnectDelay);
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  close() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

// 创建 Vue 应用
createApp({
  setup() {
    // ===== 基础状态 =====
    const apiBaseUrl = ref(localStorage.getItem('apiBaseUrl') || 'http://localhost:8000');
    const api = new ApiClient(apiBaseUrl.value);
    
    const roomId = ref('');
    const currentRoomId = ref(null);
    const isConnected = ref(false);
    const isConnecting = ref(false);
    const connectionStatus = ref('disconnected'); // disconnected, connecting, connected
    const connectionText = computed(() => ({
      disconnected: '未连接',
      connecting: '连接中...',
      connected: '已连接'
    })[connectionStatus.value]);
    
    const ws = ref(null);
    const danmakuListRef = ref(null);
    
    // ===== 数据状态 =====
    const danmakuList = ref([]);
    const userList = ref([]);
    const banList = ref([]);
    const sensitiveWords = ref([]);
    const loadingBanList = ref(false);
    const onlineUsers = computed(() => userList.value.length);
    
    // ===== 设置状态 =====
    const showSettings = ref(false);
    const autoBan = ref({
      enabled: true,
      banOnSensitive: true,
      banOnAd: true,
      blockOnSpam: true
    });
    
    // ===== 弹窗状态 =====
    const banDialog = ref({
      visible: false,
      user: null,
      msg: '',
      hour: 1,
      reason: '',
      loading: false
    });
    
    const userMenu = ref({
      visible: false,
      user: null
    });
    
    const inputWordVisible = ref(false);
    const inputWord = ref('');
    const wordInputRef = ref(null);

    // ===== 方法 =====
    
    // 切换连接状态
    async function toggleConnection() {
      if (isConnected.value) {
        await stopListening();
      } else {
        await startListening();
      }
    }
    
    // 开始监听
    async function startListening() {
      if (!roomId.value) {
        ElMessage.warning('请输入房间号');
        return;
      }
      
      const rid = parseInt(roomId.value);
      if (isNaN(rid)) {
        ElMessage.warning('房间号必须是数字');
        return;
      }
      
      isConnecting.value = true;
      connectionStatus.value = 'connecting';
      
      try {
        // 1. 启动房间
        await api.startRoom(rid);
        currentRoomId.value = rid;
        
        // 2. 连接 WebSocket
        const wsUrl = `${apiBaseUrl.value.replace('http', 'ws')}/api/ws/danmaku/${rid}`;
        ws.value = new DanmakuWebSocket(rid, wsUrl, {
          onConnect: () => {
            isConnected.value = true;
            isConnecting.value = false;
            connectionStatus.value = 'connected';
            ElMessage.success('连接成功');
            loadBanList();
          },
          onDisconnect: () => {
            isConnected.value = false;
            isConnecting.value = false;
            connectionStatus.value = 'disconnected';
          },
          onError: (err) => {
            isConnecting.value = false;
            connectionStatus.value = 'disconnected';
            ElMessage.error('连接失败');
          },
          onMessage: handleDanmakuMessage
        });
        
        await ws.value.connect();
        
      } catch (error) {
        isConnecting.value = false;
        connectionStatus.value = 'disconnected';
        ElMessage.error(error.response?.data?.detail || '启动失败');
      }
    }
    
    // 停止监听
    async function stopListening() {
      if (ws.value) {
        ws.value.close();
        ws.value = null;
      }
      
      if (currentRoomId.value) {
        try {
          await api.stopRoom(currentRoomId.value);
        } catch (e) {
          console.error('Stop room error:', e);
        }
      }
      
      isConnected.value = false;
      isConnecting.value = false;
      connectionStatus.value = 'disconnected';
      currentRoomId.value = null;
      danmakuList.value = [];
      userList.value = [];
      
      ElMessage.success('已停止');
    }
    
    // 处理弹幕消息
    function handleDanmakuMessage(data) {
      // 历史消息
      if (data.type === 'history') {
        data.data.forEach(msg => addDanmaku(msg, false));
        return;
      }
      
      // 普通弹幕消息
      if (data.type === 'danmaku') {
        addDanmaku(data, true);
        
        // 自动审核
        if (autoBan.value.enabled) {
          checkAutoModeration(data);
        }
      }
      
      // 礼物消息
      if (data.type === 'gift') {
        console.log('Gift:', data);
      }
      
      // 进入房间
      if (data.type === 'enter') {
        addUser(data.user);
      }
    }
    
    // 添加弹幕
    function addDanmaku(data, isNew) {
      const danmaku = {
        ...data,
        id: Date.now() + Math.random(),
        isNew
      };
      
      danmakuList.value.push(danmaku);
      
      // 限制数量
      if (danmakuList.value.length > 500) {
        danmakuList.value = danmakuList.value.slice(-300);
      }
      
      // 添加用户
      if (data.user) {
        addUser(data.user);
      }
      
      // 滚动到底部
      nextTick(() => {
        if (danmakuListRef.value) {
          danmakuListRef.value.scrollTop = danmakuListRef.value.scrollHeight;
        }
        
        // 移除 new 标记
        if (isNew) {
          setTimeout(() => {
            danmaku.isNew = false;
          }, 1000);
        }
      });
    }
    
    // 添加用户
    function addUser(user) {
      if (!user || !user.uid) return;
      const exists = userList.value.find(u => u.uid === user.uid);
      if (!exists) {
        userList.value.push(user);
      }
    }
    
    // 自动审核
    function checkAutoModeration(danmaku) {
      const content = danmaku.content || '';
      const userId = danmaku.user?.uid;
      
      if (!userId) return;
      
      // 敏感词检测
      if (autoBan.value.banOnSensitive) {
        for (const word of sensitiveWords.value) {
          if (content.includes(word)) {
            banUserDirect(userId, 1, `触发敏感词: ${word}`);
            ElMessage.warning(`自动禁言用户 ${danmaku.user?.name} (敏感词: ${word})`);
            return;
          }
        }
      }
      
      // 广告检测（简单规则）
      if (autoBan.value.banOnAd) {
        const adKeywords = ['加群', 'qq群', 'QQ群', 'VX', '微信', 'vx:', '微信:', '扫码', '二维码'];
        for (const keyword of adKeywords) {
          if (content.includes(keyword)) {
            banUserDirect(userId, 24, `疑似广告: ${keyword}`);
            ElMessage.warning(`自动禁言用户 ${danmaku.user?.name} (广告)`);
            return;
          }
        }
      }
    }
    
    // 显示禁言弹窗
    function banUser(user, msg = '') {
      if (!user) return;
      banDialog.value = {
        visible: true,
        user,
        msg,
        hour: 1,
        reason: '',
        loading: false
      };
    }
    
    // 确认禁言
    async function confirmBan() {
      if (!banDialog.value.user) return;
      
      banDialog.value.loading = true;
      try {
        await banUserDirect(
          banDialog.value.user.uid,
          banDialog.value.hour,
          banDialog.value.reason
        );
        ElMessage.success('禁言成功');
        banDialog.value.visible = false;
        loadBanList();
      } catch (error) {
        ElMessage.error(error.response?.data?.detail || '禁言失败');
      } finally {
        banDialog.value.loading = false;
      }
    }
    
    // 直接禁言
    async function banUserDirect(userId, hour, reason) {
      if (!currentRoomId.value) return;
      await api.banUser(currentRoomId.value, userId, hour, reason);
    }
    
    // 解禁用户
    async function unbanUser(item) {
      if (!currentRoomId.value) return;
      
      try {
        await api.unbanUser(currentRoomId.value, item.id);
        ElMessage.success('解禁成功');
        loadBanList();
      } catch (error) {
        ElMessage.error(error.response?.data?.detail || '解禁失败');
      }
    }
    
    // 删除弹幕
    async function deleteDanmaku(item) {
      // TODO: 实现删除弹幕
      ElMessage.info('删除弹幕功能开发中');
    }
    
    // 加载禁言列表
    async function loadBanList() {
      if (!currentRoomId.value) return;
      
      loadingBanList.value = true;
      try {
        const res = await api.getBanList(currentRoomId.value);
        banList.value = res.data.data || [];
      } catch (error) {
        console.error('Load ban list error:', error);
      } finally {
        loadingBanList.value = false;
      }
    }
    
    // 加载敏感词
    async function loadSensitiveWords() {
      try {
        const res = await api.getSensitiveWords();
        sensitiveWords.value = res.data.data || [];
      } catch (error) {
        console.error('Load sensitive words error:', error);
      }
    }
    
    // 添加敏感词
    async function addSensitiveWord() {
      const word = inputWord.value.trim();
      if (!word) {
        inputWordVisible.value = false;
        return;
      }
      
      if (sensitiveWords.value.includes(word)) {
        ElMessage.warning('该敏感词已存在');
        inputWordVisible.value = false;
        inputWord.value = '';
        return;
      }
      
      try {
        await api.addSensitiveWord(word);
        sensitiveWords.value.push(word);
        inputWord.value = '';
        inputWordVisible.value = false;
        ElMessage.success('添加成功');
      } catch (error) {
        ElMessage.error('添加失败');
      }
    }
    
    // 移除敏感词
    async function removeSensitiveWord(word) {
      try {
        await api.removeSensitiveWord(word);
        const idx = sensitiveWords.value.indexOf(word);
        if (idx > -1) {
          sensitiveWords.value.splice(idx, 1);
        }
        ElMessage.success('移除成功');
      } catch (error) {
        ElMessage.error('移除失败');
      }
    }
    
    // 显示输入框
    function showWordInput() {
      inputWordVisible.value = true;
      nextTick(() => {
        wordInputRef.value?.focus();
      });
    }
    
    // 显示用户菜单
    function showUserMenu(user) {
      userMenu.value = {
        visible: true,
        user
      };
    }
    
    // 清空弹幕
    function clearDanmaku() {
      danmakuList.value = [];
    }
    
    // 保存设置
    function saveSettings() {
      localStorage.setItem('apiBaseUrl', apiBaseUrl.value);
      api.baseUrl = apiBaseUrl.value;
      api.client.defaults.baseURL = apiBaseUrl.value;
      showSettings.value = false;
      ElMessage.success('保存成功');
    }
    
    // 格式化时间
    function formatTime(timestamp) {
      if (!timestamp) return '';
      // B站时间戳是毫秒
      const date = timestamp.toString().length === 13 
        ? new Date(timestamp) 
        : new Date(timestamp * 1000);
      return dayjs(date).format('HH:mm:ss');
    }
    
    // 定期刷新禁言列表
    let banListInterval = null;
    
    // 生命周期
    onMounted(() => {
      loadSensitiveWords();
      
      // 每秒刷新禁言列表
      banListInterval = setInterval(() => {
        if (isConnected.value) {
          loadBanList();
        }
      }, 5000);
    });
    
    onUnmounted(() => {
      if (banListInterval) {
        clearInterval(banListInterval);
      }
      if (ws.value) {
        ws.value.close();
      }
    });

    return {
      // 状态
      roomId,
      isConnected,
      isConnecting,
      connectionStatus,
      connectionText,
      danmakuList,
      danmakuListRef,
      userList,
      banList,
      sensitiveWords,
      loadingBanList,
      onlineUsers,
      showSettings,
      apiBaseUrl,
      autoBan,
      banDialog,
      userMenu,
      inputWordVisible,
      inputWord,
      wordInputRef,
      
      // 方法
      toggleConnection,
      banUser,
      confirmBan,
      unbanUser,
      deleteDanmaku,
      loadBanList,
      addSensitiveWord,
      removeSensitiveWord,
      showWordInput,
      showUserMenu,
      clearDanmaku,
      saveSettings,
      formatTime
    };
  }
}).use(ElementPlus).mount('#app');
