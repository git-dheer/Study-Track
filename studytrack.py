#!/usr/bin/env python3
"""
StudyTrack v1 - single-file CLI launcher that delegates to webapp package.

Usage:
  studytrack --start   # start detached server
  studytrack --stop    # stop server
  studytrack --status  # show running status
"""
import os
import sys
import argparse
import time
import signal
from pathlib import Path
from subprocess import Popen
import sqlite3

# Attempt to import Flask via webapp package. If imports fail, exit with helpful message.
try:
    # webapp package will import Flask
    import webapp
except Exception:
    pass

# Config
PORT = 8080
DATA_DIR = Path.home() / ".studytrack"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = DATA_DIR / "studytrack.pid"
LOG_FILE = DATA_DIR / "studytrack.log"
SCRIPT = os.path.abspath(__file__)

# Helpers
def write_pid(pid):
    PID_FILE.write_text(str(pid))

def read_pid():
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None

def remove_pid():
    try:
        PID_FILE.unlink()
    except Exception:
        pass

def is_running(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

def kill_group(pid):
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return True
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False

# CLI actions
def start():
    pid = read_pid()
    if pid and is_running(pid):
        print(f"StudyTrack already running (pid {pid})")
        return
    python = sys.executable
    cmd = [python, SCRIPT, "--runserver"]
    try:
        p = Popen(cmd, stdout=open(LOG_FILE, "a"), stderr=open(LOG_FILE, "a"), preexec_fn=os.setsid, close_fds=True)
        write_pid(p.pid)
        print(f"StudyTrack started on http://localhost:{PORT} (pid {p.pid})")
        print("You can close this terminal. To stop: studytrack --stop")
    except Exception as e:
        print("Failed to start StudyTrack:", e)

def stop():
    pid = read_pid()
    if not pid:
        print("StudyTrack is not running (no pid file).")
        return
    if not is_running(pid):
        print("Stale pid file found; removing.")
        remove_pid()
        return
    ok = kill_group(pid)
    if ok:
        time.sleep(0.3)
        remove_pid()
        print("StudyTrack stopped.")
    else:
        print("Failed to stop StudyTrack. Try: sudo pkill -f studytrack.py")

def status():
    pid = read_pid()
    if not pid:
        print("StudyTrack is not running.")
        return
    if is_running(pid):
        print(f"StudyTrack running (pid {pid}) at http://localhost:{PORT}")
    else:
        print("PID exists but process not running. Remove pid file and try again.")

# When launched as runserver, import and run webapp.app
def runserver():
    # import local webapp package and start app
    # keep import here so venv activation is required earlier
    from webapp.routes import create_app
    app = create_app()
    # app.run will block; we bind to 127.0.0.1
    app.run(host='127.0.0.1', port=PORT, threaded=True)

# Argparse
def main():
    parser = argparse.ArgumentParser(prog='studytrack')
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--runserver', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.runserver:
        runserver()
        return
    if args.start:
        start()
        return
    if args.stop:
        stop()
        return
    if args.status:
        status()
        return
    parser.print_help()

if __name__ == '__main__':
    main()