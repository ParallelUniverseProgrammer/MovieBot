# 🎬 MovieBot

**MovieBot** is your friendly home media assistant that lives right inside Discord.  
It connects seamlessly with **Plex, Radarr, Sonarr, and TMDb**, so you can search, discover, and manage your media library in plain English.  

Whether you want to find something to watch tonight, add a new movie to your download queue, or just check what’s in your Plex library, MovieBot makes it simple. Over time, it even learns your household’s tastes and gives smarter, more personal recommendations.

---

## ✨ Why MovieBot?

- **No new apps** — use it directly in Discord, on any device.  
- **Natural language search** — ask in plain English, get results fast.  
- **Smart library management** — add and manage movies/shows in Radarr and Sonarr.  
- **Know your library** — search and summarize what’s already in Plex.  
- **Learns your taste** — remembers your favorite genres, actors, and preferences.  
- **Safe setup** — your `.env` is never overwritten.  
- **Reliable under load** — caching, retries, and parallel requests keep it fast.  
- **Provider‑agnostic** — works with OpenAI or OpenRouter, your choice.  
- **Tinkerer‑friendly** — clear config, typed code, and easy to extend.  

**In short:** set it up once, and your household has a smart, always‑on media helper in Discord.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.8+
- Discord Bot Token and Application ID
- At least one LLM key: `OPENAI_API_KEY` or `OPENROUTER_API_KEY`
- Plex, Radarr, Sonarr, and TMDb API keys (as needed)

### 2. Install
```bash
git clone <repository-url>
cd MovieBot

python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 3. Configure with the Setup Wizard

**Option A: One‑Command Setup (Recommended)**
```bash
./setup_env_and_start.sh
```

**Option B: Manual Setup**
```bash
python main.py
```

The setup process is a **two‑step helper**:

1. **`setup_env_and_start.sh`**  
   - Checks Python version and dependencies  
   - Activates your virtual environment  
   - Validates your environment configuration  
   - Runs the setup wizard if needed  
   - Starts the bot  

2. **`setup_wizard.py`**  
   - Interactive TUI (or simple prompts if TUI isn’t available)  
   - Collects API keys and preferences  
   - Creates config files safely (never overwrites `.env`)  
   - Initializes household defaults  

💡 If `.env` already exists, changes are written to `.env.wizard.suggested` for you to review.

---

### 4. Run the Bot

**Option A: Using the setup script (Recommended)**
```bash
./setup_env_and_start.sh
```

**Option B: Direct execution**
```bash
python -m bot.discord_bot
# or
python -m bot
```

You’ll see logs like `Starting bot...` or `🔗 Sonarr client initialized ...` when it’s working.  
Leave it running — press `Ctrl-C` to stop.

For troubleshooting:
```bash
MOVIEBOT_LOG_LEVEL=DEBUG python -m bot.discord_bot
```

---

## 💬 Using MovieBot in Discord

1. **Enable Intents**  
   In the Discord Developer Portal → Your App → Bot:  
   - Enable *Message Content Intent*  
   - Give permissions: *Send Messages*, *Read Message History*  

2. **Invite the Bot**  
   In Developer Portal → OAuth2 → URL Generator:  
   - Select scopes: `bot`, `applications.commands`  
   - Choose minimal permissions (Send Messages, Read Message History, Use Slash Commands)  
   - Copy the generated URL and invite the bot to your server  

3. **Faster Development Sync**  
   - Set `DISCORD_GUILD_ID` in `.env` for near‑instant slash command sync  
   - Without it, global sync can take up to ~1 hour  

4. **First Check**  
   - Use `/ping` to confirm the bot is alive  
   - In servers: mention the bot or use slash commands  
   - In DMs: just message it directly  

---

## 🔧 Configuration

### Environment (`.env`)
```bash
# Discord
DISCORD_TOKEN=your_bot_token
APPLICATION_ID=your_application_id
DISCORD_GUILD_ID=optional_dev_guild_id

# OpenAI / OpenRouter
OPENAI_API_KEY=your_openai_key
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
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

# Logging
MOVIEBOT_LOG_LEVEL=INFO
```

**Required:**  
- `DISCORD_TOKEN`  
- `PLEX_TOKEN` + `PLEX_BASE_URL`  
- Either `OPENAI_API_KEY` or `OPENROUTER_API_KEY`  

**Optional but recommended:**  
- `DISCORD_GUILD_ID`, `APPLICATION_ID`, `RADARR_API_KEY`, `SONARR_API_KEY`, `TMDB_API_KEY`  

---

### Runtime (`config/config.yaml`)

**Minimal config:**
```yaml
household:
  displayName: Household
radarr:
  qualityProfileId: 1
  rootFolderPath: "D:\\Movies"
sonarr:
  qualityProfileId: 4
  rootFolderPath: "D:\\TV"
```

**Full example available in the repo** with advanced tuning for LLMs, caching, retries, and UX.

---

## 🧠 Smart Household Preferences

MovieBot learns what your household likes and adapts over time:

- **Genres** — remembers your favorite themes and aesthetics  
- **People** — actors, directors, creators you love  
- **Constraints** — runtime sweet spots, language, content warnings  
- **Anti‑preferences** — what to avoid (e.g. shaky‑cam, found footage)  

You can query and update preferences naturally:
```bash
@MovieBot "What genres do we like for horror movies?"
@MovieBot "Add Pedro Pascal to our favorite actors"
@MovieBot "Recommend something similar to The Matrix but more recent"
```

---

## 🎭 How It Works

1. Discord messages → processed by the agent  
2. Agent selects the right LLM role (chat, smart, worker)  
3. Agent queries tools (Plex, Radarr, Sonarr, TMDb)  
4. Two‑phase execution: read first, then write if needed  
5. Results are streamed back to Discord  

```
User → Agent → Tools → (optional) Writes → Streamed Answer
```

---

## 💡 Example Commands

### Slash Commands
```bash
/discover search query:"Inception" year:2010
/media recent
/management addmovie tmdb_id:12345
/prefs add path:"likes.genres" value:"thriller"
/utilities ping
```

### Natural Language
```
@MovieBot "What should we watch tonight?"
@MovieBot "Add The Matrix to my watchlist"
@MovieBot "Find me a thriller with Pedro Pascal"
@MovieBot "Show me my unwatched movies from 2023"
```

---

## ⚡ Performance & Reliability

- **Caching** — short (60s) and medium (240s) TTL caches  
- **Parallel execution** — up to 12 concurrent tool calls, tuned per service  
- **Circuit breaker** — recovers gracefully after failures  
- **Hedged requests** — backup requests reduce latency  
- **Deduplication** — avoids redundant API calls  

---

## 🧪 Testing

MovieBot includes both **unit tests** (fast, mocked) and **integration tests** (live services).

**Run unit tests:**
```bash
pytest tests/ -v -m "not integration"
```

**Run integration tests:**
```bash
pytest tests/ -v -m "integration"
```

**With coverage:**
```bash
pytest tests/ -v --cov=bot --cov=integrations --cov=config --cov-report=term-missing
```

---

## 🐛 Debugging with trace_agent.py

When MovieBot isn't behaving as expected, `trace_agent.py` is your best friend for understanding what's happening under the hood. This debugging tool runs the agent once and captures a detailed trace of every step, tool call, and decision.

### Usage
```bash
# Basic usage with default message
python scripts/trace_agent.py

# Custom message
python scripts/trace_agent.py --message "Find me a thriller with Pedro Pascal"

# Pretty-print the final response
python scripts/trace_agent.py --message "Show me my unwatched movies" --pretty

# Limit trace output (useful for long-running queries)
python scripts/trace_agent.py --max-events 50
```

### What You'll See

The trace shows you:
- **Agent planning** — how the agent breaks down your request
- **Tool execution** — which APIs are called and how long they take
- **LLM reasoning** — the model's decision-making process
- **Phase transitions** — read-only vs write operations
- **Performance metrics** — timing for each operation

### Example Trace Output

Here's what a complex compound query looks like:

```bash
$ python scripts/trace_agent.py --message "Show me all the horror movies in my Plex library from 2020-2023, sorted by rating, and tell me which ones I haven't watched yet"

[agent.start] Kicking off a plan and launching up to 12 tasks in parallel for 6 steps.
[heartbeat] Still working—keeping things moving in the background.
[thinking] Thinking through options (iteration 1/6) with a bias for decisive parallel moves.
[llm.start] Consulting gpt-5-mini to sketch the best next set of actions.
[llm.finish] LLM plan refined; executing the most promising actions now.
[phase.read_only] Phase Read_Only in progress.
[tool.start] Starting search plex (search_plex) to advance the goal.
[tool.finish] Finished search plex (search_plex) in 93 ms; folding results into the plan.
[heartbeat] Still working—keeping things moving in the background.
[thinking] Thinking through options (iteration 3/6) with a bias for decisive parallel moves.
[llm.start] Consulting gpt-5-mini to sketch the best next set of actions.
[heartbeat] Still working—keeping things moving in the background.
[llm.finish] LLM plan refined; executing the most promising actions now.
[tool.start] Starting search plex (search_plex) to advance the goal.
[tool.finish] Finished search plex (search_plex) in 241 ms; folding results into the plan.
[thinking] Thinking through options (iteration 5/6) with a bias for decisive parallel moves.
[llm.start] Consulting gpt-5-mini to sketch the best next set of actions.
[heartbeat] Still working—keeping things moving in the background.
[llm.finish] LLM plan refined; executing the most promising actions now.
[agent.finish] Wrapping up—returning the final picks now.

=== TRACE (tail) ===
[
  {
    "kind": "agent.start",
    "detail": "Kicking off a plan and launching up to 12 tasks in parallel for 6 steps."
  },
  {
    "kind": "phase.read_only",
    "detail": "Phase Read_Only in progress."
  },
  {
    "kind": "tool.start",
    "detail": "Starting search plex (search_plex) to advance the goal."
  },
  {
    "kind": "tool.finish",
    "detail": "Finished search plex (search_plex) in 93 ms; folding results into the plan."
  }
  // ... more events
]

=== RESPONSE ===
Running your library search and filters now — here are the horror movies from 2020–2023 in your Plex, sorted by rating (I checked Plex for watched status too):

- No results found for Horror movies between 2020–2023 in your Plex [Plex]

If you expected titles from 2020–2023 to appear, would you like me to:
- broaden the year range (e.g., 2018–2023), or
- search for related genres (thriller/psychological) or specific titles to add?
```

### Why It's Super Useful

- **Performance debugging** — see exactly which API calls are slow
- **Logic flow** — understand how the agent interprets complex requests
- **Error isolation** — pinpoint where things go wrong
- **Optimization** — identify redundant or inefficient operations
- **Development** — verify new features work as expected

Perfect for troubleshooting why a query didn't return expected results or why it's taking longer than usual.

---

## 🔒 Security & Privacy

- Local‑first: your media stays on your server  
- Preferences stored in `data/household_preferences.json`  
- Secrets live in `.env` (gitignored)  

---

## 🛠️ Development Status

Stable core with ongoing improvements to recommendations, discovery, and performance.

---

## 🤝 Contributing

1. Fork and create a feature branch  
2. Write tests for new functionality  
3. Ensure all tests pass  
4. Open a PR  

---

## 📄 License

MIT License. See `LICENSE` for details.

---

**MovieBot** — a smart, reliable, and friendly media assistant for your household.  
Set it up once, and let it handle the rest.