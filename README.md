# MovieBot

An elegant, provider‑agnostic AI assistant for your household media. MovieBot integrates with Plex, Radarr, Sonarr, and TMDb to provide intelligent recommendations, manage your libraries, and chat via Discord — powered by OpenAI‑compatible models (OpenAI or OpenRouter).

## ✨ Highlights

- Conversational agent with tool calling (50+ tools)
- Provider‑agnostic LLM routing driven entirely by `config/config.yaml`
- Role‑based model selection: `chat`, `smart`, and `worker`
- Optional reasoning effort controls per role (minimal/medium/high)
- Fast setup wizard and modern Discord UX

## 🚀 Quick Start

### 1) Prerequisites
- Python 3.8+
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
```bash
python main.py
```
You’ll be guided through:
- Discord configuration and connectivity checks
- API key setup
- Radarr/Sonarr default profiles and folders
- Household preference initialization

### 4) Run the bot
```bash
python -m bot.discord_bot
```

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

Tasks only declare the role they need (`chat` | `smart` | `worker`). The runtime chooses the first available provider based on `priority`, verifies API keys, and returns the correct model plus any role‑specific parameters every time.

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
- For `chat`, `reasoningEffort` defaults to `minimal` if not specified (keeps latency low with `gpt-5-mini`).
- Extra `params` are passed directly to the OpenAI‑compatible API (e.g., `temperature`, `top_p`, `max_tokens`, `tool_choice`).
- When using OpenRouter, we automatically send `HTTP-Referer` and `X-Title` headers derived from `OPENROUTER_SITE_URL` and `OPENROUTER_APP_NAME` to comply with their recommendations.

### Other runtime tuning
```yaml
tools:
  timeoutMs: 6000
  parallelism: 6
  retryMax: 1
  backoffBaseMs: 100
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
2. The Agent selects an LLM by role using the config router
3. The Agent reasons and calls tools (Plex, Radarr, Sonarr, TMDb)
4. Results are summarized back to the user

```
User → Agent → Tool Calls → Integrations → Answer
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
@MovieBot "What’s similar to Inception?"
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
├── data/
├── tests/
├── main.py
└── requirements.txt
```

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

[Add your license information here]

---

MovieBot — provider‑agnostic, role‑based, and tuned for practical speed.


