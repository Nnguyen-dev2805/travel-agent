import React, { useState, useEffect } from 'react';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import ChatPanel from './components/chat/ChatPanel';
import PlannerPanel from './components/planner/PlannerPanel';
import WelcomeView from './components/welcome/WelcomeView';
import LoginModal from './components/auth/LoginModal';
import CreateTripModal from './components/workspace/CreateTripModal';

import { clearToken, isAuthenticated } from './services/auth';
import {
  listWorkspaces,
  createWorkspace,
  getWorkspace,
  deleteWorkspace,
} from './services/workspaces';
import {
  listConversations,
  createConversation,
  listMessages,
  postChatMessage,
} from './services/chat';

export default function App() {
  const [isAuth, setIsAuth] = useState(isAuthenticated());
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(null);
  const [activeWorkspace, setActiveWorkspace] = useState(null);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [mobileActiveTab, setMobileActiveTab] = useState('chat'); // 'chat' | 'planner'
  const [plannerReloadTrigger, setPlannerReloadTrigger] = useState(0);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  // 1. Fetch workspaces when authenticated
  const loadWorkspaces = async (preferredWorkspaceId = null) => {
    try {
      const data = await listWorkspaces();
      setWorkspaces(data || []);

      if (data && data.length > 0) {
        const targetId =
          preferredWorkspaceId ||
          activeWorkspaceId ||
          localStorage.getItem('travel_agent_active_workspace') ||
          data[0].workspace_id;

        const exists = data.some((w) => w.workspace_id === targetId);
        const resolvedId = exists ? targetId : data[0].workspace_id;
        handleSelectWorkspace(resolvedId);
      } else {
        setActiveWorkspaceId(null);
        setActiveWorkspace(null);
        setActiveConversationId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error('Lỗi tải workspaces:', err);
    }
  };

  useEffect(() => {
    if (isAuth) {
      loadWorkspaces();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuth]);

  // 2. Select and load a workspace
  const handleSelectWorkspace = async (workspaceId) => {
    setActiveWorkspaceId(workspaceId);
    localStorage.setItem('travel_agent_active_workspace', workspaceId);

    try {
      const ws = await getWorkspace(workspaceId);
      setActiveWorkspace(ws);

      // Load or create conversation for this workspace
      const convs = await listConversations(workspaceId);
      let convId = null;
      if (convs && convs.length > 0) {
        convId = convs[0].conversation_id;
      } else {
        const newConv = await createConversation(
          workspaceId,
          `Hội thoại ${ws.title}`
        );
        convId = newConv.conversation_id;
      }

      setActiveConversationId(convId);

      // Load messages for conversation
      if (convId) {
        const msgs = await listMessages(convId);
        setMessages(msgs || []);
      }
    } catch (err) {
      console.error('Lỗi mở workspace:', err);
    }
  };

  // 3. Handle sending chat message
  const handleSendMessage = async (text, convId = null) => {
    if (!text.trim() || isChatLoading) return;

    const targetConvId = convId || activeConversationId;

    // Optimistic user message append
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

      const assistantMsg = {
        message_id: result.conversation?.assistant_message_id || `asst_${Date.now()}`,
        role: 'assistant',
        content: result.reply,
        citations: result.citations || [],
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMsg]);

      // Trigger planner reload in case itinerary version/decision was created
      setPlannerReloadTrigger((prev) => prev + 1);
    } catch (err) {
      console.error('Lỗi gửi tin nhắn:', err);
      const errorMsg = {
        message_id: `err_${Date.now()}`,
        role: 'assistant',
        content: `⚠️ Xin lỗi, đã có lỗi xảy ra: ${err.message}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // 4. Handle 1-Click Starter Template Selection
  const handleSelectTemplate = async (template) => {
    try {
      const newWs = await createWorkspace({
        title: template.title,
        destination_scope: template.destination_scope,
      });

      const newConv = await createConversation(
        newWs.workspace_id,
        template.title
      );

      await loadWorkspaces(newWs.workspace_id);
      setActiveWorkspaceId(newWs.workspace_id);
      setActiveWorkspace(newWs);
      setActiveConversationId(newConv.conversation_id);

      // Automatically send the initial prompt with the new conversation ID
      setTimeout(() => {
        handleSendMessage(template.prompt, newConv.conversation_id);
      }, 300);
    } catch (err) {
      console.error('Lỗi khởi tạo mẫu chuyến đi:', err);
    }
  };

  // 5. Handle Custom Trip Creation
  const handleCustomCreate = async ({ title, destination_scope }) => {
    try {
      const newWs = await createWorkspace({ title, destination_scope });
      const newConv = await createConversation(
        newWs.workspace_id,
        title
      );
      await loadWorkspaces(newWs.workspace_id);
      setActiveWorkspaceId(newWs.workspace_id);
      setActiveWorkspace(newWs);
      setActiveConversationId(newConv.conversation_id);
      setIsCreateModalOpen(false);
    } catch (err) {
      console.error('Lỗi tạo chuyến đi:', err);
    }
  };

  // 6. Handle Delete Workspace
  const handleDeleteWorkspace = async (workspaceId) => {
    try {
      await deleteWorkspace(workspaceId);
    } catch (err) {
      console.error('Lỗi xóa workspace:', err);
    }
    const remaining = workspaces.filter((w) => w.workspace_id !== workspaceId);
    setWorkspaces(remaining);
    if (activeWorkspaceId === workspaceId) {
      if (remaining.length > 0) {
        handleSelectWorkspace(remaining[0].workspace_id);
      } else {
        setActiveWorkspaceId(null);
        setActiveWorkspace(null);
        setActiveConversationId(null);
        setMessages([]);
        localStorage.removeItem('travel_agent_active_workspace');
      }
    }
  };

  const handleLogout = () => {
    clearToken();
    setIsAuth(false);
    setActiveWorkspaceId(null);
    setActiveWorkspace(null);
    setActiveConversationId(null);
    setMessages([]);
    localStorage.removeItem('travel_agent_active_workspace');
  };

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-surface-base text-stone-900 font-sans">
      {/* Login Modal if not authenticated */}
      {!isAuth && (
        <LoginModal
          onLoginSuccess={() => {
            setIsAuth(true);
          }}
        />
      )}

      {/* Create Trip Modal */}
      <CreateTripModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreateTrip={handleCustomCreate}
      />

      {/* Left Sidebar */}
      <Sidebar
        workspaces={workspaces}
        activeWorkspaceId={activeWorkspaceId}
        onSelectWorkspace={handleSelectWorkspace}
        onNewTripClick={() => setIsCreateModalOpen(true)}
        onDeleteWorkspace={handleDeleteWorkspace}
        onLogout={handleLogout}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Top Header */}
        <Header
          activeWorkspace={activeWorkspace}
          mobileActiveTab={mobileActiveTab}
          onMobileTabChange={(tab) => setMobileActiveTab(tab)}
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        />

        {/* Dynamic Main Body: WelcomeView vs Dual Pane */}
        {!activeWorkspace ? (
          <WelcomeView
            onSelectTemplate={handleSelectTemplate}
            onOpenCreateModal={() => setIsCreateModalOpen(true)}
          />
        ) : (
          <div className="flex-1 flex overflow-hidden">
            {/* Left/Center Pane: Chat Panel */}
            <div
              className={`flex-1 h-full flex flex-col ${
                mobileActiveTab === 'chat' ? 'flex' : 'hidden lg:flex'
              }`}
            >
              <ChatPanel
                messages={messages}
                onSendMessage={handleSendMessage}
                isLoading={isChatLoading}
                onViewPlanner={() => setMobileActiveTab('planner')}
              />
            </div>

            {/* Right Pane: Planner Panel */}
            <div
              className={`h-full ${
                mobileActiveTab === 'planner'
                  ? 'flex flex-1 lg:flex-none'
                  : 'hidden lg:flex'
              }`}
            >
              <PlannerPanel
                workspaceId={activeWorkspaceId}
                reloadTrigger={plannerReloadTrigger}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
