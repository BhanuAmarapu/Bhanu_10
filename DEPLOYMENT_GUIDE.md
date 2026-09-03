# Cloud Deployment Guide - Step by Step (Render)

This guide provides step-by-step instructions for deploying the **CloudDedup Pro** system on **Render** (the recommended free cloud hosting platform).

---

## 🚀 Quick Deploy to Render

### Step 1: Push the Latest Code to GitHub
Ensure all your files are committed and pushed:
```bash
git add .
git commit -m "Prepare codebase for cloud deployment"
git push origin main
```

### Step 2: Sign Up / Sign In on Render
1. Go to [Render](https://render.com).
2. Click **"Get Started for Free"** or **"Dashboard"**.
3. Sign up/in using your **GitHub** account to connect your repositories.

### Step 3: Create a New Web Service
1. In your Render Dashboard, click the **"New +"** button and select **"Web Service"**.
2. Connect your GitHub repository: **`BhanuAmarapu/final-project`** (or your current workspace repository).

### Step 4: Configure Web Service Settings
Fill in the configuration fields on Render as follows:

| Field | Value |
|-------|-------|
| **Name** | `cloud-dedup-pro` (or a name of your choice) |
| **Region** | Select the region closest to your users |
| **Branch** | `main` |
| **Root Directory** | (Leave empty) |
| **Environment** | `Python 3` |
| **Build Command** | `./build.sh` |
| **Start Command** | `gunicorn run:app` (runs the server via Gunicorn using run.py) |
| **Instance Type** | **Free** |

### Step 5: Configure Environment Variables
Under the **"Advanced"** settings, click **"Add Environment Variable"** and define the following variables:

```env
SECRET_KEY = your-random-secret-key
DEBUG = False
HOST = 0.0.0.0
PORT = 10000

# Database Configuration (MongoDB Atlas Connection)
MONGO_URI = mongodb+srv://bhanu89190654_db_user:P6s4X0ODr5bhcwlr@cluster0.clqmce7.mongodb.net/?appName=Cluster0
MONGO_DB = cloud_dedup

# AWS S3 Cloud Storage Configuration
USE_S3 = True
AWS_ACCESS_KEY = your-aws-access-key-id
AWS_SECRET_KEY = your-aws-secret-access-key
AWS_REGION = ap-southeast-2
S3_BUCKET_NAME = deduplicationfile
```

*Note: MongoDB Atlas provides persistent, cloud-hosted storage for all user accounts, file records, audio/video analysis metadata, and audit logs.*

### Step 6: Deploy!
1. Click **"Create Web Service"**.
2. Render will spin up the container, install requirements using `requirements.txt` via `build.sh`, and start the app.
3. Access your application via the URL provided by Render (e.g. `https://cloud-dedup-pro.onrender.com`).

---

## 🔧 Troubleshooting & Limitations

### Build Fails?
- Check the build logs in the Render console.
- Ensure all dependencies are in `requirements.txt` and `build.sh` has executable permissions.

### First Request Takes Long?
- The Render **Free Tier** puts the service to sleep after 15 minutes of inactivity. The first request after a sleep period can take 30–50 seconds to boot up the instance.

### File Uploads & AWS S3
- For security, local file uploads in Render are ephemeral and will be wiped when the service restarts.
- Set `USE_S3=True` with active credentials so that confirmed, unique files are stored permanently in your **AWS S3** bucket.
