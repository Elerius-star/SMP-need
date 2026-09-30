/* frontend/js/recorder.js
   ──────────────────────────────────────────────────────────
   Screen recording, camera recording, audio recording,
   upload to server, local download.
*/
(function () {
  const state = {
    mediaRecorder: null,
    chunks: [],
    stream: null,
    kind: 'screen',
    blob: null,
  };

  const els = {
    open: () => document.getElementById('btn-record'),
    modal: () => document.getElementById('record-modal'),
    close: () => document.getElementById('close-rec'),
    start: () => document.getElementById('start-rec'),
    stop: () => document.getElementById('stop-rec'),
    preview: () => document.getElementById('record-preview'),
    download: () => document.getElementById('download-rec'),
    upload: () => document.getElementById('upload-rec'),
  };

  function ensureKindSelector() {
    const body = els.modal()?.querySelector('.modal-body');
    if (!body || document.getElementById('rec-kind')) return;
    const sel = document.createElement('select');
    sel.id = 'rec-kind';
    sel.style.marginBottom = '12px';
    sel.innerHTML = `
      <option value="screen">🖥 Screen + mic</option>
      <option value="camera">📷 Camera + mic</option>
      <option value="audio">🎙 Audio only</option>`;
    sel.onchange = () => { state.kind = sel.value; };
    body.insertBefore(sel, body.firstChild);
  }

  function ensureUploadButton() {
    const body = els.modal()?.querySelector('.modal-body');
    if (!body || document.getElementById('upload-rec')) return;
    const actions = body.querySelector('.modal-actions');
    if (!actions) return;
    const btn = document.createElement('button');
    btn.id = 'upload-rec';
    btn.className = 'btn btn-green hidden';
    btn.textContent = 'Upload';
    actions.appendChild(btn);
  }

  async function getStream(kind) {
    if (kind === 'screen') {
      const screen = await navigator.mediaDevices.getDisplayMedia({ video: true });
      let mic = null;
      try { mic = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch {}
      if (mic) mic.getAudioTracks().forEach(t => screen.addTrack(t));
      return screen;
    }
    if (kind === 'camera') {
      return navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    }
    return navigator.mediaDevices.getUserMedia({ audio: true });
  }

  function pickMime() {
    const candidates = [
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm',
      'audio/webm',
    ];
    for (const c of candidates) {
      if (window.MediaRecorder?.isTypeSupported?.(c)) return c;
    }
    return '';
  }

  async function startRecording() {
    try {
      state.stream = await getStream(state.kind);
      const mime = pickMime();
      state.mediaRecorder = new MediaRecorder(state.stream, mime ? { mimeType: mime } : undefined);
      state.chunks = [];
      state.mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size) state.chunks.push(e.data);
      };
      state.mediaRecorder.onstop = () => {
        const type = mime.includes('audio') ? 'audio/webm' : 'video/webm';
        state.blob = new Blob(state.chunks, { type });
        const url = URL.createObjectURL(state.blob);
        const preview = els.preview();
        if (preview) {
          preview.src = url;
          preview.controls = true;
          preview.classList.remove('hidden');
        }
        const dl = els.download();
        if (dl) {
          dl.href = url;
          dl.download = `recording-${Date.now()}.webm`;
          dl.classList.remove('hidden');
        }
        const up = els.upload();
        if (up) up.classList.remove('hidden');
        state.stream.getTracks().forEach(t => t.stop());
      };
      state.mediaRecorder.start(1000); // emit data every second
      toast?.('Recording started', 'success');
    } catch (e) {
      alert('Recording denied: ' + e.message);
    }
  }

  function stopRecording() {
    if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
      state.mediaRecorder.stop();
      toast?.('Recording stopped', 'success');
    }
  }

  async function uploadRecording() {
    if (!state.blob) return;
    const fd = new FormData();
    const file = new File([state.blob], `recording-${Date.now()}.webm`, { type: state.blob.type });
    fd.append('video', file);
    fd.append('content', 'Recorded clip');
    try {
      await API.upload('/posts/', fd);
      toast?.('Uploaded as post', 'success');
      const modal = els.modal();
      if (modal) modal.classList.add('hidden');
      window.loadFeed?.(true);
    } catch (e) {
      toast?.('Upload failed', 'error');
    }
  }

  // ── UI wiring ─────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    els.open()?.addEventListener('click', () => {
      els.modal()?.classList.remove('hidden');
      ensureKindSelector();
      ensureUploadButton();
    });
    els.close()?.addEventListener('click', () => {
      els.modal()?.classList.add('hidden');
      if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') state.mediaRecorder.stop();
    });
    els.start()?.addEventListener('click', startRecording);
    els.stop()?.addEventListener('click', stopRecording);
    document.addEventListener('click', (e) => {
      if (e.target.id === 'upload-rec') uploadRecording();
    });
  });
})();