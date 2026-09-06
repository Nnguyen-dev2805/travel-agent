import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient, { sendChatMessage } from './api';
import { setToken, getToken, clearToken, PRESET_USERS } from './auth';

vi.mock('axios', () => {
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
      post: vi.fn(),
    },
  };
});

describe('Authentication Service', () => {
  const mockStorage = {};
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: (key) => mockStorage[key] || null,
      setItem: (key, value) => {
        mockStorage[key] = String(value);
      },
      removeItem: (key) => {
        delete mockStorage[key];
      },
      clear: () => {
        for (const k in mockStorage) delete mockStorage[k];
      },
    });
    localStorage.clear();
  });

  it('stores and retrieves bearer token', () => {
    expect(getToken()).toBe('');
    setToken('token_alice_secret', 'Alice');
    expect(getToken()).toBe('token_alice_secret');
  });

  it('clears token on logout', () => {
    setToken('token_test');
    clearToken();
    expect(getToken()).toBe('');
  });

  it('contains Alice and Bob presets', () => {
    expect(PRESET_USERS.length).toBeGreaterThanOrEqual(2);
    expect(PRESET_USERS[0].id).toBe('user_alice');
    expect(PRESET_USERS[1].id).toBe('user_bob');
  });
});

describe('API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends chat message via apiClient', async () => {
    apiClient.post.mockResolvedValueOnce({
      data: {
        reply: 'Xin chào!',
        model: 'gpt-4o-mini',
        citations: [],
      },
    });

    const result = await sendChatMessage('Du lịch Hội An');
    expect(apiClient.post).toHaveBeenCalledWith('/chat', {
      message: 'Du lịch Hội An',
    });
    expect(result.reply).toBe('Xin chào!');
  });
});
