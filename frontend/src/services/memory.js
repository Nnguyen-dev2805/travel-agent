import apiClient from './api';

export const listMemories = async (scope = null) => {
  const params = scope ? { scope } : {};
  const response = await apiClient.get('/memory/controls/memories', { params });
  return response.data?.memories || [];
};

export const sendMemoryCommand = async ({ utterance, conversation_id = null, scope = null }) => {
  const payload = { utterance: utterance.trim() };
  if (conversation_id) {
    payload.conversation_id = conversation_id;
  }
  if (scope) {
    payload.scope = scope;
  }
  const response = await apiClient.post('/memory/controls/commands', payload);
  return response.data;
};

export const createDeletion = async ({ version_ids }) => {
  const response = await apiClient.post('/memory/controls/deletions', {
    version_ids,
  });
  return response.data;
};

export const requestScopeExpansion = async ({ version_id }) => {
  const response = await apiClient.post('/memory/controls/expansions', {
    version_id,
  });
  return response.data;
};

export const confirmPreview = async ({ preview_id, token }) => {
  const response = await apiClient.post('/memory/controls/confirmations', {
    preview_id,
    token,
  });
  return response.data;
};
