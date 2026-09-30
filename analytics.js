/* frontend/js/analytics.js
   ──────────────────────────────────────────────────────────
   Post analytics viewer with hand-drawn SVG charts (no deps).
*/
(function () {
  const state = { currentPost: null, data: null };

  function esc(s) {
    return (s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function bar(value, max, color) {
    const pct = max > 0 ? Math.round((value / max) * 100) : 0;
    return `<div style="background:#f3f4f6;border-radius:8px;overflow:hidden;height:14px;margin:4px 0">
      <div style="width:${pct}%;height:100%;background:${color};transition:width .4s"></div>
    </div>`;
  }

  function sparkline(points, color = '#ff7a1a') {
    if (!points.length) return '';
    const max = Math.max(...points, 1);
    const w = 240, h = 60;
    const step = points.length > 1 ? w / (points.length - 1) : w;
    const path = points.map((v, i) => {
      const x = i * step;
      const y = h - (v / max) * h;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:${h}px">
      <path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>
    </svg>`;
  }

  async function openForPost(postId) {
    try {
      const data = await API.get(`/posts/${postId}/analytics/`);
      state.currentPost = postId;
      state.data = data;
      render();
    } catch (e) {
      toast?.('Analytics requires ownership', 'error');
    }
  }

  function render() {
    const d = state.data;
    if (!d) return;
    const modal = document.createElement('div');
    modal.className = 'modal';
    const likes = d.likes || 0;
    const comments = d.comments || 0;
    const reposts = d.reposts || 0;
    const views = d.views || 0;
    const max = Math.max(likes, comments, reposts, views, 1);

    // 7-point synthetic sparkline derived from current totals
    const spark = [0.4, 0.55, 0.62, 0.7, 0.8, 0.9, 1].map(x => Math.round(views * x));

    modal.innerHTML = `
      <div class="modal-body" style="max-width:640px">
        <h3>Post Analytics</h3>
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin:16px 0">
          <div class="card" style="margin:0;text-align:center">
            <div style="font-size:26px;font-weight:800;color:var(--orange)">${views}</div>
            <div style="color:var(--muted);font-size:13px">Views</div>
          </div>
          <div class="card" style="margin:0;text-align:center">
            <div style="font-size:26px;font-weight:800;color:var(--green)">${likes}</div>
            <div style="color:var(--muted);font-size:13px">Likes</div>
          </div>
          <div class="card" style="margin:0;text-align:center">
            <div style="font-size:26px;font-weight:800">${comments}</div>
            <div style="color:var(--muted);font-size:13px">Comments</div>
          </div>
          <div class="card" style="margin:0;text-align:center">
            <div style="font-size:26px;font-weight:800">${reposts}</div>
            <div style="color:var(--muted);font-size:13px">Reposts</div>
          </div>
        </div>
        <h4 style="margin-top:8px">Comparison</h4>
        <div>Views ${bar(views, max, '#3b82f6')}</div>
        <div>Likes ${bar(likes, max, '#ff7a1a')}</div>
        <div>Comments ${bar(comments, max, '#1fa463')}</div>
        <div>Reposts ${bar(reposts, max, '#8b5cf6')}</div>
        <h4 style="margin-top:16px">Views trend (synthetic)</h4>
        ${sparkline(spark, '#ff7a1a')}
        <div class="modal-actions">
          <button class="btn btn-ghost" id="ana-close">Close</button>
          <button class="btn btn-primary" id="ana-export">Export CSV</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#ana-close').onclick = () => modal.remove();
    modal.querySelector('#ana-export').onclick = () => {
      const csv = `metric,value\nviews,${views}\nlikes,${likes}\ncomments,${comments}\nreposts,${reposts}\n`;
      const blob = new Blob([csv], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `post-${state.currentPost}-analytics.csv`;
      a.click();
    };
  }

  window.Analytics = { openForPost };
})();