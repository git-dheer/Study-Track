import os
import time
import sqlite3
import datetime # Make sure this is here
from flask import Flask, render_template, request, jsonify
from pathlib import Path
from .tracker import ActivityTracker 

DATA_DIR = Path.home() / ".studytrack"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "studytrack.db"

CURRENT_TRACKER = None

LOG_INTERVAL_SECONDS = 1.0 

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
        duration INTEGER,
        target_duration INTEGER DEFAULT 0  -- <-- ADDED THIS
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
        duration = data.get('duration', 0) # <-- ADDED THIS
        if not name:
            return jsonify({'success': False, 'error': 'no name'}), 400
        
        if CURRENT_TRACKER and CURRENT_TRACKER.is_alive():
            CURRENT_TRACKER.stop()
            CURRENT_TRACKER.join()
            
        start_ts = int(time.time())
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # --- UPDATED THIS QUERY ---
        c.execute('INSERT INTO sessions (name, tags, start_ts, end_ts, duration, target_duration) VALUES (?,?,?,?,?,?)',
                  (name, tags, start_ts, 0, 0, duration))
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

    # --- THIS IS THE NEW, SMART /api/status ---
    @app.route('/api/status')
    def api_status():
        global CURRENT_TRACKER
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Get target_duration as well
        c.execute('SELECT id, name, tags, start_ts, target_duration FROM sessions WHERE end_ts=0 ORDER BY start_ts DESC LIMIT 1')
        session_row = c.fetchone()
        
        if not session_row:
            if CURRENT_TRACKER and CURRENT_TRACKER.is_alive():
                CURRENT_TRACKER.stop()
                CURRENT_TRACKER = None
            conn.close()
            return jsonify({'running': False})
            
        sid, name, tags, start_ts, target_duration = session_row
        
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
                CURRENT_TRACKER.stop()
                CURRENT_TRACKER.join()
                CURRENT_TRACKER = None
        
        conn.close()
        
        now = int(time.time())
        elapsed_focus_time = (now - start_ts) - total_break_time
        if elapsed_focus_time < 0: elapsed_focus_time = 0
        
        is_countdown = target_duration > 0
        final_display_time = elapsed_focus_time
        
        if is_countdown:
            # This is a countdown timer, calculate time left
            time_left = target_duration - elapsed_focus_time
            if time_left < 0: time_left = 0
            final_display_time = time_left
            
        return jsonify({
            'running': True,
            'status': status, 
            'session': {'id': sid, 'name': name, 'tags': tags, 'start_ts': start_ts, 'target_duration': target_duration}, 
            'elapsed': elapsed_focus_time,  # This is the raw count-up
            'elapsed_str': sec_to_hhmmss(final_display_time), # THIS IS THE FIX. This now holds the countdown.
            'is_countdown': is_countdown
        })

    @app.route('/api/all_sessions')
    def api_all_sessions():
        search_name = request.args.get('name', '').strip()
        search_tag = request.args.get('tag', '').strip()

        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            query = 'SELECT id, name, tags, start_ts, end_ts, duration FROM sessions'
            params = []
            
            where_clauses = []
            if search_name:
                where_clauses.append('name LIKE ?')
                params.append(f'%{search_name}%')
            
            if search_tag:
                where_clauses.append('tags LIKE ?')
                params.append(f'%{search_tag}%')

            if where_clauses:
                query += ' WHERE ' + ' AND '.join(where_clauses)
                
            query += ' ORDER BY start_ts DESC'
            
            c.execute(query, tuple(params))
            rows = c.fetchall()
            conn.close()
            
            sessions = []
            for r in rows:
                sessions.append({
                    'id': r[0], 
                    'name': r[1], 
                    'tags': r[2], 
                    'start_ts': r[3], 
                    'end_ts': r[4], 
                    'duration': sec_to_hhmmss(r[5])
                })
            return jsonify({'success': True, 'sessions': sessions})
        except Exception as e:
            print(f"Error getting all sessions: {e}")
            if 'conn' in locals() and conn: conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/session/<int:session_id>/summary')
    def api_get_session_summary(session_id):
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
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

            c.execute('''
                SELECT app_name, COUNT(*) as count
                FROM activity_log WHERE session_id = ?
                GROUP BY app_name ORDER BY count DESC LIMIT 5
            ''', (session_id,))
            top_apps_raw = c.fetchall()
            
            top_apps = []
            for row in top_apps_raw:
                app_duration_sec = int(row[1] * LOG_INTERVAL_SECONDS)
                top_apps.append({
                    'name': row[0], 
                    'duration_str': sec_to_hhmmss(app_duration_sec)
                })

            # --- Smarter Python-based Grouping ---
            c.execute('''
                SELECT app_name, window_title
                FROM activity_log WHERE session_id = ?
                ORDER BY timestamp ASC
            ''', (session_id,))
            raw_logs = c.fetchall()
            conn.close() 

            grouped_activity = {}

            for log in raw_logs:
                app_name = log[0]
                window_title = log[1]

                if app_name.lower().startswith('brave') and ' - ' in window_title:
                    try:
                        simplified_title = window_title.split(' - ')[-1].strip()
                        first_part = window_title.split(' - ')[0]
                        if ':' in first_part and any(char.isdigit() for char in first_part):
                            window_title = simplified_title
                    except Exception:
                        pass
                
                key = (app_name, window_title)
                if key not in grouped_activity:
                    grouped_activity[key] = 0
                grouped_activity[key] += 1

            activity_blocks_raw = []
            for (app, title), count in grouped_activity.items():
                activity_blocks_raw.append({
                    'app_name': app,
                    'window_title': title,
                    'sample_count': count
                })

            activity_blocks_sorted = sorted(activity_blocks_raw, key=lambda x: x['sample_count'], reverse=True)

            activity_blocks = []
            for block in activity_blocks_sorted:
                duration_sec = int(block['sample_count'] * LOG_INTERVAL_SECONDS)
                if duration_sec > 0:
                    activity_blocks.append({
                        'app_name': block['app_name'],
                        'window_title': block['window_title'],
                        'duration_str': sec_to_hhmmss(duration_sec)
                    })

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

    @app.route('/api/session/delete', methods=['POST'])
    def api_delete_session():
        data = request.get_json() or {}
        sid = data.get('session_id')
        if not sid:
            return jsonify({'success': False, 'error': 'no session_id'}), 400
            
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute("DELETE FROM activity_log WHERE session_id = ?", (sid,))
            c.execute("DELETE FROM breaks WHERE session_id = ?", (sid,))
            c.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'session_id': sid})
        except Exception as e:
            print(f"Error deleting session {sid}: {e}")
            if 'conn' in locals() and conn: conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/tags')
    def api_get_tags():
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute("SELECT tags FROM sessions WHERE tags IS NOT NULL AND tags != ''")
            rows = c.fetchall()
            conn.close()
            
            unique_tags = set()
            
            for row in rows:
                tags_list = [tag.strip() for tag in row[0].split(',') if tag.strip()]
                unique_tags.update(tags_list)
            
            sorted_tags = sorted(list(unique_tags))
            
            return jsonify({'success': True, 'tags': sorted_tags})
        except Exception as e:
            print(f"Error getting tags: {e}")
            if 'conn' in locals() and conn: conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/analytics/summary')
    def api_analytics_summary():
        try:
            # --- 1. Get Filters (Date Range & Tag) ---
            filter_tag = request.args.get('tag', 'all').strip()
            range_type = request.args.get('range_type', 'monthly').strip()
            start_date_str = request.args.get('start_date', None)
            end_date_str = request.args.get('end_date', None)

            # --- 2. Calculate Start/End Timestamps (for filtered queries) ---
            today = datetime.date.today()
            start_ts = 0
            end_ts = int(datetime.datetime.combine(today, datetime.time.max).timestamp())
            
            if range_type == 'daily':
                start_ts = int(datetime.datetime.combine(today, datetime.time.min).timestamp())
            elif range_type == 'weekly':
                start_of_week = today - datetime.timedelta(days=today.weekday())
                start_ts = int(datetime.datetime.combine(start_of_week, datetime.time.min).timestamp())
            elif range_type == 'monthly':
                start_of_month = today.replace(day=1)
                start_ts = int(datetime.datetime.combine(start_of_month, datetime.time.min).timestamp())
            elif range_type == 'yearly':
                start_of_year = today.replace(day=1, month=1)
                start_ts = int(datetime.datetime.combine(start_of_year, datetime.time.min).timestamp())
            elif range_type == 'custom' and start_date_str and end_date_str:
                try:
                    start_date_obj = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    end_date_obj = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    start_ts = int(datetime.datetime.combine(start_date_obj, datetime.time.min).timestamp())
                    end_ts = int(datetime.datetime.combine(end_date_obj, datetime.time.max).timestamp())
                except ValueError:
                     return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
            else:
                # Fallback for default 'monthly'
                start_of_month = today.replace(day=1)
                start_ts = int(datetime.datetime.combine(start_of_month, datetime.time.min).timestamp())
            
            # --- 3. Build Base SQL Filters ---
            sql_filters = "WHERE duration > 0 AND start_ts >= ? AND start_ts <= ?"
            sql_params = [start_ts, end_ts]
            
            if filter_tag != 'all':
                sql_filters += " AND (tags LIKE ?)"
                sql_params.append(f'%{filter_tag}%')

            # --- 4. Run Queries ---
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()

            # --- Overview Stats (Uses filtered data) ---
            c.execute(f"SELECT COUNT(id), SUM(duration) FROM sessions {sql_filters}", tuple(sql_params))
            stats_row = c.fetchone()
            total_sessions = stats_row[0] or 0
            total_duration_sec = stats_row[1] or 0
            avg_duration_sec = (total_duration_sec / total_sessions) if total_sessions > 0 else 0

            overview_stats = {
                'total_sessions': total_sessions,
                'total_time_str': sec_to_hhmmss(total_duration_sec),
                'avg_time_str': sec_to_hhmmss(avg_duration_sec)
            }

            # --- Top Applications (Uses filtered data) ---
            c.execute(f"SELECT id FROM sessions {sql_filters}", tuple(sql_params))
            session_ids = [row[0] for row in c.fetchall()]
            
            top_apps_labels = []
            top_apps_data = []
            if session_ids:
                placeholders = ','.join('?' for _ in session_ids)
                c.execute(f'''
                    SELECT app_name, COUNT(*) as sample_count
                    FROM activity_log
                    WHERE session_id IN ({placeholders})
                    GROUP BY app_name
                    ORDER BY sample_count DESC LIMIT 10
                ''', tuple(session_ids))
                top_apps_raw = c.fetchall()
                for row in top_apps_raw:
                    top_apps_labels.append(row[0])
                    top_apps_data.append(round((row[1] * LOG_INTERVAL_SECONDS) / 3600.0, 2))

            # --- Top Tags (Uses filtered data) ---
            c.execute(f"SELECT tags, duration FROM sessions {sql_filters}", tuple(sql_params))
            tags_rows = c.fetchall()
            
            tag_durations = {}
            for row in tags_rows:
                tags_list = [tag.strip() for tag in row[0].split(',') if tag.strip()]
                duration = row[1]
                for tag in tags_list:
                    if filter_tag != 'all' and tag != filter_tag:
                        continue
                    if tag not in tag_durations: tag_durations[tag] = 0
                    tag_durations[tag] += duration
            
            sorted_tags = sorted(tag_durations.items(), key=lambda item: item[1], reverse=True)
            top_tags_labels = []
            top_tags_data = []
            other_duration = 0
            for i, (tag, duration) in enumerate(sorted_tags):
                if i < 7:
                    top_tags_labels.append(tag)
                    top_tags_data.append(round(duration / 3600.0, 2))
                else:
                    other_duration += duration
            
            if other_duration > 0:
                top_tags_labels.append('Other')
                top_tags_data.append(round(other_duration / 3600.0, 2))
            
            # --- Productivity Over Time (Analytics Page - USES FILTERS) ---
            c.execute(f'''
                SELECT DATE(start_ts, 'unixepoch', 'localtime') as session_date, 
                       SUM(duration) as total_duration
                FROM sessions
                {sql_filters} 
                GROUP BY session_date
                ORDER BY session_date ASC
            ''', tuple(sql_params))
            
            daily_rows_filtered = c.fetchall()
            session_data_filtered = {row[0]: (row[1] or 0) for row in daily_rows_filtered}
            
            start_date = datetime.date.fromtimestamp(start_ts)
            end_date = datetime.date.fromtimestamp(end_ts)
            
            daily_labels_filtered = []
            daily_data_filtered = []
            
            current_date = start_date
            while current_date <= end_date:
                date_key = current_date.strftime('%Y-%m-%d')
                num_days = (end_date - start_date).days
                if num_days > 30:
                    if current_date.day % max(1, (num_days // 30)) != 1 and current_date != start_date:
                        daily_labels_filtered.append('')
                    else:
                        daily_labels_filtered.append(current_date.strftime('%b %d'))
                else:
                    daily_labels_filtered.append(current_date.strftime('%b %d'))
                duration_hours = (session_data_filtered.get(date_key, 0)) / 3600.0
                daily_data_filtered.append(round(duration_hours, 2))
                current_date += datetime.timedelta(days=1)
                
            conn.close()
            
            return jsonify({
                'success': True,
                'overview': overview_stats,
                'top_apps': {'labels': top_apps_labels, 'data': top_apps_data},
                'top_tags': {'labels': top_tags_labels, 'data': top_tags_data},
                'daily_trend': {'labels': daily_labels_filtered, 'data': daily_data_filtered} # Renamed
            })
            
        except Exception as e:
            print(f"Error in analytics summary: {e}")
            if 'conn' in locals() and conn: conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500
            
    @app.route('/api/dashboard_stats')
    def api_dashboard_stats():
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()

            # --- 1. Get Today's Focus (Corrected) ---
            today = datetime.date.today()
            today_str = today.strftime('%Y-%m-%d')
            
            # Get total duration for COMPLETED sessions today
            c.execute('''
                SELECT SUM(duration) 
                FROM sessions 
                WHERE DATE(start_ts, 'unixepoch', 'localtime') = ? AND end_ts > 0
            ''', (today_str,))
            today_completed_duration = c.fetchone()[0] or 0
            
            # NOW, find the RUNNING session's elapsed time (if it started today)
            c.execute('''
                SELECT id, start_ts, target_duration 
                FROM sessions 
                WHERE DATE(start_ts, 'unixepoch', 'localtime') = ? AND end_ts = 0
                ORDER BY start_ts DESC LIMIT 1
            ''', (today_str,))
            running_session = c.fetchone()
            
            today_running_duration = 0
            if running_session:
                # Get total break time for this running session
                total_break = get_total_break_time(conn, running_session[0])
                # Calculate elapsed time
                elapsed = (int(time.time()) - running_session[1]) - total_break
                if elapsed > 0:
                    today_running_duration = elapsed

            # Add them together
            total_today_duration = today_completed_duration + today_running_duration
            
            # --- 2. Get 30-Day Trend (for chart) ---
            start_date_30 = today - datetime.timedelta(days=29)
            start_ts_30 = int(datetime.datetime.combine(start_date_30, datetime.time.min).timestamp())
            
            c.execute('''
                SELECT DATE(start_ts, 'unixepoch', 'localtime') as session_date, 
                       SUM(duration) as total_duration
                FROM sessions
                WHERE start_ts >= ? AND duration > 0
            ''', (start_ts_30,))
            
            daily_rows = c.fetchall()
            session_data = {row[0]: (row[1] or 0) for row in daily_rows}
            
            daily_labels = []
            daily_data = []
            
            current_date = start_date_30
            while current_date <= today:
                date_key = current_date.strftime('%Y-%m-%d')
                daily_labels.append(current_date.strftime('%b %d'))
                
                # Also add today's RUNNING duration to the chart
                duration_sec = session_data.get(date_key, 0)
                if date_key == today_str:
                    duration_sec += today_running_duration
                    
                duration_hours = duration_sec / 3600.0
                daily_data.append(round(duration_hours, 2))
                current_date += datetime.timedelta(days=1)
                
            conn.close()
            
            return jsonify({
                'success': True,
                'todays_focus_str': sec_to_hhmmss(total_today_duration),
                'daily_trend': {'labels': daily_labels, 'data': daily_data}
            })
            
        except Exception as e:
            print(f"Error in dashboard stats: {e}")
            if 'conn' in locals() and conn: conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    return app