#!/bin/bash
# Build script for Render deployment

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Creating necessary directories..."
mkdir -p uploads/temp_files
mkdir -p uploads/stored_files
mkdir -p logs
mkdir -p db
mkdir -p ml_data

echo "Initializing database..."
python init_db.py

echo "Build completed successfully!"
