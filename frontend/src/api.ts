const api = "/api";
const directApi = "http://127.0.0.1:8000/api";

async function fetchWithFallback(urlPath: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${api}${urlPath}`, init);
  } catch (err) {
    try {
      return await fetch(`${directApi}${urlPath}`, init);
    } catch {
      throw err;
    }
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetchWithFallback(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) throw new Error("PLUTON could not complete that request. Check that the backend is running.");
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>);
}

export async function getRuntimeVersion() {
  return request<any>("/version");
}

export async function getRuntimeHealth() {
  return request<any>("/health");
}

export async function getDebugRuntime() {
  return request<any>("/debug/runtime");
}

export async function cancelTask(taskId: string) {
  return request<void>(`/tasks/${taskId}/cancel`, { method: "POST" });
}

export async function emergencyStop() {
  return request<{ stopped: boolean; message: string }>("/control/emergency-stop", { method: "POST" });
}

export async function getActiveTasks() {
  return request<{ active_task_count: number; active_tasks: any[] }>("/debug/runtime/active-tasks");
}

export type StreamEvent = { event: string; data: Record<string, unknown> };

export async function streamJson(
  path: string,
  body: Record<string, unknown>,
  onEvent: (event: string, data: any) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  let didTimeout = false;
  const timeoutId = setTimeout(() => {
    didTimeout = true;
    controller.abort();
  }, 90000); // 90s safety timeout

  if (signal) {
    signal.addEventListener("abort", () => controller.abort());
  }

  try {
    const response = await fetchWithFallback(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      if (response.status === 409) {
        throw new Error("This action was already resolved or is currently running.");
      }
      if (response.status === 404) {
        throw new Error("Task not found.");
      }
      throw new Error("PLUTON could not start streaming. Check that the backend is running.");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let separator = buffer.indexOf("\n\n");
        while (separator !== -1) {
          const frame = buffer.slice(0, separator);
          buffer = buffer.slice(separator + 2);
          const parsed = parseFrame(frame);
          if (parsed) onEvent(parsed.event, parsed.data);
          separator = buffer.indexOf("\n\n");
        }
      }
    } catch (readErr: any) {
      if (didTimeout) {
        throw new Error("The request timed out after 90 seconds. Please try again.");
      }
      if (signal?.aborted) {
        throw new Error("The task was cancelled.");
      }
      const msg = String(readErr?.message || readErr || "");
      if (msg.includes("BodyStreamBuffer") || msg.includes("aborted") || msg.includes("AbortError")) {
        throw new Error("The response stream was interrupted. Check your network or backend logs.");
      }
      throw readErr;
    } finally {
      reader.releaseLock();
    }
  } catch (err: any) {
    if (didTimeout) {
      throw new Error("The request timed out after 90 seconds. Please try again.");
    }
    if (signal?.aborted) {
      throw new Error("The task was cancelled.");
    }
    const msg = String(err?.message || err || "");
    if (msg.includes("BodyStreamBuffer") || msg.includes("aborted") || msg.includes("AbortError")) {
      throw new Error("The response stream was interrupted. Check your network or backend logs.");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

function parseFrame(frame: string): StreamEvent | null {
  let type = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event: type, data: JSON.parse(data) };
  } catch {
    return null;
  }
}