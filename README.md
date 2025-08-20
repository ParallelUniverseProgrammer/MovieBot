# MovieBot

A sophisticated, well-typed Python Discord bot that serves as your household's personal media assistant. MovieBot integrates with Plex, Radarr, Sonarr, and TMDb to provide intelligent movie recommendations, manage your media library, and offer conversational AI assistance powered by GPT-5.

## 🎯 Core Features

### **Discord Slash Commands**
- **`/search`** - Search your Plex library and optionally TMDb for movies/shows
- **`/watchlist addmovie`** - Add movies to Radarr by TMDb ID
- **`/watchlist addseries`** - Add TV series to Sonarr by TVDb ID  
- **`/rate`** - Set Plex ratings (1-10) on any media item
- **`/prefs get`** - View household preferences (compact or full JSON)
- **`/prefs set`** - Update household preferences with JSON values

### **Conversational AI Agent**
- **Natural language processing** - Chat with the bot using @mentions
- **Intelligent recommendations** - Get personalized suggestions based on household preferences
- **Context-aware responses** - The bot remembers conversation history and preferences
- **Tool-based reasoning** - Uses 50+ specialized tools to provide accurate information

### **Media Management Tools**
- **Plex Integration**: Search, rate, browse collections, playlists, and similar items
- **Radarr Management**: Add movies, monitor quality, check system status
- **Sonarr Management**: Add TV series, track episodes, manage downloads
- **TMDb Integration**: Search external database, get recommendations

### **Household Preference System**
- **Sophisticated taste profiles** with detailed constraints and preferences
- **Dynamic preference updates** through conversation or commands
- **Content filtering** based on genres, themes, content warnings, and aesthetics
- **Personalized recommendations** that respect household boundaries

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.8+
- Discord Bot Token and Application ID
- OpenAI API Key
- Plex Media Server
- Radarr (for movies)
- Sonarr (for TV series)
- TMDb API Key

### 2. Setup
```bash
# Clone and navigate to project
git clone <repository-url>
cd MovieBot

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. First Run
```bash
python main.py
```
The setup wizard will guide you through:
- Discord bot configuration
- API key setup
- Service connectivity testing
- Default quality profiles and root folders
- Household preference initialization

### 4. Start the Bot
```bash
python -m bot.discord_bot
```

## 🔧 Configuration

### Environment Variables (`.env`)
```bash
# Discord
DISCORD_TOKEN=your_bot_token
APPLICATION_ID=your_application_id
DISCORD_GUILD_ID=optional_dev_guild_id

# OpenAI
OPENAI_API_KEY=your_openai_key

# Plex
PLEX_BASE_URL=http://localhost:32400
PLEX_TOKEN=your_plex_token

# Radarr
RADARR_BASE_URL=http://localhost:7878
RADARR_API_KEY=your_radarr_key

# Sonarr  
SONARR_BASE_URL=http://localhost:8989
SONARR_API_KEY=your_sonarr_key

# TMDb
TMDB_API_KEY=your_tmdb_key
```

### Runtime Configuration (`config/config.yaml`)
```yaml
radarr:
  qualityProfileId: 1
  rootFolderPath: "/movies"
sonarr:
  qualityProfileId: 1
  rootFolderPath: "/tv"
```

## 🎭 How the Bot Works

### **Architecture Overview**
MovieBot uses a sophisticated multi-layered architecture:

1. **Discord Interface Layer** - Handles slash commands and natural language conversations
2. **Agent Layer** - GPT-5 powered reasoning engine with tool access
3. **Tool Registry** - 50+ specialized functions for media operations
4. **Integration Layer** - Direct API clients for Plex, Radarr, Sonarr, and TMDb
5. **Preference System** - Dynamic household taste profiles and constraints

### **Conversational Flow**
```
User Message → Agent Analysis → Tool Selection → API Calls → Response Generation
     ↓              ↓              ↓            ↓            ↓
@mention bot    GPT-5 reasoning  Choose tools  Plex/Radarr  Natural language
or slash cmd    with context     from 50+      Sonarr/TMDb   response with
                                available      API calls     results & next steps
```

### **Tool System**
The bot has access to 50+ specialized tools across categories:

**Plex Operations** (15+ tools)
- `search_plex` - Advanced library search with filtering
- `get_plex_library_sections` - Browse media sections
- `get_plex_recently_added` - Latest additions
- `get_plex_collections` - Browse curated collections
- `get_plex_similar_items` - Find related content
- `set_plex_rating` - Rate media items

**Radarr Management** (20+ tools)
- `radarr_add_movie` - Add movies to download queue
- `radarr_get_movies` - List all movies
- `radarr_system_status` - Check service health
- `radarr_disk_space` - Monitor storage
- `radarr_quality_profiles` - Manage quality settings

**Sonarr Management** (20+ tools)
- `sonarr_add_series` - Add TV series
- `sonarr_get_episodes` - List episodes
- `sonarr_monitor_episodes` - Control episode monitoring
- `sonarr_get_calendar` - View upcoming releases

**TMDb Integration** (5+ tools)
- `tmdb_search` - Search external database
- `tmdb_recommendations` - Get AI-powered suggestions

**Preference Management** (5+ tools)
- `query_household_preferences` - Ask targeted preference questions
- `update_household_preferences` - Modify taste profiles

## 💬 Usage Examples

### **Slash Commands**
```bash
/search query:"Inception" external:true
# Searches both Plex and TMDb for Inception

/watchlist addmovie tmdb_id:27205
# Adds Inception to Radarr download queue

/rate rating_key:12345 rating:9
# Sets a 9/10 rating on Plex item

/prefs get compact:true
# Shows human-readable preference summary
```

### **Natural Language Conversations**
```
@MovieBot "What should we watch tonight? I'm in the mood for something twisty and recent"

@MovieBot "Add The Matrix to my watchlist"

@MovieBot "What movies do we have that are similar to Inception?"

@MovieBot "Update our preferences - we really liked The Art of Self-Defense"
```

### **Household Preferences**
The bot maintains sophisticated preference profiles:
- **Content Constraints**: Era limits, runtime preferences, language requirements
- **Genre Preferences**: Liked/disliked genres with specific subcategories
- **Content Warnings**: Automatic filtering of sensitive topics
- **Aesthetic Preferences**: Visual style, pacing, tone requirements
- **Trusted Sources**: Favorite actors, directors, and reference films

## 🏗️ Project Structure

```
MovieBot/
├── bot/                          # Core bot functionality
│   ├── commands/                 # Discord slash commands
│   │   ├── search.py            # Plex/TMDb search
│   │   ├── watchlist.py         # Radarr/Sonarr management
│   │   ├── ratings.py           # Plex rating system
│   │   └── prefs.py             # Preference management
│   ├── tools/                   # AI agent tools
│   │   ├── registry.py          # Tool registration system
│   │   └── tool_impl.py         # 50+ tool implementations
│   ├── agent.py                 # GPT-5 reasoning engine
│   ├── agent_prompt.py          # AI system prompts
│   ├── conversation.py          # Chat history management
│   └── discord_bot.py           # Discord client
├── integrations/                 # External service clients
│   ├── plex_client.py           # Plex API integration
│   ├── radarr_client.py         # Radarr API integration
│   ├── sonarr_client.py         # Sonarr API integration
│   └── tmdb_client.py           # TMDb API integration
├── config/                       # Configuration management
│   └── loader.py                # Settings and config loading
├── llm/                         # OpenAI integration
│   └── clients.py               # LLM client wrapper
├── scripts/                      # Setup and utilities
│   └── setup_wizard.py          # Interactive configuration
├── data/                        # Persistent data
│   └── household_preferences.json # Taste profiles
├── tests/                       # Test suite
├── main.py                      # Entry point
└── requirements.txt             # Dependencies
```

## 🧪 Testing

```bash
# Run all tests
python run_tests.py

# Run with coverage
pytest --cov=bot --cov=integrations --cov=config

# Run specific test categories
pytest tests/test_bot/
pytest tests/test_integrations/
```

## 🔒 Security & Privacy

- **Local-first**: All media operations happen through your local services
- **No data sharing**: Household preferences stay on your server
- **API key security**: Sensitive tokens stored in `.env` (gitignored)
- **Permission-based**: Discord bot only accesses channels it's invited to

## 🚧 Development Status

**✅ Fully Implemented:**
- Complete Discord bot with slash commands
- GPT-5 conversational agent with 50+ tools
- Full Plex, Radarr, Sonarr, and TMDb integration
- Sophisticated household preference system
- Interactive setup wizard
- Comprehensive test suite

**🔄 Active Development:**
- Enhanced recommendation algorithms
- Additional media discovery tools
- Performance optimizations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

[Add your license information here]

## 🆘 Support

For issues and questions:
1. Check the test suite for usage examples
2. Review the configuration files
3. Check service connectivity
4. Open an issue with logs and error details

---

**MovieBot** - Your intelligent household media companion powered by AI and automation.


