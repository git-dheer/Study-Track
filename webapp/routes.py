import os
import time
import sqlite3
from flask import Flask, render_template, request, jsonify
from pathlib import Path

DATA_DIR = Path.home() / ".studytrack"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "studytrack.db"

# --- DB simple helpers ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        tags TEXT,
        start_ts INTEGER,
        end_ts INTEGER,
        duration INTEGER
    )
    ''')
    conn.commit()
    conn.close()

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')

    @app.route('/')
    def index():
        return render_template('dashboard.html')

    @app.route('/api/start', methods=['POST'])
    def api_start():
        data = request.get_json() or {}
        name = data.get('name','').strip()
        tags = data.get('tags','').strip()
        if not name:
            return jsonify({'success': False, 'error': 'no name'}), 400
        init_db()
        start_ts = int(time.time())
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('INSERT INTO sessions (name, tags, start_ts, end_ts, duration) VALUES (?,?,?,?,?)',
                  (name, tags, start_ts, 0, 0))
        sid = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'session': {'id': sid, 'name': name, 'tags': tags, 'start_ts': start_ts}})

    @app.route('/api/stop', methods=['POST'])
    def api_stop():
        data = request.get_json() or {}
        sid = data.get('session_id')
        if not sid:
            return jsonify({'success': False, 'error':'no session_id'}), 400
        end_ts = int(time.time())
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT start_ts FROM sessions WHERE id=?', (sid,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'session not found'}), 404
        duration = int(end_ts - row[0])
        c.execute('UPDATE sessions SET end_ts=?, duration=? WHERE id=?', (end_ts, duration, sid))
        conn.commit()
        conn.close()
        h = duration//3600; m=(duration%3600)//60; s=duration%60
        return jsonify({'success': True, 'duration': duration, 'duration_str': f"{h:02d}:{m:02d}:{s:02d}"})

    @app.route('/api/status')
    def api_status():
        init_db()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, name, tags, start_ts FROM sessions WHERE end_ts=0 ORDER BY start_ts DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        if not row:
            return jsonify({'running': False})
        sid, name, tags, start_ts = row
        now = int(time.time())
        elapsed = now - start_ts
        h = elapsed//3600; m=(elapsed%3600)//60; s=elapsed%60
        return jsonify({'running': True, 'session': {'id': sid, 'name': name, 'tags': tags, 'start_ts': start_ts}, 'elapsed': elapsed, 'elapsed_str': f"{h:02d}:{m:02d}:{s:02d}"})

    @app.route('/api/recent')
    def api_recent():
        init_db()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, name, tags, start_ts, end_ts, duration FROM sessions ORDER BY start_ts DESC LIMIT 10')
        rows = c.fetchall()
        conn.close()
        sessions = []
        for r in rows:
            sessions.append({'id': r[0], 'name': r[1], 'tags': r[2], 'start_ts': r[3], 'end_ts': r[4], 'duration': r[5]})
        return jsonify({'sessions': sessions})

    return app