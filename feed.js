/* frontend/js/feed.js
   ────────────────────────────────────────────────────────────
   Infinite scroll · lightbox · share · delete · edit ·
   save/bookmark · video posts · poll posts · quote posts ·
   emoji reactions · post analytics · hashtag & mention linking
*/
(function () {
  const state = { page: 1, loading: false, hasMore: true, posts: [], visible: [] };
  const DEFAULT_AVATAR_COLORS = ['#ff7a1a', '#1fa463', '#3b82f6', '#8b5cf6', '#e11d48'];

  function toast(msg, type = 'info') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.background = type === 'error' ? '#e11d48' : type === 'success' ? '#1fa463' : '#1c1e21';
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2400);
  }
  window.toast = toast;

  function timeAgo(iso) {
    const d = new Date(iso), s = (Date.now() - d) / 1000;
    if (s < 60) return `${Math.floor(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    if (s < 604800) return `${Math.floor(s / 86400)}d`;
    return d.toLocaleDateString();
  }

  function esc(str) {
    return (str || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function linkify(text) {
    return esc(text)
      .replace(/#(\w+)/g, '<a href="#" data-tag="$1" class="hashtag-link">#$1</a>')
      .replace(/@(\w+)/g, '<a href="#" data-user="$1" class="mention-link">@$1</a>')
      .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  }

  function avatarHtml(user, size = 'sm') {
    if (user.avatar) return `<img class="avatar ${size}" src="${user.avatar}" alt="${esc(user.username)}" />`;
    const color = DEFAULT_AVATAR_COLORS[(user.id || 0) % DEFAULT_AVATAR_COLORS.length];
    return `<div class="avatar ${size}" style="background:${color};display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">${(user.username || '?')[0].toUpperCase()}</div>`;
  }

  function renderPoll(poll) {
    if (!poll) return '';
    const total = poll.total_votes || 0;
    const opts = (poll.options || []).map(o => {
      const pct = total ? Math.round((o.votes_count / total) * 100) : 0;
      return `
        <div class="poll-option" data-option-id="${o.id}">
          <div class="poll-bar" style="width:${pct}%"></div>
          <div class="poll-text"><span>${esc(o.text)}</span><span>${pct}%</span></div>
        </div>`;
    }).join('');
    return `
      <div class="poll" data-poll-id="${poll.id}">
        <div class="poll-question">${esc(poll.question)}</div>
        ${opts}
        <div class="poll-footer">${total} votes · ${poll.is_open ? 'Open' : 'Closed'}</div>
      </div>`;
  }

  function renderPost(p) {
    const me = API.getUser() || {};
    const isOwner = p.author.id === me.id;
    return `
      <div class="post-card" data-id="${p.id}" data-liked="${p.is_liked}" data-bookmarked="${p.is_bookmarked}">
        <div class="post-head">
          <a href="profile.html?u=${esc(p.author.username)}">${avatarHtml(p.author, 'sm')}</a>
          <div class="meta">
            <div class="name"><a href="profile.html?u=${esc(p.author.username)}">${esc(p.author.username)}</a> ${p.author.is_verified ? '<span class="verified">✔️</span>' : ''}</div>
            <div class="time">${timeAgo(p.created_at)} · 🌍 ${p.is_edited ? '· edited' : ''}</div>
          </div>
          <div class="post-menu">
            <button class="icon-btn menu-trigger" data-id="${p.id}">⋯</button>
            <div class="dropdown hidden" data-id="${p.id}">
              ${isOwner ? `<button class="menu-item edit-post" data-id="${p.id}">✏️ Edit</button>
              <button class="menu-item pin-post" data-id="${p.id}">📌 Pin</button>
              <button class="menu-item del-post" data-id="${p.id}">🗑 Delete</button>
              <button class="menu-item analytics-post" data-id="${p.id}">📊 Analytics</button>` : ''}
              <button class="menu-item report-post" data-id="${p.id}">🚩 Report</button>
              <button class="menu-item copy-link" data-id="${p.id}">🔗 Copy link</button>
            </div>
          </div>
        </div>
        ${p.is_repost ? `<div class="repost-label">🔁 Reposted from @${esc(p.original?.author?.username || 'unknown')}</div>` : ''}
        ${p.content ? `<div class="post-content">${linkify(p.content)}</div>` : ''}
        ${p.is_quote && p.original ? `
          <div class="quote-block">
            <div><b>@${esc(p.original.author.username)}</b></div>
            <div>${linkify(p.original.content)}</div>
          </div>` : ''}
        ${p.image ? `<img class="post-image lightbox-trigger" src="${p.image}" loading="lazy" data-full="${p.image}" />` : ''}
        ${p.video ? `<video class="post-video" controls src="${p.video}"></video>` : ''}
        ${p.poll ? renderPoll(p.poll) : ''}
        <div class="reactions-row" data-id="${p.id}">
          ${['👍','❤️','😂','😮','😢','😡'].map(k => `<button class="reaction-btn" data-id="${p.id}" data-kind="${k}">${k}</button>`).join('')}
        </div>
        <div class="post-actions">
          <button class="like-btn ${p.is_liked ? 'liked' : ''}" data-id="${p.id}">
            ${p.is_liked ? '❤️' : '🤍'} <span class="like-count">${p.likes_count}</span>
          </button>
          <button class="comment-btn" data-id="${p.id}">💬 <span>${p.comments_count}</span></button>
          <button class="repost-btn" data-id="${p.id}">🔁 <span>${p.reposts_count}</span></button>
          <button class="quote-btn" data-id="${p.id}">✍️ Quote</button>
          <button class="share-btn" data-id="${p.id}">🔗 Share</button>
          <button class="bookmark-btn ${p.is_bookmarked ? 'bookmarked' : ''}" data-id="${p.id}">
            ${p.is_bookmarked ? '🔖' : '📑'}
          </button>
        </div>
        <div class="comments-section hidden" data-id="${p.id}"></div>
      </div>`;
  }

  async function loadFeed(reset = false) {
    if (state.loading) return;
    if (!state.hasMore && !reset) return;
    state.loading = true;
    if (reset) { state.page = 1; state.posts = []; document.getElementById('feed-list').innerHTML = ''; }
    document.getElementById('feed-loader').classList.remove('hidden');
    try {
      const data = await API.get(`/posts/feed/?page=${state.page}`);
      const list = data.results || data;
      if (!list.length) state.hasMore = false;
      state.posts.push(...list);
      document.getElementById('feed-list').insertAdjacentHTML('beforeend', list.map(renderPost).join(''));
      state.page += 1;
    } catch (e) {
      toast('Failed to load feed', 'error');
    } finally {
      state.loading = false;
      document.getElementById('feed-loader').classList.add('hidden');
    }
  }
  window.loadFeed = loadFeed;

  // ─── Delegated clicks ─────────────────────────────────────
  document.getElementById('feed-list').addEventListener('click', async (e) => {
    const target = e.target;

    // Menu toggle
    const menuTrigger = target.closest('.menu-trigger');
    if (menuTrigger) {
      const id = menuTrigger.dataset.id;
      document.querySelectorAll('.dropdown').forEach(d => d.classList.add('hidden'));
      const dd = document.querySelector(`.dropdown[data-id="${id}"]`);
      if (dd) dd.classList.toggle('hidden');
      e.stopPropagation();
      return;
    }

    // Menu items
    const editItem = target.closest('.edit-post');
    if (editItem) { editPost(editItem.dataset.id); return; }
    const pinItem = target.closest('.pin-post');
    if (pinItem) { await API.post(`/posts/${pinItem.dataset.id}/pin/`); toast('Pinned', 'success'); return; }
    const delItem = target.closest('.del-post');
    if (delItem) {
      if (confirm('Delete this post?')) {
        await API.del(`/posts/${delItem.dataset.id}/`);
        document.querySelector(`.post-card[data-id="${delItem.dataset.id}"]`).remove();
        toast('Deleted', 'success');
      }
      return;
    }
    const anaItem = target.closest('.analytics-post');
    if (anaItem) {
      const data = await API.get(`/posts/${anaItem.dataset.id}/analytics/`);
      alert(`Impressions: ${data.impressions}\nViews: ${data.views}\nLikes: ${data.likes}\nComments: ${data.comments}\nReposts: ${data.reposts}`);
      return;
    }
    const repItem = target.closest('.report-post');
    if (repItem) {
      const reason = prompt('Report reason (spam/abuse/nudity/misinformation/other):', 'spam');
      if (reason) {
        await API.post('/social/report/', { post: repItem.dataset.id, reason });
        toast('Reported', 'success');
      }
      return;
    }
    const copyItem = target.closest('.copy-link');
    if (copyItem) {
      navigator.clipboard?.writeText(`${location.origin}/post.html?id=${copyItem.dataset.id}`);
      toast('Link copied', 'success');
      return;
    }

    // Like
    const likeBtn = target.closest('.like-btn');
    if (likeBtn) {
      const id = likeBtn.dataset.id;
      const r = await API.post(`/posts/${id}/like/`);
      likeBtn.classList.toggle('liked', r.liked);
      likeBtn.querySelector('.like-count').textContent = r.count;
      likeBtn.firstChild.textContent = r.liked ? '❤️ ' : '🤍 ';
      return;
    }

    // Bookmark
    const bmBtn = target.closest('.bookmark-btn');
    if (bmBtn) {
      const r = await API.post(`/posts/${bmBtn.dataset.id}/bookmark/`);
      bmBtn.classList.toggle('bookmarked', r.bookmarked);
      bmBtn.textContent = r.bookmarked ? '🔖' : '📑';
      return;
    }

    // Repost
    const rpBtn = target.closest('.repost-btn');
    if (rpBtn) {
      await API.post(`/posts/${rpBtn.dataset.id}/repost/`);
      toast('Reposted', 'success');
      loadFeed(true);
      return;
    }

    // Quote
    const qBtn = target.closest('.quote-btn');
    if (qBtn) {
      const quote = prompt('Add a quote comment:');
      if (quote !== null) {
        await API.post(`/posts/${qBtn.dataset.id}/quote/`, { content: quote });
        toast('Quote posted', 'success');
        loadFeed(true);
      }
      return;
    }

    // Share
    const sBtn = target.closest('.share-btn');
    if (sBtn) {
      const url = `${location.origin}/post.html?id=${sBtn.dataset.id}`;
      if (navigator.share) {
        try { await navigator.share({ url }); } catch {}
      } else {
        navigator.clipboard?.writeText(url);
        toast('Link copied', 'success');
      }
      return;
    }

    // Lightbox
    const lbTrigger = target.closest('.lightbox-trigger');
    if (lbTrigger) {
      window.openLightbox?.(lbTrigger.dataset.full || lbTrigger.src);
      return;
    }

    // Comment toggle
    const cBtn = target.closest('.comment-btn');
    if (cBtn) {
      const id = cBtn.dataset.id;
      const box = document.querySelector(`.comments-section[data-id="${id}"]`);
      box.classList.toggle('hidden');
      if (!box.dataset.loaded) {
        await loadComments(id, box);
        box.dataset.loaded = '1';
      }
      return;
    }

    // Emoji reaction
    const rxn = target.closest('.reaction-btn');
    if (rxn) {
      await API.post(`/social/react/${rxn.dataset.id}/`, { kind: rxn.dataset.kind });
      toast('Reacted ' + rxn.dataset.kind, 'success');
      return;
    }

    // Poll vote
    const pollOpt = target.closest('.poll-option');
    if (pollOpt) {
      const poll = pollOpt.closest('.poll');
      const r = await API.post(`/posts/polls/${poll.dataset.pollId}/vote/`,
                                { option_id: pollOpt.dataset.optionId });
      // Rerender
      const card = poll.closest('.post-card');
      card.querySelector('.poll').outerHTML = renderPoll(r);
      return;
    }

    // Hashtag / mention links
    if (target.dataset.tag) { e.preventDefault(); loadHashtag(target.dataset.tag); }
    if (target.dataset.user) { e.preventDefault(); location.href = `profile.html?u=${target.dataset.user}`; }
  });

  // Close dropdowns on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.post-menu')) {
      document.querySelectorAll('.dropdown').forEach(d => d.classList.add('hidden'));
    }
  });

  async function loadComments(postId, box) {
    box.innerHTML = '<div class="loader">Loading…</div>';
    const list = await API.get(`/posts/${postId}/comments/`);
    const items = (list.results || list).map(c => `
      <div class="comment-item" data-comment-id="${c.id}">
        ${avatarHtml(c.author, 'sm')}
        <div style="flex:1">
          <b>${esc(c.author.username)}</b>
          <div>${linkify(c.content)}</div>
          <div class="comment-actions">
            <button class="comment-like" data-cid="${c.id}">❤️ ${c.likes_count}</button>
            <button class="comment-reply" data-cid="${c.id}">Reply</button>
          </div>
        </div>
      </div>`).join('') || '<div class="muted" style="color:var(--muted)">No comments yet</div>';
    box.innerHTML = `
      <div class="comments-list">${items}</div>
      <div class="comment-form">
        <input placeholder="Write a comment…" data-c-input="${postId}" />
        <button class="btn btn-primary" data-c-send="${postId}">Send</button>
      </div>`;
    box.querySelector(`[data-c-send]`).onclick = async () => {
      const input = box.querySelector(`[data-c-input]`);
      if (!input.value.trim()) return;
      await API.post(`/posts/${postId}/comments/`, { content: input.value });
      input.value = '';
      box.dataset.loaded = '';
      loadComments(postId, box);
    };
    box.querySelectorAll('.comment-like').forEach(b => b.onclick = async () => {
      const r = await API.post(`/posts/comments/${b.dataset.cid}/like/`);
      b.textContent = `❤️ ${r.count}`;
    });
  }

  async function loadHashtag(tag) {
    const list = await API.get(`/posts/hashtag/${tag}/`);
    document.getElementById('feed-list').innerHTML = (list.results || list).map(renderPost).join('');
  }
  window.loadHashtag = loadHashtag;

  // ─── Edit post (inline) ────────────────────────────────────
  function editPost(postId) {
    const card = document.querySelector(`.post-card[data-id="${postId}"]`);
    const contentEl = card.querySelector('.post-content');
    const original = contentEl.textContent;
    contentEl.innerHTML = `
      <textarea class="edit-textarea">${esc(original)}</textarea>
      <div class="edit-actions">
        <button class="btn btn-primary save-edit">Save</button>
        <button class="btn btn-ghost cancel-edit">Cancel</button>
      </div>`;
    contentEl.querySelector('.save-edit').onclick = async () => {
      const val = contentEl.querySelector('.edit-textarea').value;
      await API.patch(`/posts/${postId}/`, { content: val });
      contentEl.innerHTML = linkify(val);
      toast('Updated', 'success');
    };
    contentEl.querySelector('.cancel-edit').onclick = () => {
      contentEl.innerHTML = linkify(original);
    };
  }

  // ─── Composer (with emoji + mention autocomplete) ─────────
  let composerFile = null;
  document.getElementById('composer-image')?.addEventListener('change', (e) => {
    composerFile = e.target.files[0];
    const prev = document.getElementById('composer-preview');
    prev.innerHTML = composerFile ? `<img class="post-image" src="${URL.createObjectURL(composerFile)}" />` : '';
  });

  document.getElementById('btn-post')?.addEventListener('click', async () => {
    const content = document.getElementById('composer-input').value.trim();
    if (!content && !composerFile) return;
    const visibility = document.getElementById('composer-visibility').value;
    const fd = new FormData();
    fd.append('content', content);
    fd.append('visibility', visibility);
    if (composerFile) fd.append('image', composerFile);
    try {
      await API.upload('/posts/', fd);
      document.getElementById('composer-input').value = '';
      composerFile = null;
      document.getElementById('composer-preview').innerHTML = '';
      document.getElementById('composer-image').value = '';
      loadFeed(true);
      toast('Posted!', 'success');
    } catch { toast('Failed', 'error'); }
  });

  document.getElementById('btn-draft')?.addEventListener('click', async () => {
    const content = document.getElementById('composer-input').value.trim();
    if (!content) return;
    await API.post('/posts/drafts/', { content });
    document.getElementById('composer-input').value = '';
    toast('Draft saved', 'success');
  });

  // ─── Infinite scroll + pull-to-refresh indicator ──────────
  window.addEventListener('scroll', () => {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 400) {
      loadFeed();
    }
  });

  // ─── Keyboard: 'j'/'k' to move, 'l' to like ───────────────
  document.addEventListener('keydown', (e) => {
    if (e.target.matches('input, textarea')) return;
    const cards = [...document.querySelectorAll('.post-card')];
    if (!cards.length) return;
    const idx = cards.findIndex(c => c.classList.contains('focused'));
    if (e.key === 'j') {
      cards.forEach(c => c.classList.remove('focused'));
      const next = cards[Math.min(idx + 1, cards.length - 1)] || cards[0];
      next.classList.add('focused'); next.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else if (e.key === 'k') {
      cards.forEach(c => c.classList.remove('focused'));
      const prev = cards[Math.max(idx - 1, 0)] || cards[0];
      prev.classList.add('focused'); prev.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else if (e.key === 'l' && idx >= 0) {
      cards[idx].querySelector('.like-btn')?.click();
    }
  });

  // Init
  document.addEventListener('DOMContentLoaded', () => {
    if (!API.getToken()) { location.href = 'index.html'; return; }
    loadFeed(true);
  });
})();