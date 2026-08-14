import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Create Axios Instance with default headers
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to attach Authorization Bearer token automatically
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('travel_access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Helper function to convert raw API error details into human-readable strings
const extractErrorMessage = (error, fallbackMessage) => {
  if (error.response && error.response.data && error.response.data.detail) {
    const detail = error.response.data.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg || item.message || JSON.stringify(item)).join('; ');
    }
    if (typeof detail === 'object') {
      return JSON.stringify(detail);
    }
  }
  if (error.message && typeof error.message === 'string' && error.message !== '[object Object]') {
    return error.message;
  }
  return fallbackMessage;
};

// ----------------------------------------------------
// 1. Session ID Management in localStorage
// ----------------------------------------------------
export const getStoredSessionId = () => {
  let sessionId = localStorage.getItem('travel_chat_session_id');
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem('travel_chat_session_id', sessionId);
  }
  return sessionId;
};

export const createNewSessionId = () => {
  const newSessionId = crypto.randomUUID();
  localStorage.setItem('travel_chat_session_id', newSessionId);
  return newSessionId;
};

export const getStoredGuestSessions = () => {
  try {
    const raw = localStorage.getItem('travel_guest_sessions');
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
};

export const saveGuestSession = (sessionId, titleText) => {
  try {
    const sessions = getStoredGuestSessions();
    const cleanTitle = (titleText || 'New Chat').slice(0, 45);
    const existingIdx = sessions.findIndex((s) => s.id === sessionId);
    const updatedSession = {
      id: sessionId,
      title: cleanTitle,
      updated_at: new Date().toISOString(),
    };

    if (existingIdx >= 0) {
      sessions[existingIdx] = updatedSession;
    } else {
      sessions.unshift(updatedSession);
    }
    localStorage.setItem('travel_guest_sessions', JSON.stringify(sessions));
  } catch (e) {
    console.error('Error saving guest session:', e);
  }
};

export const deleteGuestSession = (sessionId) => {
  try {
    const sessions = getStoredGuestSessions().filter((s) => s.id !== sessionId);
    localStorage.setItem('travel_guest_sessions', JSON.stringify(sessions));
  } catch (e) {
    console.error('Error deleting guest session:', e);
  }
};

// ----------------------------------------------------
// 2. Authentication APIs
// ----------------------------------------------------
export const registerUser = async (email, password, fullName) => {
  try {
    const response = await apiClient.post('/api/v1/auth/register', {
      email,
      password,
      full_name: fullName || null,
    });
    return response.data;
  } catch (error) {
    console.error('Registration API Error:', error);
    throw new Error(extractErrorMessage(error, 'Failed to register account. Please try again.'));
  }
};

export const loginUser = async (email, password) => {
  try {
    const response = await apiClient.post('/api/v1/auth/login', {
      email,
      password,
    });
    const data = response.data;
    if (data.access_token) {
      localStorage.setItem('travel_access_token', data.access_token);
    }
    return data;
  } catch (error) {
    console.error('Login API Error:', error);
    throw new Error(extractErrorMessage(error, 'Incorrect email or password.'));
  }
};

export const getCurrentUser = async () => {
  const token = localStorage.getItem('travel_access_token');
  if (!token) return null;

  try {
    const response = await apiClient.get('/api/v1/auth/me');
    return response.data;
  } catch (error) {
    console.warn('Invalid or expired token, removing from localStorage.');
    localStorage.removeItem('travel_access_token');
    return null;
  }
};

export const logoutUser = () => {
  localStorage.removeItem('travel_access_token');
};

// ----------------------------------------------------
// 3. Chat API
// ----------------------------------------------------
export const sendChatMessage = async (message, customSessionId = null) => {
  const sessionId = customSessionId || getStoredSessionId();
  try {
    const response = await apiClient.post('/api/v1/chat', {
      message: message,
      session_id: sessionId,
    });
    return response.data;
  } catch (error) {
    console.error('Chat API Error:', error);
    throw new Error(extractErrorMessage(error, 'Failed to connect to backend server. Please check FastAPI server.'));
  }
};

// ----------------------------------------------------
// 4. Memory & Session Management APIs
// ----------------------------------------------------
export const getUserSessions = async () => {
  try {
    const response = await apiClient.get('/api/v1/memory/sessions');
    return response.data;
  } catch (error) {
    console.error('Fetch User Sessions Error:', error);
    return [];
  }
};

export const getSessionHistory = async (sessionId) => {
  if (!sessionId) return [];
  try {
    const response = await apiClient.get(`/api/v1/memory/history/${sessionId}`);
    return response.data;
  } catch (error) {
    console.error('Fetch Session History Error:', error);
    return [];
  }
};

export const deleteSessionHistory = async (sessionId) => {
  if (!sessionId) return false;
  try {
    await apiClient.delete(`/api/v1/memory/history/${sessionId}`);
    return true;
  } catch (error) {
    console.error('Delete Session Error:', error);
    return false;
  }
};

export const getUserFacts = async () => {
  try {
    const response = await apiClient.get('/api/v1/memory/facts');
    return response.data;
  } catch (error) {
    console.error('Fetch Facts Error:', error);
    return [];
  }
};

export const deleteUserFact = async (factId) => {
  try {
    await apiClient.delete(`/api/v1/memory/facts/${factId}`);
    return true;
  } catch (error) {
    console.error('Delete Fact Error:', error);
    return false;
  }
};

export const updateMemoryConsent = async (enabled) => {
  try {
    const response = await apiClient.patch('/api/v1/auth/me/memory_consent', { memory_enabled: enabled });
    return response.data;
  } catch (error) {
    console.error('Error updating memory consent:', error);
    return null;
  }
};
