/* frontend/js/groups.js
   ──────────────────────────────────────────────────────────
   Group chat management: create, add members, promote admin,
   leave, rename, delete, avatar upload.
*/
(function () {
  const state = { groups: [], editingId: null };

  function esc(s) {
    return (s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  async function loadGroups() {
    try {
      const list = await API.get('/social/conversations/');
      const all = list.results || list;
      state.groups = all.filter(c => c.is_group);
      renderGroups();
    } catch {}
  }

  function renderGroups() {
    const host = document.getElementById('groups-list');
    if (!host) return;
    host.innerHTML = state.groups.length ? state.groups.map(g => `
      <div class="group-row" data-id="${g.id}" style="display:flex;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)">
        <div class="avatar sm" style="${g.avatar ? `background-image:url(${g.avatar});background-size:cover` : ''}"></div>
        <div style="flex:1">
          <b>${esc(g.name || 'Untitled group')}</b>
          <div style="color:var(--muted);font-size:12px">${g.participants.length} members</div>
        </div>
        <button class="btn btn-ghost open-group" data-id="${g.id}">Open</button>
        <button class="btn btn-ghost edit-group" data-id="${g.id}">Edit</button>
      </div>`).join('')
      : '<div style="text-align:center;color:var(--muted);padding:20px">No groups yet</div>';

    host.querySelectorAll('.open-group').forEach(b => b.onclick = () => {
      window.ChatPanel?.openConversation?.(parseInt(b.dataset.id, 10));
      document.getElementById('chat-panel')?.classList.remove('hidden');
    });
    host.querySelectorAll('.edit-group').forEach(b =>
      b.onclick = () => openEditor(parseInt(b.dataset.id, 10)));
  }

  function openCreateModal() {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
      <div class="modal-body">
        <h3>New Group</h3>
        <div class="field"><label>Group name</label><input id="grp-name" /></div>
        <div class="field"><label>Members</label><input id="grp-members" placeholder="Search usernames, comma-separated" /></div>
        <div id="grp-results" style="max-height:180px;overflow:auto"></div>
        <div class="modal-actions">
          <button class="btn btn-primary" id="grp-create">Create</button>
          <button class="btn btn-ghost" id="grp-cancel">Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(modal);

    const selected = new Set();
    let searchTimer;
    modal.querySelector('#grp-members').oninput = (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        const q = e.target.value.trim();
        if (!q) return;
        const users = await API.get(`/auth/users/search/?q=${encodeURIComponent(q)}`);
        const box = modal.querySelector('#grp-results');
        box.innerHTML = users.map(u => `
          <div class="notif-item" data-id="${u.id}" data-name="${esc(u.username)}" style="cursor:pointer">
            <div class="avatar sm"></div>
            <b>${esc(u.username)}</b>
          </div>`).join('');
        box.querySelectorAll('.notif-item').forEach(item => item.onclick = () => {
          const id = parseInt(item.dataset.id, 10);
          if (selected.has(id)) selected.delete(id); else selected.add(id);
          item.style.background = selected.has(id) ? '#fff5ec' : '';
        });
      }, 250);
    };

    modal.querySelector('#grp-cancel').onclick = () => modal.remove();
    modal.querySelector('#grp-create').onclick = async () => {
      const name = modal.querySelector('#grp-name').value.trim();
      if (!name || !selected.size) return toast?.('Name + members required', 'error');
      try {
        await API.post('/social/conversations/', {
          user_ids: [...selected], is_group: true, name,
        });
        toast?.('Group created', 'success');
        modal.remove();
        loadGroups();
      } catch { toast?.('Failed to create group', 'error'); }
    };
  }

  async function openEditor(groupId) {
    state.editingId = groupId;
    const group = state.groups.find(g => g.id === groupId);
    if (!group) return;
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
      <div class="modal-body">
        <h3>Edit Group</h3>
        <div class="field"><label>Group name</label><input id="grp-edit-name" value="${esc(group.name || '')}" /></div>
        <div class="field"><label>Group avatar</label><input type="file" id="grp-edit-avatar" accept="image/*" /></div>
        <h4 style="margin-top:16px">Members</h4>
        <div>${group.participants.map(p => `
          <div style="display:flex;justify-content:space-between;padding:6px 0">
            <span>${esc(p.username)}</span>
            <button class="btn btn-ghost remove-member" data-uid="${p.id}">Remove</button>
          </div>`).join('')}</div>
        <div class="field" style="margin-top:12px"><label>Add members</label><input id="grp-add-members" placeholder="Search usernames" /></div>
        <div id="grp-add-results" style="max-height:150px;overflow:auto"></div>
        <div class="modal-actions">
          <button class="btn btn-primary" id="grp-save">Save</button>
          <button class="btn btn-danger" id="grp-delete">Delete group</button>
          <button class="btn btn-ghost" id="grp-close">Close</button>
        </div>
      </div>`;
    document.body.appendChild(modal);

    let searchTimer;
    modal.querySelector('#grp-add-members').oninput = (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        const q = e.target.value.trim();
        if (!q) return;
        const users = await API.get(`/auth/users/search/?q=${encodeURIComponent(q)}`);
        const box = modal.querySelector('#grp-add-results');
        box.innerHTML = users.map(u => `
          <div class="notif-item" data-id="${u.id}" style="cursor:pointer">
            <div class="avatar sm"></div><b>${esc(u.username)}</b>
          </div>`).join('');
        box.querySelectorAll('.notif-item').forEach(item => item.onclick = async () => {
          await API.post(`/social/conversations/${groupId}/add/`, { user_id: parseInt(item.dataset.id, 10) });
          toast?.('Added', 'success');
          modal.remove();
          loadGroups();
        });
      }, 250);
    };

    modal.querySelectorAll('.remove-member').forEach(b => b.onclick = async () => {
      await API.post(`/social/conversations/${groupId}/remove/`, { user_id: parseInt(b.dataset.uid, 10) });
      toast?.('Removed', 'success');
      modal.remove();
      loadGroups();
    });

    modal.querySelector('#grp-close').onclick = () => modal.remove();
    modal.querySelector('#grp-save').onclick = async () => {
      const name = modal.querySelector('#grp-edit-name').value.trim();
      const fd = new FormData();
      fd.append('name', name);
      const f = modal.querySelector('#grp-edit-avatar').files[0];
      if (f) fd.append('avatar', f);
      try {
        await API.upload(`/social/conversations/${groupId}/update/`, fd);
        toast?.('Saved', 'success');
        modal.remove();
        loadGroups();
      } catch { toast?.('Save failed', 'error'); }
    };
    modal.querySelector('#grp-delete').onclick = async () => {
      if (!confirm('Delete this group?')) return;
      await API.del(`/social/conversations/${groupId}/`);
      toast?.('Deleted', 'success');
      modal.remove();
      loadGroups();
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-new-group');
    if (btn) btn.onclick = openCreateModal;
    loadGroups();
  });

  window.Groups = { load: loadGroups, openCreateModal };
})();