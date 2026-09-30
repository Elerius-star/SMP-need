/* frontend/tests/api.test.js
   Jest tests for API wrapper — no DOM, pure logic. */
const mockFetch = jest.fn();
global.fetch = mockFetch;
global.localStorage = (() => {
  let store = {};
  return {
    getItem: (k) => store[k] ?? null,
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { store = {}; },
  };
})();

// Load API module (strip IIFE side effects by requiring fresh each test)
function loadAPI() {
  delete require.cache[require.resolve('../js/api.js')];
  require('../js/api.js');
  return global.API;
}

describe('API wrapper', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
  });

  test('setTokens + getToken + getUser', () => {
    const API = loadAPI();
    API.setTokens('access-1', 'refresh-1');
    expect(API.getToken()).toBe('access-1');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-1');
  });

  test('clearTokens wipes storage', () => {
    const API = loadAPI();
    API.setTokens('a', 'r');
    localStorage.setItem('user', '{"id":1}');
    API.clearTokens();
    expect(API.getToken()).toBeNull();
    expect(API.getUser()).toBeNull();
  });

  test('get attaches Authorization header', async () => {
    const API = loadAPI();
    API.setTokens('tok', 'ref');
    mockFetch.mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ id: 1 }),
    });
    await API.get('/me/');
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.headers['Authorization']).toBe('Bearer tok');
  });

  test('post sends JSON body', async () => {
    const API = loadAPI();
    mockFetch.mockResolvedValueOnce({
      ok: true, status: 200, json: async () => ({}),
    });
    await API.post('/x/', { a: 1 });
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.method).toBe('POST');
    expect(opts.body).toBe(JSON.stringify({ a: 1 }));
  });

  test('throws on non-ok with detail', async () => {
    const API = loadAPI();
    mockFetch.mockResolvedValueOnce({
      ok: false, status: 400, json: async () => ({ detail: 'bad' }),
    });
    await expect(API.get('/x/')).rejects.toThrow('bad');
  });

  test('204 returns null', async () => {
    const API = loadAPI();
    mockFetch.mockResolvedValueOnce({
      ok: true, status: 204, json: async () => { throw new Error('no body'); },
    });
    const r = await API.del('/x/');
    expect(r).toBeNull();
  });

  test('401 triggers refresh then retry', async () => {
    const API = loadAPI();
    API.setTokens('expired', 'refresh-ok');
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ access: 'new-tok' }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ id: 7 }) });
    const r = await API.get('/me/');
    expect(r.id).toBe(7);
    expect(API.getToken()).toBe('new-tok');
  });

  test('upload sends no Content-Type header', async () => {
    const API = loadAPI();
    API.setTokens('tok', 'ref');
    mockFetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) });
    await API.upload('/upload/', new FormData());
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.headers['Content-Type']).toBeUndefined();
    expect(opts.method).toBe('POST');
  });
});