import { FormEvent, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { cancelTask, emergencyStop, getDebugRuntime, getRuntimeHealth, getRuntimeVersion, request, streamJson } from "./api";
import type {
  Activity,
  Confirmation,
  Diagnostics,
  Memory,
  Message,
  ProviderStatus,
  RuntimeIdentity,
  Session,
  Task,
  TaskState,
  ToolInfo,
  View,
} from "./types";

const starter: Message = {
  role: "assistant",
  text: "Hello — I'm Pluton. What would you like to accomplish?",
};

function App() {
  const [view, setView] = useState<View>("conversations");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([starter]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentTaskState, setCurrentTaskState] = useState<TaskState | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [confirmations, setConfirmations] = useState<Confirmation[]>([]);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryText, setMemoryText] = useState("");
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeIdentity | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const loadSessions = async () => {
    const list = await request<Session[]>("/sessions");
    setSessions(list);
    return list;
  };
  const loadTasks = async () => setTasks(await request<Task[]>("/tasks"));
  const loadMemories = async () => setMemories(await request<Memory[]>("/memories"));

  const loadRuntime = async () => {
    try {
      const [ver, health, debug] = await Promise.all([
        getRuntimeVersion().catch(() => null),
        getRuntimeHealth().catch(() => null),
        getDebugRuntime().catch(() => null),
      ]);
      if (ver || health || debug) {
        setRuntimeInfo({ ...ver, ...health, ...debug });
      }
    } catch {
      setRuntimeInfo(null);
    }
  };

  useEffect(() => {
    void request<ProviderStatus>("/settings/status").then(setProvider).catch(() => setProvider(null));
    void request<ToolInfo[]>("/tools").then(setTools).catch(() => setTools([]));
    void loadRuntime();
    void loadSessions().then((loaded) => {
      let savedId: string | null = null;
      try {
        savedId = localStorage.getItem("pluton_active_session");
      } catch {}
      if (savedId && loaded.some((s) => s.id === savedId)) {
        void selectSession(savedId);
      } else if (loaded.length > 0) {
        void selectSession(loaded[0].id);
      }
    }).catch(() => setSessions([]));
  }, []);

  useEffect(() => {
    if (view === "tasks") void loadTasks();
    if (view === "memory") void loadMemories();
    if (view === "conversations") {
      void loadSessions();
      void loadRuntime();
    }
  }, [view]);

  function appendDelta(old: Message[], delta: string): Message[] {
    const next = [...old];
    const last = next[next.length - 1];
    if (last && last.role === "assistant") next[next.length - 1] = { ...last, role: "assistant", text: last.text + delta };
    else next.push({ role: "assistant", text: delta });
    return next;
  }

  function handleEvent(event: string, data: any) {
    switch (event) {
      case "session":
        setActiveSessionId(data.session_id as string);
        try {
          localStorage.setItem("pluton_active_session", data.session_id as string);
        } catch {}
        break;
      case "task":
        setActiveTaskId(data.task_id as string);
        setCurrentTaskState("PLANNING");
        break;
      case "text":
        setMessages((old) => appendDelta(old, data.delta as string));
        break;
      case "activity":
        setActivities((old) => {
          const act = data as Activity;
          if (act.diagnostics?.state) {
            setCurrentTaskState(act.diagnostics.state);
          }
          return [...old, act];
        });
        break;
      case "confirmation":
        setPendingTaskId(data.task_id as string);
        setCurrentTaskState("AWAITING_APPROVAL");
        setConfirmations(data.confirmations as Confirmation[]);
        break;
      case "done":
        setCurrentTaskState((data.status as TaskState) || "COMPLETED");
        setMessages((old) => {
          const next = [...old];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") {
            next[next.length - 1] = {
              ...last,
              role: "assistant",
              text: (data.message as string) || last.text,
              state: data.status as TaskState,
              task_id: data.task_id as string,
            };
          } else {
            next.push({
              role: "assistant",
              text: data.message as string,
              state: data.status as TaskState,
              task_id: data.task_id as string,
            });
          }
          return next;
        });
        setConfirmations([]);
        setPendingTaskId(null);
        void loadSessions();
        void loadRuntime();
        break;
      case "error":
        setCurrentTaskState("FAILED");
        setMessages((old) => {
          const next = [...old];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") {
            next[next.length - 1] = {
              ...last,
              role: "assistant",
              text: (data.message as string) || "Task execution failed.",
              state: "FAILED",
              error: data.message as string,
            };
          } else {
            next.push({
              role: "assistant",
              text: (data.message as string) || "Task execution failed.",
              state: "FAILED",
              error: data.message as string,
            });
          }
          return next;
        });
        setConfirmations([]);
        setPendingTaskId(null);
        void loadSessions();
        void loadRuntime();
        break;
    }
  }

  async function selectSession(id: string) {
    setActiveSessionId(id);
    try {
      localStorage.setItem("pluton_active_session", id);
    } catch {}
    setActivities([]);
    setConfirmations([]);
    setPendingTaskId(null);
    setCurrentTaskState(null);
    try {
      const items = await request<Task[]>("/tasks?session_id=" + encodeURIComponent(id));
      const built: Message[] = [];
      for (const task of items) {
        built.push({ role: "user", text: task.request, task_id: task.id });
        if (task.response) {
          built.push({
            role: "assistant",
            text: task.response,
            task_id: task.id,
            state: task.status as TaskState,
          });
        }
        if (task.status === "CONFIRMING") {
          const pending = await request<{ confirmations: Confirmation[] }>(`/tasks/${task.id}/confirmations`).catch(() => ({ confirmations: [] }));
          if (pending.confirmations.length) {
            setPendingTaskId(task.id);
            setConfirmations(pending.confirmations);
            setCurrentTaskState("AWAITING_APPROVAL");
          }
        }
      }
      if (built.length) setMessages(built);
      else setMessages([starter]);
    } catch {
      setMessages([starter]);
    }
  }

  function newTask() {
    setActiveSessionId(null);
    try {
      localStorage.removeItem("pluton_active_session");
    } catch {}
    setMessages([starter]);
    setActivities([]);
    setConfirmations([]);
    setPendingTaskId(null);
    setCurrentTaskState(null);
    setActiveTaskId(null);
    setInput("");
    setView("conversations");
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const value = input.trim();
    if (!value || busy) return;
    setInput("");
    setBusy(true);
    setCurrentTaskState("CREATED");
    setActivities([]);
    setConfirmations([]);
    setPendingTaskId(null);
    setMessages((old) => [...old, { role: "user", text: value }, { role: "assistant", text: "", state: "PLANNING" }]);

    abortControllerRef.current = new AbortController();

    try {
      await streamJson("/chat", { message: value, session_id: activeSessionId, stream: true }, handleEvent, abortControllerRef.current.signal);
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : "Something went wrong.";
      setCurrentTaskState("FAILED");
      setMessages((old) => {
        const next = [...old];
        const last = next[next.length - 1];
        if (last && last.role === "assistant" && !last.text) {
          next[next.length - 1] = { ...last, role: "assistant", text: errMsg, state: "FAILED", error: errMsg };
        } else {
          next.push({ role: "assistant", text: errMsg, state: "FAILED", error: errMsg });
        }
        return next;
      });
      setConfirmations([]);
      setPendingTaskId(null);
    } finally {
      setBusy(false);
      abortControllerRef.current = null;
      void loadSessions();
      void loadRuntime();
    }
  }

  async function handleCancelTask() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (activeTaskId) {
      try {
        await cancelTask(activeTaskId);
      } catch {}
    }
    setBusy(false);
    setCurrentTaskState("CANCELLED");
    setConfirmations([]);
    setPendingTaskId(null);
  }

  async function handleEmergencyStop() {
    try {
      await emergencyStop();
    } catch {}
    await handleCancelTask();
  }

  async function respondToConfirmation(approved: boolean) {
    if (!pendingTaskId || busy) return;
    const currentTaskId = pendingTaskId;
    setBusy(true);
    setCurrentTaskState(approved ? "EXECUTING" : "CANCELLED");
    setConfirmations([]);
    setPendingTaskId(null);
    try {
      await streamJson(`/tasks/${currentTaskId}/${approved ? "approve" : "deny"}`, { stream: true }, handleEvent);
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : "Something went wrong.";
      setCurrentTaskState("FAILED");
      setMessages((old) => {
        const next = [...old];
        const last = next[next.length - 1];
        if (last && last.role === "assistant" && !last.text) {
          next[next.length - 1] = { ...last, role: "assistant", text: errMsg, state: "FAILED", error: errMsg };
        } else {
          next.push({ role: "assistant", text: errMsg, state: "FAILED", error: errMsg });
        }
        return next;
      });
    } finally {
      setBusy(false);
      void loadSessions();
      void loadRuntime();
    }
  }

  async function saveMemory(event: FormEvent) {
    event.preventDefault();
    if (!memoryText.trim()) return;
    await request<Memory>("/memories", { method: "POST", body: JSON.stringify({ content: memoryText.trim() }) });
    setMemoryText("");
    await loadMemories();
  }

  async function removeMemory(id: string) {
    await request<void>(`/memories/${id}`, { method: "DELETE" });
    await loadMemories();
  }

  async function removeSession(id: string) {
    await request<void>(`/sessions/${id}`, { method: "DELETE" });
    if (activeSessionId === id) newTask();
    await loadSessions();
  }

  const [showActivity, setShowActivity] = useState(false);
  const [showSessions, setShowSessions] = useState(true);

  return (
    <main className={`shell ${showActivity ? "with-activity" : "without-activity"}`}>
      <aside className="sidebar">
        <div className="brand">
          <span>✦</span> PLUTON <small className="v2-tag">V2</small>
        </div>
        <button className="new" onClick={newTask}>
          ＋ New task
        </button>
        <button className="emergency-stop-btn" onClick={handleEmergencyStop} title="Instantly halt all computer input, revoke tokens, and cancel active workers">
          🛑 EMERGENCY STOP
        </button>
        <nav aria-label="PLUTON navigation">
          <Nav active={view === "conversations"} onClick={() => setView("conversations")}>◈ Conversations</Nav>
          <Nav active={view === "tasks"} onClick={() => setView("tasks")}>✓ Tasks</Nav>
          <Nav active={view === "automations"} onClick={() => setView("automations")}>↻ Automations</Nav>
          <Nav active={view === "memory"} onClick={() => setView("memory")}>◇ Memory</Nav>
          <Nav active={view === "settings"} onClick={() => setView("settings")}>⚙ Settings</Nav>
        </nav>
        <div className="sidebar-toggle-group">
          <button
            type="button"
            className={`quiet-toggle-btn ${showActivity ? "active" : ""}`}
            onClick={() => setShowActivity((prev) => !prev)}
            title="Toggle Activity & Telemetry sidebar"
          >
            ⚡ {showActivity ? "Hide Telemetry" : "Telemetry"}
          </button>
        </div>
        <div className="sidebar-footer">
          <strong>Universal Computer Control</strong>
          <br />
          <span className="mono-sub">Build: {runtimeInfo?.build_id || "v2-phase1"}</span>
          <br />
          <span className="mono-sub">Tiers 1-6 Active</span>
        </div>
      </aside>

      <section className="workspace">
        {view === "conversations" && (
          <Conversations
            sessions={sessions}
            activeSessionId={activeSessionId}
            messages={messages}
            input={input}
            busy={busy}
            currentTaskState={currentTaskState}
            provider={provider}
            runtimeInfo={runtimeInfo}
            confirmations={confirmations}
            showDiagnostics={showDiagnostics}
            onToggleDiagnostics={() => setShowDiagnostics((prev) => !prev)}
            onInput={setInput}
            onSelectSession={selectSession}
            onNewTask={newTask}
            onRemoveSession={removeSession}
            onSend={send}
            onCancel={handleCancelTask}
            onEmergencyStop={handleEmergencyStop}
            onRespondConfirmation={respondToConfirmation}
          />
        )}
        {view === "tasks" && <Tasks tasks={tasks} />}
        {view === "automations" && <Automations />}
        {view === "memory" && <Memories memories={memories} text={memoryText} onText={setMemoryText} onSave={saveMemory} onDelete={removeMemory} />}
        {view === "settings" && <Settings provider={provider} tools={tools} runtimeInfo={runtimeInfo} />}
      </section>

      <aside className="activity">
        <div className="activity-header">
          <p className="eyebrow">CANONICAL ACTIVITY TIMELINE</p>
          {currentTaskState && (
            <span className={`task-state-badge ${currentTaskState.toLowerCase()}`}>
              {currentTaskState}
            </span>
          )}
        </div>

        {view === "conversations" && activities.length ? (
          <div className="timeline-container">
            {activities.map((item, idx) => (
              <TimelineItem key={`${item.name}-${idx}`} activity={item} />
            ))}
          </div>
        ) : (
          <p className="muted">
            {view === "conversations"
              ? "Verified computer control telemetry will appear here in real time."
              : "Select a section to manage your local PLUTON foundation."}
          </p>
        )}

        <div className="diagnostics-summary">
          <div className="diag-row">
            <span>Kernel Token:</span>
            <strong className="text-emerald">{busy || currentTaskState ? "AUTHORIZED" : "STANDBY"}</strong>
          </div>
          <div className="diag-row">
            <span>Browser Link:</span>
            <strong>{runtimeInfo?.browser_detected ? "ATTACHED (Brave)" : "STANDALONE"}</strong>
          </div>
          <div className="diag-row">
            <span>Verification:</span>
            <strong>MANDATORY</strong>
          </div>
        </div>

        <div className="guardrail">
          <strong>Security Kernel Active</strong>
          <span>Zero computer input permitted without an active authorized task token.</span>
        </div>
      </aside>
    </main>
  );
}

function TimelineItem({ activity }: { activity: Activity }) {
  const [open, setOpen] = useState(false);
  const diag = activity.diagnostics || {};
  const isFailed = activity.status === "failed" || diag.error;
  const isVerified = activity.status === "completed" || activity.status === "verified" || diag.verified === true;

  return (
    <div className={`activity-card ${isFailed ? "failed" : isVerified ? "verified" : "executing"}`}>
      <div className="activity-card-header">
        <span className="activity-name">{activity.name}</span>
        <span className={`pill-mini ${isFailed ? "failed" : isVerified ? "completed" : "executing"}`}>
          {isFailed ? "VERIFICATION FAILED" : isVerified ? "VERIFIED" : "EXECUTING"}
        </span>
      </div>
      <p className="activity-summary">{activity.summary}</p>

      <div className="activity-meta">
        {diag.execution_tier && <span className="meta-tag">Tier {diag.execution_tier}</span>}
        {diag.execution_strategy && <span className="meta-tag">{diag.execution_strategy}</span>}
        {diag.latency_ms && <span className="meta-tag">{Math.round(diag.latency_ms)}ms</span>}
      </div>

      <button className="diag-toggle" onClick={() => setOpen((prev) => !prev)}>
        {open ? "▲ Hide Details" : "▼ Diagnostics"}
      </button>

      {open && (
        <div className="diag-panel">
          {diag.task_id && <div><span>Task ID:</span> <code>{diag.task_id}</code></div>}
          {diag.capability && <div><span>Capability:</span> <code>{diag.capability}</code></div>}
          {diag.target && <div><span>Target:</span> <code>{diag.target}</code></div>}
          {diag.verification_strategy && <div><span>Strategy:</span> <code>{diag.verification_strategy}</code></div>}
          {diag.browser_hwnd && <div><span>HWND:</span> <code>{diag.browser_hwnd}</code></div>}
          {diag.browser_pid && <div><span>PID:</span> <code>{diag.browser_pid}</code></div>}
          {diag.error && <div className="text-danger"><span>Error:</span> {diag.error}</div>}
        </div>
      )}
    </div>
  );
}

type ConversationsProps = {
  sessions: Session[];
  activeSessionId: string | null;
  messages: Message[];
  input: string;
  busy: boolean;
  currentTaskState: TaskState | null;
  provider: ProviderStatus | null;
  runtimeInfo: RuntimeIdentity | null;
  confirmations: Confirmation[];
  showDiagnostics: boolean;
  onToggleDiagnostics: () => void;
  onInput: (value: string) => void;
  onSelectSession: (id: string) => void;
  onNewTask: () => void;
  onRemoveSession: (id: string) => void;
  onSend: (event: FormEvent) => void;
  onCancel: () => void;
  onEmergencyStop: () => void;
  onRespondConfirmation: (approved: boolean) => void;
};

function Conversations({
  sessions,
  activeSessionId,
  messages,
  input,
  busy,
  currentTaskState,
  provider,
  runtimeInfo,
  confirmations,
  showDiagnostics,
  onToggleDiagnostics,
  onInput,
  onSelectSession,
  onNewTask,
  onRemoveSession,
  onSend,
  onCancel,
  onEmergencyStop,
  onRespondConfirmation,
}: ConversationsProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  const handleScroll = () => {
    if (!conversationRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = conversationRef.current;
    isNearBottomRef.current = scrollHeight - scrollTop - clientHeight < 150;
  };

  useEffect(() => {
    if (isNearBottomRef.current && conversationRef.current) {
      if (typeof conversationRef.current.scrollTo === "function") {
        conversationRef.current.scrollTo({
          top: conversationRef.current.scrollHeight,
          behavior: "smooth",
        });
      } else {
        conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
      }
    }
  }, [messages, busy, confirmations]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      formRef.current?.requestSubmit();
    }
  }

  return (
    <div className="chat-layout">
      <aside className="session-panel">
        <button className="session-new" onClick={onNewTask}>
          ＋ New conversation
        </button>
        {sessions.map((session) => (
          <div className="session-row" key={session.id}>
            <button
              className={`session-item ${session.id === activeSessionId ? "active" : ""}`}
              onClick={() => onSelectSession(session.id)}
            >
              <strong>{session.title}</strong>
              <span>{session.task_count} message{session.task_count === 1 ? "" : "s"}</span>
            </button>
            <button className="session-delete" title="Delete conversation" onClick={() => onRemoveSession(session.id)}>
              ×
            </button>
          </div>
        ))}
        {!sessions.length && <p className="muted">No conversations yet. Start one below.</p>}
      </aside>

      <section className="chat-panel">
        <PageHeader
          eyebrow="UNIVERSAL COMPUTER CONTROL"
          title="Canonical Desktop Substrate"
          subtitle="Real-world computer automation across applications, browsers, tabs, keyboard, and filesystem."
          runtimeInfo={runtimeInfo}
        />

        {!provider?.configured && (
          <div className="setup-banner">
            <strong>Provider required</strong>
            <span>
              PLUTON's real agent is ready, but needs <code>{provider?.provider?.toLowerCase() === "freellmapi" ? "PLUTON_FREELLMAPI_API_KEY" : "PLUTON_OPENAI_API_KEY"}</code> in <code>.env</code> before it can answer.
            </span>
          </div>
        )}

        <div className="conversation" ref={conversationRef} onScroll={handleScroll}>
          {messages.map((message, index) => (
            <article key={index} className={`message ${message.role}`}>
              <div className="avatar">{message.role === "assistant" ? "P" : "You"}</div>
              <div className="message-body">
                <p>{message.text}</p>
                {message.state && (
                  <div className="message-footer">
                    <span className={`task-state-badge-inline ${message.state.toLowerCase()}`}>
                      {message.state}
                    </span>
                    {message.task_id && <span className="task-id-tag">Task: {message.task_id.slice(0, 8)}</span>}
                  </div>
                )}
              </div>
            </article>
          ))}

          {confirmations.length > 0 && (
            <ConfirmationCard
              confirmations={confirmations}
              busy={busy}
              onApprove={() => onRespondConfirmation(true)}
              onDeny={() => onRespondConfirmation(false)}
            />
          )}

          {busy && !confirmations.length && (
            <article className="message assistant">
              <div className="avatar">P</div>
              <div className="message-body">
                <p className="typing">
                  {currentTaskState === "PLANNING" ? "Planning deterministic capability path…" : "Executing & verifying state transition…"}
                </p>
                <div className="busy-controls">
                  <span className="task-state-badge-inline executing">{currentTaskState || "EXECUTING"}</span>
                  <button type="button" className="cancel-task-btn" onClick={onCancel}>
                    ⏹ Stop Task
                  </button>
                </div>
              </div>
            </article>
          )}
        </div>

        {/* Live Task Status Bar & Emergency Stop */}
        <div className="task-status-bar">
          <div className="status-info">
            <span className={`status-indicator ${busy ? (currentTaskState?.toLowerCase() || "executing") : "idle"}`} />
            <span className="status-label">
              {busy ? (currentTaskState || "EXECUTING") : "READY (ZERO INPUT INVARIANT ACTIVE)"}
            </span>
          </div>
          <div className="status-controls">
            {busy ? (
              <button type="button" className="emergency-stop-btn" onClick={onEmergencyStop}>
                ⏹ EMERGENCY STOP ALL
              </button>
            ) : (
              <span className="security-tag">PHYSICAL I/O LOCKED</span>
            )}
          </div>
        </div>

        <form ref={formRef} onSubmit={onSend} className="sticky-composer">
          <textarea
            value={input}
            onChange={(event) => onInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Pluton to help with anything…"
            rows={2}
          />
          <div className="form-actions">
            {busy && (
              <button type="button" className="cancel-btn-primary" onClick={onCancel}>
                ⏹ Stop
              </button>
            )}
            <button disabled={busy || !input.trim() || confirmations.length > 0}>
              {busy ? "Working…" : "Send"}
            </button>
          </div>
          <div className="form-footer">
            <small>PLUTON V2 Brahma-Style Universal Loop · Zero Unverified Success</small>
            <button type="button" className="diag-global-btn" onClick={onToggleDiagnostics}>
              {showDiagnostics ? "Hide Diagnostics" : "Developer Diagnostics"}
            </button>
          </div>
        </form>

        {showDiagnostics && (
          <div className="developer-diagnostics-drawer">
            <h4>DEVELOPER RUNTIME DIAGNOSTICS</h4>
            <div className="diag-grid">
              <div><span>Runtime Build:</span> <code>{runtimeInfo?.build_id || "v2-phase1"}</code></div>
              <div><span>Live Server PID:</span> <code>{runtimeInfo?.pid || "Direct"}</code></div>
              <div><span>Active Status:</span> <code>{runtimeInfo?.status || "ok"}</code></div>
              <div><span>UIA Query Method:</span> <code>{runtimeInfo?.has_find_elements_by_query ? "VERIFIED (Present)" : "Unknown"}</code></div>
              <div><span>Browser Engine:</span> <code>{runtimeInfo?.browser_engine_class || "BrowserEngine"}</code></div>
              <div><span>Web Resolver:</span> <code>Semantic DOM (5-Tier) / UIA Tree</code></div>
              <div><span>Tiers:</span> <code>1 (Native API), 2 (CDP/DOM), 3 (UIA), 4 (Input), 5 (Vision)</code></div>
              <div><span>Browser Identity:</span> <code>MATCHED (Visible Tab Bound)</code></div>
              <div><span>Verification Gate:</span> <code>Pre/Post-State Readback</code></div>
              <div><span>Target Resolver:</span> <code>Canonical (Exact → Contextual)</code></div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ConfirmationCard({
  confirmations,
  busy,
  onApprove,
  onDeny,
}: {
  confirmations: Confirmation[];
  busy: boolean;
  onApprove: () => void;
  onDeny: () => void;
}) {
  return (
    <div className="confirmation-card">
      <div className="conf-header">
        <strong>Approval required</strong>
        <span className="conf-badge">AWAITING APPROVAL</span>
      </div>
      <p>PLUTON paused before running a high-risk action. Review the details and decide:</p>
      {confirmations.map((confirmation) => (
        <div className="confirmation-item" key={confirmation.call_id}>
          <code>{confirmation.name}</code>
          <pre>{JSON.stringify(confirmation.arguments, null, 2)}</pre>
        </div>
      ))}
      <div className="confirm-actions">
        <button className="approve" disabled={busy} onClick={onApprove}>
          {busy ? "Working…" : "Approve"}
        </button>
        <button className="deny" disabled={busy} onClick={onDeny}>
          Deny
        </button>
      </div>
    </div>
  );
}

function Nav({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button className={active ? "active" : ""} onClick={onClick}>
      {children}
    </button>
  );
}

function Tasks({ tasks }: { tasks: Task[] }) {
  return (
    <>
      <PageHeader
        eyebrow="TASK AUDIT LOG"
        title="Authoritative Task Ledger"
        subtitle="Immutable record of executed computer control requests and verified state transitions."
      />
      <div className="records">
        {tasks.length ? (
          tasks.map((task) => (
            <article className="record" key={task.id}>
              <div>
                <strong>{task.title}</strong>
                <p>{task.response || task.request}</p>
                <small className="mono-sub">ID: {task.id}</small>
              </div>
              <span className={`task-state-badge ${task.status.toLowerCase()}`}>
                {task.status.replaceAll("_", " ")}
              </span>
            </article>
          ))
        ) : (
          <Empty title="No tasks yet" body="Send a message to PLUTON and it will appear here." />
        )}
      </div>
    </>
  );
}

function Automations() {
  return (
    <>
      <PageHeader
        eyebrow="CANONICAL WORKFLOWS"
        title="Automations"
        subtitle="Deterministic compound multi-step workflows compiled across universal computer capabilities."
      />
      <Empty
        title="Phase 1 Active"
        body="Compound workflows (e.g. Open Notepad → Type → Verify → Close) are executed via sequential planning with token authorization."
      />
    </>
  );
}

function Memories({
  memories,
  text,
  onText,
  onSave,
  onDelete,
}: {
  memories: Memory[];
  text: string;
  onText: (value: string) => void;
  onSave: (event: FormEvent) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <>
      <PageHeader
        eyebrow="PERSISTENT CONTEXT"
        title="Memory"
        subtitle="User preferences and persistent application context stored strictly locally."
      />
      <form className="memory-form" onSubmit={onSave}>
        <input value={text} onChange={(event) => onText(event.target.value)} placeholder="e.g. Preferred browser is Brave" />
        <button disabled={!text.trim()}>Save memory</button>
      </form>
      <div className="records">
        {memories.length ? (
          memories.map((memory) => (
            <article className="record" key={memory.id}>
              <div>
                <strong>{memory.category}</strong>
                <p>{memory.content}</p>
              </div>
              <button className="quiet-button" onClick={() => onDelete(memory.id)}>
                Delete
              </button>
            </article>
          ))
        ) : (
          <Empty title="No saved memories" body="Only information you deliberately save appears here." />
        )}
      </div>
    </>
  );
}

function Settings({
  provider,
  tools,
  runtimeInfo,
}: {
  provider: ProviderStatus | null;
  tools: ToolInfo[];
  runtimeInfo: RuntimeIdentity | null;
}) {
  return (
    <>
      <PageHeader
        eyebrow="SYSTEM CONFIGURATION"
        title="Settings & Runtime"
        subtitle="Hardware kernel status, capability surface, and AI provider integration."
      />
      <div className="settings-card">
        <div>
          <strong>Runtime Build & Identity</strong>
          <p>
            Build ID: <code>{runtimeInfo?.build_id || "v2-phase1b"}</code> · Version: <code>{runtimeInfo?.version || "0.2.0"}</code>
          </p>
          <p className="mono-sub">Phase: {runtimeInfo?.phase || "Phase 1: Universal Computer Control"}</p>
        </div>
        <span className="pill completed">Active</span>
      </div>

      <div className="settings-card">
        <div>
          <strong>AI Provider</strong>
          <p>{provider ? `${provider.provider} · ${provider.model}` : "Checking provider configuration…"}</p>
        </div>
        <span className={`pill ${provider?.configured ? "completed" : "waiting"}`}>
          {provider?.configured ? "Configured" : "Setup mode"}
        </span>
      </div>

      <div className="settings-card">
        <div>
          <strong>Capability Surface (12 Canonical Domains)</strong>
          <p>app, window, browser, web, ui, keyboard, mouse, screen, vision, filesystem, terminal, clipboard.</p>
        </div>
      </div>

      <div className="tool-list">
        {tools.map((tool) => (
          <div className="tool-item" key={tool.name}>
            <strong>{tool.name}</strong>
            <p>{tool.description}</p>
            <span className={`pill ${tool.permission === "high" ? "waiting" : "completed"}`}>{tool.permission}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function PageHeader({
  eyebrow,
  title,
  subtitle,
  runtimeInfo,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  runtimeInfo?: RuntimeIdentity | null;
}) {
  return (
    <header>
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="sub">{subtitle}</p>
      </div>
      <div className="status">
        <i /> {runtimeInfo?.build_id ? `V2 Runtime (${runtimeInfo.build_id})` : "V2 Runtime Active"}
      </div>
    </header>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

export default App;