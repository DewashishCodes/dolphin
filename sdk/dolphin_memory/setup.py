"""
Dolphin Auto-Setup
===================
Automatically installs Ollama and pulls the required model.

Usage (CLI):
    dolphin-setup

Usage (Python):
    from dolphin_memory.setup import run_setup
    run_setup()

Usage (Module):
    python -m dolphin_memory.setup
"""

import os
import sys
import shutil
import subprocess
import platform
import logging
import time

logger = logging.getLogger("dolphin.setup")

OLLAMA_DOWNLOAD_URLS = {
    "Windows": "https://ollama.com/download/OllamaSetup.exe",
    "Darwin": "https://ollama.com/download/Ollama-darwin.zip",
    "Linux": "https://ollama.com/download/ollama-linux-amd64",
}

DEFAULT_MODEL = "llama3.2"


def _print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║   🐬 Dolphin Memory — Auto Setup                ║
║                                                  ║
║   This will install:                             ║
║   1. Ollama (local LLM runtime)                  ║
║   2. Llama 3.2 model (~2GB download)             ║
╚══════════════════════════════════════════════════╝
    """)


def check_ollama_installed() -> bool:
    """Check if Ollama is available on the system PATH."""
    return shutil.which("ollama") is not None


def check_ollama_running() -> bool:
    """Check if Ollama server is running."""
    try:
        import ollama
        ollama.list()
        return True
    except Exception:
        return False


def check_model_available(model: str = DEFAULT_MODEL) -> bool:
    """Check if the required model is already pulled."""
    try:
        import ollama
        models = ollama.list()
        model_names = []
        if hasattr(models, 'models'):
            model_names = [m.model for m in models.models]
        elif isinstance(models, dict):
            model_names = [m.get('name', '') for m in models.get('models', [])]

        # Check for exact match or prefix match (e.g., 'llama3.2:latest')
        for name in model_names:
            if model in name:
                return True
        return False
    except Exception:
        return False


def install_ollama():
    """Download and install Ollama for the current platform."""
    system = platform.system()
    url = OLLAMA_DOWNLOAD_URLS.get(system)

    if not url:
        print(f"❌ Unsupported platform: {system}")
        print("Please install Ollama manually: https://ollama.com/download")
        return False

    print(f"📥 Downloading Ollama for {system}...")

    if system == "Windows":
        # Download the installer
        installer_path = os.path.join(os.environ.get("TEMP", "."), "OllamaSetup.exe")
        try:
            import urllib.request
            urllib.request.urlretrieve(url, installer_path)
            print(f"📦 Running installer: {installer_path}")
            print("⚠️  Please follow the Ollama installer wizard.")
            print("   After installation, Ollama will start automatically.")
            subprocess.run([installer_path], check=True)
            return True
        except Exception as e:
            print(f"❌ Download failed: {e}")
            print(f"Please download manually: {url}")
            return False

    elif system == "Linux":
        # Linux: Use the install script
        print("Running Ollama install script...")
        try:
            subprocess.run(
                ["curl", "-fsSL", "https://ollama.com/install.sh", "|", "sh"],
                shell=True, check=True
            )
            return True
        except Exception as e:
            print(f"❌ Install failed: {e}")
            print("Try manually: curl -fsSL https://ollama.com/install.sh | sh")
            return False

    elif system == "Darwin":
        # macOS: Direct download
        print(f"Please download Ollama from: {url}")
        print("Or install via Homebrew: brew install ollama")

        try:
            subprocess.run(["brew", "install", "ollama"], check=True)
            return True
        except FileNotFoundError:
            print("Homebrew not found. Please install manually from https://ollama.com")
            return False


def pull_model(model: str = DEFAULT_MODEL):
    """Pull the required LLM model."""
    print(f"\n📥 Pulling model: {model}")
    print("   This may take a few minutes on first download (~2GB)...")

    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=False,
            text=True,
        )
        if result.returncode == 0:
            print(f"✅ Model '{model}' is ready!")
            return True
        else:
            print(f"❌ Failed to pull model. Exit code: {result.returncode}")
            return False
    except FileNotFoundError:
        print("❌ 'ollama' command not found. Is Ollama installed?")
        return False
    except Exception as e:
        print(f"❌ Error pulling model: {e}")
        return False


def setup_supabase_schema():
    """Print instructions for setting up Supabase tables."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    print("\n📋 SUPABASE SETUP")
    print("=" * 50)

    if os.path.exists(schema_path):
        print(f"SQL schema file: {schema_path}")
        print("\nTo set up your Supabase tables:")
        print("1. Go to your Supabase dashboard → SQL Editor")
        print(f"2. Copy the contents of: {schema_path}")
        print("3. Paste and click RUN")
    else:
        print("Schema file not found. Please run the migration manually.")
        print("See: https://github.com/DewashishCodes/dolphin#supabase-setup")

    print()


def run_setup():
    """Main setup entrypoint. Called by `dolphin-setup` CLI command."""
    _print_banner()

    # Step 1: Check/Install Ollama
    print("🔍 Step 1: Checking Ollama installation...")
    if check_ollama_installed():
        print("✅ Ollama is installed!")
    else:
        print("⚠️  Ollama not found. Installing...")
        success = install_ollama()
        if not success:
            print("\n❌ Could not install Ollama automatically.")
            print("Please install it manually from: https://ollama.com/download")
            print("Then run 'dolphin-setup' again.")
            sys.exit(1)

        # Wait for Ollama to be available after install
        print("\n⏳ Waiting for Ollama to be available...")
        for _ in range(30):
            if check_ollama_installed():
                break
            time.sleep(1)
        else:
            print("⚠️  Ollama installed but not on PATH yet.")
            print("Please restart your terminal and run 'dolphin-setup' again.")
            sys.exit(1)

    # Step 2: Check if Ollama is running
    print("\n🔍 Step 2: Checking Ollama server...")
    if check_ollama_running():
        print("✅ Ollama is running!")
    else:
        print("⚠️  Ollama is installed but not running.")
        print("   Starting Ollama...")
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            print("✅ Ollama started!")
        except Exception as e:
            print(f"⚠️  Could not start Ollama: {e}")
            print("   Please start it manually: ollama serve")

    # Step 3: Pull the model
    print(f"\n🔍 Step 3: Checking model '{DEFAULT_MODEL}'...")
    if check_model_available(DEFAULT_MODEL):
        print(f"✅ Model '{DEFAULT_MODEL}' is already available!")
    else:
        pull_model(DEFAULT_MODEL)

    # Step 4: Supabase instructions
    setup_supabase_schema()

    # Done!
    print("=" * 50)
    print("🎉 Setup complete! You're ready to use Dolphin Memory.")
    print()
    print("Quick start:")
    print('  from dolphin_memory import DolphinMemory')
    print('  m = DolphinMemory(supabase_url="...", supabase_key="...")')
    print('  m.add("I love Python", user_id="user_1")')
    print()


if __name__ == "__main__":
    run_setup()
