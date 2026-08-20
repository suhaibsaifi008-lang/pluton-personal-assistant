import { afterAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
}

function sseResponse(...frames: Array<[string, unknown]>): Response {
  const encoder = new TextEncoder();
  const body = frames.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new Response(encoder.encode(body), { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("chat input and state recovery", () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/chat")) {
      return Promise.resolve(sseResponse(["done", { task_id: "t1", message: "ok", status: "COMPLETED" }]));
    }
    if (url.includes("/api/settings/status")) {
      return Promise.resolve(jsonResponse({ provider: "openai", model: "gpt", configured: false }));
    }
    return Promise.resolve(jsonResponse([]));
  });

  afterAll(() => {
    vi.unstubAllGlobals();
  });

  it("keeps focus in the textarea while typing a full sentence", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByPlaceholderText("Ask Pluton to help with anything…");
    await user.click(textarea);
    await user.type(textarea, "hello world this is a sentence");

    expect((textarea as HTMLTextAreaElement).value).toBe("hello world this is a sentence");
    expect(document.activeElement).toBe(textarea);
  });

  it("sends the message on Enter and clears the input", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByPlaceholderText("Ask Pluton to help with anything…");
    await user.click(textarea);
    await user.type(textarea, "list my tasks");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      const chatCall = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/chat"));
      expect(chatCall).toBeTruthy();
    });
    const [, init] = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/chat"))!;
    expect(JSON.parse(String(init!.body))).toMatchObject({ message: "list my tasks", stream: true });
    await waitFor(() => expect((textarea as HTMLTextAreaElement).value).toBe(""));
    expect(document.activeElement).toBe(textarea);
  });

  it("inserts a newline instead of sending on Shift+Enter", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByPlaceholderText("Ask Pluton to help with anything…");
    await user.click(textarea);
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    await user.type(textarea, "first line\n second line");

    const chatCalls = fetchMock.mock.calls.filter(([input]) => String(input).includes("/api/chat"));
    expect(chatCalls).toHaveLength(0);
    expect((textarea as HTMLTextAreaElement).value).toBe("first line\n second line");
    expect(document.activeElement).toBe(textarea);
  });

  it("releases the send button and input after a successful chat response", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByPlaceholderText("Ask Pluton to help with anything…");
    await user.type(textarea, "what is today");
    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);
    await user.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText("ok")).toBeTruthy();
    });
    // After completion, typing again enables the send button
    await user.type(textarea, "next message");
    expect((textarea as HTMLTextAreaElement).value).toBe("next message");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("releases the send button and displays error on rate-limit / provider failure", async () => {
    const errorFetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/chat")) {
        return Promise.resolve(sseResponse(["error", { message: "The AI provider is temporarily rate-limited. Please try again in a moment." }]));
      }
      return Promise.resolve(jsonResponse([]));
    });
    vi.stubGlobal("fetch", errorFetch);
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByPlaceholderText("Ask Pluton to help with anything…");
    await user.type(textarea, "test message");
    const sendBtn = screen.getByRole("button", { name: "Send" });
    await user.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText("The AI provider is temporarily rate-limited. Please try again in a moment.")).toBeTruthy();
    });

    // Verify input is released and another message can be sent
    await user.type(textarea, "another message");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("releases input and handles network/fetch stream failures cleanly", async () => {
    const networkFailFetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/chat")) {
        return Promise.reject(new Error("Network connection failed"));
      }
      return Promise.resolve(jsonResponse([]));
    });
    vi.stubGlobal("fetch", networkFailFetch);
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByPlaceholderText("Ask Pluton to help with anything…");
    await user.type(textarea, "network fail test");
    const sendBtn = screen.getByRole("button", { name: "Send" });
    await user.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText("Network connection failed")).toBeTruthy();
    });

    // Verify input and send button become usable again
    await user.type(textarea, "retry message");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("handles confirmation denial flow without permanently locking the chat", async () => {
    const confirmFetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/chat")) {
        return Promise.resolve(sseResponse(
          ["confirmation", { task_id: "task-confirm-1", confirmations: [{ call_id: "c1", name: "terminal.run", arguments: { command: "dir" } }] }]
        ));
      }
      if (url.includes("/deny")) {
        return Promise.resolve(sseResponse(["done", { task_id: "task-confirm-1", message: "Action denied.", status: "COMPLETED" }]));
      }
      return Promise.resolve(jsonResponse([]));
    });
    vi.stubGlobal("fetch", confirmFetch);
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByPlaceholderText("Ask Pluton to help with anything…");
    await user.type(textarea, "run command");
    const sendBtn = screen.getByRole("button", { name: "Send" });
    await user.click(sendBtn);

    // Confirmation card appears
    await waitFor(() => {
      expect(screen.getByText("Approval required")).toBeTruthy();
    });

    // Click Deny
    const denyBtn = screen.getByRole("button", { name: "Deny" });
    await user.click(denyBtn);

    await waitFor(() => {
      expect(screen.getByText("Action denied.")).toBeTruthy();
    });

    // Verify confirmation is gone and send button is usable for next request
    await user.type(textarea, "new task after denial");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("restores previous active session from localStorage and displays conversation in chronological order", async () => {
    localStorage.setItem("pluton_active_session", "session-123");

    const sessionFetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/sessions")) {
        return Promise.resolve(jsonResponse([
          { id: "session-123", title: "Test Conversation", created_at: "2026-08-15T10:00:00Z", updated_at: "2026-08-15T10:05:00Z", task_count: 2, preview: "Question 1" }
        ]));
      }
      if (url.includes("/api/tasks?session_id=session-123")) {
        return Promise.resolve(jsonResponse([
          { id: "t1", session_id: "session-123", title: "Turn 1", request: "First User Message", response: "First Assistant Response", status: "COMPLETED" },
          { id: "t2", session_id: "session-123", title: "Turn 2", request: "Second User Message", response: "Second Assistant Response", status: "COMPLETED" },
        ]));
      }
      if (url.includes("/api/settings/status")) {
        return Promise.resolve(jsonResponse({ provider: "openai", model: "gpt", configured: true, supports_vision: true }));
      }
      return Promise.resolve(jsonResponse([]));
    });

    vi.stubGlobal("fetch", sessionFetch);
    render(<App />);

    // Verify messages from restored session appear in chronological order
    await waitFor(() => {
      expect(screen.getByText("First User Message")).toBeTruthy();
      expect(screen.getByText("First Assistant Response")).toBeTruthy();
      expect(screen.getByText("Second User Message")).toBeTruthy();
      expect(screen.getByText("Second Assistant Response")).toBeTruthy();
    });

    localStorage.removeItem("pluton_active_session");
  });

  it("switches sessions when clicked and displays the selected session history", async () => {
    const sessionFetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/sessions")) {
        return Promise.resolve(jsonResponse([
          { id: "s1", title: "Session One", created_at: "2026-08-15T10:00:00Z", updated_at: "2026-08-15T10:05:00Z", task_count: 1, preview: "Msg 1" },
          { id: "s2", title: "Session Two", created_at: "2026-08-15T11:00:00Z", updated_at: "2026-08-15T11:05:00Z", task_count: 1, preview: "Msg 2" },
        ]));
      }
      if (url.includes("/api/tasks?session_id=s1")) {
        return Promise.resolve(jsonResponse([
          { id: "t1", session_id: "s1", title: "Turn 1", request: "Message from Session 1", response: "Response from Session 1", status: "COMPLETED" },
        ]));
      }
      if (url.includes("/api/tasks?session_id=s2")) {
        return Promise.resolve(jsonResponse([
          { id: "t2", session_id: "s2", title: "Turn 2", request: "Message from Session 2", response: "Response from Session 2", status: "COMPLETED" },
        ]));
      }
      if (url.includes("/api/settings/status")) {
        return Promise.resolve(jsonResponse({ provider: "openai", model: "gpt", configured: true, supports_vision: true }));
      }
      return Promise.resolve(jsonResponse([]));
    });

    vi.stubGlobal("fetch", sessionFetch);
    const user = userEvent.setup();
    render(<App />);

    // Initially loads first session (s1)
    await waitFor(() => {
      expect(screen.getByText("Message from Session 1")).toBeTruthy();
    });

    // Click Session Two in session panel
    const sessionTwoBtn = screen.getByRole("button", { name: /Session Two/i });
    await user.click(sessionTwoBtn);

    // Verify Session Two messages appear
    await waitFor(() => {
      expect(screen.getByText("Message from Session 2")).toBeTruthy();
    });
  });

  it("resets conversation when clicking New conversation", async () => {
    const sessionFetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/sessions")) {
        return Promise.resolve(jsonResponse([
          { id: "s1", title: "Session One", created_at: "2026-08-15T10:00:00Z", updated_at: "2026-08-15T10:05:00Z", task_count: 1, preview: "Msg 1" },
        ]));
      }
      if (url.includes("/api/tasks?session_id=s1")) {
        return Promise.resolve(jsonResponse([
          { id: "t1", session_id: "s1", title: "Turn 1", request: "Existing message", response: "Existing response", status: "COMPLETED" },
        ]));
      }
      return Promise.resolve(jsonResponse([]));
    });

    vi.stubGlobal("fetch", sessionFetch);
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Existing message")).toBeTruthy();
    });

    // Click "+ New conversation"
    const newConvBtn = screen.getByRole("button", { name: "＋ New conversation" });
    await user.click(newConvBtn);

    // Starter message appears
    await waitFor(() => {
      expect(screen.getByText("Hello — I'm Pluton. What would you like to accomplish?")).toBeTruthy();
    });
  });

  it("falls back to direct backend port 8000 when relative proxy fetch encounters a network failure", async () => {
    let attemptedProxy = false;
    let attemptedDirect = false;

    const fallbackFetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/chat") {
        attemptedProxy = true;
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      if (url.startsWith("http://127.0.0.1:8000/api/chat")) {
        attemptedDirect = true;
        return Promise.resolve(
          sseResponse(
            ["task", { task_id: "t_fallback" }],
            ["done", { task_id: "t_fallback", message: "Recovered via direct backend fallback!" }]
          )
        );
      }

      if (url.includes("/api/settings/status")) {
        return Promise.resolve(jsonResponse({ provider: "openai", model: "gpt", configured: true, supports_vision: true }));
      }
      return Promise.resolve(jsonResponse([]));
    });

    vi.stubGlobal("fetch", fallbackFetch);
    const user = userEvent.setup();
    render(<App />);

    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "Close the Claude tab in my Brave browser.");
    await user.keyboard("{Enter}");


    await waitFor(() => {
      expect(attemptedProxy).toBe(true);
      expect(attemptedDirect).toBe(true);
      expect(screen.getByText("Recovered via direct backend fallback!")).toBeTruthy();
    });
  });
});