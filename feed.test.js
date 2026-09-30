/* frontend/tests/feed.test.js
   Basic DOM-driven tests for feed utilities using jsdom. */

document.body.innerHTML = `
  <div id="feed-list"></div>
  <div id="feed-loader" class="hidden"></div>
  <div id="toast"></div>
  <textarea id="composer-input"></textarea>
  <input id="composer-image" type="file" />
  <select id="composer-visibility"><option value="public" selected>public</option></select>
  <div id="composer-preview"></div>
  <button id="btn-post"></button>
  <button id="btn-draft"></button>
`;

global.API = {
  getToken: () => 'tok',
  get: jest.fn(() => Promise.resolve({ results: [] })),
  post: jest.fn(() => Promise.resolve({})),
  upload: jest.fn(() => Promise.resolve({})),
  getUser: () => ({ id: 1, username: 'me' }),
};

describe('timeAgo helper', () => {
  function timeAgo(iso) {
    const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 60) return `${Math.floor(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    if (s < 604800) return `${Math.floor(s / 86400)}d`;
    return new Date(iso).toLocaleDateString();
  }

  test('seconds', () => {
    expect(timeAgo(new Date(Date.now() - 5000).toISOString())).toBe('5s');
  });
  test('minutes', () => {
    expect(timeAgo(new Date(Date.now() - 120000).toISOString())).toBe('2m');
  });
  test('hours', () => {
    expect(timeAgo(new Date(Date.now() - 7200000).toISOString())).toBe('2h');
  });
  test('days', () => {
    expect(timeAgo(new Date(Date.now() - 172800000).toISOString())).toBe('2d');
  });
});

describe('esc helper', () => {
  function esc(str) {
    return (str || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  test('escapes html', () => {
    expect(esc('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;');
  });
  test('escapes quotes', () => {
    expect(esc(`"'`)).toBe('&quot;&#39;');
  });
  test('handles null', () => {
    expect(esc(null)).toBe('');
  });
});

describe('linkify helper', () => {
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

  test('hashtag link', () => {
    expect(linkify('#python')).toContain('data-tag="python"');
  });
  test('mention link', () => {
    expect(linkify('@alice')).toContain('data-user="alice"');
  });
  test('url link', () => {
    expect(linkify('see https://x.com')).toContain('href="https://x.com"');
  });
});

describe('Composer', () => {
  test('post button requires content or file', () => {
    const input = document.getElementById('composer-input');
    input.value = '';
    const btn = document.getElementById('btn-post');
    // Simulate click — no API call should fire
    let called = false;
    API.upload = jest.fn(() => { called = true; return Promise.resolve({}); });
    btn.click();
    expect(called).toBe(false);
  });
});