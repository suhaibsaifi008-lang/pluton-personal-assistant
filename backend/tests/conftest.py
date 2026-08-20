import os

os.environ["PLUTON_DATABASE_URL"] = "sqlite:///./data/test_pluton.db"
os.environ["PLUTON_OPENAI_API_KEY"] = ""

import pytest

from app.database import Base, engine


@pytest.fixture(autouse=True)
def _reset_database():
    from app.tools.computer_safety import enable_computer_control, disable_computer_control
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    enable_computer_control("pytest-test-task")
    yield
    disable_computer_control("pytest-test-task")
    Base.metadata.drop_all(bind=engine)