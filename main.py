"""Buildozer entry point for the Android build.

The Kivy UI lives in ``android/kivy_app.py``; the directory is added to
``sys.path`` instead of being imported as a package so it cannot shadow the
``android`` module provided by python-for-android/pyjnius.
"""

from __future__ import annotations

import os
import sys

_ANDROID_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "android")
if _ANDROID_DIR not in sys.path:
    sys.path.insert(0, _ANDROID_DIR)

from kivy_app import main  # noqa: E402


if __name__ == "__main__":
    main()
