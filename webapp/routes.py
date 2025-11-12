import os
import time
import sqlite3
import datetime
from flask import Flask, render_template, request, jsonify
from pathlib import Path
from .tracker import ActivityTracker 

DATA_DIR = Path.home() / ".studytrack"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "studytrack.db"

CURRENT_TRACKER = None

# --- DB simple helpers ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Sessions table
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
    # Activity log table
    c.execute('''
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        timestamp INTEGER,
        app_name TEXT,
        window_title TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions (id)
    )
    ''')
    # Breaks table
    c.execute('''
    CREATE TABLE IF NOT EXISTS breaks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        pause_ts INTEGER,
        resume_ts INTEGER,
        FOREIGN KEY (session_id) REFERENCES sessions (id)
    )
    ''')
    conn.commit()
    conn.close()
    
# --- HELPER: Format Time ---
def sec_to_hhmmss(seconds):
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m:02d}m {s:02d}s"

# --- HELPER: Get total break time ---
def get_total_break_time(conn, session_id):
    c = conn.cursor()
    c.execute("SELECT SUM(resume_ts - pause_ts) FROM breaks WHERE session_id = ? AND resume_ts IS NOT NULL", (session_id,))
    total_break = c.fetchone()[0] or 0
    return total_break

# --- MAIN APP ---
def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    
    init_db() # Ensure DB is created on startup

    # === PAGE ROUTES ===

    @app.route('/')
    def index():
        # This route now serves the 'Dashboard' page
        return render_template('dashboard.html', page_id='dashboard')

    @app.route('/timers')
    def timers_page():
        return render_template('timers.html', page_id='timers')

    @app.route('/history')
    def history_page():
        return render_template('history.html', page_id='history')

    @app.route('/analytics')
    def analytics_page():
        return render_template('analytics.html', page_id='analytics')

    @app.route('/session/<int:session_id>/summary')
    def session_summary_page(session_id):
        return render_template('summary.html', page_id='summary', session_id=session_id)

    # === API ROUTES ===

    @app.route('/api/start', methods=['POST'])
    def api_start():
        global CURRENT_TRACKER 
        data = request.get_json() or {}
        name = data.get('name','').strip()
        tags = data.get('tags','').strip()
        if not name:
            return jsonify({'success': False, 'error': 'no name'}), 400
        
        if CURRENT_TRACKER and CURRENT_TRACKER.is_alive():
            CURRENT_TRACKER.stop()
            CURRENT_TRACKER.join()
            
        start_ts = int(time.time())
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('INSERT INTO sessions (name, tags, start_ts, end_ts, duration) VALUES (?,?,?,?,?)',
                  (name, tags, start_ts, 0, 0))
        sid = c.lastrowid
        conn.commit()
        conn.close()
        
        CURRENT_TRACKER = ActivityTracker(session_id=sid, db_file=DB_FILE)
        CURRENT_TRACKER.start()
        
        return jsonify({'success': True, 'session': {'id': sid, 'name': name, 'tags': tags, 'start_ts': start_ts}})

    @app.route('/api/pause', methods=['POST'])
    def api_pause():
        global CURRENT_TRACKER
        data = request.get_json() or {}
        sid = data.get('session_id')
        if not sid:
            return jsonify({'success': False, 'error': 'no session_id'}), 400

        if CURRENT_TRACKER and CURRENT_TRACKER.is_alive() and CURRENT_TRACKER.session_id == sid:
            print(f"Pausing tracker for session {sid}")
            CURRENT_TRACKER.stop()
            CURRENT_TRACKER.join()
            CURRENT_TRACKER = None
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE breaks SET resume_ts = ? WHERE session_id = ? AND resume_ts IS NULL", (int(time.time()), sid))
        c.execute("INSERT INTO breaks (session_id, pause_ts, resume_ts) VALUES (?, ?, NULL)", (sid, int(time.time())))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'status': 'paused'})

    @app.route('/api/resume', methods=['POST'])
    def api_resume():
        global CURRENT_TRACKER
        data = request.get_json() or {}
        sid = data.get('session_id')
        if not sid:
            return jsonify({'success': False, 'error': 'no session_id'}), 400
            
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE breaks SET resume_ts = ? WHERE session_id = ? AND resume_ts IS NULL", (int(time.time()), sid))
        conn.commit()
        conn.close()
        
        if CURRENT_TRACKER and CURRENT_TRACKER.is_alive():
             CURRENT_TRACKER.stop()
             CURRENT_TRACKER.join()

        print(f"Resuming tracker for session {sid}")
        CURRENT_TRACKER = ActivityTracker(session_id=sid, db_file=DB_FILE)
        CURRENT_TRACKER.start()
        
        return jsonify({'success': True, 'status': 'running'})

    @app.route('/api/stop', methods=['POST'])
    def api_stop():
        global CURRENT_TRACKER 
        data = request.get_json() or {}
        sid = data.get('session_id')
        if not sid:
            return jsonify({'success': False, 'error':'no session_id'}), 400
            
        if CURRENT_TRACKER and CURRENT_TRACKER.is_alive() and CURRENT_TRACKER.session_id == sid:
            CURRENT_TRACKER.stop()
            CURRENT_TRACKER.join()
            CURRENT_TRACKER = None
            
        end_ts = int(time.time())
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute("UPDATE breaks SET resume_ts = ? WHERE session_id = ? AND resume_ts IS NULL", (end_ts, sid))
        conn.commit()
        
        c.execute('SELECT start_ts FROM sessions WHERE id=?', (sid,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'session not found'}), 404
            
        start_ts = row[0]
        
        total_break_time = get_total_break_time(conn, sid)
        final_duration = (end_ts - start_ts) - total_break_time
        if final_duration < 0: final_duration = 0 

        c.execute('UPDATE sessions SET end_ts=?, duration=? WHERE id=?', (end_ts, final_duration, sid))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'session_id': sid
        })

    @app.route('/api/status')
    def api_status():
        global CURRENT_TRACKER
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('SELECT id, name, tags, start_ts FROM sessions WHERE end_ts=0 ORDER BY start_ts DESC LIMIT 1')
        session_row = c.fetchone()
        
        if not session_row:
            if CURRENT_TRACKER and CURRENT_TRACKER.is_alive():
                CURRENT_TRACKER.stop()
                CURRENT_TRACKER = None
            conn.close()
            return jsonify({'running': False})
            
        sid, name, tags, start_ts = session_row
        
        c.execute("SELECT pause_ts FROM breaks WHERE session_id = ? AND resume_ts IS NULL ORDER BY pause_ts DESC LIMIT 1", (sid,))
        pause_row = c.fetchone()
        
        status = 'running' 
        total_break_time = get_total_break_time(conn, sid)
        
        if pause_row:
            status = 'paused'
            current_pause_ts = pause_row[0]
            current_break_duration = (int(time.time()) - current_pause_ts)
            if current_break_duration > 0:
                total_break_time += current_break_duration
            
            if CURRENT_TRACKER and CURRENT_TRACKER.is_alive():
                print("Status check: Paused state, stopping running tracker.")
                CURRENT_TRACKER.stop()
                CURRENT_TRACKER.join()
                CURRENT_TRACKER = None
        
        conn.close()
        
        now = int(time.time())
        elapsed_focus_time = (now - start_ts) - total_break_time
        if elapsed_focus_time < 0: elapsed_focus_time = 0
            
        return jsonify({
            'running': True,
            'status': status, 
            'session': {'id': sid, 'name': name, 'tags': tags, 'start_ts': start_ts}, 
            'elapsed': elapsed_focus_time, 
            'elapsed_str': sec_to_hhmmss(elapsed_focus_time)
        })

    @app.route('/api/recent')
    def api_recent():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Query for ALL sessions, including the running one
        c.execute('SELECT id, name, tags, start_ts, end_ts, duration FROM sessions ORDER BY start_ts DESC LIMIT 10')
        rows = c.fetchall()
        conn.close()
        sessions = []
        for r in rows:
            sessions.append({'id': r[0], 'name': r[1], 'tags': r[2], 'start_ts': r[3], 'end_ts': r[4], 
                             'duration': sec_to_hhmmss(r[5])}) # Format time
        return jsonify({'sessions': sessions})


    @app.route('/api/session/<int:session_id>/summary')
    def api_get_session_summary(session_id):
        LOG_INTERVAL_SECONDS = 1.0 # Use 1-second interval
        try:
            conn = sqlite3.connect(DB_FILE)
            # DO NOT use conn.row_factory
            c = conn.cursor()
            
            # --- FIX #1: Access by index ---
            c.execute("SELECT name, tags, start_ts, end_ts, duration FROM sessions WHERE id=?", (session_id,))
            session_row = c.fetchone()
            if not session_row:
                conn.close()
                return jsonify({'success': False, 'error': 'Session not found'}), 404
            
            s_name = session_row[0]
            s_tags = session_row[1]
            s_start = session_row[2]
            s_end = session_row[3]
            s_duration = session_row[4]
            # -------------------------------

            # --- FIX #2: Access by index ---
            c.execute('''
                SELECT app_name, COUNT(*) as count
                FROM activity_log WHERE session_id = ?
                GROUP BY app_name ORDER BY count DESC LIMIT 5
            ''', (session_id,))
            top_apps_raw = c.fetchall()
            
            top_apps = []
            for row in top_apps_raw:
                app_duration_sec = int(row[1] * LOG_INTERVAL_SECONDS) # 0=name, 1=count
                top_apps.append({
                    'name': row[0], 
                    'duration_str': sec_to_hhmmss(app_duration_sec)
                })
            # -------------------------------

            # --- FIX #3: Smarter Python-based Grouping ---
            c.execute('''
                SELECT app_name, window_title
                FROM activity_log WHERE session_id = ?
                ORDER BY timestamp ASC
            ''', (session_id,))
            raw_logs = c.fetchall()
            conn.close() 

            # This dictionary will hold the summed time
            # The key will be (app_name, simplified_window_title)
            # The value will be the sample_count
            grouped_activity = {}

            for log in raw_logs:
                app_name = log[0]
                window_title = log[1]

                # --- Smart Title Cleaning ---
                # This is the key part. We simplify titles.
                
                # 1. Clean browser titles (like the one in your screenshot)
                # "00:52 - StudyTrack" becomes "StudyTrack"
                # "01:00 - StudyTrack" becomes "StudyTrack"
                if app_name.lower().startswith('brave') and ' - ' in window_title:
                    try:
                        # Split "00:52 - StudyTrack" and take the last part
                        simplified_title = window_title.split(' - ')[-1].strip()
                        # If the first part was a timer (e.g., "00:52"), this is a good simplification.
                        # We check if the first part looks like a timer.
                        first_part = window_title.split(' - ')[0]
                        if ':' in first_part and any(char.isdigit() for char in first_part):
                            window_title = simplified_title
                        else:
                            # If it's "Google - Gmail", we keep it as "Google - Gmail"
                            pass
                    except Exception:
                        pass # Keep original title if splitting fails

                # 2. Add more cleaning rules here if needed
                # e.g., for VSCode: "file.py - MyProject" -> "MyProject"
                
                # --- Grouping ---
                key = (app_name, window_title)
                if key not in grouped_activity:
                    grouped_activity[key] = 0
                grouped_activity[key] += 1 # Add one sample (1 second)

            # Convert the dictionary to a list
            activity_blocks_raw = []
            for (app, title), count in grouped_activity.items():
                activity_blocks_raw.append({
                    'app_name': app,
                    'window_title': title,
                    'sample_count': count
                })

            # Sort the list by time spent (highest first)
            activity_blocks_sorted = sorted(activity_blocks_raw, key=lambda x: x['sample_count'], reverse=True)

            # Format for the frontend
            activity_blocks = []
            for block in activity_blocks_sorted:
                duration_sec = int(block['sample_count'] * LOG_INTERVAL_SECONDS)
                if duration_sec > 0:
                    activity_blocks.append({
                        'app_name': block['app_name'],
                        'window_title': block['window_title'],
                        'duration_str': sec_to_hhmmss(duration_sec)
                    })
            # -------------------------------

            return jsonify({
                'success': True,
                'session': {
                    'id': session_id,
                    'name': s_name,
                    'tags': s_tags,
                    'start_time': s_start,
                    'end_time': s_end,
                    'duration_str': sec_to_hhmmss(s_duration)
                },
                'summary': {'top_apps': top_apps, 'total_logs': len(raw_logs)},
                'activity_blocks': activity_blocks
            })
        except Exception as e:
            print(f"Error getting summary: {e}")
            if 'conn' in locals() and conn: conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500
        

    # === NEW API ROUTE FOR ANALYTICS CHART ===
    @app.route('/api/analytics/weekly_summary')
    def api_analytics_weekly_summary():
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # 1. Get today's date (in user's local timezone)
            today = datetime.date.today()
            seven_days_ago = today - datetime.timedelta(days=6)
            
            # 2. Generate date labels for the last 7 days
            # Format: 'Nov 13'
            labels = [(today - datetime.timedelta(days=i)).strftime('%b %d') for i in range(6, -1, -1)]
            
            # 3. Get the start timestamp for the query (7 days ago at midnight)
            start_ts = int(datetime.datetime.combine(seven_days_ago, datetime.time.min).timestamp())

            # 4. Query the DB
            # We select the date of the session (local time) and sum the duration
            c.execute('''
                SELECT 
                    DATE(start_ts, 'unixepoch', 'localtime') as session_date, 
                    SUM(duration) as total_duration
                FROM sessions
                WHERE start_ts >= ? AND duration > 0
                GROUP BY session_date
                ORDER BY session_date ASC
            ''', (start_ts,))
            
            rows = c.fetchall()
            conn.close()

            # 5. Process the data into a dictionary for easy lookup
            session_data = {row[0]: (row[1] or 0) for row in rows}
            
            # 6. Build the final data array, matching dates from our query
            data = []
            for i in range(6, -1, -1):
                date_key = (today - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
                # Add duration in HOURS for the chart
                duration_hours = (session_data.get(date_key, 0)) / 3600.0
                data.append(round(duration_hours, 2))
                
            return jsonify({'success': True, 'labels': labels, 'data': data})
            
        except Exception as e:
            print(f"Error in weekly summary: {e}")
            if 'conn' in locals() and conn: conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    return app

    return app