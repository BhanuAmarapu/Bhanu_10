# GitHub Setup Guide

## 📋 Prerequisites
- GitHub account (create one at https://github.com if you don't have one)
- Git installed on your computer (already done ✓)

## 🚀 Steps to Push to GitHub

### Step 1: Create a New Repository on GitHub

1. Go to https://github.com/new
2. Fill in the repository details:
   - **Repository name**: `Hybrid-ML_CNS-Deduplication-System` (or your preferred name)
   - **Description**: "ML-Assisted Lightweight Secure Data Deduplication for Cloud Storage"
   - **Visibility**: Choose Public or Private
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)
3. Click "Create repository"

### Step 2: Link Your Local Repository to GitHub

After creating the repository, GitHub will show you commands. Use these:

```bash
# Add the remote repository (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/Hybrid-ML_CNS-Deduplication-System.git

# Verify the remote was added
git remote -v

# Push your code to GitHub
git push -u origin main
```

**Note**: If your default branch is `master` instead of `main`, use:
```bash
git branch -M main
git push -u origin main
```

### Step 3: Enter GitHub Credentials

When you run `git push`, you'll be prompted for credentials:
- **Username**: Your GitHub username
- **Password**: Use a Personal Access Token (PAT), NOT your GitHub password

#### How to Create a Personal Access Token:
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Give it a name (e.g., "Deduplication Project")
4. Select scopes: Check `repo` (full control of private repositories)
5. Click "Generate token"
6. **IMPORTANT**: Copy the token immediately (you won't see it again!)
7. Use this token as your password when pushing

### Step 4: Verify Upload

After pushing, go to your GitHub repository URL:
```
https://github.com/YOUR_USERNAME/Hybrid-ML_CNS-Deduplication-System
```

You should see all your files!

---

## 🔄 Future Updates

After making changes to your code:

```bash
# Check what changed
git status

# Add all changes
git add .

# Commit with a message
git commit -m "Description of changes"

# Push to GitHub
git push
```

---

## 🛡️ Security Notes

The `.gitignore` file has been created to exclude:
- ✅ Environment variables (.env files)
- ✅ Database files (*.db)
- ✅ Uploaded files
- ✅ Logs
- ✅ Python cache files
- ✅ ML model files (can be large)

**IMPORTANT**: Never commit:
- AWS credentials
- Secret keys
- Database files with user data
- Uploaded user files

---

## 📝 Quick Commands Reference

```bash
# Check repository status
git status

# View commit history
git log --oneline

# Create a new branch
git checkout -b feature-name

# Switch branches
git checkout main

# Pull latest changes from GitHub
git pull

# Clone repository to another computer
git clone https://github.com/YOUR_USERNAME/Hybrid-ML_CNS-Deduplication-System.git
```

---

## 🎯 Next Steps

1. Create the GitHub repository
2. Run the commands from Step 2
3. Add a nice README badge (optional):
   ```markdown
   ![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
   ![Flask](https://img.shields.io/badge/flask-3.0+-green.svg)
   ![License](https://img.shields.io/badge/license-MIT-blue.svg)
   ```

Good luck! 🚀
