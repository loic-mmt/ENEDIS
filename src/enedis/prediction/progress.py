"""Minimal terminal display; workers never own the spinner."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from itertools import cycle
import logging
from os import devnull
from shutil import get_terminal_size
import sys
from threading import Event, Lock, Thread


class TerminalProgress:
    def __init__(self, stream=None, *, interval=0.1):
        self.stream = sys.stdout if stream is None else stream
        self.interval = interval
        self._animated = self.stream.isatty()
        self._lock = Lock()
        self._stopped = Event()
        self._thread = None
        self._frames = cycle("/-\\|")
        self._status = ""
        self._width = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()  # Aussi exécuté lors d'une exception ou d'un Ctrl+C.

    def print_status(self, message):
        with self._lock:
            self._status = message
            if not self._animated:
                return  # Un fichier de logs ne reçoit ni animation ni retours chariot.
            self._render()
            if self._thread is None:
                self._stopped.clear()
                self._thread = Thread(target=self._animate, name="terminal-spinner", daemon=True)
                self._thread.start()

    def _render(self):
        columns = max(1, get_terminal_size().columns - 1)
        line = f"{next(self._frames)}  {self._status}"[:columns]
        self.stream.write("\r" + line.ljust(min(self._width, columns)))  # Efface l'ancien texte sans déborder.
        self.stream.flush()
        self._width = len(line)

    def _animate(self):
        while not self._stopped.wait(self.interval):
            with self._lock:
                self._render()

    def stop(self):
        self._stopped.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        with self._lock:
            if self._width:
                self.stream.write("\r" + " " * self._width + "\r")
                self.stream.flush()
                self._width = 0

    def write(self, message, *, error=False):
        self.stop()
        stream = sys.stderr if error else self.stream
        stream.write(message + "\n")
        stream.flush()

    def iteration(self, current, total, model, fit_seconds, predict_seconds):
        self.write(f"[{current}/{total}] [{model}] Fit time elapsed: {fit_seconds:.2f}s "
                   f"- Pred time elapsed: {predict_seconds:.2f}s")


@contextmanager
def quiet_model_output():
    """Silence library chatter locally; exceptions still reach the caller."""
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with open(devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous)
