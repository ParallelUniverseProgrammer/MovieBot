#!/bin/bash

# Exit on any error
set -e

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if virtual environment exists and activate it
activate_venv() {
    if [ ! -d ".venv" ]; then
        echo "❌  Virtual environment not found. Please run setup first:"
        echo "    python -m venv .venv"
        echo "    source .venv/bin/activate"
        echo "    pip install -r requirements.txt"
        exit 1
    fi
    
    if [ ! -f ".venv/bin/activate" ]; then
        echo "❌  Virtual environment activation script not found."
        exit 1
    fi
    
    echo "🔧  Activating virtual environment..."
    source .venv/bin/activate
    
    # Verify activation worked
    if [ -z "$VIRTUAL_ENV" ]; then
        echo "❌  Failed to activate virtual environment."
        exit 1
    fi
    
    echo "✅  Virtual environment activated: $VIRTUAL_ENV"
}

# Function to check if Python is available
check_python() {
    if ! command_exists python; then
        echo "❌  Python not found in PATH."
        exit 1
    fi
    
    # Check Python version (requires 3.8+)
    python_version=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    python_major=$(echo "$python_version" | cut -d. -f1)
    python_minor=$(echo "$python_version" | cut -d. -f2)
    
    if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 8 ]); then
        echo "❌  Python 3.8+ required, found $python_version"
        exit 1
    fi
    
    echo "✅  Python $python_version found"
}

# Function to check environment configuration
check_env() {
    echo "🔍  Checking environment configuration..."
    
    if [ ! -f .env ]; then
        echo "🔧  .env file not found. Launching setup wizard..."
        python -m config.setup_wizard
        return
    fi

    # Read .env into associative array for key lookup
    declare -A env_map
    while IFS='=' read -r key value; do
        # Ignore comments and blank lines
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        # Remove whitespace and quotes
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | sed -E "s/^['\"]?(.*?)['\"]?$/\1/" | xargs)
        env_map["$key"]="$value"
    done < <(grep -E '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=' .env 2>/dev/null || true)

    # Determine if OpenRouter is present and valid
    openrouter_present=0
    if [[ -n "${env_map[OPENROUTER_API_KEY]}" && -n "${env_map[OPENROUTER_BASE_URL]}" ]]; then
        openrouter_present=1
        echo "✅  OpenRouter configuration detected"
    fi

    # List of required keys (add or remove as needed)
    required_keys=(
        "PLEX_TOKEN"
        "PLEX_BASE_URL"
    )

    # Only require OPENAI_API_KEY if OpenRouter is not present
    if [[ $openrouter_present -eq 0 ]]; then
        required_keys+=("OPENAI_API_KEY")
    fi

    # Check for Discord configuration (optional but recommended)
    discord_configured=0
    if [[ -n "${env_map[DISCORD_TOKEN]}" ]]; then
        discord_configured=1
        echo "✅  Discord bot token configured"
        
        # Check if guild ID is set (optional)
        if [[ -n "${env_map[DISCORD_GUILD_ID]}" ]]; then
            echo "✅  Discord guild ID configured (faster command sync)"
        else
            echo "ℹ️   Discord guild ID not set (commands will sync globally, may take up to 1 hour)"
        fi
    else
        echo "⚠️   Discord bot token not configured"
    fi

    # Validate required keys
    missing_required=()
    for key in "${required_keys[@]}"; do
        val="${env_map[$key]}"
        if [ -z "$val" ]; then
            missing_required+=("$key")
        fi
    done

    # Check for any issues
    has_issues=0
    
    if [ "${#missing_required[@]}" -gt 0 ]; then
        echo "❌  The following required environment variables are missing or empty:"
        for key in "${missing_required[@]}"; do
            echo "    $key"
        done
        has_issues=1
    fi

    if [ $has_issues -eq 1 ]; then
        echo ""
        echo "🔧  Please complete your environment configuration."
        python -m config.setup_wizard
    else
        echo "✅  Environment configuration validated successfully!"
        
        # Show summary of what's configured
        echo ""
        echo "📋  Configuration Summary:"
        echo "    Plex: ✅ Configured"
        if [[ $openrouter_present -eq 1 ]]; then
            echo "    LLM: ✅ OpenRouter configured"
        else
            echo "    LLM: ✅ OpenAI configured"
        fi
        
        if [[ $discord_configured -eq 1 ]]; then
            echo "    Discord: ✅ Bot configured"
        else
            echo "    Discord: ⚠️  Not configured (bot may not work)"
        fi
    fi
}

# Function to check if required Python packages are installed
check_dependencies() {
    echo "🔍  Checking Python dependencies..."
    
    # Check if key packages are available
    if ! python -c "import discord" 2>/dev/null; then
        echo "❌  discord.py not found. Installing dependencies..."
        pip install -r requirements.txt
    fi
    
    if ! python -c "import yaml" 2>/dev/null; then
        echo "❌  PyYAML not found. Installing dependencies..."
        pip install -r requirements.txt
    fi
    
    echo "✅  Python dependencies verified"
}

# Main execution
main() {
    echo "🚀  MovieBot Environment Setup and Launch"
    echo "=========================================="
    echo ""
    
    # Check Python first
    check_python
    
    # Activate virtual environment
    activate_venv
    
    # Check dependencies
    check_dependencies
    
    # Check environment configuration
    check_env
    
    echo ""
    echo "🎯  Starting MovieBot Discord bot..."
    echo "    Press Ctrl+C to stop the bot"
    echo ""
    
    # Start the bot
    python -m bot.discord_bot
}

# Run main function
main "$@"