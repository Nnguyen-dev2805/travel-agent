import apiClient from './api';

export const listConversations = async (workspaceId) => {
  const response = await apiClient.get(`/workspaces/${workspaceId}/conversations`);
  return response.data?.conversations || [];
};

export const createConversation = async (workspaceId, title = 'Lập kế hoạch chuyến đi') => {
  const response = await apiClient.post(`/workspaces/${workspaceId}/conversations`, {
    title: title.trim(),
  });
  return response.data;
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
