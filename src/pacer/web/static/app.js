// pacer-ai frontend — static methods, all onclick-driven. No event listener spaghetti.
const Pacer = {
  token: localStorage.getItem('pacer_token') || null,
  studentId: localStorage.getItem('pacer_student_id') || null,
  sessionId: null,
  eventSource: null,

  // ─── init ───────────────────────────────────────────────

  init() {
    if (this.token) {
      this._showChat();
      this._connectSSE();
    } else {
      this._showLogin();
    }
    this._initTheme();
  },

  // ─── login / logout ────────────────────────────────────

  async login() {
    const sid = document.getElementById('login-student-id').value.trim();
    const pin = document.getElementById('login-pin').value.trim();
    if (!sid || !pin) return;
    try {
      const resp = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: parseInt(sid), pin }),
      });
      if (!resp.ok) { alert('登录失败'); return; }
      const data = await resp.json();
      this.token = data.token;
      this.studentId = data.student_id;
      localStorage.setItem('pacer_token', this.token);
      localStorage.setItem('pacer_student_id', this.studentId);
      this._showChat();
      this._connectSSE();
      this._loadName();
    } catch (e) { alert('连接失败: ' + e.message); }
  },

  logout() {
    if (this.eventSource) this.eventSource.close();
    localStorage.removeItem('pacer_token');
    localStorage.removeItem('pacer_student_id');
    this.token = null;
    this.studentId = null;
    this.sessionId = null;
    document.getElementById('messages').innerHTML = '';
    this._showLogin();
  },

  // ─── theme ─────────────────────────────────────────────

  _initTheme() {
    if (localStorage.getItem('pacer_theme') === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  },

  toggleTheme() {
    const is = document.documentElement.getAttribute('data-theme') === 'dark';
    document.documentElement.setAttribute('data-theme', is ? 'light' : 'dark');
    localStorage.setItem('pacer_theme', is ? 'light' : 'dark');
  },

  // ─── screen toggle ─────────────────────────────────────

  _showLogin() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('chat-screen').style.display = 'none';
    const c = document.getElementById('fluid-canvas');
    if (c) c.style.display = 'block';
  },

  _showChat() {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('chat-screen').style.display = 'flex';
    const c = document.getElementById('fluid-canvas');
    if (c) c.style.display = 'none';
  },

  async _loadName() {
    try {
      const r = await fetch('/profile/', { headers: { 'Authorization': 'Bearer ' + this.token } });
      if (r.ok) {
        const p = await r.json();
        document.getElementById('header-name').textContent = (p.name || '同学') + ' · pacer';
      }
    } catch (e) {}
  },

  // ─── SSE ───────────────────────────────────────────────

  _connectSSE() {
    if (this.eventSource) this.eventSource.close();
    this.eventSource = new EventSource('/events/stream?token=' + encodeURIComponent(this.token));
    this.eventSource.addEventListener('assistant_message', e => {
      const d = JSON.parse(e.data);
      this._addMsg('assistant', d.text, d.agent);
      this._hideTyping();
    });
    this.eventSource.addEventListener('ping', () => {});
    this.eventSource.onerror = () => setTimeout(() => this._connectSSE(), 3000);
  },

  // ─── send ──────────────────────────────────────────────

  async send() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text || !this.token) return;
    input.value = '';
    input.style.height = 'auto';

    const es = document.getElementById('empty-state');
    if (es) es.style.display = 'none';

    this._addMsg('user', text);
    this._showTyping();
    document.getElementById('send-btn').disabled = true;

    try {
      const r = await fetch('/message/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + this.token },
        body: JSON.stringify({ text, session_id: this.sessionId }),
      });
      const d = await r.json();
      this.sessionId = d.session_id;
    } catch (e) {
      this._hideTyping();
      this._addMsg('assistant', '出错了，请稍后重试。');
    }
    document.getElementById('send-btn').disabled = false;
  },

  sendPreset(text) {
    document.getElementById('chat-input').value = text;
    this.send();
  },

  newChat() {
    this.sessionId = null;
    const msgs = document.getElementById('messages');
    msgs.innerHTML = `<div id="empty-state" class="empty-state">
      <div class="empty-state-icon">☀️</div><h1>新对话</h1><p>有什么想聊的？</p>
      <div class="suggestions">
        <button class="suggestion" onclick="Pacer.sendPreset('帮我讲一道导数题')">📐 讲一道导数题</button>
        <button class="suggestion" onclick="Pacer.sendPreset('帮我制定今天的学习计划')">📋 今日学习计划</button>
        <button class="suggestion" onclick="Pacer.sendPreset('帮我分析一下这道错题')">📝 分析错题</button>
        <button class="suggestion" onclick="Pacer.sendPreset('最近有点焦虑，想聊聊')">💭 聊聊压力</button>
      </div></div>`;
  },

  // ─── messages ──────────────────────────────────────────

  _addMsg(role, content, agent) {
    if (!content) return;
    const div = document.createElement('div');
    div.className = 'msg msg-' + role;
    let tag = '';
    if (agent === 'subject_teacher') tag = '<span class="msg-agent-badge">📚 学科老师</span>';
    if (agent === 'mood_companion') tag = '<span class="msg-agent-badge">💗 心态陪伴</span>';
    div.innerHTML = tag + '<div class="msg-bubble">' + this._md(content) + '</div>';
    document.getElementById('messages').appendChild(div);
    const sc = document.getElementById('chat-scroll');
    if (sc) sc.scrollTop = sc.scrollHeight;
  },

  _md(t) {
    return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/```(\w*)\n([\s\S]*?)```/g,'<pre><code>$2</code></pre>')
      .replace(/`([^`]+)`/g,'<code>$1</code>')
      .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
      .replace(/\n/g,'<br>');
  },

  _showTyping() {
    const d = document.createElement('div');
    d.className = 'msg msg-assistant';
    d.id = 'typing';
    d.innerHTML = '<div class="msg-bubble typing"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
    document.getElementById('messages').appendChild(d);
    const sc = document.getElementById('chat-scroll');
    if (sc) sc.scrollTop = sc.scrollHeight;
  },

  _hideTyping() {
    const t = document.getElementById('typing');
    if (t) t.remove();
  },

  // ─── upload ────────────────────────────────────────────

  async upload(input) {
    const file = input.files[0];
    if (!file) return;
    this._addMsg('user', '[上传了图片]');
    this._showTyping();
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/upload/image', {
        method: 'POST', headers: { 'Authorization': 'Bearer ' + this.token }, body: fd,
      });
      const d = await r.json();
      this._hideTyping();
      if (d.auto_filled_stem) {
        document.getElementById('chat-input').value = d.auto_filled_stem;
        document.getElementById('chat-input').focus();
        this._addMsg('assistant', '识别为一道 ' + (d.auto_routed_to_subject || '') + ' 题：\n' + d.auto_filled_stem + '\n\n直接发送，我来讲解。', 'subject_teacher');
      }
    } catch (e) {
      this._hideTyping();
      this._addMsg('assistant', '图片处理出错，请重试。');
    }
    input.value = '';
  },
};

document.addEventListener('DOMContentLoaded', () => Pacer.init());
