import sys

import httpx
import pytest

from app import tools as tools_module
from app.security import PermissionLevel


def test_filesystem_write_within_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "_workspace", lambda: tmp_path)
    result = tools_module._write_file("notes/hello.txt", "hi there")
    assert (tmp_path / "notes" / "hello.txt").read_text(encoding="utf-8") == "hi there"
    assert result["path"].endswith("notes\\hello.txt") or result["path"].endswith("notes/hello.txt")


def test_filesystem_read_rejects_outside_workspace(tmp_path, monkeypatch):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret")
    monkeypatch.setattr(tools_module, "_workspace", lambda: tmp_path)
    with pytest.raises(ValueError):
        tools_module._read_file(str(outside))


def test_terminal_denies_destructive_commands():
    for command in ["rm -rf /", "format c:", "shutdown /s", "Remove-Item -Recurse C:\\", "del /f x"]:
        result = tools_module._run_command(command)
        assert result.get("denied"), f"expected denial for: {command}"


def test_terminal_runs_safe_command():
    result = tools_module._run_command("hostname")
    assert result.get("exit_code") == 0
    assert result.get("output", "").strip()


def test_terminal_rejects_shell_bypass():
    assert tools_module._run_command("powershell -c 'Remove-Item x'").get("denied")
    assert tools_module._run_command("cmd /c del x").get("denied")


def test_web_fetch_rejects_non_http():
    result = tools_module._web_fetch("file:///etc/passwd")
    assert "error" in result


def test_web_search_parses_results(monkeypatch):
    html = (
        '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com&rut=1">Example Site</a>'
        '<a class="result__snippet">The example snippet</a>'
    )

    class FakeResponse:
        status_code = 200
        text = html

        def raise_for_status(self):
            pass

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: FakeResponse())
    result = tools_module._web_search("example")
    assert result["results"][0]["url"] == "https://example.com"
    assert result["results"][0]["title"] == "Example Site"
    assert result["results"][0]["snippet"] == "The example snippet"


def test_web_search_reports_failure(monkeypatch):
    class FakeResponse:
        status_code = 500
        text = ""

        def raise_for_status(self):
            raise httpx.HTTPStatusError("boom", request=httpx.Request("GET", "https://example.com"), response=httpx.Response(500))

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: FakeResponse())
    result = tools_module._web_search("anything")
    assert "error" in result


def test_memory_tools_roundtrip():
    saved = tools_module._memory_save("user is learning piano", "fact")
    assert saved["memory_id"]
    recalled = tools_module._memory_recall("piano learning", limit=5)
    assert any("piano" in memory["content"] for memory in recalled["memories"])


def test_all_tools_have_permission_levels():
    for name, tool in tools_module.TOOLS.items():
        assert isinstance(tool.permission, PermissionLevel)
        assert tool.name == name
        assert tool.input_schema.get("type") == "object"


def test_high_risk_tools_classification():
    high = sorted([name for name, tool in tools_module.TOOLS.items() if tool.permission == PermissionLevel.HIGH])
    assert high == ["computer.close_window", "computer.hotkey", "computer.launch_app", "terminal.run"]




def test_filesystem_list_dir_within_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "_workspace", lambda: tmp_path)
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file1.txt").write_text("content", encoding="utf-8")
    result = tools_module._list_dir(".")
    assert result["count"] == 2
    names = [e["name"] for e in result["entries"]]
    assert "subdir" in names
    assert "file1.txt" in names
    file_entry = next(e for e in result["entries"] if e["name"] == "file1.txt")
    assert file_entry["type"] == "file"
    assert file_entry["size_bytes"] == 7
    dir_entry = next(e for e in result["entries"] if e["name"] == "subdir")
    assert dir_entry["type"] == "directory"
    assert dir_entry["size_bytes"] is None


def test_filesystem_list_dir_rejects_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "_workspace", lambda: tmp_path)
    outside = tmp_path.parent
    result = tools_module._list_dir(str(outside))
    assert "error" in result
    assert "outside" in result["error"].lower()


def test_browser_open_url_validates_scheme():
    assert "error" in tools_module._browser_open_url("file:///etc/passwd")
    assert "error" in tools_module._browser_open_url("javascript:alert(1)")
    assert "error" in tools_module._browser_open_url("")


def test_browser_open_url_calls_webbrowser(monkeypatch):
    called = []
    monkeypatch.setattr(tools_module.webbrowser, "open", lambda url: called.append(url) or True)
    result = tools_module._browser_open_url("https://example.com/test")
    assert result.get("opened") is True
    assert called == ["https://example.com/test"]


def test_app_launch_allows_allowlisted_apps(monkeypatch):
    launched = []
    if hasattr(tools_module.os, "startfile"):
        monkeypatch.setattr(tools_module.os, "startfile", lambda target: launched.append(target))
    else:
        monkeypatch.setattr(tools_module.subprocess, "Popen", lambda args: launched.append(args[0]))
    result = tools_module._app_launch("notepad")
    assert result.get("launched") is True
    assert result.get("type") == "application"
    assert "notepad.exe" in launched


def test_app_launch_rejects_unapproved_target():
    result = tools_module._app_launch("powershell.exe")
    assert "error" in result
    assert "not an approved application" in result["error"]

    result2 = tools_module._app_launch("malicious_script.bat")
    assert "error" in result2


def test_app_launch_opens_workspace_folder(tmp_path, monkeypatch):
    folder = tmp_path / "project_docs"
    folder.mkdir()
    monkeypatch.setattr(tools_module, "_workspace", lambda: tmp_path)
    opened = []
    if hasattr(tools_module.os, "startfile"):
        monkeypatch.setattr(tools_module.os, "startfile", lambda target: opened.append(target))
    else:
        monkeypatch.setattr(tools_module.subprocess, "Popen", lambda args: opened.append(args))
    result = tools_module._app_launch("project_docs")
    assert result.get("launched") is True
    assert result.get("type") == "folder"


def test_system_info_returns_non_sensitive_fields():
    info = tools_module._system_info()
    assert "os" in info
    assert "platform" in info
    assert "processor" in info
    assert "username" in info
    assert info["username"]
    # Check no sensitive keys
    for sensitive in ["password", "token", "key", "secret", "cookie"]:
        assert sensitive not in info


def test_tools_package_modular_domain_imports():
    from app.tools.base import Tool, validate_tool_arguments
    from app.tools.registry import ToolRegistry
    from app.tools.filesystem import _read_file, _write_file, _list_dir
    from app.tools.terminal import _run_command
    from app.tools.browser import _browser_open_url, _app_launch
    from app.tools.web import _web_search, _web_fetch
    from app.tools.memory import recall_memories, _memory_save
    from app.tools.system import _system_info, _clock

    assert callable(_read_file)
    assert callable(_run_command)
    assert callable(_browser_open_url)
    assert callable(_web_search)
    assert callable(recall_memories)
    assert callable(_system_info)


def test_all_registered_tools_have_valid_schemas_and_callables():
    for tool in tools_module.TOOLS.list():
        assert tool.name
        assert tool.description
        assert tool.permission in (PermissionLevel.LOW, PermissionLevel.MEDIUM, PermissionLevel.HIGH)
        assert isinstance(tool.input_schema, dict)
        assert tool.input_schema.get("type") == "object"
        assert callable(tool.execute)