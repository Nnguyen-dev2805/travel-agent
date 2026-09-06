import apiClient from './api';

export const listItineraries = async (workspaceId) => {
  const response = await apiClient.get(`/workspaces/${workspaceId}/planner/itineraries`);
  return Array.isArray(response.data) ? response.data : response.data?.items || [];
};

export const getItinerary = async (workspaceId, versionId) => {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/planner/itineraries/${versionId}`
  );
  return response.data;
};

export const acceptItinerary = async (workspaceId, versionId) => {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/planner/itineraries/${versionId}/accept`
  );
  return response.data;
};

export const listDecisions = async (workspaceId) => {
  const response = await apiClient.get(`/workspaces/${workspaceId}/planner/decisions`);
  return Array.isArray(response.data) ? response.data : response.data?.items || [];
};
