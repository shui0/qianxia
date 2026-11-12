"""Run the watchdog from Task Scheduler without opening a console."""

import os
from pathlib import Path
import subprocess


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"

    with (logs / "watchdog-launcher.log").open("ab") as log:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
             "RemoteSigned", "-File", str(root / "watchdog.ps1")],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    raise SystemExit(result.returncode)
