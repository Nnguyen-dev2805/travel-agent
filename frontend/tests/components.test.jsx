import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import LoginModal from "../src/components/auth/LoginModal";
import ChatMessage from "../src/components/chat/ChatMessage";
import Header from "../src/components/layout/Header";
import Sidebar from "../src/components/layout/Sidebar";
import WelcomeView from "../src/components/welcome/WelcomeView";
import * as authService from "../src/services/auth";

describe("LoginModal Component", () => {
  it("renders presets and login buttons", () => {
    render(<LoginModal onLoginSuccess={() => {}} />);
    expect(screen.getByText("Travel Agent AI")).toBeDefined();
    expect(screen.getByText("Alice")).toBeDefined();
    expect(screen.getByText("Bob")).toBeDefined();
    expect(screen.getByPlaceholderText(/Nhập Bearer Token/i)).toBeDefined();
  });

  it("triggers onLoginSuccess when a preset is selected", () => {
    const handleLogin = vi.fn();
    render(<LoginModal onLoginSuccess={handleLogin} />);
    const aliceBtn = screen.getByText("Alice");
    fireEvent.click(aliceBtn);
    expect(handleLogin).toHaveBeenCalledOnce();
  });
});

describe("ChatMessage & CitationPopover Components", () => {
  it("renders markdown formatted message and citations", () => {
    const msg = {
      role: "assistant",
      content: "Chào bạn! Đây là gợi ý ẩm thực:\n\n### 1. Phở Hà Nội\n- **Địa chỉ:** 49 Bát Đàn",
      citations: [
        {
          title: "Cẩm nang Ẩm thực Hà Nội",
          url: "https://vietnam.travel/ha-noi-food",
          snippet: "Phở là tinh hoa ẩm thực đất Hà Thành.",
        },
      ],
    };

    render(<ChatMessage message={msg} />);
    expect(screen.getByText("Chào bạn! Đây là gợi ý ẩm thực:")).toBeDefined();
    expect(screen.getByText("1. Phở Hà Nội")).toBeDefined();
    expect(screen.getByText(/49 Bát Đàn/)).toBeDefined();

    // Verify citation badge rendered
    const citationBtn = screen.getByText("Cẩm nang Ẩm thực Hà Nội");
    expect(citationBtn).toBeDefined();

    // Click to open popover
    fireEvent.click(citationBtn);
    expect(screen.getByText("Nguồn xác thực")).toBeDefined();
    expect(screen.getByText(/Phở là tinh hoa ẩm thực/)).toBeDefined();
  });
});

describe("Header Component (Clean Break Sentinel)", () => {
  it("does not render any memory or planner buttons", () => {
    render(<Header onToggleSidebar={() => {}} onLoginClick={() => {}} onLogout={() => {}} />);
    expect(screen.queryByText(/Memory/i)).toBeNull();
    expect(screen.queryByText(/Planner/i)).toBeNull();
    expect(screen.queryByText(/Kế hoạch/i)).toBeNull();
    expect(screen.queryByText(/Bộ nhớ/i)).toBeNull();
  });

  it("renders user profile and logout button when authenticated", () => {
    vi.spyOn(authService, "isAuthenticated").mockReturnValue(true);
    vi.spyOn(authService, "getUserProfile").mockReturnValue({ name: "Alice", token: "secret" });
    const handleLogout = vi.fn();

    render(<Header onToggleSidebar={() => {}} onLoginClick={() => {}} onLogout={handleLogout} />);
    expect(screen.getByText("Alice")).toBeDefined();
    const logoutBtn = screen.getByRole("button", { name: /Đăng xuất/i });
    expect(logoutBtn).toBeDefined();
    fireEvent.click(logoutBtn);
    expect(handleLogout).toHaveBeenCalledOnce();
  });
});

describe("Sidebar Component", () => {
  const sampleConversations = [
    { conversation_id: "conv_1", title: "Hà Giang 3N2Đ" },
    { conversation_id: "conv_2", title: "Đà Nẵng Food Tour" },
  ];

  it("renders conversations list and handles selection", () => {
    const handleSelect = vi.fn();
    const handleNew = vi.fn();

    render(
      <Sidebar
        conversations={sampleConversations}
        activeConversationId="conv_1"
        onSelectConversation={handleSelect}
        onNewChat={handleNew}
        onDeleteConversation={() => {}}
        onLogout={() => {}}
      />
    );

    expect(screen.getByText("Cuộc trò chuyện mới")).toBeDefined();
    expect(screen.getByText("Hà Giang 3N2Đ")).toBeDefined();
    expect(screen.getByText("Đà Nẵng Food Tour")).toBeDefined();

    fireEvent.click(screen.getByText("Đà Nẵng Food Tour"));
    expect(handleSelect).toHaveBeenCalledWith("conv_2");

    fireEvent.click(screen.getByText("Cuộc trò chuyện mới"));
    expect(handleNew).toHaveBeenCalledOnce();
  });

  it("calls onDeleteConversation on confirm", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const handleDelete = vi.fn();

    render(
      <Sidebar
        conversations={sampleConversations}
        activeConversationId="conv_1"
        onSelectConversation={() => {}}
        onNewChat={() => {}}
        onDeleteConversation={handleDelete}
        onLogout={() => {}}
      />
    );

    const deleteBtns = screen.getAllByRole("button", { name: /Xóa/i });
    expect(deleteBtns.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(deleteBtns[0]);
    expect(handleDelete).toHaveBeenCalledWith("conv_1");
  });
});

describe("WelcomeView Component", () => {
  it("renders trip starters and handles template selection", () => {
    const handleSelectTemplate = vi.fn();
    render(<WelcomeView onSelectTemplate={handleSelectTemplate} />);

    expect(screen.getByText("Where should we begin?")).toBeDefined();
    expect(screen.getByText("Hành Trình Mùa Hoa Hà Giang")).toBeDefined();

    const starterCard = screen.getByText("Hành Trình Mùa Hoa Hà Giang").closest("button");
    fireEvent.click(starterCard);
    expect(handleSelectTemplate).toHaveBeenCalledOnce();
  });
});

describe("ChatMessage turn status (ADR 0023)", () => {
  it("renders a failed turn distinctly from an empty reply", () => {
    render(<ChatMessage message={{ role: "assistant", content: "", status: "failed" }} />);
    expect(screen.getByTestId("turn-failed")).toBeDefined();
    expect(screen.getByText(/không tạo được câu trả lời/i)).toBeDefined();
  });

  it("does not render a pending turn as a completed reply", () => {
    render(<ChatMessage message={{ role: "assistant", content: "", status: "pending" }} />);
    expect(screen.getByTestId("turn-pending")).toBeDefined();
    // No copyable body exists yet, so the action bar must not be offered.
    expect(screen.queryByTitle("Sao chép")).toBeNull();
  });

  it("renders a complete turn as a normal assistant reply", () => {
    render(
      <ChatMessage
        message={{ role: "assistant", content: "Xin chào", status: "complete" }}
      />
    );
    expect(screen.getByText("Xin chào")).toBeDefined();
    expect(screen.queryByTestId("turn-pending")).toBeNull();
    expect(screen.queryByTestId("turn-failed")).toBeNull();
  });

  it("treats a message with no status as complete", () => {
    // Every row written before the status column existed has no status.
    render(<ChatMessage message={{ role: "assistant", content: "Câu trả lời cũ" }} />);
    expect(screen.getByText("Câu trả lời cũ")).toBeDefined();
    expect(screen.queryByTestId("turn-pending")).toBeNull();
    expect(screen.queryByTestId("turn-failed")).toBeNull();
  });

  it("never renders a user message as a pending or failed turn", () => {
    render(<ChatMessage message={{ role: "user", content: "Câu hỏi" }} />);
    expect(screen.getByText("Câu hỏi")).toBeDefined();
    expect(screen.queryByTestId("turn-pending")).toBeNull();
    expect(screen.queryByTestId("turn-failed")).toBeNull();
  });
});
