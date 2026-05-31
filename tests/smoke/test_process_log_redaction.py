"""livekit-server credentials must not appear in application logs (TWLK-004).

`LiveKitProcess.start()` passes `--keys "<api_key>: <api_secret>"` to the
binary; the startup log line must carry a redacted form, never the real
secret.
"""

import logging

from twins_livekit_local.process import LiveKitProcess


class _FakePopen:
    def __init__(self, *args, **kwargs):
        self.pid = 4242

    def poll(self):
        return None


def test_start_log_redacts_keys(monkeypatch, caplog):
    proc = LiveKitProcess(
        binary_path="/fake/livekit-server",
        port=7880,
        webhook_url="",
        api_key="REAL_API_KEY",
        api_secret="REAL_API_SECRET",
    )
    monkeypatch.setattr("twins_livekit_local.process.os.path.isfile", lambda p: True)
    monkeypatch.setattr("twins_livekit_local.process.subprocess.Popen", _FakePopen)
    monkeypatch.setattr(LiveKitProcess, "_wait_for_ready", lambda self: None)

    with caplog.at_level(logging.INFO, logger="twins_livekit_local.process"):
        proc.start()

    startup_lines = [r.getMessage() for r in caplog.records if "Starting livekit-server" in r.getMessage()]
    assert startup_lines, "no startup log line captured"
    line = startup_lines[0]
    assert "REAL_API_KEY" not in line
    assert "REAL_API_SECRET" not in line
    assert "***:***" in line
