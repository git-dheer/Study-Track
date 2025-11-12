#!/usr/bin/env python3
"""
StudyTrack - Phase 1 single-file CLI + Flask app

Usage:
  studytrack.py --start      # start detached server
  studytrack.py --stop       # stop running server
  studytrack.py --status     # show running status
  studytrack.py --runserver  # run server in foreground (internal)
"""

import os
import sys
import argparse
import sqlite3
import signal
import time
import json
from datetime import datetime
from pathlib import Path
from subprocess import Popen
import atexit

# Minimal external dependency: Flask
try:
    from flask import Flask, request, jsonify, redirect, url_for, render_template_string
except Exception as e:
    print("Flask not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

APP_NAME = "StudyTrack"
PORT = 8080
# app data directory
DATA_DIR = Path.home() / ".studytrack"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = DATA_DIR / "studytrack.pid"
DB_FILE = DATA_DIR / "studytrack.db"
LOG_FILE = DATA_DIR / "studytrack.log"

# --- Simple SQLite wrapper ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        tags TEXT,
        start_ts INTEGER,
        end_ts INTEGER,
        duration INTEGER
      )
    """)
    conn.commit()
    conn.close()

def start_session_in_db(name, tags, start_ts):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (name, tags, start_ts, end_ts, duration) VALUES (?, ?, ?, ?, ?)",
              (name, tags, start_ts, 0, 0))
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id

def stop_session_in_db(session_id, end_ts):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT start_ts FROM sessions WHERE id=?", (session_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    duration = int(end_ts - row[0])
    c.execute("UPDATE sessions SET end_ts=?, duration=? WHERE id=?", (end_ts, duration, session_id))
    conn.commit()
    conn.close()
    return duration

def get_last_running_session():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, tags, start_ts FROM sessions WHERE end_ts=0 ORDER BY start_ts DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row  # or None

# --- PID management & process control ---
def write_pid(pid):
    PID_FILE.write_text(str(pid))

def read_pid():
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        return pid
    except:
        return None

def remove_pid():
    try:
        PID_FILE.unlink()
    except:
        pass

def is_process_running(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

def kill_process_group(pid):
    try:
        # kill the process group
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return True
    except Exception as e:
        return False

# --- Flask app (templates inline for single-file simplicity) ---
app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>StudyTrack</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<style>
  body { background: #0b1020; color: #e6eef8; }
  .card { background: #0f1724; border: 1px solid #1f2937; }
  .muted { color: #94a3b8; }
</style>
</head>
<body class="min-h-screen p-6">
<div class="max-w-3xl mx-auto">
  <div class="mb-6">
    <h1 class="text-3xl font-semibold">StudyTrack</h1>
    <p class="muted">Local study timer — runs at <code>http://localhost:{{port}}</code></p>
  </div>

  <div class="card p-6 rounded-lg shadow-sm mb-6">
    <form id="sessionForm" onsubmit="return false;">
      <div class="mb-4">
        <label class="block text-sm mb-1">Session name</label>
        <input id="sessionName" class="w-full p-2 rounded bg-gray-900 border border-gray-700" placeholder="E.g. Math practice" />
      </div>

      <div class="mb-4">
        <label class="block text-sm mb-1">Tags (comma separated)</label>
        <input id="tags" class="w-full p-2 rounded bg-gray-900 border border-gray-700" placeholder="study,projectX" />
      </div>

      <div class="flex items-center space-x-3">
        <button id="startBtn" class="px-4 py-2 rounded bg-green-600 hover:bg-green-500" onclick="startSession()">Start</button>
        <button id="stopBtn" class="px-4 py-2 rounded bg-red-600 hover:bg-red-500" onclick="stopSession()" disabled>Stop</button>
        <div id="timer" class="ml-4 font-mono text-lg">00:00:00</div>
      </div>
      <p class="muted mt-3 text-sm">Tip: close the terminal after starting StudyTrack. Use <code>studytrack --stop</code> to stop the server.</p>
    </form>
  </div>

  <div class="card p-6 rounded-lg shadow-sm">
    <h2 class="text-lg font-medium mb-3">Recent sessions</h2>
    <div id="sessionsList" class="space-y-3 muted">Loading...</div>
  </div>
</div>

<script>
let runningSession = null;
let timerInterval = null;

function secToHHMMSS(s){
  let h = Math.floor(s/3600); s %= 3600;
  let m = Math.floor(s/60); let sec = s%60;
  return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(sec).padStart(2,'0');
}

async function startSession(){
  const name = document.getElementById('sessionName').value.trim();
  const tags = document.getElementById('tags').value.trim();
  if (!name){
    alert('Please enter a session name.');
    return;
  }
  const res = await fetch('/api/start', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, tags})
  });
  const data = await res.json();
  if (data.success){
    runningSession = data.session;
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    startTimerClient();
    refreshSessions();
  } else {
    alert('Failed to start session: '+(data.error||'unknown'));
  }
}

async function stopSession(){
  if (!runningSession) return;
  const res = await fetch('/api/stop', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: runningSession.id})
  });
  const data = await res.json();
  if (data.success){
    runningSession = null;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    stopTimerClient();
    refreshSessions();
    alert('Session ended. Duration: ' + data.duration_str);
  } else {
    alert('Failed to stop session: '+(data.error||'unknown'));
  }
}

function startTimerClient(){
  stopTimerClient();
  timerInterval = setInterval(async ()=>{
    const res = await fetch('/api/status');
    const data = await res.json();
    if (data.running){
      document.getElementById('timer').innerText = data.elapsed_str;
    } else {
      document.getElementById('timer').innerText = '00:00:00';
    }
  }, 800);
}

function stopTimerClient(){
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = null;
}

async function refreshSessions(){
  const res = await fetch('/api/recent');
  const data = await res.json();
  const el = document.getElementById('sessionsList');
  if (!data.sessions || data.sessions.length===0){
    el.innerHTML = '<div class="muted">No sessions yet.</div>';
    return;
  }
  el.innerHTML = '';
  data.sessions.forEach(s=>{
    const start = new Date(s.start_ts*1000);
    const endTxt = s.end_ts ? (' — ' + new Date(s.end_ts*1000).toLocaleString()) : ' — running';
    const dur = s.duration ? secToHHMMSS(s.duration) : '-';
    const node = document.createElement('div');
    node.className = 'p-3 rounded bg-gray-900 border border-gray-800';
    node.innerHTML = '<div class="font-medium">'+escapeHtml(s.name)+'</div>' +
                     '<div class="muted text-sm">'+escapeHtml(s.tags || '')+' · ' + start.toLocaleString() + endTxt + ' · '+dur+'</div>';
    el.appendChild(node);
  });
}

function escapeHtml(unsafe) {
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}

async function getStatusAndInit(){
  const res = await fetch('/api/status');
  const data = await res.json();
  if (data.running){
    runningSession = data.session;
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    startTimerClient();
  } else {
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
  }
  refreshSessions();
}

getStatusAndInit();
</script>
</body>
</html>
"""

# --- Flask routes for API ---
@app.route("/")
def index():
    return render_template_string(INDEX_HTML, port=PORT)

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json() or {}
    name = data.get("name","").strip()
    tags = data.get("tags","").strip()
    if not name:
        return jsonify({"success": False, "error":"no name"}), 400
    # ensure db
    init_db()
    start_ts = int(time.time())
    sid = start_session_in_db(name, tags, start_ts)
    # return session info
    return jsonify({"success": True, "session": {"id": sid, "name": name, "tags": tags, "start_ts": start_ts}})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    data = request.get_json() or {}
    sid = data.get("session_id")
    if not sid:
        return jsonify({"success": False, "error":"no session_id"}), 400
    end_ts = int(time.time())
    duration = stop_session_in_db(sid, end_ts)
    if duration is None:
        return jsonify({"success": False, "error":"session not found"}), 404
    # return duration nicely formatted
    h = duration // 3600
    m = (duration % 3600) // 60
    s = duration % 60
    dur_str = f"{h:02d}:{m:02d}:{s:02d}"
    return jsonify({"success": True, "duration": duration, "duration_str": dur_str})

@app.route("/api/status", methods=["GET"])
def api_status():
    # returns whether a session is running and elapsed seconds
    row = get_last_running_session()
    if not row:
        return jsonify({"running": False})
    sid, name, tags, start_ts = row
    now = int(time.time())
    elapsed = now - start_ts
    h = elapsed // 3600
    m = (elapsed % 3600) // 60
    s = elapsed % 60
    return jsonify({"running": True, "session": {"id": sid, "name": name, "tags": tags, "start_ts": start_ts}, "elapsed": elapsed, "elapsed_str": f"{h:02d}:{m:02d}:{s:02d}"})

@app.route("/api/recent", methods=["GET"])
def api_recent():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, tags, start_ts, end_ts, duration FROM sessions ORDER BY start_ts DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    sessions = []
    for r in rows:
        sessions.append({"id": r[0], "name": r[1], "tags": r[2], "start_ts": r[3], "end_ts": r[4], "duration": r[5]})
    return jsonify({"sessions": sessions})

# --- Server run function ---
def run_flask():
    # ensure db exists
    init_db()
    # write a tiny log line
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] Starting StudyTrack server on port {PORT}\n")
    # run flask
    app.run(host="127.0.0.1", port=PORT, threaded=True)

# --- CLI behavior: start/stop/status ---
def cli_start():
    # if pid file exists and process running, warn
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"StudyTrack appears to be already running (pid {pid}).")
        return

    # spawn detached process that runs this script with --runserver
    python = sys.executable
    cmd = [python, os.path.abspath(__file__), "--runserver"]
    # detach with new process group
    try:
        p = Popen(cmd, stdout=open(LOG_FILE, "a"), stderr=open(LOG_FILE, "a"), preexec_fn=os.setsid, close_fds=True)
        write_pid(p.pid)
        print(f"StudyTrack started on http://localhost:{PORT} (pid {p.pid})")
        print("You can close this terminal. To stop: studytrack --stop")
    except Exception as e:
        print("Failed to start StudyTrack:", e)

def cli_stop():
    pid = read_pid()
    if not pid:
        print("StudyTrack is not running (no pid file).")
        return
    if not is_process_running(pid):
        print("PID file exists but process not running. Removing stale pid file.")
        remove_pid()
        return
    ok = kill_process_group(pid)
    if ok:
        # give it a moment
        time.sleep(0.4)
        remove_pid()
        print("StudyTrack stopped.")
    else:
        print("Failed to stop StudyTrack. You may try sudo pkill -f studytrack.py")

def cli_status():
    pid = read_pid()
    if not pid:
        print("StudyTrack is not running.")
        return
    if is_process_running(pid):
        print(f"StudyTrack is running (pid {pid}) at http://localhost:{PORT}")
    else:
        print("PID file exists but process not running. Remove pid file and try again.")

# If script is launched with --runserver, run Flask in foreground
def main():
    parser = argparse.ArgumentParser(description="StudyTrack CLI")
    parser.add_argument("--start", action="store_true", help="Start StudyTrack (detached)")
    parser.add_argument("--stop", action="store_true", help="Stop StudyTrack")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--runserver", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.runserver:
        # run flask server (foreground) - used by detached launcher
        run_flask()
        return

    if args.start:
        cli_start()
        return
    if args.stop:
        cli_stop()
        return
    if args.status:
        cli_status()
        return

    # default: open web UI in browser if running, else show help
    print("StudyTrack - use --start to run server in background, --stop to stop it, --status to check.")
    sys.exit(0)

if __name__ == "__main__":
    main()
