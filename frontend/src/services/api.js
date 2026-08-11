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
    throw new Error(extractErrorMessage(error, 'Không thể đăng ký tài khoản. Vui lòng thử lại!'));
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
    throw new Error(extractErrorMessage(error, 'Email hoặc mật khẩu không chính xác!'));
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
    throw new Error(extractErrorMessage(error, 'Không thể kết nối tới Backend FastAPI. Vui lòng kiểm tra server!'));
  }
};

// ----------------------------------------------------
// 4. Long-term Memory APIs
// ----------------------------------------------------
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
