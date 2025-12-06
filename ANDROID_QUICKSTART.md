# Android App - Quickstart Installation Guide

## Minimal Steps to Install on Your Phone

### Prerequisites (5 mins)
1. **Install Android Studio**: Download from https://developer.android.com/studio
2. **Enable Developer Mode on your phone**:
   - Go to Settings → About Phone
   - Tap "Build Number" 7 times
   - Go back to Settings → Developer Options
   - Enable "USB Debugging"

### Setup (10 mins)

#### 1. Get Your Computer's IP Address
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```
Note the IP (e.g., `192.168.1.100`)

#### 2. Configure the Android Project
```bash
cd /Users/ishaylevi/work/OrgOs/android
echo "api.base.url=http://YOUR_IP_HERE:8000/" > local.properties
```
Replace `YOUR_IP_HERE` with your actual IP.

Example:
```bash
echo "api.base.url=http://192.168.1.100:8000/" > local.properties
```

#### 3. Open in Android Studio
1. Launch Android Studio
2. Click "Open"
3. Navigate to `/Users/ishaylevi/work/OrgOs/android`
4. Click "OK"
5. Wait for Gradle sync (2-5 mins)

### Build & Install (5 mins)

#### Option A: Install via USB Cable
1. Connect your phone via USB
2. Click the green "Run" button (▶️) in Android Studio
3. Select your device
4. Wait for build and install

#### Option B: Install via Wireless
1. In Android Studio: Run → Edit Configurations
2. Select your device
3. Click "Pair Devices Using Wi-Fi"
4. Follow the pairing process
5. Click Run

### First Launch
1. App opens
2. Enter your name
3. Start using!

---

## Current App Status

The Android project has:
- ✅ Complete Gradle setup
- ✅ API client (all endpoints)
- ✅ Data models
- ✅ Repository layer
- ⏳ UI components (need implementation)

**To have a fully working app, you need to:**
1. Implement the 4 screen fragments
2. Create XML layouts
3. Add navigation

**Estimated time**: 4-6 hours of Android development

---

## Fastest Alternative: Use Web Interface

**Instead of building the Android app, use the web interface on your phone:**

1. Get your computer's IP: `ifconfig | grep "inet "`
2. On phone browser: `http://YOUR_IP:8000/docs`
3. Fully functional immediately!

The web interface (Swagger UI) works perfectly on mobile and has all features.

---

## Summary

**Immediate Access (Recommended):**
→ Use web interface on phone: `http://YOUR_IP:8000/docs`

**Native Android App:**
→ Needs UI implementation (~4-6 hours)
→ Foundation is complete and ready for development

Choose the web interface for immediate use, or implement the Android UI for native app experience.

