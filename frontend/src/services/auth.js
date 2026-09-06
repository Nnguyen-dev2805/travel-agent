/**
 * Authentication and Token Management Service for Travel Agent.
 * Manages Bearer Tokens and User Profiles in localStorage.
 */

const TOKEN_STORAGE_KEY = 'travel_agent_auth_token';
const USER_STORAGE_KEY = 'travel_agent_auth_user';

export const PRESET_USERS = [
  {
    id: 'user_alice',
    name: 'Alice (Đà Nẵng & Hội An)',
    token: 'token_alice_secret',
    badge: 'Alice',
    color: 'bg-amber-100 text-amber-800 border-amber-300',
  },
  {
    id: 'user_bob',
    name: 'Bob (Hà Giang Explorer)',
    token: 'token_bob_secret',
    badge: 'Bob',
    color: 'bg-teal-100 text-teal-800 border-teal-300',
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
    storage.setItem(USER_STORAGE_KEY, userName.trim());
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
  const name = getStorage().getItem(USER_STORAGE_KEY) || 'Người dùng';
  const preset = PRESET_USERS.find((u) => u.token === token);
  return {
    token,
    name,
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

