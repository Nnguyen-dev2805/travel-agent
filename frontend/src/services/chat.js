import apiClient from './api';

export const listConversations = async () => {
  const response = await apiClient.get('/conversations');
  return response.data?.conversations || [];
};

export const createConversation = async (title = 'Cuộc trò chuyện mới') => {
  const response = await apiClient.post('/conversations', {
    title: title.trim(),
  });
  return response.data;
};

export const deleteConversation = async (conversationId) => {
  await apiClient.delete(`/conversations/${conversationId}`);
};

export const listMessages = async (conversationId) => {
  const response = await apiClient.get(`/conversations/${conversationId}/messages`);
  return response.data?.messages || [];
};

export const postChatMessage = async ({ message, conversation_id }) => {
  const payload = { message: message.trim() };
  if (conversation_id) {
    payload.conversation_id = conversation_id;
  }
  const response = await apiClient.post('/chat', payload);
  return response.data;
};
