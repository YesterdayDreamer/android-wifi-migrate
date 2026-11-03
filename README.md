# WiFi Migrate

**Cross-brand Android Wi-Fi Migration Toolkit**

A Windows companion for organizing, converting, and migrating saved Wi-Fi networks across Android devices and brands.

[简体中文](README.zh-CN.md)

---

## Start here: Try WiFi Password Manager first

**In most cases, you may not need this project at all.**

If both your old and new Android phones support [Shizuku](https://github.com/RikkaApps/Shizuku), and [WiFi Password Manager](https://github.com/Khh-vu/wifi-password-manager) works on both devices, it is usually the simplest way to export and restore your saved Wi-Fi networks.

WiFi Password Manager already supports:

- Viewing saved Wi-Fi networks and passwords.
- Importing and exporting configurations as JSON.
- GZip compression and encrypted exports.
- Managing and restoring saved networks through Shizuku or root access.

**Recommended:** Try WiFi Password Manager before installing WiFi Migrate.

- [WiFi Password Manager — GitHub](https://github.com/Khh-vu/wifi-password-manager)
- [WiFi Password Manager — F-Droid](https://f-droid.org/packages/io.github.wifi_password_manager/)
- [Shizuku — GitHub](https://github.com/RikkaApps/Shizuku)

WiFi Password Manager currently targets Android 11 and newer. Actual availability depends on your device, Android version, and system permissions.

---

## Why WiFi Migrate?

Android does not provide one universal method for transferring saved Wi-Fi configurations across all manufacturers and system versions.

Some devices work well with Shizuku-based tools. Others have limited debugging options, different system restrictions, or no convenient way to restore multiple networks.

**WiFi Migrate connects these different methods through a single Windows desktop workflow.**

It does not aim to replace WiFi Password Manager or reinvent Android Wi-Fi backup. Instead, it helps when existing tools are not sufficient.

With WiFi Migrate, you can:

- Import Wi-Fi data from different sources.
- Organize and merge multiple backups.
- Identify duplicate networks and conflicting credentials.
- Select which networks to migrate.
- Choose a suitable transfer method for the target device.
- Generate QR codes and printable PDF sheets.
- Archive original backups for future use.

## When should you use it?

| Your situation | Recommended approach |
|---|---|
| Both phones support Shizuku and WiFi Password Manager | Use WiFi Password Manager directly |
| You already have a WiFi Password Manager backup | Open it in WiFi Migrate to inspect, organize, and export |
| Your old phone has no wireless debugging | Try starting Shizuku through USB ADB |
| Your old phone cannot use Shizuku | Import an existing backup or try supported legacy backup methods |
| Your new phone cannot use WiFi Password Manager | Try the Android import helper or another supported method |
| You only need to migrate a few networks | Generate QR codes |
| You want to keep a long-term Wi-Fi backup | Export JSON / CSV and archive the original files |
| You want to transfer networks saved on Windows | Import Windows WLAN configurations |

---

## Features

### 1. Multiple data sources

Import Wi-Fi configurations from:

- WiFi Password Manager JSON exports.
- GZip-compressed JSON exports.
- Legacy Android ADB backups (`.ab` / `.adb`).
- TAR archives and supported Android settings files.
- Windows WLAN XML files.
- Existing CSV and JSON files.
- Windows saved Wi-Fi configurations.

You can also open an existing backup without connecting a phone or installing ADB.

### 2. Unified Wi-Fi management

All supported inputs are converted into a common data model.

- Search, filter, and sort networks.
- View SSIDs, passwords, hidden-network flags, and security types.
- Detect duplicates.
- Identify networks with the same SSID but different passwords or security configurations.
- Merge multiple backups while retaining conflict information.
- Select individual networks or the entire collection for migration.

Original security parameters and other available configuration fields are preserved in the extended backup format whenever possible.

### 3. Multiple migration methods

Choose a migration method according to the capabilities of your target phone.

| Method | Description | Status |
|---|---|---|
| **WiFi Password Manager** | Import networks through Shizuku and the Android app | Recommended |
| **Android Import Helper** | Submit networks through Android's system confirmation interface | Experimental |
| **Direct ADB Migration** | Preview and attempt to save networks directly through ADB | Experimental |
| **QR Code Transfer** | Scan individual Wi-Fi configuration QR codes | Available |

The software keeps source and target devices separate and uses explicit ADB device selection to avoid accidentally operating on the wrong phone.

### 4. Export and backup

Supported outputs include:

| Format | Purpose |
|---|---|
| Extended JSON | Preserve as much original configuration data as possible |
| WiFi Password Manager-compatible JSON | Interoperability with WiFi Password Manager |
| CSV | Convenient viewing and data processing |
| QR PNG | Individual Wi-Fi QR codes |
| Offline scan sheet | Browse and check QR codes locally |
| A4 PDF | Printable QR code collection |
| Original backup archive | Preserve source files with SHA-256 verification |

**Compatibility note:** Importing a native WiFi Password Manager backup and importing a JSON file generated by WiFi Migrate are two different operations. The latter should be verified against the target app version before relying on it.

QR codes and some migration methods cannot represent every Android Wi-Fi configuration. Unsupported security types and advanced settings may be skipped or require manual handling.

---

## How to use

### Step 1 — Get Wi-Fi configurations from the old device

The recommended approach is to use WiFi Password Manager:

1. Install Shizuku and WiFi Password Manager on the old phone.
2. Start Shizuku and authorize WiFi Password Manager.
3. Export the saved Wi-Fi networks from the app.
4. Transfer the exported JSON or GZip file to your Windows PC.

If wireless debugging is unavailable, USB ADB may be used to start Shizuku, depending on device support.

Alternatively, open an existing backup file or try the supported legacy backup methods.

### Step 2 — Review and organize

Open the backup in WiFi Migrate:

1. Inspect the parsed networks.
2. Review duplicates and conflicting entries.
3. Merge additional backups if needed.
4. Select the networks you want to migrate.
5. Generate the appropriate target-side data.

### Step 3 — Transfer to the new device

Connect the target phone and choose an available method:

- WiFi Password Manager import.
- Android Import Helper.
- Direct ADB migration.
- QR code scanning.

Some methods require authorization or confirmation on the phone itself.

### Step 4 — Verify the result

WiFi Migrate distinguishes between:

- File transferred.
- Configuration submitted.
- System confirmed saving.
- Network visible in the saved-network list.
- Automatic reconnection verified.

A successful file transfer does not mean the network has been saved. A system confirmation does not guarantee automatic reconnection.

---

## Requirements

- Windows desktop.
- Python environment compatible with the project dependencies.
- Android Debug Bridge (ADB) for device-connected workflows.
- Shizuku and WiFi Password Manager for the recommended app-based migration route.

ADB is optional for offline backup processing and QR / PDF generation. The application can discover an existing ADB installation or guide users through obtaining official Android Platform Tools.

See the project documentation and release notes for installation details.

---

## Compatibility and testing status

The following results reflect actual device testing, not universal compatibility guarantees.

| Feature | Current verification |
|---|---|
| HarmonyOS 4.2 → vivo X200 Ultra | WiFi Password Manager export/import successfully tested |
| Starting Shizuku through USB ADB | Tested on a Huawei device |
| Android Import Helper | Installation, launch, and file transfer tested on a Xiaomi device; system saving still needs verification |
| Direct ADB migration | Read-only preview tested on Huawei and Xiaomi; actual writing and automatic reconnection remain unverified |
| QR / PDF | Sample generation and QR decoding tested |

Experimental features are provided for evaluation and may not work on every device or firmware version.

---

## Privacy and security

WiFi Migrate is designed for local processing.

- No cloud account is required.
- Wi-Fi data is processed locally on your PC.
- Original backup files can be archived separately.
- Migration reports do not intentionally include plaintext Wi-Fi passwords.

**Important:** Exported JSON, CSV, QR images, PDFs, and offline HTML pages may contain plaintext credentials or scannable Wi-Fi information. Treat them as sensitive files and never upload personal backups to public repositories.

---

## Acknowledgements

- [WiFi Password Manager](https://github.com/Khh-vu/wifi-password-manager) — Android Wi-Fi management and backup/restore.
- [Shizuku](https://github.com/RikkaApps/Shizuku) — Privileged API access for Android applications.
- [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools) — Android device communication utilities.

## License

See [LICENSE](LICENSE) for license information.