import axios from 'axios';
import { getToken } from './auth';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor: Attach Bearer Token if available
apiClient.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Normalize errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    let errorMessage = 'Không thể kết nối tới máy chủ FastAPI.';
    if (error.response?.data) {
      const { detail } = error.response.data;
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        errorMessage = detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
      }
    } else if (error.message) {
      errorMessage = error.message;
    }
    const enhancedError = new Error(errorMessage);
    enhancedError.status = error.response?.status;
    enhancedError.data = error.response?.data;
    return Promise.reject(enhancedError);
  }
);

export default apiClient;

// Legacy compatibility helper
export const sendChatMessage = async (message, conversationId = null) => {
  const payload = { message };
  if (conversationId) {
    payload.conversation_id = conversationId;
  }
  const response = await apiClient.post('/chat', payload);
  return response.data;
};
