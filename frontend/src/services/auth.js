/**
 * Authentication and Token Management Service for Travel Agent.
 * Manages Bearer Tokens and User Profiles in localStorage.
 *
 * The preset tokens match the documented local development registry in
 * `.env.example` (`LOCAL_AUTH_TOKENS_JSON` with `dev-token-alice` /
 * `dev-token-bob`). A mismatch made the quick-login presets authenticate
 * against nothing: the UI treated the user as logged in, and the first real
 * request came back 401. The presets are a development convenience for the
 * documented registry, not a second source of truth.
 */

const TOKEN_STORAGE_KEY = 'travel_agent_auth_token';
const USER_STORAGE_KEY = 'travel_agent_auth_user';

export const PRESET_USERS = [
  {
    id: 'alice',
    name: 'Alice',
    token: 'dev-token-alice',
    badge: 'Alice',
    color: 'bg-sidebar-mist text-graphite-ink border-hairline',
  },
  {
    id: 'bob',
    name: 'Bob',
    token: 'dev-token-bob',
    badge: 'Bob',
    color: 'bg-sidebar-mist text-graphite-ink border-hairline',
  },
];

const getStorage = () => {
  if (typeof window !== 'undefined' && window.localStorage) {
    return window.localStorage;
  }
  if (typeof localStorage !== 'undefined') {
    return localStorage;
  }
  return {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
};

export const getToken = () => {
  return getStorage().getItem(TOKEN_STORAGE_KEY) || '';
};

export const setToken = (token, userName = '') => {
  if (!token) return;
  const storage = getStorage();
  storage.setItem(TOKEN_STORAGE_KEY, token.trim());
  if (userName) {
    storage.setItem(USER_STORAGE_KEY, userName.replace(/\s*\(.*?\)/g, '').trim());
  } else {
    const preset = PRESET_USERS.find((u) => u.token === token.trim());
    if (preset) {
      storage.setItem(USER_STORAGE_KEY, preset.name);
    } else {
      storage.setItem(USER_STORAGE_KEY, 'Custom User');
    }
  }
};

export const clearToken = () => {
  const storage = getStorage();
  storage.removeItem(TOKEN_STORAGE_KEY);
  storage.removeItem(USER_STORAGE_KEY);
};

export const isAuthenticated = () => {
  return Boolean(getToken());
};

export const getUserProfile = () => {
  const token = getToken();
  let name = getStorage().getItem(USER_STORAGE_KEY) || 'Người dùng';
  name = name.replace(/\s*\(.*?\)/g, '').trim() || 'Người dùng';
  const preset = PRESET_USERS.find((u) => u.token === token);
  return {
    token,
    name: preset?.name || name,
    isPreset: Boolean(preset),
    presetId: preset?.id || null,
  };
};

export const getOwnerUserId = () => {
  const profile = getUserProfile();
  if (profile.presetId) {
    return profile.presetId;
  }
  const token = getToken();
  if (token) {
    const preset = PRESET_USERS.find((u) => u.token === token.trim());
    if (preset) return preset.id;
  }
  return 'local-developer';
};

