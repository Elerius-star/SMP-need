/* frontend/js/chat.js
   ──────────────────────────────────────────────────────────
   WebSocket-based chat with typing indicators, read receipts,
   media messages, conversation list.
*/
(function () {
  const state = {
    ws: null,
    convId: null,
    conversations: [],
    typingTimeout: null,
    reconnectTimer: null,
  };

  const els = {
    panel: () => document.getElementById('chat-panel'),
    messages: () => document.getElementById('chat-messages'),
    input: () => document.getElementById('chat-input'),
    send: () => document.getElementById('send-chat'),
  };

  function esc(s) {
    return (s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  // ── Conversation list ─────────────────────────────────────
  async function loadConversations() {
    try {
      const list = await API.get('/social/conversations/');
      state.conversations = list.results || list;
      renderConversationList();
    } catch {}
  }

  function renderConversationList() {
    const panel = els.panel();
    if (!panel) return;
    let listEl = panel.querySelector('#conv-list');
    if (!listEl) {
      listEl = document.createElement('div');
      listEl.id = 'conv-list';
      listEl.style.cssText = 'max-height:180px;overflow-y:auto;border-bottom:1px solid var(--border)';
      panel.insertBefore(listEl, panel.querySelector('#chat-messages'));
    }
    listEl.innerHTML = state.conversations.map(c => `
      <div class="conv-item ${c.id === state.convId ? 'active' : ''}" data-id="${c.id}" style="padding:10px 12px;cursor:pointer;border-bottom:1px solid var(--border)">
        <b>${c.is_group ? esc(c.name || 'Group') : esc(c.participants.map(p => p.username).join(', '))}</b>
        <div style="font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          ${c.last_message ? esc(c.last_message.content || '📎 attachment') : 'No messages'}
        </div>
      </div>`).join('');
    listEl.onclick = (e) => {
      const item = e.target.closest('.conv-item');
      if (item) openConversation(parseInt(item.dataset.id, 10));
    };
  }

  async function openConversation(id) {
    state.convId = id;
    renderConversationList();
    await loadMessages(id);
    connectWS(id);
  }

  async function loadMessages(id) {
    try {
      const list = await API.get(`/social/conversations/${id}/messages/`);
      const msgs = list.results || list;
      const me = API.getUser() || {};
      const box = els.messages();
      if (!box) return;
      box.innerHTML = msgs.map(m => renderMessage(m, me)).join('');
      box.scrollTop = box.scrollHeight;
    } catch {}
  }

  function renderMessage(m, me) {
    const mine = m.sender.id === me.id;
    return `
      <div class="chat-bubble ${mine ? 'mine' : 'theirs'}" data-id="${m.id}">
        ${!mine ? `<div style="font-size:12px;font-weight:700">${esc(m.sender.username)}</div>` : ''}
        ${m.content ? `<div>${esc(m.content)}</div>` : ''}
        ${m.image ? `<img src="${m.image}" style="max-width:100%;border-radius:8px;margin-top:4px" />` : ''}
        ${m.file ? `<a href="${m.file}" target="_blank">📎 Download</a>` : ''}
        <div style="font-size:10px;opacity:.7;margin-top:2px">${m.is_read ? '✓✓' : '✓'}</div>
      </div>`;
  }

  // ── WebSocket ─────────────────────────────────────────────
  function connectWS(convId) {
    if (state.ws) { try { state.ws.close(); } catch {} }
    const token = API.getToken();
    if (!token) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://127.0.0.1:8000/ws/chat/${convId}/?token=${token}`;
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.onopen = () => console.log('[chat] open', convId);
    ws.onmessage = (evt) => {
      let msg; try { msg = JSON.parse(evt.data); } catch { return; }
      handleIncoming(msg);
    };
    ws.onclose = () => {
      console.log('[chat] closed, reconnecting in 3s');
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = setTimeout(() => state.convId && connectWS(state.convId), 3000);
    };
  }

  function handleIncoming(msg) {
    const me = API.getUser() || {};
    const box = els.messages();
    if (!box) return;

    if (msg.type === 'message') {
      const html = `
        <div class="chat-bubble ${msg.sender_id === me.id ? 'mine' : 'theirs'}">
          ${msg.sender_id !== me.id ? `<div style="font-size:12px;font-weight:700">${esc(msg.sender)}</div>` : ''}
          <div>${esc(msg.content)}</div>
        </div>`;
      box.insertAdjacentHTML('beforeend', html);
      box.scrollTop = box.scrollHeight;
      send({ type: 'read' });
    } else if (msg.type === 'typing') {
      let ind = box.querySelector('.typing-indicator');
      if (!ind) {
        ind = document.createElement('div');
        ind.className = 'typing-indicator';
        ind.style.cssText = 'font-size:12px;color:var(--muted);padding:4px 0';
        box.appendChild(ind);
      }
      ind.textContent = `${msg.username} is typing…`;
      clearTimeout(state.typingTimeout);
      state.typingTimeout = setTimeout(() => ind.remove(), 2500);
      box.scrollTop = box.scrollHeight;
    } else if (msg.type === 'read') {
      box.querySelectorAll('.chat-bubble.mine div:last-child').forEach(el => el.textContent = '✓✓');
    } else if (msg.type === 'presence') {
      toast?.(`${msg.username} ${msg.event === 'join' ? 'joined' : 'left'}`, 'info');
    }
  }

  function send(payload) {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify(payload));
  }

  function sendMessage() {
    const input = els.input();
    if (!input) return;
    const content = input.value.trim();
    if (!content) return;
    send({ type: 'message', content });
    input.value = '';
  }

  function sendTyping() {
    send({ type: 'typing' });
  }

  // ── UI wiring ─────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    els.send()?.addEventListener('click', sendMessage);
    els.input()?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    els.input()?.addEventListener('input', () => {
      clearTimeout(state.typingTimeout);
      sendTyping();
    });
    document.getElementById('btn-chat')?.addEventListener('click', loadConversations);

    // Media message upload
    const chatInputWrap = document.querySelector('.chat-input');
    if (chatInputWrap && !document.getElementById('chat-media')) {
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.id = 'chat-media';
      fileInput.hidden = true;
      chatInputWrap.appendChild(fileInput);
      const attachBtn = document.createElement('button');
      attachBtn.className = 'btn btn-ghost';
      attachBtn.textContent = '📎';
      chatInputWrap.insertBefore(attachBtn, els.input());
      attachBtn.onclick = () => fileInput.click();
      fileInput.onchange = async () => {
        if (!state.convId || !fileInput.files[0]) return;
        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        await API.upload(`/social/conversations/${state.convId}/media/`, fd);
        loadMessages(state.convId);
      };
    }
  });

  window.ChatPanel = { refresh: loadConversations, openConversation };
})();