/* frontend/js/lightbox.js
   Simple fullscreen image lightbox with keyboard nav.
*/
(function () {
  let overlayEl = null;
  let imgEl = null;

  function ensureOverlay() {
    if (overlayEl) return;
    overlayEl = document.createElement('div');
    overlayEl.className = 'lightbox-overlay';
    overlayEl.style.cssText = `
      position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:9999;
      display:none;align-items:center;justify-content:center;padding:20px;`;
    imgEl = document.createElement('img');
    imgEl.style.cssText = `
      max-width:100%;max-height:100%;border-radius:12px;
      box-shadow:0 20px 60px rgba(0,0,0,.6);`;
    overlayEl.appendChild(imgEl);

    const closeBtn = document.createElement('button');
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = `
      position:absolute;top:20px;right:20px;font-size:26px;color:#fff;
      background:rgba(255,255,255,.15);border-radius:50%;width:44px;height:44px;
      display:flex;align-items:center;justify-content:center;`;
    closeBtn.onclick = close;
    overlayEl.appendChild(closeBtn);

    overlayEl.addEventListener('click', (e) => { if (e.target === overlayEl) close(); });
    document.body.appendChild(overlayEl);
  }

  function open(src) {
    if (!src) return;
    ensureOverlay();
    imgEl.src = src;
    overlayEl.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }

  function close() {
    if (!overlayEl) return;
    overlayEl.style.display = 'none';
    imgEl.src = '';
    document.body.style.overflow = '';
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });

  window.openLightbox = open;
  window.closeLightbox = close;
})();