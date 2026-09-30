/* frontend/js/profile.js
   ──────────────────────────────────────────────────────────
   Profile page: header, tabs (posts/likes/media), edit modal,
   avatar upload, follower/following lists, follow toggle,
   block/mute/report menu.
*/
(function () {
  const params = new URLSearchParams(location.search);
  const username = params.get('u') || (API.getUser() || {}).username;
  if (!username) { location.href = 'index.html'; return; }

  const state = { user: null, tab: 'posts', isOwn: false };

  function esc(s) {
    return (s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function avatar(u, cls = '') {
    if (u.avatar) return `<img class="avatar ${cls}" src="${u.avatar}" alt="${esc(u.username)}" />`;
    const colors = ['#ff7a1a', '#1fa463', '#3b82f6', '#8b5cf6', '#e11d48'];
    const c = colors[(u.id || 0) % colors.length];
    return `<div class="avatar ${cls}" style="background:${c};display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">${(u.username || '?')[0].toUpperCase()}</div>`;
  }

  function timeAgo(iso) {
    const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 60) return `${Math.floor(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    if (s < 604800) return `${Math.floor(s / 86400)}d`;
    return new Date(iso).toLocaleDateString();
  }

  async function load() {
    try {
      state.user = await API.get(`/auth/users/${username}/`);
    } catch {
      document.getElementById('profile-header').innerHTML =
        '<div style="text-align:center;padding:24px;color:var(--muted)">User not found</div>';
      return;
    }
    const me = API.getUser();
    state.isOwn = me && me.id === state.user.id;
    renderHeader();
    loadTab('posts');
  }

  function renderHeader() {
    const u = state.user;
    const me = API.getUser();
    const isFollowing = u.is_following;
    const followLabel = isFollowing ? 'Following' : (u.is_private ? 'Request' : 'Follow');
    document.getElementById('profile-header').innerHTML = `
      <div class="profile-banner" style="height:160px;background:linear-gradient(135deg,#ff7a1a33,#1fa46333);border-radius:14px 14px 0 0;${u.banner ? `background-image:url(${u.banner});background-size:cover` : ''}"></div>
      <div style="display:flex;gap:18px;align-items:center;padding:0 20px;margin-top:-40px">
        ${avatar(u, 'lg')}
        <div style="flex:1;padding-top:40px">
          <h2 style="display:flex;gap:8px;align-items:center">${esc(u.username)} ${u.is_verified ? '<span class="verified">✔️</span>' : ''}</h2>
          <div style="color:var(--muted);font-size:14px">@${esc(u.username)}</div>
        </div>
        <div style="padding-top:40px;display:flex;gap:8px">
          ${state.isOwn
            ? `<button class="btn btn-ghost" id="edit-btn">Edit Profile</button>
               <button class="btn btn-ghost" id="settings-btn">⚙️</button>`
            : `<button class="btn ${isFollowing ? 'btn-ghost' : 'btn-primary'}" id="follow-btn">${followLabel}</button>
               <button class="btn btn-ghost" id="more-btn">⋯</button>`}
        </div>
      </div>
      <div style="padding:16px 20px">
        <p style="margin:8px 0">${esc(u.bio || '')}</p>
        <div style="display:flex;gap:16px;color:var(--muted);font-size:14px">
          ${u.location ? `<span>📍 ${esc(u.location)}</span>` : ''}
          ${u.website ? `<a href="${esc(u.website)}" target="_blank">🔗 ${esc(u.website)}</a>` : ''}
          <span>📅 Joined ${new Date(u.date_joined).toLocaleDateString()}</span>
        </div>
        <div style="display:flex;gap:20px;margin-top:12px;font-size:14px">
          <span><b>${u.posts_count}</b> <span style="color:var(--muted)">Posts</span></span>
          <span id="followers-link" style="cursor:pointer"><b>${u.followers_count}</b> <span style="color:var(--muted)">Followers</span></span>
          <span id="following-link" style="cursor:pointer"><b>${u.following_count}</b> <span style="color:var(--muted)">Following</span></span>
        </div>
      </div>`;

    const followBtn = document.getElementById('follow-btn');
    if (followBtn) followBtn.onclick = toggleFollow;
    const moreBtn = document.getElementById('more-btn');
    if (moreBtn) moreBtn.onclick = showMoreMenu;
    const editBtn = document.getElementById('edit-btn');
    if (editBtn) editBtn.onclick = openEditModal;
    const settingsBtn = document.getElementById('settings-btn');
    if (settingsBtn) settingsBtn.onclick = () => location.href = 'dashboard.html#settings';
    document.getElementById('followers-link').onclick = () => showUsersModal('followers');
    document.getElementById('following-link').onclick = () => showUsersModal('following');

    document.querySelectorAll('.tab-btn').forEach(b => b.onclick = () => {
      document.querySelectorAll('.tab-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      loadTab(b.dataset.tab);
    });
  }

  async function toggleFollow() {
    if (!API.getUser()) { location.href = 'index.html'; return; }
    const r = await API.post(`/social/follow/${state.user.id}/`);
    await load();
    if (r.following) toast?.('Following', 'success');
    else if (r.requested) toast?.('Request sent', 'success');
    else toast?.('Unfollowed');
  }

  function showMoreMenu() {
    const menu = document.createElement('div');
    menu.className = 'modal';
    menu.innerHTML = `
      <div class="modal-body" style="max-width:280px">
        <button class="menu-item" data-act="block">${state.user.is_blocked ? 'Unblock' : 'Block'}</button>
        <button class="menu-item" data-act="mute">${state.user.is_muted ? 'Unmute' : 'Mute'}</button>
        <button class="menu-item" data-act="report">Report</button>
        <button class="menu-item" data-act="copy">Copy profile link</button>
        <button class="btn btn-ghost" style="width:100%;margin-top:8px">Cancel</button>
      </div>`;
    document.body.appendChild(menu);
    menu.querySelector('.btn-ghost').onclick = () => menu.remove();
    menu.querySelectorAll('.menu-item').forEach(b => b.onclick = async () => {
      const act = b.dataset.act;
      if (act === 'block') await API.post(`/auth/users/${state.user.id}/block/`);
      else if (act === 'mute') await API.post(`/auth/users/${state.user.id}/mute/`);
      else if (act === 'report') {
        const reason = prompt('Reason (spam/abuse/nudity/misinformation/other):', 'spam');
        if (reason) await API.post('/social/report/', { user_reported: state.user.id, reason });
      } else if (act === 'copy') {
        navigator.clipboard?.writeText(location.href);
        toast?.('Link copied', 'success');
      }
      menu.remove();
      load();
    });
  }

  async function loadTab(tab) {
    state.tab = tab;
    const box = document.getElementById('profile-posts');
    box.innerHTML = '<div class="skeleton-card"></div><div class="skeleton-card"></div>';
    try {
      let url;
      if (tab === 'posts') url = `/posts/user/${username}/`;
      else if (tab === 'likes') url = `/posts/user/${username}/likes/`;
      else if (tab === 'media') url = `/posts/user/${username}/media/`;
      const data = await API.get(url);
      const list = data.results || data;
      if (!list.length) {
        box.innerHTML = `<div class="card" style="text-align:center;color:var(--muted);padding:40px">No ${tab} yet</div>`;
        return;
      }
      box.innerHTML = list.map(p => `
        <div class="post-card">
          <div class="post-head">
            ${avatar(p.author, 'sm')}
            <div class="meta">
              <div class="name">${esc(p.author.username)}</div>
              <div class="time">${timeAgo(p.created_at)}</div>
            </div>
          </div>
          ${p.content ? `<div class="post-content">${esc(p.content)}</div>` : ''}
          ${p.image ? `<img class="post-image lightbox-trigger" src="${p.image}" data-full="${p.image}" />` : ''}
          ${p.video ? `<video class="post-video" controls src="${p.video}"></video>` : ''}
          <div class="post-actions">
            <span>❤️ ${p.likes_count}</span>
            <span>💬 ${p.comments_count}</span>
            <span>🔁 ${p.reposts_count}</span>
          </div>
        </div>`).join('');
      box.querySelectorAll('.lightbox-trigger').forEach(img => img.onclick = () =>
        window.openLightbox?.(img.dataset.full));
    } catch {
      box.innerHTML = '<div class="card" style="color:var(--danger)">Failed to load</div>';
    }
  }

  async function showUsersModal(kind) {
    const data = await API.get(`/social/${kind}/${username}/`);
    const list = data.results || data;
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
      <div class="modal-body">
        <h3>${kind === 'followers' ? 'Followers' : 'Following'}</h3>
        <div style="max-height:400px;overflow-y:auto">
          ${list.length ? list.map(u => `
            <div class="user-row" data-id="${u.id}">
              ${avatar(u, 'sm')}
              <div style="flex:1"><b>${esc(u.username)}</b> ${u.is_verified ? '✔️' : ''}</div>
              <a class="btn btn-ghost" href="profile.html?u=${esc(u.username)}">View</a>
            </div>`).join('') : '<div style="text-align:center;color:var(--muted);padding:20px">Nobody yet</div>'}
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" style="width:100%">Close</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector('.btn-ghost').onclick = () => modal.remove();
  }

  function openEditModal() {
    const u = state.user;
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'edit-profile-modal';
    modal.innerHTML = `
      <div class="modal-body">
        <h3>Edit Profile</h3>
        <div class="field"><label>Bio</label><textarea id="edit-bio" maxlength="280">${esc(u.bio || '')}</textarea></div>
        <div class="field"><label>Location</label><input id="edit-location" value="${esc(u.location || '')}" /></div>
        <div class="field"><label>Website</label><input id="edit-website" value="${esc(u.website || '')}" /></div>
        <div class="field"><label>Birth date</label><input type="date" id="edit-birth" value="${u.birth_date || ''}" /></div>
        <div class="field"><label>Avatar</label><input type="file" id="edit-avatar" accept="image/*" /></div>
        <div class="field"><label>Banner</label><input type="file" id="edit-banner" accept="image/*" /></div>
        <label style="display:block;margin:8px 0"><input type="checkbox" id="edit-private" ${u.is_private ? 'checked' : ''} /> Private account</label>
        <div class="modal-actions">
          <button class="btn btn-primary" id="save-profile">Save</button>
          <button class="btn btn-ghost" id="cancel-edit">Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector('#cancel-edit').onclick = () => modal.remove();
    modal.querySelector('#save-profile').onclick = async () => {
      try {
        const payload = {
          bio: modal.querySelector('#edit-bio').value,
          location: modal.querySelector('#edit-location').value,
          website: modal.querySelector('#edit-website').value,
          birth_date: modal.querySelector('#edit-birth').value || null,
          is_private: modal.querySelector('#edit-private').checked,
        };
        await API.patch('/auth/me/update/', payload);

        const avatarFile = modal.querySelector('#edit-avatar').files[0];
        if (avatarFile) {
          const fd = new FormData();
          fd.append('avatar', avatarFile);
          await API.upload('/auth/me/avatar/', fd);
        }
        const bannerFile = modal.querySelector('#edit-banner').files[0];
        if (bannerFile) {
          const fd = new FormData();
          fd.append('banner', bannerFile);
          await API.upload('/auth/me/banner/', fd);
        }
        toast?.('Profile updated', 'success');
        modal.remove();
        const fresh = await API.get('/auth/me/');
        localStorage.setItem('user', JSON.stringify(fresh));
        await load();
      } catch (e) {
        toast?.('Update failed', 'error');
      }
    };
  }

  // Tabs listeners wired after header render inside renderHeader.
  document.addEventListener('DOMContentLoaded', load);
})();