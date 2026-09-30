/* frontend/js/emoji.js
   Emoji picker — lightweight, no external deps.
*/
(function () {
  const EMOJIS = [
    '😀','😃','😄','😁','😆','😅','😂','🤣','😊','😇',
    '🙂','🙃','😉','😌','😍','🥰','😘','😗','😙','😚',
    '😋','😛','😝','😜','🤪','🤨','🧐','🤓','😎','🤩',
    '🥳','😏','😒','😞','😔','😟','😕','🙁','☹️','😣',
    '😖','😫','😩','🥺','😢','😭','😤','😠','😡','🤬',
    '👍','👎','👏','🙌','🤝','🙏','💪','✌️','🤞','👋',
    '❤️','🧡','💛','💚','💙','💜','🖤','🤍','💔','💕',
    '🔥','✨','🎉','🎊','🎁','🏆','⭐','🌟','💯','✅',
    '🍕','🍔','🍟','🌮','🍣','🍰','🍩','☕','🍺','🍷',
    '🚀','⚡','💡','📌','📎','🔗','📷','🎥','🎵','🎧',
  ];

  let pickerEl = null;
  let currentCallback = null;

  function open(anchor, callback) {
    close();
    currentCallback = callback;
    pickerEl = document.createElement('div');
    pickerEl.className = 'emoji-picker';
    pickerEl.style.cssText = `
      position:absolute;background:var(--white);border:1px solid var(--border);
      border-radius:12px;box-shadow:var(--shadow-lg);padding:8px;z-index:90;
      display:grid;grid-template-columns:repeat(8,1fr);gap:4px;width:320px;
      max-height:260px;overflow-y:auto;`;
    const rect = anchor.getBoundingClientRect();
    pickerEl.style.left = `${rect.left}px`;
    pickerEl.style.top = `${rect.bottom + 6 + window.scrollY}px`;
    pickerEl.innerHTML = EMOJIS.map(e =>
      `<button class="emoji-btn" style="font-size:22px;padding:6px;border-radius:8px;background:transparent">${e}</button>`
    ).join('');
    document.body.appendChild(pickerEl);

    pickerEl.querySelectorAll('.emoji-btn').forEach(btn => {
      btn.onmouseover = () => btn.style.background = '#fff7ef';
      btn.onmouseout = () => btn.style.background = 'transparent';
      btn.onclick = (e) => {
        e.stopPropagation();
        currentCallback?.(btn.textContent);
        close();
      };
    });

    // Close on outside click
    setTimeout(() => {
      document.addEventListener('click', outsideClose, { once: true });
    }, 0);
  }

  function outsideClose(e) {
    if (pickerEl && !pickerEl.contains(e.target)) close();
    else if (pickerEl) document.addEventListener('click', outsideClose, { once: true });
  }

  function close() {
    pickerEl?.remove();
    pickerEl = null;
    currentCallback = null;
  }

  window.EmojiPicker = { open, close, list: EMOJIS };
})();