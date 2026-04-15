"""
Entry point for Công Văn Processor (top-level script for PyInstaller).
"""
import sys
import os

# Ensure the project root is on sys.path when run as a script or .exe
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    main()

