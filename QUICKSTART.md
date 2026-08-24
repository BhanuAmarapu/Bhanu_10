# Quick Start Guide

## 🚀 How to Run the Application

You have **two ways** to run this application:

### Option 1: Simple Run (Recommended)
```bash
python run.py
```
This starts the server with automatic ML model and database checks.

### Option 2: Direct Run
```bash
python app.py
```
Runs the Flask app directly.

---

## 📋 First Time Setup

If this is your first time running the application:

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Setup Script** (Optional but recommended):
   ```bash
   python scripts/setup.py
   ```
   This will:
   - Check all dependencies
   - Create necessary directories
   - Initialize the database
   - Create a default admin user

3. **Start the Application**:
   ```bash
   python run.py
   ```

---

## 🔐 Default Credentials

- **Username**: `admin`
- **Password**: `admin123`

⚠️ **IMPORTANT**: Change the default password after first login!

---

## 🌐 Access the Application

Once running, open your browser and go to:
```
http://127.0.0.1:5000
```

---

## 🛑 Stopping the Server

Press `CTRL+C` in the terminal where the server is running.

---

## ❓ Troubleshooting

### Port Already in Use
If you see "Port 5000 is already in use":
```powershell
# Windows PowerShell
Stop-Process -Name python -Force
```

### Database Errors
If you see database errors:
```bash
python init_db.py
```

### Missing Dependencies
```bash
pip install -r requirements.txt
```

---

## 📁 Project Structure

```
Hybrid ML-CNS Dedupliation System/
├── app.py                  # Main Flask application
├── run.py                  # Entry point script
├── config.py               # Configuration settings
├── ml_model.py            # ML prediction logic
├── dedup.py               # Deduplication engine
├── auditing.py            # Integrity verification
├── utils.py               # Helper functions
├── init_db.py             # Database initialization
├── requirements.txt       # Python dependencies
├── scripts/
│   └── setup.py          # Setup script
├── templates/            # HTML templates
├── static/              # CSS, JS, images
├── db/                  # SQLite database
├── uploads/             # Uploaded files
└── ml_data/            # ML training data
```

---

## ✨ Features

- ✅ User authentication (login/register)
- ✅ Role-based access control (user/admin)
- ✅ ML-based duplicate prediction
- ✅ Secure file deduplication with CNS
- ✅ AWS S3 cloud storage integration
- ✅ Integrity auditing
- ✅ Real-time dashboard with analytics
- ✅ Admin file management (view/delete/rename)

---

## 🔧 Configuration

Edit `config.py` or `.env` to configure:
- AWS S3 credentials
- Storage paths
- Security settings
- ML model parameters
