import React, { useState, useEffect } from 'react';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import ChatPanel from './components/chat/ChatPanel';
import WelcomeView from './components/welcome/WelcomeView';
import LoginModal from './components/auth/LoginModal';

import { clearToken, isAuthenticated } from './services/auth';
import {
  listConversations,
  deleteConversation,
  listMessages,
  postChatMessage,
} from './services/chat';

export default function App() {
  const [isAuth, setIsAuth] = useState(isAuthenticated());
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window !== 'undefined' && window.localStorage) {
      return localStorage.getItem('travel_agent_sidebar_collapsed') === 'true';
    }
    return false;
  });

  // C3/C4: a resolved response must only be applied to the conversation it was
  // requested for. Each async path takes a sequence token and drops its result
  // if a newer request has since started or the active conversation changed.
  const historySeqRef = React.useRef(0);
  const sendSeqRef = React.useRef(0);
  const activeConversationIdRef = React.useRef(activeConversationId);

  React.useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  const handleToggleSidebarCollapse = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== 'undefined' && window.localStorage) {
        localStorage.setItem('travel_agent_sidebar_collapsed', String(next));
      }
      return next;
    });
  };

  // 1. Fetch conversations when authenticated
  const loadConversations = async (preferredConvId = null) => {
    try {
      const data = await listConversations();
      setConversations(data || []);

      if (data && data.length > 0) {
        const targetId = preferredConvId || activeConversationId;
        if (targetId && data.some((c) => c.conversation_id === targetId)) {
          // Awaited, so the caller can rely on the history having landed. It used
          // to be fire-and-forget, which let `handleSelectConversation`'s
          // `setMessages(history)` resolve *after* a caller appended a message of
          // its own — and the history overwrote it.
          await handleSelectConversation(targetId);
        }
      }
    } catch (err) {
      console.error('Lỗi tải conversations:', err);
    }
  };

  // Refresh only the sidebar list, leaving the message view alone.
  //
  // The first turn needs this and not `loadConversations`: the reply for that turn
  // is already in local state, so a history read would either race the append
  // (fire-and-forget) or render the stored reply a second time (awaited). The list
  // refresh is all that is actually missing after a conversation is created.
  const refreshConversationList = async () => {
    try {
      const data = await listConversations();
      setConversations(data || []);
    } catch (err) {
      console.error('Lỗi tải conversations:', err);
    }
  };

  useEffect(() => {
    if (isAuth) {
      loadConversations();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuth]);

  // Listen for 401 unauthorized events to force clean logout
  useEffect(() => {
    const handleUnauthorized = () => {
      clearToken();
      setIsAuth(false);
      setConversations([]);
      setActiveConversationId(null);
      setMessages([]);
      // Same reason as `handleNewChat`: a history response already in flight
      // would otherwise resolve into the logged-out view. This handler clears
      // state directly rather than going through `handleNewChat`, so the
      // invalidation has to be repeated here.
      historySeqRef.current += 1;
    };
    if (typeof window !== "undefined") {
      window.addEventListener("auth:unauthorized", handleUnauthorized);
      return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
    }
  }, []);

  // Global ⌘K / Ctrl+K keyboard shortcut to start a new chat
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  // 2. Select conversation and load message history
  const handleSelectConversation = async (convId) => {
    const seq = ++historySeqRef.current;
    setActiveConversationId(convId);
    setMessages([]);
    try {
      const msgs = await listMessages(convId);
      if (seq !== historySeqRef.current) return;
      setMessages(msgs || []);
    } catch (err) {
      if (seq !== historySeqRef.current) return;
      console.error('Lỗi mở conversation:', err);
      setMessages([{
        message_id: `err_${Date.now()}`,
        role: 'assistant',
        content: 'Không tải được nội dung hội thoại này.',
        created_at: new Date().toISOString(),
      }]);
    }
  };

  // 3. Start a fresh conversation
  const handleNewChat = () => {
    // Invalidate any in-flight history load. `handleSelectConversation` bumps
    // this counter, so select-vs-select is already safe — but New Chat, delete
    // and logout all land here, and without the bump a response for the
    // conversation the user just left resolves into the new, empty view.
    historySeqRef.current += 1;

    // Both of these have to move *synchronously*, not via the effect that
    // maintains `activeConversationIdRef`. `isStale()` reads that ref and the send
    // sequence, and in this tick neither the effect nor the state update has run —
    // so an in-flight send could still compare equal and append its reply to the
    // new, empty conversation.
    sendSeqRef.current += 1;
    activeConversationIdRef.current = null;

    setActiveConversationId(null);
    setMessages([]);
  };

  // 4. Send chat message (auto-creates conversation if activeConversationId is null)
  const handleSendMessage = async (text) => {
    if (!text.trim() || isChatLoading) return;

    const sendSeq = ++sendSeqRef.current;
    const targetConvId = activeConversationId;
    const isStale = () =>
      sendSeq !== sendSeqRef.current ||
      targetConvId !== activeConversationIdRef.current;

    // Optimistic user message
    const tempUserMsg = {
      message_id: `temp_${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsChatLoading(true);

    try {
      const result = await postChatMessage({
        message: text,
        conversation_id: targetConvId,
      });

      if (isStale()) return;

      const returnedConvId = result.conversation?.conversation_id;
      if (!targetConvId && returnedConvId) {
        // Move the ref synchronously for the same reason `handleNewChat` does: the
        // effect that maintains it has not run yet, so a second send started in
        // this window would compare against the wrong conversation.
        activeConversationIdRef.current = returnedConvId;
        setActiveConversationId(returnedConvId);
        // The list only. This turn's messages are already in local state, so a
        // history read here would either race the append below or duplicate the
        // reply, which the server has already stored.
        await refreshConversationList();
      }

      const assistantMsg = {
        message_id: result.conversation?.assistant_message_id || `asst_${Date.now()}`,
        role: 'assistant',
        content: result.reply,
        citations: result.citations || [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      if (isStale()) return;
      console.error('Lỗi gửi tin nhắn:', err);
      // C2 (ADR 0023), frontend half: a first-turn generation failure returns
      // 500 with the conversation_id the backend already committed, preserved
      // by the API interceptor on `err.data`. Bind to it before rendering the
      // error, so the user's retry continues this conversation instead of
      // auto-creating a phantom second one — the exact defect the backend half
      // of ADR 0023 exists to fix. Only the unbound first turn needs this: a
      // turn sent into an already-bound conversation already retries into it.
      const failedConvId = targetConvId || err?.data?.conversation_id || null;
      if (!targetConvId && failedConvId) {
        // Synchronous, for the same reason `handleNewChat` moves these: the
        // maintainer effect has not run in this tick, so an in-flight send
        // comparing against the ref would read the old (null) conversation.
        activeConversationIdRef.current = failedConvId;
        setActiveConversationId(failedConvId);
        // The failed conversation exists server-side, so the sidebar should
        // show it — without a history read, which would race the error message
        // below and, on success, duplicate what the server stored.
        refreshConversationList();
      }
      const errorMsg = {
        message_id: `err_${Date.now()}`,
        role: 'assistant',
        content: `⚠️ Xin lỗi, đã có lỗi xảy ra: ${err.message}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      // Clear loading when no newer send has started. Keying on the sequence
      // (not on isStale) matters: a discarded response must still release the
      // input, or the composer stays disabled forever after a switch.
      if (sendSeq === sendSeqRef.current) setIsChatLoading(false);
    }
  };

  // 5. Select template
  const handleSelectTemplate = (template) => {
    handleSendMessage(template.prompt);
  };

  // 6. Delete conversation
  const handleDeleteConversation = async (convId) => {
    try {
      await deleteConversation(convId);
    } catch (err) {
      // Do NOT drop it from the list. The server refused, so the conversation
      // still exists: removing it here would tell the user it is gone and then
      // show it again on the next load, which is worse than doing nothing.
      console.error('Lỗi xóa conversation:', err);
      return;
    }
    const remaining = conversations.filter((c) => c.conversation_id !== convId);
    setConversations(remaining);
    if (activeConversationId === convId) {
      handleNewChat();
    }
  };

  const handleLogout = () => {
    clearToken();
    setIsAuth(false);
    setConversations([]);
    handleNewChat();
  };

  // Primary Authentication Gate: unauthenticated users see login only
  if (!isAuth) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-pure-white text-graphite-ink font-sans">
        <LoginModal
          onLoginSuccess={() => {
            setIsAuth(true);
          }}
        />
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-pure-white text-graphite-ink font-sans">

      {/* Left Sidebar */}
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        onLogout={handleLogout}
        onLoginClick={() => setIsAuth(false)}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={handleToggleSidebarCollapse}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">
        <Header
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
          onLogout={handleLogout}
        />

        {/* Dynamic Main Body: WelcomeView vs Active Chat Panel */}
        {!activeConversationId && messages.length === 0 ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            <WelcomeView onSelectTemplate={handleSelectTemplate} />
            <div className="p-4 max-w-[768px] w-full mx-auto pb-6">
              <ChatPanel
                messages={[]}
                onSendMessage={handleSendMessage}
                isLoading={isChatLoading}
              />
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            <ChatPanel
              messages={messages}
              onSendMessage={handleSendMessage}
              isLoading={isChatLoading}
            />
          </div>
        )}
      </div>
    </div>
  );
}
