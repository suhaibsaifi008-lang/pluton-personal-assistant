from app.tools.computer_router import ComputerActionRouter, IntentType


def test_action_router_parses_list_windows():
    router = ComputerActionRouter()
    intent = router.parse_intent("What windows are currently open?")
    assert intent.intent_type == IntentType.WINDOW_LIST


def test_action_router_parses_list_browser_tabs():
    router = ComputerActionRouter()
    intent = router.parse_intent("What tabs do I have open in Brave?")
    assert intent.intent_type == IntentType.BROWSER_TAB_LIST
    assert intent.browser == "Brave"


def test_action_router_parses_switch_tab():
    router = ComputerActionRouter()
    intent = router.parse_intent("Switch to the Claude tab in my Brave browser")
    assert intent.intent_type == IntentType.BROWSER_TAB_SWITCH
    assert intent.target == "Claude"
    assert intent.browser == "Brave"


def test_action_router_parses_close_tab():
    router = ComputerActionRouter()
    intent = router.parse_intent("Close the YouTube tab in Brave")
    assert intent.intent_type == IntentType.BROWSER_TAB_CLOSE
    assert intent.target.lower() == "youtube"
    assert intent.browser == "Brave"


def test_action_router_parses_switch_window():
    router = ComputerActionRouter()
    intent = router.parse_intent("Switch to Calculator")
    assert intent.intent_type == IntentType.WINDOW_SWITCH
    assert intent.target == "Calculator"


def test_action_router_parses_app_launch():
    router = ComputerActionRouter()
    intent = router.parse_intent("Open Settings")
    assert intent.intent_type == IntentType.APP_LAUNCH
    assert intent.target == "settings"


def test_action_router_parses_browser_navigation():
    router = ComputerActionRouter()
    intent = router.parse_intent("Open Gmail")
    assert intent.intent_type == IntentType.BROWSER_NAVIGATE
    assert intent.target == "gmail"


def test_action_router_parses_inspect_controls():
    router = ComputerActionRouter()
    intent = router.parse_intent("Tell me what buttons and controls are visible on this window")
    assert intent.intent_type == IntentType.INSPECT_UI


def test_action_router_parses_ui_interaction():
    router = ComputerActionRouter()
    intent = router.parse_intent("Click Bluetooth button")
    assert intent.intent_type == IntentType.UI_INTERACT
    assert intent.target == "Bluetooth"
    assert intent.action_verb == "invoke"
