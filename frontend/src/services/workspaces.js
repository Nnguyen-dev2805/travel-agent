import apiClient from './api';
import { getOwnerUserId } from './auth';

export const listWorkspaces = async (ownerUserId = null) => {
  const owner = ownerUserId || getOwnerUserId();
  const response = await apiClient.get('/workspaces', {
    params: { owner_user_id: owner },
  });
  return response.data?.workspaces || [];
};

export const getWorkspace = async (workspaceId) => {
  const response = await apiClient.get(`/workspaces/${workspaceId}`);
  return response.data;
};

export const createWorkspace = async ({ title, destination_scope, owner_user_id = null }) => {
  const owner = owner_user_id || getOwnerUserId();
  const payload = {
    owner_user_id: owner,
    title: title.trim(),
  };
  if (destination_scope && destination_scope.trim()) {
    payload.destination_scope = destination_scope.trim();
  }
  const response = await apiClient.post('/workspaces', payload);
  return response.data;
};

export const deleteWorkspace = async (workspaceId) => {
  await apiClient.post(`/workspaces/${workspaceId}/deletion-requests`, {});
  const response = await apiClient.post(`/workspaces/${workspaceId}/deletion-confirmations`, {});
  return response.data;
};
