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

// The backend pages message history (`DEFAULT_HISTORY_LIMIT` 50 per page) and
// returns `next_cursor` — the last message id — whenever more records exist.
// Dropping the cursor made a conversation longer than one page render only its
// oldest 50 messages, with everything newer (including fresh replies) missing
// from the UI. This follows the cursor until it is exhausted, so opening a
// conversation shows its full transcript in transcript order.
//
// The page bound exists so a misbehaving cursor can never turn the client into
// an unbounded fetch: 10 pages at the default limit is 500 messages, and a
// transcript that exceeds it deserves a load-more UI rather than a longer loop.
const MAX_HISTORY_PAGES = 10;

export const listMessages = async (conversationId) => {
  const all = [];
  let cursor = null;

  for (let page = 0; page < MAX_HISTORY_PAGES; page += 1) {
    // One argument on the first page so the call shape stays identical to the
    // cursorless request; cursor pages pass `params` explicitly.
    const response = cursor
      ? await apiClient.get(`/conversations/${conversationId}/messages`, {
          params: { after_message_id: cursor },
        })
      : await apiClient.get(`/conversations/${conversationId}/messages`);
    const data = response.data || {};
    const messages = data.messages || [];
    all.push(...messages);

    if (!data.next_cursor || messages.length === 0) break;
    cursor = data.next_cursor;
  }

  return all;
};

export const postChatMessage = async ({ message, conversation_id }) => {
  const payload = { message: message.trim() };
  if (conversation_id) {
    payload.conversation_id = conversation_id;
  }
  const response = await apiClient.post('/chat', payload);
  return response.data;
};
