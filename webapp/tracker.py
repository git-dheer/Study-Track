import time
import sqlite3
import threading
import subprocess
import json
import psutil
from pathlib import Path

# How often to log the active app (in seconds)
LOG_INTERVAL = 1.0 # Was 5.0

class ActivityTracker(threading.Thread):
    """
    A background thread that monitors the active Hyprland window
    and logs it to the database.
    """
    def __init__(self, session_id, db_file):
        super().__init__()
        self.session_id = session_id
        self.db_file = db_file
        self.running = False
        self._stop_event = threading.Event()
        self.client_cache = {} # Cache for PID -> app_name
        
    def stop(self):
        """Signals the thread to stop."""
        self._stop_event.set()

    def run(self):
            """The main loop for the tracking thread."""
            self.running = True
            print(f"[Tracker] Starting for session {self.session_id} (Hyprland Mode)")
            
            # We remove self.last_app and self.last_title, they are no longer needed
            # self.last_app = None
            # self.last_title = None

            while not self._stop_event.is_set():
                try:
                    app_name, window_title = self._get_active_window_info()

                    # --- THIS IS THE FIX ---
                    # We must log EVERY sample, not just changes.
                    # The old "if" statement was the bug.
                    if app_name:
                        self._log_activity_to_db(app_name, window_title)
                    # ---------------------

                except Exception as e:
                    print(f"[Tracker] Error in loop: {e}")
                    
                # Wait for the specified interval
                self._stop_event.wait(LOG_INTERVAL)
                
            print(f"[Tracker] Stopping for session {self.session_id}")
            self.running = False

    def _get_active_window_info(self):
        """
        Fetches the application name and window title of the
        currently focused window using hyprctl.
        """
        try:
            # 1. Get the active window's JSON data
            result = subprocess.run(
                ['hyprctl', 'activewindow', '-j'],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            
            window_title = data.get('title', '')
            pid = data.get('pid', -1)
            
            # 2. Get the application name (class)
            # 'initialClass' is often more reliable than 'class'
            app_name = data.get('initialClass')
            
            # 3. Fallback using 'class' if 'initialClass' is empty
            if not app_name:
                 app_name = data.get('class', 'Unknown')

            # 4. Fallback using psutil if class is still unknown (e.g., for terminals)
            # This helps differentiate 'foot' from 'btop' running in foot
            if pid != -1:
                try:
                    # Check cache first
                    if pid in self.client_cache:
                        app_name = self.client_cache[pid]
                    else:
                        proc = psutil.Process(pid)
                        # If the app name is a generic terminal, try to get the child process
                        if app_name.lower() in ['foot', 'kitty', 'alacritty', 'wezterm']:
                            children = proc.children()
                            if children:
                                # Get the name of the most recent child (likely the command)
                                app_name = children[-1].name()
                        
                        self.client_cache[pid] = app_name # Cache the result
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass # Process might have died or be a system process

            return app_name, window_title

        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            # This can happen if no window is focused or hyprctl isn't found
            return "Desktop", "No window focused"
        except Exception as e:
            print(f"[Tracker] Error getting window info: {e}")
            return None, None

    def _log_activity_to_db(self, app_name, window_title):
        """Writes the collected activity to the SQLite database."""
        try:
            conn = sqlite3.connect(self.db_file)
            c = conn.cursor()
            c.execute(
                "INSERT INTO activity_log (session_id, timestamp, app_name, window_title) VALUES (?, ?, ?, ?)",
                (self.session_id, int(time.time()), app_name, window_title)
            )
            conn.commit()
            conn.close()
            print(f"[Tracker] Logged: {app_name} - {window_title}")
        except Exception as e:
            print(f"[Tracker] DB Error: {e}")