# Minecraft Java Edition Launcher

A custom launcher for Minecraft Java Edition that maintains user credentials for connecting to online servers.

## Features

- ✅ Microsoft/Mojang authentication
- ✅ Secure credential storage (local encryption)
- ✅ Maintains active session for online servers
- ✅ Intuitive graphical interface with PyQt5
- ✅ Automatic detection of Minecraft installation
- ✅ Saves credentials for future use
- ✅ Full support for NeoForge, Forge, Fabric, and Vanilla versions
- ✅ Automatic Java runtime detection and download
- ✅ Proper handling of version inheritance and library management

## Requirements

- **Python 3.8 or higher**
- **Minecraft Java Edition** installed (uses standard `.minecraft` directory)
- **Java Runtime Environment (JRE)** - The launcher can automatically download the required version
- **Internet connection** for authentication and downloading game files

## Installation

### 1. Clone or download this repository

```bash
git clone <repository-url>
cd launcher
```

### 2. Create a virtual environment (recommended)

```bash
# On Windows
python -m venv .venv
.venv\Scripts\activate

# On Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Verify installation

Make sure all required packages are installed:
- `requests` - For HTTP requests
- `cryptography` - For credential encryption
- `PyQt5` - For the graphical interface
- `PyQtWebEngine` - For OAuth authentication flow

## Usage

### Running the Launcher

1. **Start the launcher:**
   ```bash
   python launcher.py
   ```

2. **Authenticate:**
   - Click "Sign In" to authenticate with your Microsoft account
   - Follow the on-screen instructions to complete the OAuth flow
   - The launcher will open a browser window for Microsoft authentication

3. **Launch Minecraft:**
   - Once authenticated, select a Minecraft version from the dropdown
   - Click "Launch Minecraft" to start the game
   - The launcher will automatically:
     - Detect or download the required Java version
     - Build the correct classpath and module path
     - Extract native libraries to a temporary directory
     - Launch the game with proper credentials

### Command Line Usage

You can also launch Minecraft directly from the command line:

```bash
python launcher.py
```

The launcher will use saved credentials if available, or prompt for authentication.

## How It Works

### Authentication Flow

The launcher uses Microsoft OAuth 2.0 flow for authentication:

1. **Microsoft Authentication** - User signs in with Microsoft account
2. **Xbox Live Authentication** - Account is verified with Xbox Live
3. **Minecraft Services Authentication** - Access token is obtained from Minecraft Services
4. **Profile Retrieval** - Minecraft profile and UUID are retrieved

### Credential Storage

- Credentials are stored encrypted using Fernet (symmetric encryption)
- Stored in `credentials.json` (encrypted)
- Encryption key stored in `key.key`
- Both files are in `.gitignore` for security

### Minecraft Launch Process

1. **Version Detection** - Automatically detects installed Minecraft versions
2. **Version Inheritance** - Properly merges parent and child version JSONs
3. **Library Management** - Resolves all required libraries from merged JSON
4. **Classpath Construction** - Builds complete classpath with all libraries + version JAR
5. **Module Path Construction** - Builds module path with only explicitly listed JARs
6. **Native Extraction** - Extracts native libraries to unique temporary directory (`bin/<HASH>`)
7. **JVM Arguments** - Constructs proper JVM arguments respecting order and conditional rules
8. **Launch** - Executes Java with all required arguments

### Key Features

- **Duplicate Prevention**: Automatically removes duplicate JARs from classpath and module path
- **Native Library Handling**: Extracts only required native libraries for the current architecture
- **Version Inheritance**: Properly handles version inheritance chains (e.g., NeoForge → Vanilla)
- **Flag Filtering**: Omits flags without values (e.g., `--width`, `--height` when empty)

## Project Structure

```
launcher/
├── launcher.py              # Main GUI application
├── minecraft_launcher.py    # Core Minecraft launching logic
├── auth_manager.py          # Microsoft authentication manager
├── credential_storage.py    # Encrypted credential storage
├── java_downloader.py       # Java runtime downloader
├── config.py               # Configuration management
├── requirements.txt         # Python dependencies
├── launcher_config.json     # Launcher configuration
└── README.md               # This file
```

## Troubleshooting

### "Minecraft not detected"

- Ensure Minecraft Java Edition is installed
- The launcher searches in standard paths:
  - **Windows**: `%APPDATA%\.minecraft`
  - **Linux**: `~/.minecraft`
  - **macOS**: `~/Library/Application Support/minecraft`

### "Java not found"

- The launcher can automatically download the required Java version
- If manual installation is needed:
  - Install Java Runtime Environment (JRE) 8 or higher
  - Ensure Java is in your system PATH
  - Or specify Java path in the launcher settings

### Authentication errors

- Verify your internet connection
- Ensure you have a Microsoft account linked to Minecraft
- Try signing out and signing in again
- Clear browser cookies if OAuth flow fails

### "Invalid package name" error (NeoForge)

- This error is typically caused by duplicate JARs or incorrect native library handling
- The launcher now automatically:
  - Removes duplicate JARs from classpath and module path
  - Extracts natives to unique temporary directories
  - Uses proper JVM arguments pointing to the correct native directory

### Game fails to launch

- Check the error log in `.minecraft/logs/launcher_stderr_*.log`
- Verify all required libraries are downloaded
- Ensure the version JSON is valid and complete
- Check that Java version matches the required version

## Security Notes

- ⚠️ **Never share** `credentials.json` or `key.key` files
- ⚠️ These files are automatically excluded from git (`.gitignore`)
- ⚠️ If sharing your computer, use "Sign Out" before closing
- ⚠️ Credentials are encrypted locally but still sensitive

## Technical Details

### Version Inheritance

The launcher properly handles version inheritance by:
- Recursively loading parent versions
- Merging libraries, arguments, and other sections
- Child versions override parent values when conflicts occur
- Maintaining proper order (parent first, then child)

### Classpath vs Module Path

- **Classpath (`-cp`)**: Contains ALL libraries + version JAR (for compatibility)
- **Module Path (`-p`)**: Contains only JARs explicitly listed for Java module system
- Both are passed simultaneously (as the official launcher does)

### Native Library Extraction

- Natives are extracted from `*-natives-<platform>.jar` files
- Extracted to unique temporary directory: `.minecraft/bin/<HASH>/`
- Only architecture-specific files are extracted (e.g., `windows/x64/`)
- Files are placed directly in the root of the hash directory (no nested structure)

## Limitations

- This launcher is a custom implementation focused on core functionality
- For advanced features (mod management, version downloads, etc.), consider using official launchers or more complete alternatives
- Minecraft must be properly installed with all dependencies
- Some edge cases in version JSONs may not be fully supported

## Contributing

Contributions are welcome! Please ensure:
- Code follows Python PEP 8 style guidelines
- All changes are tested with multiple Minecraft versions
- Security best practices are followed for credential handling

## License

This project is open source and available for personal use.

## Acknowledgments

- Built for compatibility with official Minecraft launcher behavior
- Supports NeoForge, Forge, Fabric, and Vanilla versions
- Implements proper handling of Java module system and classpath
