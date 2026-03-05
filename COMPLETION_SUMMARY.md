# Task Completion Summary

## Features Implemented
1.  **Persistent Bubble Control**:
    *   Added a **toggle switch** in `Settings -> User Interface -> Persistent Bubble` to enable/disable the floating chat bubble.
    *   **Instant Toggle**: The bubble now appears/disappears *immediately* when you flip the switch, no need to click "Save Settings".
    *   The setting persists across restarts.

2.  **Autostart Integration**:
    *   The application now starts in **minimized** mode on login.
    *   It checks your settings and only shows the bubble if enabled.

3.  **Reliability Improvements**:
    *   Fixed `wmctrl` fallback for X11 environments.
    *   Cleaned up CSS warnings.
    *   Added explicit logic to reload settings from disk to ensure the latest toggle state is respected.

## How to Test
1.  **Restart**: Close `nerva-ui` and relaunch it (or log out/in).
2.  **Toggle**: Open Settings. Flip the "Persistent Bubble" switch. The bubble should appear/disappear instantly.

Status: **Completed** ✅
