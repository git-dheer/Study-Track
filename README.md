
### 🧾 **README.md**


# 🌙 StudyTrack

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-Backend-lightgrey?logo=flask)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Version-2.0-success)
![Dark Mode](https://img.shields.io/badge/Theme-Dark%20Mode-black)

A lightweight, local-first time tracker and productivity dashboard.

StudyTrack runs a minimal Flask server on your local machine (`http://localhost:8080`) to give you a private, web-based interface for tracking your study sessions, work, and projects. It features detailed activity tracking (for Hyprland users) and a full analytics dashboard.

---

## 🚀 Features

* **Modern UI:** A clean, dark-mode, and responsive dashboard.
* **Multiple Timer Modes:**
    * **Stopwatch:** A simple start/pause/stop timer for flexible sessions.
    * **Pomodoro:** A fully functional Pomodoro timer that logs focus/break cycles as a single session.
    * **Timer:** A countdown timer that automatically starts and stops a session when the time is up.
* **Dynamic Dashboard:** See your "Today's Focus," your currently running session, and a 30-day productivity chart, all in one place.
* **Session History:** A searchable and filterable list of all past sessions, with the ability to delete old entries.
* **Detailed Analytics:**
    * Filter your entire productivity history by date range (Daily, Weekly, Monthly, Custom) and by tag.
    * **Overview Cards:** See total time, total sessions, and average session length for any period.
    * **Productivity Chart:** A filterable line chart to see your focus trends over time.
    * **Activity Analysis:** Pie charts and bar charts show your time distribution across different apps and tags.
* **Smart Activity Tracking:**
    * (For Hyprland) Uses `hyprctl` and `psutil` to log your active application and window title every second.
    * **Smart Grouping:** The session summary intelligently groups activity, turning "00:52 - App" and "00:53 - App" into a single "App" entry.

---

## ⚙️ Installation

```bash
# 1. Clone the repo
git clone [https://github.com/git-dheer/Study-Track.git](https://github.com/git-dheer/Study-Track.git)
cd Study-Track

# 2. Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
````

-----

## 🖥️ Usage

The app is controlled by the main `studytrack.py` script.

```bash
# Start the server in the background (recommended)
python3 studytrack.py --start

# Stop the background server
python3 studytrack.py --stop

# Check the status
python3 studytrack.py --status

# --- OR ---

# Run the server in the foreground (for debugging)
python3 studytrack.py --runserver
```

> ⚡ Once started, open your browser to
> **[http://localhost:8080](https://www.google.com/search?q=http://localhost:8080)**

-----



## 🧰 Wrapper (Optional)

If you want to use a simple CLI shortcut instead of running Flask manually,
create a file at `/usr/local/bin/studytrack`:

```bash
#!/bin/bash
DIR="/home/<username>/Documents/GitHub/Study-Track"
source "$DIR/venv/bin/activate"
python "$DIR/studytrack.py" "$@"
```

Then make it executable:

```bash
sudo chmod +x /usr/local/bin/studytrack
```

---


## 🤝 Contributing

Pull requests are welcome!
For major changes, please open an issue first to discuss what you’d like to modify or add.

---

## 📜 License

This project is licensed under the [MIT License](LICENSE).

---

### 💡 Author

Made with ❤️ by **Dheer Parekh**

💻 [GitHub Profile](https://github.com/git-dheer)

