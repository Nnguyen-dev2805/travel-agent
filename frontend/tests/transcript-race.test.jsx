/**
 * C3/C4: a resolved response must only be applied to the conversation it was
 * requested for.
 *
 * C3 — the assistant reply was appended to whichever conversation was open.
 * C4 — an out-of-order history load overwrote the newer conversation's
 * transcript.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  listConversations: vi.fn(),
  listMessages: vi.fn(),
  postChatMessage: vi.fn(),
  deleteConversation: vi.fn(),
}));

vi.mock("../src/services/auth", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, isAuthenticated: () => true, clearToken: vi.fn() };
});

vi.mock("../src/services/chat", () => ({
  listConversations: mocks.listConversations,
  listMessages: mocks.listMessages,
  postChatMessage: mocks.postChatMessage,
  deleteConversation: mocks.deleteConversation,
}));

import App from "../src/App";

const CONVERSATIONS = [
  { conversation_id: "a", title: "Conv A" },
  { conversation_id: "b", title: "Conv B" },
];

function flush() {
  // `act` so React observes the state updates the awaited microtasks produce —
  // the resolved send/history promises update App state outside React's event
  // handlers, and without this wrapper those updates warn and, worse, race the
  // assertions in exactly the tests whose subject is async correctness.
  return act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("transcript race guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom does not implement scrollIntoView; ChatPanel calls it on mount.
    Element.prototype.scrollIntoView = vi.fn();
    mocks.listConversations.mockResolvedValue(CONVERSATIONS);
    mocks.listMessages.mockResolvedValue([]);
    mocks.deleteConversation.mockResolvedValue(undefined);
  });

  it("does not write a reply into a conversation the user has left", async () => {
    let resolveSend;
    mocks.postChatMessage.mockReturnValue(
      new Promise((resolve) => {
        resolveSend = resolve;
      })
    );

    render(<App />);
    await waitFor(() => expect(screen.getByText("Conv A")).toBeTruthy());

    fireEvent.click(screen.getByText("Conv A"));
    await waitFor(() => expect(mocks.listMessages).toHaveBeenCalledWith("a"));

    fireEvent.change(screen.getByLabelText("Nội dung câu hỏi"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await waitFor(() => expect(mocks.postChatMessage).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Conv B"));
    await waitFor(() => expect(mocks.listMessages).toHaveBeenCalledWith("b"));

    resolveSend({
      reply: "A REPLY",
      citations: [],
      conversation: { conversation_id: "a" },
    });
    await flush();

    expect(screen.queryByText("A REPLY")).toBeNull();
  });

  it("ignores a history response that resolves after a newer selection", async () => {
    let resolveSlowHistory;
    mocks.listMessages.mockImplementation((convId) =>
      convId === "a"
        ? new Promise((resolve) => {
            resolveSlowHistory = resolve;
          })
        : Promise.resolve([
            { message_id: "b1", role: "user", content: "B MESSAGE" },
          ])
    );

    render(<App />);
    await waitFor(() => expect(screen.getByText("Conv A")).toBeTruthy());

    fireEvent.click(screen.getByText("Conv A"));
    fireEvent.click(screen.getByText("Conv B"));

    await waitFor(() => expect(screen.getByText("B MESSAGE")).toBeTruthy());

    resolveSlowHistory([
      { message_id: "a1", role: "user", content: "A MESSAGE" },
    ]);
    await flush();

    expect(screen.queryByText("A MESSAGE")).toBeNull();
    expect(screen.getByText("B MESSAGE")).toBeTruthy();
  });

  it("re-enables the composer after a discarded send", async () => {
    let resolveSend;
    mocks.postChatMessage.mockReturnValue(
      new Promise((resolve) => {
        resolveSend = resolve;
      })
    );

    render(<App />);
    await waitFor(() => expect(screen.getByText("Conv A")).toBeTruthy());

    fireEvent.click(screen.getByText("Conv A"));
    await waitFor(() => expect(mocks.listMessages).toHaveBeenCalledWith("a"));

    fireEvent.change(screen.getByLabelText("Nội dung câu hỏi"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));

    fireEvent.click(screen.getByText("Conv B"));
    resolveSend({
      reply: "A REPLY",
      citations: [],
      conversation: { conversation_id: "a" },
    });
    await flush();

    const textarea = screen.getByLabelText("Nội dung câu hỏi");
    expect(textarea.disabled).toBe(false);
  });

  // C2 frontend half: a first-turn generation failure returns 500 with the
  // conversation_id the backend already committed (ADR 0023). The interceptor
  // preserves the body on `err.data`, so the client can bind to that
  // conversation and retry into it instead of auto-creating a phantom second
  // one. Without this, the defect ADR 0023 fixed server-side still exists
  // end-to-end.
  it("binds the conversation the backend returned on a first-turn failure", async () => {
    const generationError = new Error("Chat generation failed.");
    generationError.status = 500;
    generationError.data = {
      detail: "Chat generation failed.",
      conversation_id: "cv_survived",
    };
    // mockImplementation (not mockRejectedValueOnce): the second send in this
    // test is the retry, and it failing the same way is part of the scenario.
    mocks.postChatMessage.mockImplementation(() =>
      Promise.reject(generationError)
    );

    render(<App />);
    await waitFor(() => expect(screen.getByText("Conv A")).toBeTruthy());

    // No conversation selected: this is the first turn of a new chat.
    fireEvent.change(screen.getByLabelText("Nội dung câu hỏi"), {
      target: { value: "first message" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await waitFor(() =>
      expect(screen.getByText(/Chat generation failed/i)).toBeTruthy()
    );

    // The retry must go to cv_survived, not auto-create another conversation.
    fireEvent.change(screen.getByLabelText("Nội dung câu hỏi"), {
      target: { value: "retry message" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await waitFor(() => expect(mocks.postChatMessage).toHaveBeenCalledTimes(2));

    expect(mocks.postChatMessage).toHaveBeenLastCalledWith({
      message: "retry message",
      conversation_id: "cv_survived",
    });
  });

  it("keeps the already-bound conversation when a later turn fails", async () => {
    const generationError = new Error("Chat generation failed.");
    generationError.status = 500;
    generationError.data = {
      detail: "Chat generation failed.",
      conversation_id: "a", // the conversation the turn was bound to
    };
    mocks.postChatMessage.mockImplementation(() =>
      Promise.reject(generationError)
    );

    render(<App />);
    await waitFor(() => expect(screen.getByText("Conv A")).toBeTruthy());

    fireEvent.click(screen.getByText("Conv A"));
    await waitFor(() => expect(mocks.listMessages).toHaveBeenCalledWith("a"));

    fireEvent.change(screen.getByLabelText("Nội dung câu hỏi"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await waitFor(() =>
      expect(screen.getByText(/Chat generation failed/i)).toBeTruthy()
    );

    // A failure on a bound turn must not rebind away from the conversation the
    // user is looking at, even when the error body carries the same id.
    fireEvent.change(screen.getByLabelText("Nội dung câu hỏi"), {
      target: { value: "again" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await waitFor(() => expect(mocks.postChatMessage).toHaveBeenCalledTimes(2));

    expect(mocks.postChatMessage).toHaveBeenLastCalledWith({
      message: "again",
      conversation_id: "a",
    });
  });
});
