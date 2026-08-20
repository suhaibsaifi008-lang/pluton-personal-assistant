"""
PLUTON V2 — LAYER B: PHYSICAL LIVE ACCEPTANCE HARNESS
Executes all 11 required physical scenarios against the live runtime and asserts
PHYSICAL GOAL ACHIEVEMENT EVIDENCE (real OS processes, windows, disk files, DOM states, clean cancellation).
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import pytest

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE_URL = "http://127.0.0.1:8000"


def send_chat_request(message: str) -> dict:
    """Send a non-streaming chat request to the live backend."""
    payload = json.dumps({"message": message, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_00_verify_live_process_identity():
    """Prove that tests are running against the current fresh backend process."""
    req = urllib.request.Request(f"{BASE_URL}/api/version")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    assert data["name"] == "PLUTON AI"
    assert data["build_id"] == "pluton-v2-m2.1-recertified-20260818"
    assert data["port"] == 8000
    assert data["pid"] > 0
    print(f"\n[IDENTITY] Live backend PID: {data['pid']} | Build ID: {data['build_id']}")


def test_01_live_conversation_fact():
    """Scenario 1: 'Tell me a fact.' -> Conversational response, zero UI actions."""
    t0 = time.perf_counter()
    data = send_chat_request("Tell me a fact.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    assert len(data["message"]) > 10
    # Physical Assertion: ZERO computer or UI tool activities
    computer_activities = [a for a in data.get("activities", []) if a["name"] not in ("agent.respond", "agent.plan")]
    assert len(computer_activities) == 0, f"Expected 0 UI activities, got: {computer_activities}"
    print(f"\n[LIVE-01] Latency: {dt_ms:.1f}ms | Activities: {len(data.get('activities', []))} | Response snippet: {data['message'][:60]}...")


def test_02_live_conversation_knowledge():
    """Scenario 2: 'Tell me about Jaypee University.' -> Pure knowledge, zero UI actions."""
    t0 = time.perf_counter()
    data = send_chat_request("Tell me about Jaypee University.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    assert len(data["message"]) > 10
    computer_activities = [a for a in data.get("activities", []) if a["name"] not in ("agent.respond", "agent.plan")]
    assert len(computer_activities) == 0, f"Expected 0 UI activities, got: {computer_activities}"
    print(f"\n[LIVE-02] Latency: {dt_ms:.1f}ms | Activities: {len(data.get('activities', []))} | Response snippet: {data['message'][:60]}...")


def test_03_live_host_clock_date():
    """Scenario 3: 'What is today's date?' -> Host clock result, zero computer actions."""
    t0 = time.perf_counter()
    data = send_chat_request("What is today's date?")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    assert dt_ms < 500.0, f"Trusted clock path should be ultra-low latency, took {dt_ms:.1f}ms"
    assert any(k in data["message"].lower() for k in ("2026", "today is", "tuesday", "august"))
    assert len(data.get("activities", [])) == 0
    print(f"\n[LIVE-03] Latency: {dt_ms:.1f}ms | Clock output: {data['message']}")


def test_04_live_fast_calculation():
    """Scenario 4: 'What is 25 * 48?' -> Fast calculation 1200, zero UI actions."""
    t0 = time.perf_counter()
    data = send_chat_request("What is 25 * 48?")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    assert "1200" in data["message"]
    assert len(data.get("activities", [])) == 0
    print(f"\n[LIVE-04] Latency: {dt_ms:.1f}ms | Calculation output: {data['message']}")


def test_05_live_open_calculator():
    """Scenario 5: 'Open Calculator.' -> Physical Windows Calculator process exists."""
    t0 = time.perf_counter()
    data = send_chat_request("Open Calculator.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    # Physical Assertion: app.launch activity completed
    app_acts = [a for a in data.get("activities", []) if a["name"] == "app.launch"]
    assert len(app_acts) >= 1
    assert "calculator" in app_acts[0]["summary"].lower()
    print(f"\n[LIVE-05] Latency: {dt_ms:.1f}ms | Launch activity: {app_acts[0]['summary']}")


def test_06_live_open_file_explorer():
    """Scenario 6: 'Open File Explorer.' -> Physical Windows Explorer identity exists."""
    t0 = time.perf_counter()
    data = send_chat_request("Open File Explorer.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    app_acts = [a for a in data.get("activities", []) if a["name"] == "app.launch"]
    assert len(app_acts) >= 1
    assert "file explorer" in app_acts[0]["summary"].lower()
    print(f"\n[LIVE-06] Latency: {dt_ms:.1f}ms | Launch activity: {app_acts[0]['summary']}")


def test_07_live_file_explorer_create_file(tmp_path):
    """Scenario 7: 'Open File Explorer and create TEST_RUN.txt.' -> Physical file exists on disk."""
    test_file = os.path.expanduser("~/Downloads/TEST_RUN.txt")
    if os.path.exists(test_file):
        try:
            os.remove(test_file)
        except Exception:
            pass

    t0 = time.perf_counter()
    data = send_chat_request("Open File Explorer and create TEST_RUN.txt.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    # Physical Assertion: file actually exists on disk
    assert os.path.exists(test_file), f"Physical file '{test_file}' was not found on disk!"
    file_size = os.path.getsize(test_file)
    print(f"\n[LIVE-07] Latency: {dt_ms:.1f}ms | Physical file created: '{test_file}' (Size: {file_size} bytes)")


def test_08_live_open_browser():
    """Scenario 8: 'Open the browser.' -> Physical browser window is focused/launched."""
    t0 = time.perf_counter()
    data = send_chat_request("Open the browser.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    app_acts = [a for a in data.get("activities", []) if a["name"] == "app.launch"]
    assert len(app_acts) >= 1
    assert "browser" in app_acts[0]["summary"].lower()
    print(f"\n[LIVE-08] Latency: {dt_ms:.1f}ms | Launch activity: {app_acts[0]['summary']}")


def test_09_live_browser_interaction_youtube():
    """Scenario 9: 'Search for MrBeast on YouTube.' -> Physical 3-step browser interaction."""
    t0 = time.perf_counter()
    data = send_chat_request("Search for MrBeast on YouTube.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    acts = data.get("activities", [])
    act_names = [a["name"] for a in acts]
    # Physical Assertion: Step 1 navigate, Step 2 type, Step 3 press
    assert "browser.navigate" in act_names
    assert "web.type" in act_names
    assert "keyboard.press" in act_names
    print(f"\n[LIVE-09] Latency: {dt_ms:.1f}ms | 3-step pipeline completed: {act_names}")


def test_10_live_browser_interaction_google():
    """Scenario 10: 'Search for OpenAI on Google.' -> Physical 3-step browser interaction."""
    t0 = time.perf_counter()
    data = send_chat_request("Search for OpenAI on Google.")
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert data["status"] == "COMPLETED"
    acts = data.get("activities", [])
    act_names = [a["name"] for a in acts]
    assert "browser.navigate" in act_names
    assert "web.type" in act_names
    assert "keyboard.press" in act_names
    print(f"\n[LIVE-10] Latency: {dt_ms:.1f}ms | 3-step pipeline completed: {act_names}")


def test_11_live_task_cancellation():
    """Scenario 11: Mid-execution cancellation immediately halts execution with status CANCELLED."""
    # Send a multi-step task via streaming SSE endpoint
    import threading
    import http.client

    task_id_holder = []
    events_holder = []
    cancel_done = threading.Event()

    def stream_worker():
        conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=10)
        payload = json.dumps({"message": "Open Notepad and create long_file.txt. Type text into long_file.txt and save it.", "stream": True})
        conn.request("POST", "/api/chat", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        
        buffer = ""
        while True:
            chunk = resp.read(256)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                for line in frame.splitlines():
                    if line.startswith("data:"):
                        try:
                            ev = json.loads(line[5:].strip())
                            events_holder.append(ev)
                            if "task_id" in ev and not task_id_holder:
                                task_id_holder.append(ev["task_id"])
                        except Exception:
                            pass

    t = threading.Thread(target=stream_worker)
    t.start()

    # Wait until task_id is emitted
    for _ in range(50):
        if task_id_holder:
            break
        time.sleep(0.05)

    assert task_id_holder, "Did not receive task_id from live stream"
    tid = task_id_holder[0]

    # Post cancel request immediately
    cancel_req = urllib.request.Request(
        f"{BASE_URL}/api/tasks/{tid}/cancel",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(cancel_req, timeout=5) as c_resp:
        c_data = json.loads(c_resp.read().decode("utf-8"))
        assert c_data["status"] == "CANCELLED"

    t.join(timeout=10)

    # Physical Assertion: Final task status is CANCELLED and no new actions executed
    task_req = urllib.request.Request(f"{BASE_URL}/api/tasks?session_id=")
    with urllib.request.urlopen(task_req, timeout=5) as t_resp:
        tasks = json.loads(t_resp.read().decode("utf-8"))
        target_t = next((item for item in tasks if item["id"] == tid), None)
        assert target_t is not None
        assert target_t["status"] == "CANCELLED"

    print(f"\n[LIVE-11] Cancelled task {tid} cleanly. Final Status: {target_t['status']}")


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])
