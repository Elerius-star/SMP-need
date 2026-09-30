/* frontend/js/webrtc.js
   ──────────────────────────────────────────────────────────
   Full WebRTC with WebSocket signaling. Supports 1:1 and
   group calls, screen share during call, mute, camera off.
*/
(function () {
  const ICE = {
    iceServers: [
      { urls: 'stun:stun.l.google.com:19302' },
      { urls: 'stun:stun1.l.google.com:19302' },
    ],
  };

  const state = {
    ws: null,
    localStream: null,
    screenStream: null,
    peers: {},           // peer_id -> RTCPeerConnection
    dataChannels: {},    // peer_id -> RTCDataChannel
    room: null,
    myPeerId: null,
    inCall: false,
    muted: false,
    cameraOff: false,
  };

  // ── DOM ───────────────────────────────────────────────────
  const els = {
    openBtn: () => document.getElementById('btn-video'),
    modal: () => document.getElementById('video-modal'),
    local: () => document.getElementById('local-video'),
    remote: () => document.getElementById('remote-video'),
    remoteGrid: () => document.getElementById('remote-grid'),
    startBtn: () => document.getElementById('start-call'),
    endBtn: () => document.getElementById('end-call'),
    closeBtn: () => document.getElementById('close-video'),
    muteBtn: () => document.getElementById('mute-btn'),
    camBtn: () => document.getElementById('cam-btn'),
    shareBtn: () => document.getElementById('share-screen-btn'),
    roomInput: () => document.getElementById('room-input'),
  };

  function ensureRoomInput() {
    const body = els.modal()?.querySelector('.modal-body');
    if (!body || document.getElementById('room-input')) return;
    const wrap = document.createElement('div');
    wrap.className = 'field';
    wrap.innerHTML = `<label>Room name</label><input id="room-input" value="general" />`;
    body.insertBefore(wrap, body.firstChild);
  }

  function ensureControlButtons() {
    const body = els.modal()?.querySelector('.modal-body');
    if (!body || document.getElementById('mute-btn')) return;
    const actions = body.querySelector('.modal-actions');
    if (!actions) return;
    const muteBtn = document.createElement('button');
    muteBtn.id = 'mute-btn';
    muteBtn.className = 'btn btn-ghost';
    muteBtn.textContent = '🎤 Mute';
    const camBtn = document.createElement('button');
    camBtn.id = 'cam-btn';
    camBtn.className = 'btn btn-ghost';
    camBtn.textContent = '📷 Camera';
    const shareBtn = document.createElement('button');
    shareBtn.id = 'share-screen-btn';
    shareBtn.className = 'btn btn-ghost';
    shareBtn.textContent = '🖥 Share';
    actions.insertBefore(muteBtn, actions.firstChild);
    actions.insertBefore(camBtn, muteBtn.nextSibling);
    actions.insertBefore(shareBtn, camBtn.nextSibling);

    const grid = document.createElement('div');
    grid.id = 'remote-grid';
    grid.className = 'video-grid-extra';
    body.appendChild(grid);
  }

  // ── WebSocket signaling ───────────────────────────────────
  function connectSignaling(room) {
    const token = API.getToken();
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const host = '127.0.0.1:8000';
    const url = `${proto}://${host}/ws/call/${room}/?token=${token}`;
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.onopen = () => console.log('[signal] open', room);
    ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch { return; }
      handleSignal(msg);
    };
    ws.onclose = () => console.log('[signal] closed');
    ws.onerror = (e) => console.error('[signal] error', e);
  }

  function sendSignal(payload) {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify(payload));
  }

  async function handleSignal(msg) {
    const type = msg.type;
    if (type === 'peer-joined') {
      // We are the offerer for the new peer
      const pc = createPeerConnection(msg.peer_id, true);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      sendSignal({ type: 'offer', target: msg.peer_id, sdp: offer });
    } else if (type === 'peer-left') {
      closePeer(msg.peer_id);
    } else if (type === 'offer') {
      const pc = createPeerConnection(msg.peer_id, false);
      await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      sendSignal({ type: 'answer', target: msg.peer_id, sdp: answer });
    } else if (type === 'answer') {
      const pc = state.peers[msg.peer_id];
      if (pc) await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
    } else if (type === 'ice') {
      const pc = state.peers[msg.peer_id];
      if (pc && msg.candidate) {
        try { await pc.addIceCandidate(new RTCIceCandidate(msg.candidate)); } catch {}
      }
    }
  }

  function createPeerConnection(peerId, isOfferer) {
    if (state.peers[peerId]) return state.peers[peerId];
    const pc = new RTCPeerConnection(ICE);
    state.peers[peerId] = pc;

    // Add local tracks
    state.localStream?.getTracks().forEach(t => pc.addTrack(t, state.localStream));

    // ICE
    pc.onicecandidate = (e) => {
      if (e.candidate) {
        sendSignal({ type: 'ice', target: peerId, candidate: e.candidate });
      }
    };

    // Remote stream
    const remoteStream = new MediaStream();
    pc.ontrack = (e) => {
      e.streams[0].getTracks().forEach(t => remoteStream.addTrack(t));
      attachRemoteStream(peerId, remoteStream);
    };

    // Connection state
    pc.onconnectionstatechange = () => {
      console.log(`[peer ${peerId}] ${pc.connectionState}`);
      if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) {
        closePeer(peerId);
      }
    };

    // Data channel for chat over WebRTC (optional)
    if (isOfferer) {
      const dc = pc.createDataChannel('chat');
      wireDataChannel(peerId, dc);
    } else {
      pc.ondatachannel = (e) => wireDataChannel(peerId, e.channel);
    }

    return pc;
  }

  function wireDataChannel(peerId, dc) {
    state.dataChannels[peerId] = dc;
    dc.onmessage = (e) => {
      console.log(`[dc ${peerId}]`, e.data);
    };
  }

  function attachRemoteStream(peerId, stream) {
    let video = document.querySelector(`video[data-peer="${peerId}"]`);
    if (!video) {
      video = document.createElement('video');
      video.autoplay = true;
      video.playsInline = true;
      video.dataset.peer = peerId;
      video.style.cssText = 'width:100%;border-radius:12px;background:#000;aspect-ratio:4/3';
      els.remoteGrid()?.appendChild(video);
      // First peer also mirrors into the main "remote-video" slot
      const primary = els.remote();
      if (primary && !primary.srcObject) {
        primary.srcObject = stream;
      }
    }
    video.srcObject = stream;
    video.play().catch(() => {});
  }

  function closePeer(peerId) {
    const pc = state.peers[peerId];
    if (pc) { try { pc.close(); } catch {} delete state.peers[peerId]; }
    document.querySelector(`video[data-peer="${peerId}"]`)?.remove();
  }

  // ── Call control ──────────────────────────────────────────
  async function startCall() {
    const room = els.roomInput()?.value?.trim() || 'general';
    state.room = room;
    try {
      state.localStream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720 }, audio: true,
      });
      const local = els.local();
      if (local) {
        local.srcObject = state.localStream;
        local.play().catch(() => {});
      }
      connectSignaling(room);
      state.inCall = true;
      toast?.('In call', 'success');
    } catch (e) {
      alert('Camera/mic denied: ' + e.message);
    }
  }

  function endCall() {
    Object.keys(state.peers).forEach(closePeer);
    state.localStream?.getTracks().forEach(t => t.stop());
    state.screenStream?.getTracks().forEach(t => t.stop());
    state.ws?.close();
    state.localStream = null;
    state.screenStream = null;
    state.ws = null;
    state.inCall = false;
    const l = els.local(); if (l) l.srcObject = null;
    const r = els.remote(); if (r) r.srcObject = null;
    els.remoteGrid()?.replaceChildren();
  }

  function toggleMute() {
    if (!state.localStream) return;
    state.muted = !state.muted;
    state.localStream.getAudioTracks().forEach(t => t.enabled = !state.muted);
    const btn = els.muteBtn();
    if (btn) btn.textContent = state.muted ? '🔇 Unmute' : '🎤 Mute';
  }

  function toggleCamera() {
    if (!state.localStream) return;
    state.cameraOff = !state.cameraOff;
    state.localStream.getVideoTracks().forEach(t => t.enabled = !state.cameraOff);
    const btn = els.camBtn();
    if (btn) btn.textContent = state.cameraOff ? '📷 Show cam' : '📷 Camera';
  }

  async function toggleScreenShare() {
    if (state.screenStream) {
      // stop screen share, revert to camera
      state.screenStream.getTracks().forEach(t => t.stop());
      state.screenStream = null;
      for (const pc of Object.values(state.peers)) {
        const senders = pc.getSenders().filter(s => s.track?.kind === 'video');
        const camTrack = state.localStream?.getVideoTracks()[0];
        if (camTrack && senders[0]) await senders[0].replaceTrack(camTrack);
      }
      const btn = els.shareBtn();
      if (btn) btn.textContent = '🖥 Share';
      return;
    }
    try {
      state.screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      const track = state.screenStream.getVideoTracks()[0];
      for (const pc of Object.values(state.peers)) {
        const senders = pc.getSenders().filter(s => s.track?.kind === 'video');
        if (senders[0]) await senders[0].replaceTrack(track);
      }
      track.onended = () => toggleScreenShare();
      const btn = els.shareBtn();
      if (btn) btn.textContent = '🛑 Stop sharing';
    } catch (e) {
      alert('Screen share denied');
    }
  }

  // ── Wire UI ───────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    els.openBtn()?.addEventListener('click', () => {
      els.modal()?.classList.remove('hidden');
      ensureRoomInput();
      ensureControlButtons();
    });
    els.closeBtn()?.addEventListener('click', () => {
      els.modal()?.classList.add('hidden');
      if (state.inCall) endCall();
    });
    document.getElementById('start-call')?.addEventListener('click', startCall);
    document.getElementById('end-call')?.addEventListener('click', endCall);
    document.addEventListener('click', (e) => {
      if (e.target.id === 'mute-btn') toggleMute();
      if (e.target.id === 'cam-btn') toggleCamera();
      if (e.target.id === 'share-screen-btn') toggleScreenShare();
    });
  });
})();