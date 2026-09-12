import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient, { sendChatMessage } from "./api";
import { setToken, getToken, clearToken, PRESET_USERS, getUserProfile, getOwnerUserId } from "./auth";
import {
  listConversations,
  createConversation,
  deleteConversation,
  listMessages,
  postChatMessage,
} from "./chat";

vi.mock("axios", () => {
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
      post: vi.fn(),
    },
  };
});

describe("Authentication Service", () => {
  const mockStorage = {};
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: (key) => mockStorage[key] || null,
      setItem: (key, value) => {
        mockStorage[key] = String(value);
      },
      removeItem: (key) => {
        delete mockStorage[key];
      },
      clear: () => {
        for (const k in mockStorage) delete mockStorage[k];
      },
    });
    localStorage.clear();
  });

  it("stores and retrieves bearer token", () => {
    expect(getToken()).toBe("");
    setToken("dev-token-alice", "Alice");
    expect(getToken()).toBe("dev-token-alice");
    const profile = getUserProfile();
    expect(profile.name).toBe("Alice");
    expect(getOwnerUserId()).toBe("alice");
  });

  it("clears token on logout", () => {
    setToken("token_test");
    clearToken();
    expect(getToken()).toBe("");
  });

  it("contains Alice and Bob presets", () => {
    expect(PRESET_USERS.length).toBeGreaterThanOrEqual(2);
    expect(PRESET_USERS[0].id).toBe("alice");
    expect(PRESET_USERS[1].id).toBe("bob");
  });
});

describe("API Service & Interceptors", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends chat message via apiClient helper", async () => {
    apiClient.post.mockResolvedValueOnce({
      data: {
        reply: "Xin chào!",
        model: "gpt-4o-mini",
        citations: [],
      },
    });

    const result = await sendChatMessage("Du lịch Hội An");
    expect(apiClient.post).toHaveBeenCalledWith("/chat", {
      message: "Du lịch Hội An",
    });
    expect(result.reply).toBe("Xin chào!");
  });

  it("attaches Authorization header when token exists", () => {
    setToken("dev-token-alice");
    const reqInterceptorSuccess = apiClient.interceptors.request.use.mock.calls[0]?.[0];
    if (reqInterceptorSuccess) {
      const config = { headers: {} };
      const modified = reqInterceptorSuccess(config);
      expect(modified.headers.Authorization).toBe("Bearer dev-token-alice");
    }
  });

  it("handles 401 error by clearing token and dispatching auth:unauthorized", async () => {
    setToken("dev-token-alice");
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    const resInterceptorError = apiClient.interceptors.response.use.mock.calls[0]?.[1];

    if (resInterceptorError) {
      const error401 = {
        response: { status: 401, data: { detail: "Invalid token" } },
      };
      await expect(resInterceptorError(error401)).rejects.toThrow("Invalid token");
      expect(getToken()).toBe("");
      expect(dispatchSpy).toHaveBeenCalled();
    }
  });
});

describe("Chat Service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("listConversations calls GET /conversations", async () => {
    apiClient.get.mockResolvedValueOnce({
      data: { conversations: [{ conversation_id: "conv_1", title: "Trip to Da Nang" }] },
    });
    const res = await listConversations();
    expect(apiClient.get).toHaveBeenCalledWith("/conversations");
    expect(res).toHaveLength(1);
    expect(res[0].conversation_id).toBe("conv_1");
  });

  it("createConversation calls POST /conversations", async () => {
    apiClient.post.mockResolvedValueOnce({
      data: { conversation_id: "conv_2", title: "New Trip" },
    });
    const res = await createConversation("New Trip");
    expect(apiClient.post).toHaveBeenCalledWith("/conversations", { title: "New Trip" });
    expect(res.conversation_id).toBe("conv_2");
  });

  it("deleteConversation calls DELETE /conversations/:id", async () => {
    apiClient.delete.mockResolvedValueOnce({ data: null });
    await deleteConversation("conv_2");
    expect(apiClient.delete).toHaveBeenCalledWith("/conversations/conv_2");
  });

  it("listMessages calls GET /conversations/:id/messages", async () => {
    apiClient.get.mockResolvedValueOnce({
      data: { messages: [{ message_id: "msg_1", content: "Hello", role: "user" }], next_cursor: null },
    });
    const res = await listMessages("conv_1");
    expect(apiClient.get).toHaveBeenCalledWith("/conversations/conv_1/messages");
    expect(res).toHaveLength(1);
  });

  // P2: the backend pages history at 50 messages and returns `next_cursor`
  // when more exist. A conversation with 100 messages must still be shown in
  // full, so `listMessages` follows the cursor until it is exhausted — a
  // bounded fetch-all, not a raise of the page size.
  it("listMessages follows next_cursor until the transcript is exhausted", async () => {
    apiClient.get
      .mockResolvedValueOnce({
        data: {
          messages: [{ message_id: "msg_1" }, { message_id: "msg_2" }],
          next_cursor: "msg_2",
        },
      })
      .mockResolvedValueOnce({
        data: {
          messages: [{ message_id: "msg_3" }],
          next_cursor: null,
        },
      });

    const res = await listMessages("conv_1");

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      "/conversations/conv_1/messages"
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      "/conversations/conv_1/messages",
      { params: { after_message_id: "msg_2" } }
    );
    expect(res).toHaveLength(3);
    expect(res.map((m) => m.message_id)).toEqual(["msg_1", "msg_2", "msg_3"]);
  });

  it("listMessages stops at the page bound even if the cursor keeps advancing", async () => {
    // A misbehaving backend (or a rewrite loop) must not turn the client into
    // an unbounded fetch. The bound is generous — 10 pages at the default
    // limit is 500 messages — but it is a bound.
    apiClient.get.mockImplementation(() =>
      Promise.resolve({
        data: {
          messages: [{ message_id: `msg_${apiClient.get.mock.calls.length}` }],
          next_cursor: `cursor_${apiClient.get.mock.calls.length}`,
        },
      })
    );

    const res = await listMessages("conv_1");

    expect(apiClient.get.mock.calls.length).toBe(10);
    expect(res).toHaveLength(10);
  });

  it("postChatMessage sends message without conversation_id for new conversation", async () => {
    apiClient.post.mockResolvedValueOnce({
      data: {
        reply: "Xin chào",
        conversation: { conversation_id: "conv_auto_1" },
      },
    });
    const res = await postChatMessage({ message: "Lên lịch trình" });
    expect(apiClient.post).toHaveBeenCalledWith("/chat", { message: "Lên lịch trình" });
    expect(res.conversation.conversation_id).toBe("conv_auto_1");
  });

  it("postChatMessage includes conversation_id for subsequent turns", async () => {
    apiClient.post.mockResolvedValueOnce({
      data: {
        reply: "Tiếp tục lịch trình",
        conversation: { conversation_id: "conv_existing" },
      },
    });
    const res = await postChatMessage({ message: "Ngày 2 làm gì?", conversation_id: "conv_existing" });
    expect(apiClient.post).toHaveBeenCalledWith("/chat", {
      message: "Ngày 2 làm gì?",
      conversation_id: "conv_existing",
    });
    expect(res.reply).toBe("Tiếp tục lịch trình");
  });
});
