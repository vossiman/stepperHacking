import pytest


@pytest.fixture
def home_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("STEPPER_QUESTS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture(scope="session", autouse=True)
def qapp():
    # One QApplication for the run, created before any test can make a bare
    # QCoreApplication, which would rule out pixmaps for the rest of the run.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        yield app
