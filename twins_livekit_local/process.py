"""livekit-server process lifecycle management."""

import logging
import os
import signal
import subprocess
import time

import requests

logger = logging.getLogger(__name__)


class LiveKitProcess:
    """Manages the livekit-server binary lifecycle."""

    def __init__(self, binary_path: str, port: int, webhook_url: str, api_key: str = "devkey", api_secret: str = "secret"):
        self._binary_path = binary_path
        self._port = port
        self._webhook_url = webhook_url
        self._api_key = api_key
        self._api_secret = api_secret
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        """Start livekit-server --dev on the configured port."""
        if self._process and self._process.poll() is None:
            logger.warning("livekit-server already running (pid=%d)", self._process.pid)
            return

        if not self._binary_path:
            raise RuntimeError(
                "LIVEKIT_BIN not set. Set it to the path of your livekit-server binary.\n"
                "Example: export LIVEKIT_BIN=./e2e/bin/livekit-server"
            )

        if not os.path.isfile(self._binary_path):
            raise RuntimeError(
                f"livekit-server binary not found at: {self._binary_path}\n"
                "Download it from https://github.com/livekit/livekit/releases"
            )

        cmd = [
            self._binary_path,
            "--dev",
            "--port", str(self._port),
            "--bind", "127.0.0.1",
            "--keys", f"{self._api_key}: {self._api_secret}",
        ]

        if self._webhook_url:
            cmd.extend(["--webhook-url", self._webhook_url])

        logger.info("Starting livekit-server: %s", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for server to be ready
        self._wait_for_ready()

    def stop(self) -> None:
        """SIGTERM the process, wait for clean shutdown."""
        if not self._process:
            return

        if self._process.poll() is not None:
            self._process = None
            return

        logger.info("Stopping livekit-server (pid=%d)", self._process.pid)
        self._process.send_signal(signal.SIGTERM)

        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("livekit-server didn't stop gracefully, sending SIGKILL")
            self._process.kill()
            self._process.wait(timeout=5)

        self._process = None

    def restart(self) -> None:
        """Stop + start. Used by /_twin/reset."""
        self.stop()
        self.start()

    def is_healthy(self) -> bool:
        """Check if the server is responding on its port."""
        try:
            resp = requests.get(f"http://127.0.0.1:{self._port}", timeout=2)
            return resp.status_code < 500
        except Exception:
            return False

    def _wait_for_ready(self, timeout: float = 10.0) -> None:
        """Wait for livekit-server to start accepting connections."""
        start = time.time()
        while time.time() - start < timeout:
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"livekit-server exited with code {self._process.returncode}"
                )

            if self.is_healthy():
                logger.info("livekit-server ready on port %d", self._port)
                return

            time.sleep(0.2)

        raise RuntimeError(
            f"livekit-server did not become ready within {timeout}s on port {self._port}"
        )
