import socket
import threading
import time
from typing import Optional

from virtual_tcu.config.constants import Cfg
from virtual_tcu.telemetry.logger import TelemetryLogger
from virtual_tcu.telemetry.model import Telemetry
from virtual_tcu.telemetry.parser import parse_fh6_packet


class TelemetryReceiver:
    def __init__(self, logger: TelemetryLogger, on_packet=None):
        self._sock: Optional[socket.socket] = None
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._latest: Optional[Telemetry] = None
        self._latest_raw: Optional[bytes] = None
        self._lock = threading.Lock()
        self._logger = logger
        self.on_packet = on_packet
        self.packets_total = 0
        self.last_recv_time = 0.0
        self.error_msg = ""

    def start(self) -> bool:
        if self._running.is_set():
            self.stop()
        
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.settimeout(0.5)
            self._sock.bind((Cfg.UDP_IP, Cfg.UDP_PORT))
        except OSError as e:
            self.error_msg = str(e)
            return False
            
        self._running.set()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="UDP")
        self._thread.start()
        return True

    def stop(self):
        self._running.clear()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _loop(self):
        while self._running.is_set():
            try:
                raw, _ = self._sock.recvfrom(1024)
                td = parse_fh6_packet(raw)
                if td is not None:
                    now = time.time()
                    with self._lock:
                        self.packets_total += 1
                        self.last_recv_time = now
                        self._latest = td
                        self._latest_raw = raw
                    # Ensure logger call is outside the lock to avoid blocking UDP ingest
                    self._logger.write_packet(raw)
                    if self.on_packet:
                        self.on_packet(td, raw)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                print(f"[UDP] unexpected error: {e}")
                time.sleep(0.1)

    def latest(self) -> Optional[Telemetry]:
        with self._lock:
            return self._latest

    def latest_raw(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_raw

    @property
    def is_live(self) -> bool:
        with self._lock:
            return (time.time() - self.last_recv_time) < 2.5
