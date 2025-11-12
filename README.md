
### 🧾 **README.md**


# 🌙 StudyTrack

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-Backend-lightgrey?logo=flask)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Version-v1.0-success)
![Dark Mode](https://img.shields.io/badge/Theme-Dark%20Mode-black)

> **StudyTrack** is a lightweight local web app designed for focus sessions, studying, and productivity tracking — built for Linux systems like **Omarchy**.  
> It runs a minimal Flask server locally and opens as a web app in your browser.

---

## 🚀 Features

✅ Start & stop study/work sessions  
✅ Add **tags** (e.g., `study`, `work`, `project`)  
✅ Real-time **timer display**  
✅ Auto-saves sessions to local database  
✅ **Dark, responsive UI** optimized for low-RAM systems  
✅ Simple CLI interface — start, stop, and check status  

---

## 🧩 Tech Stack

- **Backend:** Flask (Python)
- **Frontend:** HTML + TailwindCSS (dark mode)
- **Database:** SQLite (local)
- **Environment:** Linux (tested on Omarchy / Arch-based systems)
- **Command Interface:** Bash wrapper for CLI control

---

## ⚙️ Installation

```bash
# 1. Clone the repo
git clone https://github.com/git-dheer/Study-Track.git
cd Study-Track

# 2. Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
````

---

## 🖥️ Usage

### CLI Commands

```bash
# Start the local Flask server
studytrack --start

# Check status
studytrack --status

# Stop the app
studytrack --stop
```

> ⚡ Once started, open your browser (or installed web app) at
> **[http://localhost:8080](http://localhost:8080)**

You can now create sessions, assign tags, and view summaries directly in the web UI.

---

## 📂 Project Structure

```
Study-Track/
├── studytrack.py           # main CLI + Flask launcher
├── requirements.txt
├── .gitignore
├── README.md
├── webapp/
│   ├── app.py              # Flask routes + APIs
│   ├── static/
│   │   └── styles.css
│   └── templates/
│       └── dashboard.html  # dark-mode UI
└── data/
    └── sessions.db         # local SQLite DB (auto-generated)
```

---

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

## 📊 Roadmap

🔹 v2.0 — Application & website usage tracking

🔹 v3.0 — Charts and visual analytics

🔹 v4.0 — Focus goals, daily summaries, and productivity scores

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

