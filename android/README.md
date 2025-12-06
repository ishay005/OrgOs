# OrgOs Android App

Android client for the OrgOs Perception Alignment System.

## Features

- ✅ User registration and authentication
- ✅ Alignment management (select team members to compare with)
- ✅ Daily question prompts with smart input types
- ✅ Misalignment detection and visualization
- ✅ Daily notifications with WorkManager
- ✅ Debug menu for testing

## Tech Stack

- **Language**: Kotlin
- **Architecture**: MVVM (ViewModel + StateFlow)
- **Networking**: Retrofit + OkHttp
- **DI**: Hilt (Android dependency injection)
- **Storage**: SharedPreferences
- **Async**: Kotlin Coroutines
- **Navigation**: Jetpack Navigation Component
- **UI**: Material Design 3

## Prerequisites

- Android Studio Hedgehog or later
- Kotlin 1.9+
- Min SDK: 24 (Android 7.0)
- Target SDK: 34 (Android 14)

## Setup

1. Open the `android` folder in Android Studio
2. Configure backend URL in `local.properties`:
   ```
   api.base.url=http://10.0.2.2:8000/
   ```
   Note: `10.0.2.2` is the emulator's alias for `localhost`

3. Sync Gradle and build

## Configuration

### Backend URL

For development:
- **Emulator**: Use `http://10.0.2.2:8000/`
- **Physical Device**: Use your computer's IP (e.g., `http://192.168.1.100:8000/`)

Update in `local.properties` or `NetworkModule.kt`

## Project Structure

```
android/
├── app/
│   ├── src/main/
│   │   ├── java/com/orgos/
│   │   │   ├── data/
│   │   │   │   ├── api/          # Retrofit interfaces
│   │   │   │   ├── model/        # Data models
│   │   │   │   ├── repository/   # Repositories
│   │   │   │   └── local/        # SharedPreferences
│   │   │   ├── ui/
│   │   │   │   ├── registration/ # Registration screen
│   │   │   │   ├── alignment/    # Alignment list
│   │   │   │   ├── questions/    # Daily questions
│   │   │   │   ├── misalignment/ # Misalignment view
│   │   │   │   └── debug/        # Debug menu
│   │   │   ├── di/               # Hilt modules
│   │   │   ├── notification/     # Notification manager
│   │   │   └── MainActivity.kt
│   │   ├── res/
│   │   │   ├── layout/           # XML layouts
│   │   │   ├── navigation/       # Navigation graph
│   │   │   └── values/           # Strings, colors, themes
│   │   └── AndroidManifest.xml
│   ├── build.gradle.kts
│   └── proguard-rules.pro
├── gradle/
├── build.gradle.kts
├── settings.gradle.kts
└── README.md
```

## Screens

### 1. Registration (First Run)
- Collects user name and email
- Creates user on backend
- Stores user_id locally

### 2. Alignment List
- Shows all users
- Toggle to align/unalign with each user
- Updates via API

### 3. Daily Questions
- Fetches questions from backend
- Smart input types:
  - Enum → Dropdown
  - Bool → Switch
  - Int → Number picker / Slider
  - String → Text field
- "Skip" option for each question
- Submits answers to backend

### 4. Misalignments
- Groups by person
- Shows perception gaps
- Color-coded by severity

## Notifications

- Daily notification at configured time (default 10:00)
- Uses WorkManager for reliability
- Tapping opens Daily Questions screen

## Debug Menu

Long-press on app title to access:
- View all attributes
- View raw misalignments
- Test API connectivity
- Clear local data

## API Integration

All API calls include `X-User-Id` header:

```kotlin
@Headers("X-User-Id: {userId}")
@GET("questions/next")
suspend fun getQuestions(
    @Header("X-User-Id") userId: String,
    @Query("max_questions") maxQuestions: Int
): List<QuestionResponse>
```

## Build & Run

```bash
# Debug build
./gradlew assembleDebug

# Release build
./gradlew assembleRelease

# Install on device
./gradlew installDebug

# Run tests
./gradlew test
```

## Testing

```bash
# Unit tests
./gradlew testDebugUnitTest

# Instrumentation tests
./gradlew connectedDebugAndroidTest
```

## Troubleshooting

### Cannot connect to backend
- Emulator: Use `10.0.2.2` instead of `localhost`
- Physical device: Ensure same WiFi, use computer's IP
- Check backend is running: `http://localhost:8000/health`

### User ID not persisting
- Check SharedPreferences in debug menu
- Clear app data and re-register

### Notifications not working
- Check notification permissions (Android 13+)
- Verify WorkManager is scheduled
- Check battery optimization settings

## License

[Add your license]

