import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const sendChatMessage = async (message) => {
  try {
    const response = await axios.post(`${API_BASE_URL}/api/v1/chat`, {
      message: message,
    });
    return response.data;
  } catch (error) {
    console.error('API Error:', error);
    if (error.response && error.response.data && error.response.data.detail) {
      throw new Error(error.response.data.detail);
    }
    throw new Error('Không thể kết nối tới Backend FastAPI. Hãy kiểm tra xem server đã chạy chưa!');
  }
};
