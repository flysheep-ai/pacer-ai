// pacer-ai frontend — plain global functions, zero "this" issues.
var _token = localStorage.getItem('pacer_token') || null;
var _sid = localStorage.getItem('pacer_student_id') || null;
var _sessionId = null;
var _es = null;

// ─── init ──────────────────────────────────────────────────

function _initPacer() {
  if (_token) { showChat(); connectSSE(); }
  else { showLogin(); }
  _initTheme();
}

// ─── theme ────────────────────────────────────────────────

function _initTheme() {
  if (localStorage.getItem('pacer_theme') === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
}
function toggleTheme() {
  var is = document.documentElement.getAttribute('data-theme') === 'dark';
  document.documentElement.setAttribute('data-theme', is ? 'light' : 'dark');
  localStorage.setItem('pacer_theme', is ? 'light' : 'dark');
}

// ─── screen ───────────────────────────────────────────────

function showLogin() {
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('chat-screen').style.display = 'none';
  if (typeof fluidStart === 'function') fluidStart();
}
function showChat() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('chat-screen').style.display = 'flex';
  if (typeof fluidStop === 'function') fluidStop();
}

// ─── login / logout ───────────────────────────────────────

async function doLogin() {
  var sid = document.getElementById('login-student-id').value.trim();
  var pin = document.getElementById('login-pin').value.trim();
  if (!sid || !pin) return;
  try {
    var r = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ student_id: parseInt(sid), pin: pin }),
    });
    if (!r.ok) { alert('登录失败'); return; }
    var d = await r.json();
    _token = d.token; _sid = d.student_id;
    localStorage.setItem('pacer_token', _token);
    localStorage.setItem('pacer_student_id', _sid);
    showChat(); connectSSE(); loadName();
  } catch (e) { alert('连接失败'); }
}

function doLogout() {
  if (_es) _es.close();
  localStorage.removeItem('pacer_token');
  localStorage.removeItem('pacer_student_id');
  _token = null; _sid = null; _sessionId = null;
  document.getElementById('messages').innerHTML = '';
  showLogin();
}

// ─── profile ──────────────────────────────────────────────

async function loadName() {
  try {
    var r = await fetch('/profile/', { headers: { 'Authorization': 'Bearer ' + _token } });
    if (r.ok) {
      var p = await r.json();
      document.getElementById('header-name').textContent = (p.name || '同学') + ' · pacer';
    }
  } catch (e) {}
}

function showProfile() { alert('个人中心将在后续版本上线'); }

// ─── SSE ──────────────────────────────────────────────────

function connectSSE() {
  if (_es) _es.close();
  _es = new EventSource('/events/stream?token=' + encodeURIComponent(_token));
  _es.addEventListener('assistant_message', function (e) {
    var d = JSON.parse(e.data);
    addMsg('assistant', d.text, d.agent);
    hideTyping();
  });
  _es.addEventListener('ping', function () {});
  _es.onerror = function () { setTimeout(connectSSE, 3000); };
}

// ─── send ─────────────────────────────────────────────────

async function doSend() {
  var input = document.getElementById('chat-input');
  var text = input.value.trim();
  if (!text || !_token) return;
  input.value = ''; input.style.height = 'auto';

  var es = document.getElementById('empty-state');
  if (es) es.style.display = 'none';

  addMsg('user', text);
  showTyping();
  document.getElementById('send-btn').disabled = true;

  try {
    var r = await fetch('/message/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + _token },
      body: JSON.stringify({ text: text, session_id: _sessionId }),
    });
    var d = await r.json();
    _sessionId = d.session_id;
  } catch (e) {
    hideTyping();
    addMsg('assistant', '出错了，请稍后重试。');
  }
  document.getElementById('send-btn').disabled = false;
}

function sendPreset(text) {
  document.getElementById('chat-input').value = text;
  doSend();
}

function newChat() {
  _sessionId = null;
  document.getElementById('messages').innerHTML =
    '<div id="empty-state" class="empty-state">' +
    '<h1>新对话</h1><p>有什么想聊的？</p>' +
    '<div class="suggestions">' +
    '<button class="suggestion" onclick="sendPreset(\'帮我讲一道导数题\')">讲一道导数题</button>' +
    '<button class="suggestion" onclick="sendPreset(\'帮我制定今天的学习计划\')">今日学习计划</button>' +
    '<button class="suggestion" onclick="sendPreset(\'帮我分析一下这道错题\')">分析错题</button>' +
    '<button class="suggestion" onclick="sendPreset(\'最近有点焦虑，想聊聊\')">聊聊压力</button>' +
    '</div></div>';
}

// ─── messages ─────────────────────────────────────────────

function addMsg(role, content, agent) {
  if (!content) return;
  var div = document.createElement('div');
  div.className = 'msg msg-' + role;
  var tag = '';
  if (agent === 'subject_teacher') tag = '<span class="msg-agent-badge">学科老师</span>';
  if (agent === 'mood_companion') tag = '<span class="msg-agent-badge">心态陪伴</span>';
  div.innerHTML = tag + '<div class="msg-bubble">' + md(content) + '</div>';
  document.getElementById('messages').appendChild(div);
  var sc = document.getElementById('chat-scroll');
  if (sc) sc.scrollTop = sc.scrollHeight;
}

function md(t) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

function showTyping() {
  var d = document.createElement('div');
  d.className = 'msg msg-assistant'; d.id = 'typing';
  d.innerHTML = '<div class="msg-bubble typing"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
  document.getElementById('messages').appendChild(d);
  var sc = document.getElementById('chat-scroll');
  if (sc) sc.scrollTop = sc.scrollHeight;
}

function hideTyping() {
  var t = document.getElementById('typing');
  if (t) t.remove();
}

// ─── upload ───────────────────────────────────────────────

async function doUpload(input) {
  var file = input.files[0];
  if (!file) return;
  addMsg('user', '[上传了图片]');
  showTyping();
  var fd = new FormData();
  fd.append('file', file);
  try {
    var r = await fetch('/upload/image', {
      method: 'POST', headers: { 'Authorization': 'Bearer ' + _token }, body: fd,
    });
    var d = await r.json();
    hideTyping();
    if (d.auto_filled_stem) {
      document.getElementById('chat-input').value = d.auto_filled_stem;
      document.getElementById('chat-input').focus();
      addMsg('assistant', '识别为一道 ' + (d.auto_routed_to_subject || '') + ' 题：\n' + d.auto_filled_stem + '\n\n直接发送，我来讲解。', 'subject_teacher');
    }
  } catch (e) {
    hideTyping();
    addMsg('assistant', '图片处理出错，请重试。');
  }
  input.value = '';
}

document.addEventListener('DOMContentLoaded', _initPacer);
