/* frontend/js/search.js
   ──────────────────────────────────────────────────────────
   Full search page: users, posts, hashtags, with filters.
*/
(function () {
  const state = { query: '', type: 'all', results: {} };

  function esc(s) {
    return (s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function render(results) {
    const host = document.getElementById('search-root');
    if (!host) return;
    const users = results.users || [];
    const posts = results.posts || [];
    const tags = results.tags || [];

    host.innerHTML = `
      <div class="tabs" style="display:flex;gap:8px;margin-bottom:16px">
        <button class="btn btn-ghost tab-btn ${state.type === 'all' ? 'active' : ''}" data-type="all">All</button>
        <button class="btn btn-ghost tab-btn ${state.type === 'users' ? 'active' : ''}" data-type="users">Users</button>
        <button class="btn btn-ghost tab-btn ${state.type === 'posts' ? 'active' : ''}" data-type="posts">Posts</button>
        <button class="btn btn-ghost tab-btn ${state.type === 'tags' ? 'active' : ''}" data-type="tags">Hashtags</button>
      </div>

      ${(state.type === 'all' || state.type === 'users') && users.length ? `
        <h4>Users</h4>
        <div class="card">
          ${users.map(u => `
            <div style="display:flex;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)">
              <div class="avatar sm"></div>
              <a href="profile.html?u=${esc(u.username)}" style="flex:1;color:var(--text)"><b>${esc(u.username)}</b></a>
              <button class="btn btn-ghost follow-btn" data-id="${u.id}">Follow</button>
            </div>`).join('')}
        </div>` : ''}

      ${(state.type === 'all' || state.type === 'posts') && posts.length ? `
        <h4>Posts</h4>
        ${posts.map(p => `
          <div class="post-card">
            <div class="post-head">
              <div class="avatar sm"></div>
              <div class="meta"><div class="name">${esc(p.author.username)}</div></div>
            </div>
            <div class="post-content">${esc(p.content)}</div>
            ${p.image ? `<img class="post-image lightbox-trigger" src="${p.image}" data-full="${p.image}" />` : ''}
          </div>`).join('')}` : ''}

      ${(state.type === 'all' || state.type === 'tags') && tags.length ? `
        <h4>Hashtags</h4>
        <div class="card">
          ${tags.map(t => `<div style="padding:8px 0"><a href="#" data-tag="${esc(t.name)}">#${esc(t.name)}</a> <span style="color:var(--muted);font-size:12px">${t.post_count} posts</span></div>`).join('')}
        </div>` : ''}

      ${!users.length && !posts.length && !tags.length ? '<div class="card" style="text-align:center;color:var(--muted);padding:40px">No results</div>' : ''}`;

    host.querySelectorAll('.tab-btn').forEach(b => b.onclick = () => {
      state.type = b.dataset.type;
      render(results);
    });
    host.querySelectorAll('.follow-btn').forEach(b => b.onclick = async () => {
      const r = await API.post(`/social/follow/${b.dataset.id}/`);
      b.textContent = r.following ? 'Following' : 'Follow';
    });
    host.querySelectorAll('.lightbox-trigger').forEach(img => img.onclick = () =>
      window.openLightbox?.(img.dataset.full));
    host.querySelectorAll('[data-tag]').forEach(a => a.onclick = (e) => {
      e.preventDefault();
      window.loadHashtag?.(a.dataset.tag);
      location.href = 'dashboard.html';
    });
  }

  async function performSearch(q) {
    state.query = q;
    const [users, posts, tags] = await Promise.all([
      API.get(`/auth/users/search/?q=${encodeURIComponent(q)}`).catch(() => []),
      API.get(`/posts/hashtag/${encodeURIComponent(q)}/`).catch(() => ({ results: [] })),
      API.get('/posts/trending/').catch(() => []),
    ]);
    render({
      users: users.results || users,
      posts: posts.results || posts,
      tags: (tags.results || tags).filter(t => t.name.includes(q.toLowerCase())),
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('page-search-input');
    let t;
    if (input) {
      input.oninput = (e) => {
        clearTimeout(t);
        t = setTimeout(() => performSearch(e.target.value.trim()), 300);
      };
      const q = new URLSearchParams(location.search).get('q');
      if (q) { input.value = q; performSearch(q); }
    }
  });

  window.SearchPage = { performSearch };
})();