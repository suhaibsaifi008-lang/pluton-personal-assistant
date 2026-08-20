from app.security import PermissionLevel, requires_confirmation


def test_high_risk_actions_need_confirmation():
    assert requires_confirmation(PermissionLevel.HIGH)
    assert not requires_confirmation(PermissionLevel.LOW)
    assert not requires_confirmation(PermissionLevel.MEDIUM)