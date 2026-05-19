class PacerApp {
  constructor() {
    this.token = localStorage.getItem('pacer_token');
    this.studentId = localStorage.getItem('pacer_student_id');
    this.currentSessionId = null;
    this.messages = [];
    this.eventSource = null;
    this.fluidCanvas = document.getElementById('fluid-canvas');
    this.loginEl = document.getElementById('login-screen');
    this.chatEl = document.getElementById('chat-screen');
    this.messagesEl = document.getElementById('messages');
    this.suggestionsEl = document.getElementById('suggestions');
    this.chatInput = document.getElementById('chat-input');
    this.sendBtn = document.getElementById('send-btn');
    this.sessionsList = document.getElementById('sessions-list');
    this.newChatBtn = document.getElementById('new-chat-btn');
    this.themeToggle = document.getElementById('theme-toggle');
    this.uploadBtn = document.getElementById('upload-btn');
    this.fileInput = document.getElementById('file-input');
    this.logoutBtn = document.getElementById('logout-btn');
    this.profileBtn = document.getElementById('profile-btn');
  }

  init() {
    if (this.token) {
      this.connectSSE();
      this.showChat();
    } else {
      this.showLogin();
    }
    this.bindEvents();
    this.initTheme();
  }

  bindEvents() {
    document.getElementById('login-form').addEventListener('submit', e => {
      e.preventDefault();
      this.login();
    });
    this.sendBtn.addEventListener('click', () => this.send());
    this.chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    });
    this.chatInput.addEventListener('input', () => this.autoGrow());
    this.newChatBtn.addEventListener('click', () => this.newSession());
    this.themeToggle.addEventListener('click', () => this.toggleTheme());
    this.uploadBtn.addEventListener('click', () => this.fileInput.click());
    this.fileInput.addEventListener('change', e => this.handleUpload(e));
    this.logoutBtn.addEventListener('click', () => this.logout());
    this.profileBtn.addEventListener('click', () => this.toggleProfile());
  }

  initTheme() {
    const saved = localStorage.getItem('pacer_theme');
    if (saved === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  }

  toggleTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('pacer_theme', isDark ? 'light' : 'dark');
  }

  async login() {
    const sid = document.getElementById('login-student-id').value.trim();
    const pin = document.getElementById('login-pin').value.trim();
    if (!sid || !pin) return;
    try {
      const resp = await fetch('/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: parseInt(sid), pin }),
      });
      if (!resp.ok) {
        alert('登录失败，请检查学号和密码');
        return;
      }
      const data = await resp.json();
      this.token = data.token;
      this.studentId = data.student_id;
      localStorage.setItem('pacer_token', this.token);
      localStorage.setItem('pacer_student_id', this.studentId);
      this.connectSSE();
      this.showChat();
    } catch (e) {
      alert('连接失败: ' + e.message);
    }
  }

  logout() {
    if (this.eventSource) this.eventSource.close();
    localStorage.removeItem('pacer_token');
    localStorage.removeItem('pacer_student_id');
    this.token = null;
    this.studentId = null;
    this.currentSessionId = null;
    this.messages = [];
    this.messagesEl.innerHTML = '';
    this.showLogin();
  }

  showLogin() {
    this.loginEl.style.display = 'flex';
    this.chatEl.style.display = 'none';
    if (this.fluidCanvas) this.fluidCanvas.style.display = 'block';
  }

  showChat() {
    this.loginEl.style.display = 'none';
    this.chatEl.style.display = 'flex';
    if (this.fluidCanvas) this.fluidCanvas.style.display = 'none';
    this.loadProfile();
  }

  async loadProfile() {
    try {
      const resp = await fetch('/profile/', {
        headers: { 'Authorization': `Bearer ${this.token}` },
      });
      if (resp.ok) {
        const p = await resp.json();
        const nameEl = document.getElementById('student-name');
        if (nameEl) nameEl.textContent = p.name || '同学';
      }
    } catch (e) {}
  }

  toggleProfile() {
    alert('学生信息面板将在后续版本上线');
  }

  connectSSE() {
    if (this.eventSource) this.eventSource.close();
    this.eventSource = new EventSource(`/events/stream?token=${encodeURIComponent(this.token)}`);
    this.eventSource.addEventListener('assistant_message', e => {
      const data = JSON.parse(e.data);
      this.addMessage('assistant', data.text, data.agent);
      this.hideTyping();
    });
    this.eventSource.addEventListener('ping', () => {});
    this.eventSource.onerror = () => {
      setTimeout(() => this.connectSSE(), 3000);
    };
  }

  async send() {
    const text = this.chatInput.value.trim();
    if (!text || !this.token) return;
    this.chatInput.value = '';
    this.chatInput.style.height = 'auto';
    // Hide suggestions on first message
    if (this.suggestionsEl) this.suggestionsEl.style.display = 'none';
    this.addMessage('user', text);
    this.showTyping();
    this.sendBtn.disabled = true;
    try {
      const resp = await fetch('/message/send', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.token}`,
        },
        body: JSON.stringify({ text, session_id: this.currentSessionId }),
      });
      const data = await resp.json();
      this.currentSessionId = data.session_id;
    } catch (e) {
      this.hideTyping();
      this.addMessage('assistant', '出错了，请稍后重试。');
    }
    this.sendBtn.disabled = false;
  }

  addMessage(role, content, agent) {
    if (!content) return;
    this.messages.push({ role, content, agent });
    const el = document.createElement('div');
    el.className = `msg msg-${role}`;
    const tag = agent && agent !== 'homeroom'
      ? `<span class="msg-agent-badge">${this.agentLabel(agent)}</span>`
      : '';
    el.innerHTML = `${tag}<div class="msg-bubble">${this.simpleMarkdown(content)}</div>`;
    this.messagesEl.appendChild(el);
    const scroll = document.getElementById('chat-scroll');
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
  }

  agentLabel(agent) {
    return { subject_teacher: '📚 学科老师', mood_companion: '💗 心态陪伴', homeroom: '' }[agent] || agent;
  }

  simpleMarkdown(text) {
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  showTyping() {
    const el = document.createElement('div');
    el.className = 'msg msg-assistant';
    el.id = 'typing-indicator';
    el.innerHTML = '<div class="msg-bubble typing"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
    this.messagesEl.appendChild(el);
    const scroll = document.getElementById('chat-scroll');
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
  }

  hideTyping() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  autoGrow() {
    this.chatInput.style.height = 'auto';
    this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 180) + 'px';
  }

  newSession() {
    this.currentSessionId = null;
    this.messages = [];
    this.messagesEl.innerHTML = '';
    if (this.suggestionsEl) this.suggestionsEl.style.display = 'flex';
  }

  handleSuggestion(text) {
    if (this.suggestionsEl) this.suggestionsEl.style.display = 'none';
    this.chatInput.value = text;
    this.send();
  }

  async handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    this.addMessage('user', '[上传了图片]');
    this.showTyping();
    const form = new FormData();
    form.append('file', file);
    try {
      const resp = await fetch('/upload/image', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${this.token}` },
        body: form,
      });
      const data = await resp.json();
      this.hideTyping();
      if (data.auto_filled_stem) {
        this.chatInput.value = data.auto_filled_stem;
        this.chatInput.focus();
        this.addMessage('assistant',
          `识别为一道 ${data.auto_routed_to_subject || ''} 题：\n${data.auto_filled_stem}\n\n直接发送，我来讲解。`,
          'subject_teacher');
      }
    } catch (e) {
      this.hideTyping();
      this.addMessage('assistant', '图片处理出错，请重试。');
    }
    this.fileInput.value = '';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new PacerApp();
  window.app.init();
});
