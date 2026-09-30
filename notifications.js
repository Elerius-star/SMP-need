/* frontend/js/notifications.js
   ──────────────────────────────────────────────────────────
   Service worker registration, push notification permission,
   Notification API integration, badge API, WebSocket stream
   for real-time notification updates.
*/
(function () {
  const state = { ws: null, permission: null };

  async function requestPermission() {
    if (!('Notification' in window)) return 'unsupported';
    if (Notification.permission === 'granted') { state.permission = 'granted'; return 'granted'; }
    if (Notification.permission === 'denied') { state.permission = 'denied'; return 'denied'; }
    const result = await Notification.requestPermission();
    state.permission = result;
    return result;
  }

  async function showLocalNotification(title, body, url) {
    if (state.permission !== 'granted') return;
    try {
      const reg = await navigator.serviceWorker?.getRegistration();
      if (reg) {
        reg.showNotification(title, {
          body,
          icon: '/favicon.ico',
          badge: '/favicon.ico',
          data: { url: url || '/dashboard.html' },
        });
      } else {
        const n = new Notification(title, { body, icon: '/favicon.ico' });
        n.onclick = () => { window.focus(); if (url) location.href = url; };
      }
    } catch (e) { console.warn('Notification error', e); }
  }

  function updateBadge(count) {
    if ('setAppBadge' in navigator) {
      if (count > 0) navigator.setAppBadge(count).catch(() => {});
      else navigator.clearAppBadge?.().catch(() => {});
    }
    // Fallback: document title
    const base = document.title.replace(/^\(\d+\)\s*/, '');
    document.title = count > 0 ? `(${count}) ${base}` : base;
  }

  // ── WebSocket stream for real-time notifications ──────────
  function connectNotifWS() {
    const token = API.getToken();
    if (!token) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://127.0.0.1:8000/ws/notifications/?token=${token}`;
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.onmessage = (evt) => {
      let payload; try { payload = JSON.parse(evt.data); } catch { return; }
      const verb = ({
        like: 'liked your post', comment: 'commented on your post',
        follow: 'followed you', mention: 'mentioned you',
        repost: 'reposted your post', dm: 'sent you a message',
        reaction: 'reacted to your post',
      })[payload.type] || 'interacted with you';
      showLocalNotification('SMP-Need', `${payload.actor} ${verb}`,
        payload.post ? `dashboard.html#post-${payload.post}` : 'dashboard.html');
      // Update badge
      const badge = document.getElementById('notif-badge');
      const current = parseInt(badge?.textContent || '0', 10);
      updateBadge(current + 1);
      if (badge) badge.textContent = current + 1;
    };
    ws.onclose = () => {
      setTimeout(() => { if (API.getToken()) connectNotifWS(); }, 5000);
    };
  }

  // ── Service Worker registration ───────────────────────────
  async function registerSW() {
    if (!('serviceWorker' in navigator)) return;
    try {
      const reg = await navigator.serviceWorker.register('/sw.js');
      console.log('[SW] registered', reg.scope);
    } catch (e) {
      console.warn('[SW] registration failed', e);
    }
  }

  // ── Visibility change: refresh badge when tab focused ─────
  document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible' && API.getToken()) {
      try {
        const list = await API.get('/social/notifications/');
        const items = list.results || list;
        const unread = items.filter(n => !n.is_read).length;
        updateBadge(unread);
      } catch {}
    }
  });

  // ── Init ──────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    if (!API.getToken()) return;
    registerSW();
    connectNotifWS();
    requestPermission().then(p => console.log('[notif] permission:', p));
  });
})();