# MovieBot

An elegant, provider‑agnostic AI assistant for your household media. MovieBot connects Plex, Radarr, Sonarr, and TMDb with a modern Discord experience — powered by OpenAI‑compatible models (OpenAI or OpenRouter). It's fast to set up, pleasant to use, and designed for contributors.

## ✨ Highlights

- Conversational agent with tool calling (90+ tools)
- Provider‑agnostic LLM routing, configured in `config/config.yaml`
- Role‑based model selection: `chat`, `smart`, and `worker`
- Optional reasoning effort per role (minimal / medium / high)
- Fast setup wizard and a modern, DM‑friendly Discord UX

Why people like it:
- Minimal config, sensible defaults, and a "no surprises" setup (your `.env` is never overwritten)
- Clear separation of concerns (config routing picks the model; agents do the work)
- Friendly codebase for contributors (typed, testable, and easy to navigate)

## 🚀 Quick Start

### 1) Prerequisites
- Python 3.10+
- Discord Bot Token and Application ID
- At least one LLM key: `OPENAI_API_KEY` or `OPENROUTER_API_KEY`
- Plex, Radarr, Sonarr, and TMDb API keys as needed

### 2) Install
```bash
git clone <repository-url>
cd MovieBot

python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 3) Configure via Setup Wizard

**Option A: One-Command Setup (Recommended)**
```bash
./setup_env_and_start.sh
```

**Option B: Manual Setup**
```bash
python main.py
```

#### Setup Process: The One-Two Punch

MovieBot uses a sophisticated two-stage setup process:

1. **`setup_env_and_start.sh`** - The Bash orchestrator that:
   - Validates Python environment and virtual environment
   - Checks dependencies and installs missing packages
   - Validates environment configuration
   - Automatically launches the setup wizard if needed
   - Starts the bot when everything is ready

2. **`setup_wizard.py`** - The Python wizard that:
   - Provides an interactive curses-based TUI (or simple prompt fallback)
   - Collects all necessary API keys and configuration
   - Creates configuration files safely (never overwrites existing `.env`)
   - Sets up household preferences and defaults

#### Setup Notes:
- Running `./setup_env_and_start.sh` handles the entire setup-to-launch process automatically
- The wizard will never overwrite your existing `.env`. If `.env` exists, changes are written to `.env.wizard.suggested` for you to review and merge
- The wizard pre-fills from your `.env`, and secret inputs are hidden
- To force-run the wizard at any time (even if config looks complete):
```bash
python -c "from pathlib import Path; from scripts.setup_wizard import run_interactive; run_interactive(Path('.').resolve())"
```

You'll be guided through:
- Discord configuration
- API key setup
- Radarr/Sonarr default profiles and folders
- Household preference initialization

### 4) Run the bot
```bash
python -m bot.discord_bot
```
What to expect:
- This is a long‑running process; leave it running. Press `Ctrl-C` to stop it.
- If you see messages like `Starting bot...` or `🔗 Sonarr client initialized ...`, the app is starting correctly.
- Increase verbosity when troubleshooting:
```bash
MOVIEBOT_LOG_LEVEL=DEBUG python -m bot.discord_bot
```

### Discord setup (intents and invite)

1) In the Discord Developer Portal → Your App → Bot:
- Enable "Message Content Intent".
- Recommended permissions: Send Messages, Read Message History.

2) Invite the bot to your server:
- In Developer Portal → OAuth2 → URL Generator: select scopes `bot` and `applications.commands`.
- Choose minimal permissions (Send Messages, Read Message History, Use Slash Commands).
- Copy the generated URL and open it to add the bot.

3) Faster slash command sync during development:
- Set `DISCORD_GUILD_ID` in `.env` to your dev server ID for near‑instant command sync.
- Without this, global command propagation can take up to ~1 hour.

4) Health check and first message:
- Use `/ping` to verify the bot is responsive in your server.
- In servers, either mention the bot or use slash commands. In DMs, just message it.

## 🔧 Configuration

### Environment (`.env`)
```bash
# Discord
DISCORD_TOKEN=your_bot_token
APPLICATION_ID=your_application_id
DISCORD_GUILD_ID=optional_dev_guild_id

# OpenAI / OpenRouter (provide either or both)
OPENAI_API_KEY=your_openai_key
OPENROUTER_API_KEY=your_openrouter_key

# Optional but recommended for OpenRouter rankings/attribution per docs
# Set to your app/site so OpenRouter can attribute traffic correctly
OPENROUTER_SITE_URL=https://your-site-or-repo-url
OPENROUTER_APP_NAME=MovieBot

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

Required vs optional:
- Required for the setup gate in `python main.py`: `DISCORD_TOKEN`, `OPENAI_API_KEY`, `PLEX_TOKEN`, `RADARR_API_KEY`, `SONARR_API_KEY`, `TMDB_API_KEY`.
- Optional but recommended: `DISCORD_GUILD_ID`, `APPLICATION_ID`.
- Defaults: `PLEX_BASE_URL`, `RADARR_BASE_URL`, `SONARR_BASE_URL` have sensible localhost defaults.
- OpenRouter support: You may use `OPENROUTER_API_KEY` at runtime. For OpenRouter header attribution, set `OPENROUTER_SITE_URL` and `OPENROUTER_APP_NAME`.

Note on providers and the setup gate:
- The runtime supports OpenAI and OpenRouter. However, the `python main.py` completeness check currently requires `OPENAI_API_KEY` specifically.
- If you plan to use OpenRouter only, start the bot directly with:
```bash
python -m bot.discord_bot
```
and set your `llm.providers.priority` to prefer `openrouter`.

### Runtime (`config/config.yaml`)

Minimum viable config for Radarr/Sonarr:
```yaml
radarr:
  qualityProfileId: 1
  rootFolderPath: "/movies"
sonarr:
  qualityProfileId: 1
  rootFolderPath: "/tv"
```

### Provider‑agnostic LLM routing

Tasks declare only the role they need (`chat` | `smart` | `worker`). The runtime selects the first available provider based on `priority`, verifies API keys, and returns the correct model plus any role‑specific parameters.

Two equivalent ways to specify models per role:

1) Simple string form (backwards compatible):
```yaml
llm:
  maxIters: 8
  providers:
    priority: [openai, openrouter]
    openai:
      chat: gpt-5-mini
      smart: gpt-5
      worker: gpt-5-nano
    openrouter:
      chat: z-ai/glm-4.5-air:free
      smart: z-ai/glm-4.5-air:free
      worker: z-ai/glm-4.5-air:free
```

2) Advanced object form (optional reasoning and params per role):
```yaml
llm:
  maxIters: 8
  providers:
    priority: [openai, openrouter]
    openai:
      chat:
        model: gpt-5-mini
        reasoningEffort: minimal   # default for chat if omitted
        params:
          temperature: 1
          tool_choice: auto
      smart:
        model: gpt-5
        params:
          temperature: 1
      worker:
        model: gpt-5-nano
        params:
          temperature: 0.7
    openrouter:
      chat:
        model: z-ai/glm-4.5-air:free
        reasoningEffort: minimal
      smart:
        model: z-ai/glm-4.5-air:free
      worker:
        model: z-ai/glm-4.5-air:free
        params:
          temperature: 0.7
```

Notes:
- The router respects `providers.priority` and required API keys.
- For `chat`, `reasoningEffort` defaults to `minimal` (keeps latency low with `gpt-5-mini`).
- Extra `params` are passed directly to the OpenAI‑compatible API (e.g., `temperature`, `top_p`, `max_tokens`, `tool_choice`).
- With OpenRouter, tracking headers (`HTTP-Referer`, `X-Title`) derive from `OPENROUTER_SITE_URL` and `OPENROUTER_APP_NAME`.

Troubleshooting:
- Slash commands not appearing: set `DISCORD_GUILD_ID` for your dev server and rerun; otherwise global sync may take up to ~1 hour.
- Bot "starts and stops": that's `Ctrl-C` interrupting. Leave it running to stay online.
- "Missing intents/permissions": enable Message Content Intent and ensure the bot has Send Messages + Read Message History in your server.
- Model provider errors: verify the selected provider has a valid API key and that `llm.providers.priority` matches your keys.
- Radarr/Sonarr connectivity: confirm base URLs and API keys; ensure services are reachable from your machine.

### Other runtime tuning
```yaml
tools:
  timeoutMs: 6000
  parallelism: 6
  retryMax: 1
  backoffBaseMs: 100
llm:
  # Defaults if not set per-role; kept tight to reduce unnecessary loops
  maxIters: 4
  agentMaxIters: 4
  workerMaxIters: 3
ux:
  progressThresholdMs: 3000
  progressUpdateIntervalMs: 5000
  progressUpdateFrequency: 2
http:
  connectTimeoutMs: 2000
  readTimeoutMs: 8000
  totalTimeoutMs: 12000
  maxConnections: 100
cache:
  ttlShortSec: 60
  ttlMediumSec: 300
```

## 🎭 How It Works

1. Discord events are processed and converted to messages
2. The agent selects an LLM by role using the config router
3. The agent reasons and calls tools (Plex, Radarr, Sonarr, TMDb)
4. Two-phase execution: a read-only probe first, then writes (if needed)
5. Early finalize heuristic: if results are sufficient (or writes succeed), the agent performs a finalize‑only pass
6. Final responses are streamed to Discord for snappy UX

```
User → Agent → Read Tools → (optional) Write Tools → Streamed Answer
```

## 💬 Examples

### Slash commands
```bash
/search query:"Inception" external:true
/watchlist addmovie tmdb_id:27205
/rate rating_key:12345 rating:9
/prefs get compact:true
```

### Natural language
```
@MovieBot "What should we watch tonight?"
@MovieBot "Add The Matrix to my watchlist"
@MovieBot "What's similar to Inception?"
```

## 🧱 Project Structure

```
MovieBot/
├── bot/
│   ├── agent.py
│   ├── discord_bot.py
│   ├── tools/
│   └── commands/
├── config/
│   └── loader.py
├── llm/
│   └── clients.py
├── integrations/
├── scripts/
│   └── setup_wizard.py
├── data/
├── tests/
├── main.py
├── setup_env_and_start.sh
└── requirements.txt
```

**Key Setup Files:**
- **`setup_env_and_start.sh`** - Main setup orchestrator and launcher
- **`scripts/setup_wizard.py`** - Interactive configuration wizard
- **`main.py`** - Alternative setup entry point

## 🧪 Testing

```bash
# Unit tests
pytest -q

# Coverage
pytest --cov=bot --cov=integrations --cov=config
```

Integration tests (optional) reuse your existing `.env` and local services.

## 🔒 Security & Privacy

- Local‑first: your media stays on your server
- Preferences are stored in `data/household_preferences.json`
- Secrets live in `.env` (gitignored)

## 🛠️ Development Status

Stable core with active improvements to recommendations, discovery tools, and performance.

## 🤝 Contributing

1. Fork and create a feature branch
2. Write tests for new functionality
3. Ensure all tests pass
4. Open a PR

## 📄 License

MIT License. See `LICENSE` for details.

---

MovieBot — provider‑agnostic, role‑based, and tuned for practical speed.


