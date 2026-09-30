/* frontend/js/dashboard.js
   ──────────────────────────────────────────────────────────
   Notifications polling, dark mode, drag-drop upload,
   emoji picker, mention autocomplete, keyboard shortcuts,
   settings panel, trending sidebar, suggested users.
*/
(function () {
  const me = API.getUser();
  if (!me) return;

  const state = { notifTimer: null, trendingTimer: null, settingsOpen: false };

  // ── Nav avatar ────────────────────────────────────────────
  const nav = document.getElementById('nav-avatar');
  if (nav && me.avatar) nav.style.backgroundImage = `url(${me.avatar})`;

  // ── Logout ────────────────────────────────────────────────
  document.getElementById('btn-logout')?.addEventListener('click', () => {
    API.clearTokens();
    location.href = 'index.html';
  });

  // ── Notifications polling ─────────────────────────────────
  async function pollNotifs() {
    try {
      const list = await API.get('/social/notifications/');
      const items = list.results || list;
      const unread = items.filter(n => !n.is_read).length;
      const badge = document.getElementById('notif-badge');
      if (badge) badge.textContent = unread;
      const box = document.getElementById('notif-list');
      if (box) box.innerHTML = items.length ? items.map(n => `
        <div class="notif-item ${n.is_read ? '' : 'unread'}" data-id="${n.id}">
          <div class="avatar sm"></div>
          <div><b>${n.actor.username}</b> ${notifVerb(n.type)}</div>
        </div>`).join('') : '<div style="color:var(--muted);padding:12px">No notifications</div>';
    } catch {}
  }
  function notifVerb(type) {
    return ({
      like: 'liked your post', comment: 'commented on your post',
      follow: 'followed you', mention: 'mentioned you',
      repost: 'reposted your post', dm: 'sent you a message',
      reaction: 'reacted to your post', follow_request: 'requested to follow you',
    })[type] || 'interacted with you';
  }
  pollNotifs();
  state.notifTimer = setInterval(pollNotifs, 30000);

  document.getElementById('btn-notif')?.addEventListener('click', () => {
    document.getElementById('notif-drawer')?.classList.toggle('hidden');
    API.post('/social/notifications/read/').then(pollNotifs);
  });
  document.getElementById('close-notif')?.addEventListener('click', () =>
    document.getElementById('notif-drawer')?.classList.add('hidden'));

  // ── Trending ──────────────────────────────────────────────
  async function loadTrending() {
    try {
      const list = await API.get('/posts/trending/');
      const el = document.getElementById('trending-list');
      if (!el) return;
      el.innerHTML = list.map(t =>
        `<li data-tag="${t.name}">#${t.name} <span style="color:var(--muted);font-size:12px">(${t.post_count})</span></li>`
      ).join('');
      el.onclick = (e) => {
        const li = e.target.closest('li');
        if (li) window.loadHashtag?.(li.dataset.tag);
      };
    } catch {}
  }
  loadTrending();
  state.trendingTimer = setInterval(loadTrending, 60000);

  // ── Search with debounce + dropdown ───────────────────────
  let searchTimer;
  document.getElementById('search-input')?.addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      const q = e.target.value.trim();
      let box = document.getElementById('search-results');
      if (!q) { box?.remove(); return; }
      try {
        const users = await API.get(`/auth/users/search/?q=${encodeURIComponent(q)}`);
        if (!box) {
          box = document.createElement('div');
          box.id = 'search-results';
          box.className = 'card';
          box.style.cssText = 'position:absolute;top:60px;width:400px;z-index:60;max-height:320px;overflow:auto';
          document.querySelector('.search').appendChild(box);
        }
        box.innerHTML = users.length ? users.map(u => `
          <div class="notif-item" data-user="${u.username}" style="cursor:pointer">
            <div class="avatar sm"></div>
            <b>${u.username}</b> ${u.is_verified ? '✔️' : ''}
          </div>`).join('') : '<div style="padding:8px;color:var(--muted)">No results</div>';
        box.onclick = (ev) => {
          const item = ev.target.closest('[data-user]');
          if (item) location.href = `profile.html?u=${item.dataset.user}`;
        };
      } catch {}
    }, 250);
  });

  // ── Chat panel toggle ─────────────────────────────────────
  document.getElementById('btn-chat')?.addEventListener('click', () => {
    document.getElementById('chat-panel')?.classList.toggle('hidden');
    window.ChatPanel?.refresh?.();
  });
  document.getElementById('close-chat')?.addEventListener('click', () =>
    document.getElementById('chat-panel')?.classList.add('hidden'));

  // ── Theme toggle ──────────────────────────────────────────
  document.getElementById('btn-theme')?.addEventListener('click', () => {
    document.body.classList.toggle('dark');
    localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
  });
  if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark');
  // Sync server-side preference if logged in
  if (me.theme_preference === 'dark') document.body.classList.add('dark');

  // ── Drag-drop upload onto composer ────────────────────────
  const composer = document.querySelector('.composer');
  if (composer) {
    ['dragenter', 'dragover'].forEach(evt =>
      composer.addEventListener(evt, (e) => {
        e.preventDefault();
        composer.style.borderColor = 'var(--orange)';
        composer.style.background = '#fff7ef';
      }));
    ['dragleave', 'drop'].forEach(evt =>
      composer.addEventListener(evt, (e) => {
        e.preventDefault();
        composer.style.borderColor = '';
        composer.style.background = '';
      }));
    composer.addEventListener('drop', (e) => {
      const file = e.dataTransfer.files?.[0];
      if (!file) return;
      const dt = new DataTransfer();
      dt.items.add(file);
      const input = document.getElementById('composer-image');
      if (input) {
        input.files = dt.files;
        input.dispatchEvent(new Event('change'));
      }
    });
  }

  // ── Emoji picker for composer ─────────────────────────────
  function attachEmojiPicker() {
    const composer = document.querySelector('.composer-actions');
    if (!composer || document.getElementById('emoji-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'emoji-btn';
    btn.className = 'btn btn-ghost';
    btn.textContent = '😊';
    composer.insertBefore(btn, composer.firstChild);
    btn.onclick = (e) => {
      e.stopPropagation();
      window.EmojiPicker?.open(btn, (emoji) => {
        const input = document.getElementById('composer-input');
        if (!input) return;
        input.value += emoji;
        input.focus();
      });
    };
  }
  attachEmojiPicker();

  // ── Mention autocomplete in composer ──────────────────────
  const composerInput = document.getElementById('composer-input');
  if (composerInput) {
    let mentionStart = -1;
    let mentionBox = null;

    composerInput.addEventListener('input', async (e) => {
      const value = composerInput.value;
      const pos = composerInput.selectionStart;
      const upto = value.slice(0, pos);
      const m = upto.match(/@(\w*)$/);
      if (!m) { closeMention(); return; }
      mentionStart = pos - m[0].length;
      const q = m[1];
      try {
        const users = await API.get(`/auth/users/search/?q=${encodeURIComponent(q)}`);
        if (!users.length) { closeMention(); return; }
        showMentionBox(users);
      } catch { closeMention(); }
    });

    composerInput.addEventListener('blur', () => setTimeout(closeMention, 200));

    function showMentionBox(users) {
      closeMention();
      mentionBox = document.createElement('div');
      mentionBox.className = 'mention-box';
      mentionBox.style.cssText = 'position:absolute;background:var(--white);border:1px solid var(--border);border-radius:10px;box-shadow:var(--shadow-lg);z-index:80;max-height:220px;overflow:auto;min-width:200px';
      const rect = composerInput.getBoundingClientRect();
      mentionBox.style.left = rect.left + 'px';
      mentionBox.style.top = (rect.bottom + 4) + 'px';
      mentionBox.innerHTML = users.slice(0, 6).map(u => `
        <div class="mention-item" data-username="${u.username}" style="padding:8px 12px;cursor:pointer">
          <b>@${u.username}</b>
        </div>`).join('');
      document.body.appendChild(mentionBox);
      mentionBox.querySelectorAll('.mention-item').forEach(item => {
        item.onmousedown = (ev) => {
          ev.preventDefault();
          const value = composerInput.value;
          const after = value.slice(composerInput.selectionStart);
          composerInput.value = value.slice(0, mentionStart) + '@' + item.dataset.username + ' ' + after;
          composerInput.focus();
          closeMention();
        };
      });
    }
    function closeMention() {
      if (mentionBox) { mentionBox.remove(); mentionBox = null; }
    }
  }

  // ── Profile mini card ─────────────────────────────────────
  const mini = document.getElementById('profile-mini');
  if (mini) {
    mini.innerHTML = `
      <div style="display:flex;gap:12px;align-items:center">
        <div class="avatar"></div>
        <div>
          <div style="font-weight:700">${me.username}</div>
          <div style="color:var(--muted);font-size:13px">${me.bio || 'No bio yet'}</div>
        </div>
      </div>
      <div style="display:flex;gap:16px;margin-top:14px;font-size:13px;color:var(--muted)">
        <div><b style="color:var(--text)">${me.posts_count || 0}</b> Posts</div>
        <div><b style="color:var(--text)">${me.followers_count || 0}</b> Followers</div>
        <div><b style="color:var(--text)">${me.following_count || 0}</b> Following</div>
      </div>`;
  }

  // ── Suggested users ───────────────────────────────────────
  API.get('/auth/users/search/?q=a').then(users => {
    const el = document.getElementById('suggested-users');
    if (!el) return;
    el.innerHTML = users.slice(0, 5).map(u => `
      <div style="display:flex;gap:10px;align-items:center;padding:8px 0">
        <div class="avatar sm"></div>
        <div style="flex:1"><b>${u.username}</b></div>
        <button class="btn btn-ghost follow-btn" data-id="${u.id}">Follow</button>
      </div>`).join('');
    el.querySelectorAll('.follow-btn').forEach(b => b.onclick = async () => {
      const r = await API.post(`/social/follow/${b.dataset.id}/`);
      b.textContent = r.following ? 'Following' : 'Follow';
    });
  }).catch(() => {});

  // ── Settings panel (opened from profile link or gear) ─────
  async function openSettings() {
    if (state.settingsOpen) return;
    state.settingsOpen = true;
    let settings = {};
    try { settings = await API.get('/auth/me/settings/'); } catch {}
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'settings-modal';
    modal.innerHTML = `
      <div class="modal-body">
        <h3>Settings</h3>
        <label style="display:block;margin:8px 0"><input type="checkbox" id="set-email" ${settings.email_notifications ? 'checked' : ''} /> Email notifications</label>
        <label style="display:block;margin:8px 0"><input type="checkbox" id="set-push" ${settings.push_notifications ? 'checked' : ''} /> Push notifications</label>
        <label style="display:block;margin:8px 0"><input type="checkbox" id="set-online" ${settings.show_online_status ? 'checked' : ''} /> Show online status</label>
        <label style="display:block;margin:8px 0"><input type="checkbox" id="set-autoplay" ${settings.autoplay_videos ? 'checked' : ''} /> Autoplay videos</label>
        <label style="display:block;margin:8px 0"><input type="checkbox" id="set-filter" ${settings.sensitive_content_filter ? 'checked' : ''} /> Sensitive content filter</label>
        <div class="field"><label>Allow DMs from</label>
          <select id="set-dm">
            <option value="everyone" ${settings.allow_dm_from === 'everyone' ? 'selected' : ''}>Everyone</option>
            <option value="followers" ${settings.allow_dm_from === 'followers' ? 'selected' : ''}>Followers</option>
            <option value="none" ${settings.allow_dm_from === 'none' ? 'selected' : ''}>Nobody</option>
          </select>
        </div>
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="btn btn-primary" id="save-settings">Save</button>
          <button class="btn btn-ghost" id="close-settings">Cancel</button>
        </div>
        <div style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px">
          <button class="btn btn-ghost" id="deactivate-account">Deactivate account</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#close-settings').onclick = () => { modal.remove(); state.settingsOpen = false; };
    modal.querySelector('#save-settings').onclick = async () => {
      await API.patch('/auth/me/settings/', {
        email_notifications: modal.querySelector('#set-email').checked,
        push_notifications: modal.querySelector('#set-push').checked,
        show_online_status: modal.querySelector('#set-online').checked,
        autoplay_videos: modal.querySelector('#set-autoplay').checked,
        sensitive_content_filter: modal.querySelector('#set-filter').checked,
        allow_dm_from: modal.querySelector('#set-dm').value,
      });
      toast?.('Settings saved', 'success');
      modal.remove();
      state.settingsOpen = false;
    };
    modal.querySelector('#deactivate-account').onclick = async () => {
      if (!confirm('Deactivate your account? You can reactivate by logging in again.')) return;
      await API.post('/auth/me/deactivate/');
      API.clearTokens();
      location.href = 'index.html';
    };
  }
  window.openSettings = openSettings;
  if (location.hash === '#settings') openSettings();

  // ── Keyboard shortcuts ────────────────────────────────────
  document.addEventListener('keydown', (e) => {
    const inField = e.target.matches('input, textarea, select');
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal').forEach(m => m.remove());
      document.getElementById('notif-drawer')?.classList.add('hidden');
      state.settingsOpen = false;
    }
    if (e.ctrlKey && e.key === 'n') { e.preventDefault(); composerInput?.focus(); }
    if (e.key === '?' && !inField) {
      alert('Shortcuts:\nCtrl+N: New post\n/: Search\nj/k: Next/prev post\nl: Like\nEsc: Close modals');
    }
    if (e.key === '/' && !inField) {
      e.preventDefault();
      document.getElementById('search-input')?.focus();
    }
  });

  // ── Cleanup on unload ─────────────────────────────────────
  window.addEventListener('beforeunload', () => {
    clearInterval(state.notifTimer);
    clearInterval(state.trendingTimer);
  });
})();