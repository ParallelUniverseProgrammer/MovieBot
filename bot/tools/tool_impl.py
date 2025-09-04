from __future__ import annotations

import json
import asyncio
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Tuple, Union

try:
    import orjson  # type: ignore
except Exception:  # pragma: no cover
    orjson = None

from config.loader import load_settings, load_runtime_config
from bot.workers.plex_search import PlexSearchWorker


def make_search_plex(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        worker = PlexSearchWorker(project_root)
        return await worker.search(
            query=args.get("query"),
            limit=args.get("limit", 20),
            response_level=args.get("response_level"),
            filters=args.get("filters"),
        )

    return impl


def make_sonarr_episode_fallback_search(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Handle episode fallback search when season packs fail using sub-agent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent
        
        series_id = int(args["series_id"])
        season_number = int(args["season_number"])
        series_title = str(args["series_title"])
        target_episodes = [int(ep) for ep in args["target_episodes"]]
        
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        
        # Get provider from main agent context or fall back to config
        # The main agent should pass this information when calling the tool
        provider = args.get("provider") or config.get("llm", {}).get("provider", "openai")
        api_key = args.get("api_key") or settings.openai_api_key or config.get("llm", {}).get("apiKey", "")
        
        # Create sub-agent for focused episode search with correct provider settings
        sub_agent = SubAgent(
            api_key=api_key,
            project_root=project_root,
            provider=provider
        )
        
        try:
            result = await sub_agent.handle_episode_fallback_search(
                series_id, season_number, series_title, target_episodes
            )
            return result
        finally:
            # Clean up sub-agent resources
            if hasattr(sub_agent.llm, 'client') and hasattr(sub_agent.llm.client, 'close'):
                await sub_agent.llm.client.close()

    return impl


def make_sonarr_quality_fallback(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Handle quality fallback when preferred quality isn't available using sub-agent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent
        
        series_id = int(args["series_id"])
        target_quality = str(args["target_quality"])
        fallback_qualities = [str(q) for q in args["fallback_qualities"]]
        
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        
        # Get provider from main agent context or fall back to config
        # The main agent should pass this information when calling the tool
        provider = args.get("provider") or config.get("llm", {}).get("provider", "openai")
        api_key = args.get("api_key") or settings.openai_api_key or config.get("llm", {}).get("apiKey", "")
        
        # Create sub-agent for quality management with correct provider settings
        sub_agent = SubAgent(
            api_key=api_key,
            project_root=project_root,
            provider=provider
        )
        
        try:
            result = await sub_agent.handle_quality_fallback(
                series_id, target_quality, fallback_qualities
            )
            return result
        finally:
            # Clean up sub-agent resources
            if hasattr(sub_agent.llm, 'client') and hasattr(sub_agent.llm.client, 'close'):
                await sub_agent.llm.client.close()

    return impl




def _flatten(obj: Any, base_path: str = "") -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{base_path}.{k}" if base_path else k
            items.extend(_flatten(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{base_path}[{i}]"
            items.extend(_flatten(v, path))
    else:
        items.append((base_path, str(obj)))
    return items


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _join(values: List[str], *, empty: str = "-", max_items: int | None = None) -> str:
    if not values:
        return empty
    items = values if (max_items is None or len(values) <= max_items) else values[:max_items] + ["…"]
    return ", ".join(items)


def _pick(obj: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in obj:
            return obj[k]
    return None


def build_preferences_context(data: Dict[str, Any]) -> str:
    """Build a compact, curated context string from the household preferences JSON."""
    likes = data.get("likes", {}) or {}
    dislikes = data.get("dislikes", {}) or {}
    constraints = data.get("constraints", {}) or {}
    profile = data.get("profile", {}) or {}
    anchors = data.get("anchors", {}) or {}
    heuristics = data.get("heuristics", {}) or {}
    curiosities = data.get("currentCuriosities", {}) or {}

    # Header / snapshot
    notes = (data.get("notes") or "").strip()
    plaus = profile.get("plausibilityScore10")
    header_bits: List[str] = []
    if notes:
        header_bits.append(notes)
    if plaus is not None:
        header_bits.append(f"plausibility ~{plaus}/10")
    header = "; ".join(header_bits)

    # Likes / dislikes
    like_genres = _join(_as_list(likes.get("genres")), max_items=8)
    like_people = _join(_as_list(likes.get("people")), max_items=8)
    like_vibes = _join(_as_list(likes.get("vibes")), max_items=8)
    like_aesthetics = _join(_as_list(likes.get("aesthetics")), max_items=8)
    like_motifs = _join(_as_list(likes.get("motifs")), max_items=8)

    dislike_genres = _join(_as_list(dislikes.get("genres")), max_items=8)
    dislike_aesthetics = _join(_as_list(dislikes.get("aesthetics")), max_items=8)
    dislike_tones = _join(_as_list(dislikes.get("tones")), max_items=8)
    dislike_structure = _join(_as_list(dislikes.get("structure")), max_items=8)
    dislike_vibes = _join(_as_list(dislikes.get("vibes")), max_items=8)

    # Constraints
    era_min = constraints.get("eraMinYear")
    lang_whitelist = _join(_as_list(_pick(constraints, "languageWhitelist", "languages")), max_items=6)
    rt = constraints.get("runtimeSweetSpotMins") or []
    rt_str = f"{rt[0]}–{rt[1]} min" if isinstance(rt, list) and len(rt) == 2 else "-"
    cw = _join(_as_list(constraints.get("contentWarnings")))
    visuals_disallow = _join(_as_list(constraints.get("visualsDisallow")))
    jumps = constraints.get("allowJumpScares")

    # Profile sliders / cues
    tone_non = _pick(profile.get("tone", {}), "nonHorror") if isinstance(profile.get("tone"), dict) else None
    tone_hor = _pick(profile.get("tone", {}), "horror") if isinstance(profile.get("tone"), dict) else None
    pacing = profile.get("pacing")
    structure = profile.get("structure")
    visuals = profile.get("visuals")
    reality = profile.get("reality")
    meta = profile.get("meta")
    ending = profile.get("ending")
    gore = profile.get("goreViolence")
    humor_non = _pick(profile.get("humor", {}), "nonHorror") if isinstance(profile.get("humor"), dict) else None
    humor_hor = _pick(profile.get("humor", {}), "horror") if isinstance(profile.get("humor"), dict) else None

    # Anchors
    loved = _join(_as_list(anchors.get("loved")), max_items=8)
    responded = _join(_as_list(_pick(anchors, "respondedTo", "responded")), max_items=8)
    comfort = _join(_as_list(anchors.get("comfortSignals")), max_items=8)
    faces = _join(_as_list(_pick(anchors, "trustedFaces", "faces")), max_items=8)

    # Heuristics
    lead = heuristics.get("lead")
    pairing = heuristics.get("pairing")
    themes = _join(_as_list(heuristics.get("themes")), max_items=8)
    chamber = heuristics.get("chamber")
    slow_burn = heuristics.get("slowBurn")
    exposition = heuristics.get("exposition")
    couple_first = heuristics.get("coupleFirst")
    zero_spoilers = heuristics.get("zeroSpoilers")
    max_options = heuristics.get("maxOptions")

    # Curiosities
    vibes_tonight = _join(_as_list(_pick(curiosities, "vibesTonight", "vibes")), max_items=6)
    themes_soon = _join(_as_list(_pick(curiosities, "themesSoon", "themes")), max_items=6)

    anti = _join(_as_list(data.get("antiPreferences")), max_items=8)
    never_titles = _join(_as_list(data.get("neverRecommend", {}).get("titles")), max_items=8)

    parts: List[str] = []
    if header:
        parts.append(f"Flavor: {header}.")
    parts.append(f"Constraints: {era_min or '-'}+, lang [{lang_whitelist}], runtime {rt_str}; disallow [{visuals_disallow}]; flags [{cw}]; jump scares: {'ok' if jumps else 'avoid' if jumps is False else '-'}.")
    parts.append(f"Likes: genres [{like_genres}]; vibes [{like_vibes}]; aesthetics [{like_aesthetics}]; motifs [{like_motifs}]; faces [{like_people}].")
    parts.append(f"Dislikes: genres [{dislike_genres}]; aesthetics [{dislike_aesthetics}]; tones [{dislike_tones}]; structure [{dislike_structure}]; vibes [{dislike_vibes}].")
    # Profile cues condensed
    profile_bits: List[str] = []
    if tone_non:
        profile_bits.append(f"non-horror tone: {tone_non}")
    if tone_hor:
        profile_bits.append(f"horror tone: {tone_hor}")
    profile_fields = [
        ("pacing", pacing),
        ("structure", structure),
        ("visuals", visuals),
        ("reality", reality),
        ("meta", meta),
        ("ending", ending),
        ("gore/violence", gore),
    ]
    for label, val in profile_fields:
        if val:
            profile_bits.append(f"{label}: {val}")
    if humor_non:
        profile_bits.append(f"humor(non-horror): {humor_non}")
    if humor_hor:
        profile_bits.append(f"humor(horror): {humor_hor}")
    if profile_bits:
        parts.append("Profile: " + "; ".join(profile_bits) + ".")
    # Anchors
    anchor_bits: List[str] = []
    if loved and loved != "-":
        anchor_bits.append(f"loved [{loved}]")
    if responded and responded != "-":
        anchor_bits.append(f"responded [{responded}]")
    if comfort and comfort != "-":
        anchor_bits.append(f"comfort [{comfort}]")
    if faces and faces != "-":
        anchor_bits.append(f"faces [{faces}]")
    if anchor_bits:
        parts.append("Anchors: " + "; ".join(anchor_bits) + ".")
    # Heuristics
    heur_bits: List[str] = []
    if lead:
        heur_bits.append(f"lead: {lead}")
    if pairing:
        heur_bits.append(f"pair: {pairing}")
    if themes and themes != "-":
        heur_bits.append(f"themes [{themes}]")
    if chamber:
        heur_bits.append(f"chamber: {chamber}")
    if slow_burn:
        heur_bits.append(f"slow-burn: {slow_burn}")
    if exposition:
        heur_bits.append(f"exposition: {exposition}")
    if couple_first is not None:
        heur_bits.append(f"couple-first: {'yes' if couple_first else 'no'}")
    if zero_spoilers is not None:
        heur_bits.append(f"zero-spoilers: {'yes' if zero_spoilers else 'no'}")
    if max_options is not None:
        heur_bits.append(f"options: {max_options}")
    if heur_bits:
        parts.append("Heuristics: " + "; ".join(heur_bits) + ".")
    # Curiosities
    cur_bits: List[str] = []
    if vibes_tonight and vibes_tonight != "-":
        cur_bits.append(f"vibes tonight [{vibes_tonight}]")
    if themes_soon and themes_soon != "-":
        cur_bits.append(f"themes soon [{themes_soon}]")
    if cur_bits:
        parts.append("Curiosities: " + "; ".join(cur_bits) + ".")
    if anti and anti != "-":
        parts.append(f"Anti-prefs: [{anti}].")
    if never_titles and never_titles != "-":
        parts.append(f"Never recommend: titles [{never_titles}].")

    out = "\n".join(parts)
    # Hard cap to keep context efficient
    if len(out) > 1800:
        out = out[:1797] + "…"
    return out


class PreferencesStore:
    """Async, cached preferences store with deep-merge and path ops."""
    def __init__(self, project_root: Path) -> None:
        self.path = project_root / "data" / "household_preferences.json"
        self._cache: Dict[str, Any] | None = None
        self._mtime: float | None = None
        self._lock = asyncio.Lock()
        self._size: int | None = None

    def _loads(self, data: bytes | str) -> Dict[str, Any]:
        if orjson:
            return orjson.loads(data)  # type: ignore[arg-type]
        return json.loads(data)  # type: ignore[arg-type]

    def _dumps(self, obj: Any) -> bytes:
        if orjson:
            return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
        return json.dumps(obj, indent=2).encode("utf-8")

    async def _read_file(self) -> Dict[str, Any]:
        def _read() -> Dict[str, Any]:
            with open(self.path, "rb") as f:
                raw = f.read()
            return self._loads(raw)
        return await asyncio.to_thread(_read)

    async def _write_file(self, data: Dict[str, Any]) -> None:
        def _write() -> None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "wb") as f:
                f.write(self._dumps(data))
        await asyncio.to_thread(_write)

    async def load(self) -> Dict[str, Any]:
        async with self._lock:
            try:
                st = os.stat(self.path)
                mtime = st.st_mtime
                size = st.st_size
            except FileNotFoundError:
                self._cache = {}
                self._mtime = None
                self._size = None
                return {}

            # Re-read if cache missing or file characteristics changed
            if self._cache is None or self._mtime != mtime or self._size != size:
                self._cache = await self._read_file()
                self._mtime = mtime
                self._size = size
            return self._cache

    async def save(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            await self._write_file(data)
            try:
                st = os.stat(self.path)
                self._mtime = st.st_mtime
                self._size = st.st_size
            except FileNotFoundError:
                self._mtime = None
                self._size = None
            self._cache = data

    def _ensure_container_for_path(self, data: Dict[str, Any], parts: List[str]) -> Dict[str, Any]:
        cur: Any = data
        for p in parts[:-1]:
            if not isinstance(cur, dict):
                return data
            if p not in cur or not isinstance(cur[p], (dict, list)):
                cur[p] = {}
            cur = cur[p]
        return data

    def _get_by_path(self, data: Dict[str, Any], dotted_path: str) -> Any:
        cur: Any = data
        for part in dotted_path.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    def _set_by_path(self, data: Dict[str, Any], dotted_path: str, value: Any) -> Dict[str, Any]:
        parts = dotted_path.split('.')
        self._ensure_container_for_path(data, parts)
        cur: Any = data
        for p in parts[:-1]:
            cur = cur[p]
        cur[parts[-1]] = value
        return data

    def _list_append(self, data: Dict[str, Any], dotted_path: str, value: Any) -> Dict[str, Any]:
        parts = dotted_path.split('.')
        self._ensure_container_for_path(data, parts)
        cur: Any = data
        for p in parts[:-1]:
            cur = cur[p]
        lst = cur.get(parts[-1])
        if lst is None:
            cur[parts[-1]] = [value]
            return data
        if not isinstance(lst, list):
            raise ValueError(f"Path '{dotted_path}' is not a list")
        if value not in lst:
            lst.append(value)
        return data

    def _list_remove_value(self, data: Dict[str, Any], dotted_path: str, value: Any) -> Dict[str, Any]:
        cur = self._get_by_path(data, dotted_path)
        if not isinstance(cur, list):
            raise ValueError(f"Path '{dotted_path}' is not a list")
        try:
            cur.remove(value)
        except ValueError:
            pass
        return data

    def _deep_merge(self, base: Any, patch: Any) -> Any:
        if isinstance(base, dict) and isinstance(patch, dict):
            for k, v in patch.items():
                if k in base:
                    base[k] = self._deep_merge(base[k], v)
                else:
                    base[k] = v
            return base
        return patch


def make_read_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    store = PreferencesStore(project_root)
    async def impl(args: dict) -> dict:
        data = await store.load()

        keys = args.get("keys")
        jpath = args.get("path")
        compact = bool(args.get("compact", False))
        if jpath:
            # Simple dotted path navigation
            cur: Any = data
            for part in str(jpath).split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    cur = None
                    break
            return {"path": jpath, "value": cur}
        if keys:
            return {k: data.get(k) for k in keys}
        if compact:
            try:
                context = build_preferences_context(data)
            except Exception:
                # Fallback to a simple flattened string if formatting fails
                flat = _flatten(data)
                context = "; ".join(f"{k}: {v}" for k, v in flat[:100])
            return {"compact": context}
        return data

    return impl


def make_update_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    store = PreferencesStore(project_root)
    async def impl(args: dict) -> dict:
        # Supports: patch (deep merge), path+value (set), append/remove_value for lists, and json patch ops
        patch = args.get("patch")
        dotted_path = args.get("path")
        value: Any = args.get("value")
        append = args.get("append")
        remove_value = args.get("remove_value")
        ops = args.get("ops")

        # Allow stringified JSON value to be parsed
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                pass
        if isinstance(append, str):
            try:
                append = json.loads(append)
            except Exception:
                pass
        if isinstance(remove_value, str):
            try:
                remove_value = json.loads(remove_value)
            except Exception:
                pass

        data = await store.load()

        if ops:
            # Minimal JSON Patch support: add, replace, remove
            if not isinstance(ops, list):
                raise ValueError("ops must be a list of JSON patch operations")
            for op in ops:
                if not isinstance(op, dict):
                    continue
                operation = op.get("op")
                path_str = op.get("path", "").lstrip("/").replace("/", ".")
                if operation in ("add", "replace"):
                    val = op.get("value")
                    data = store._set_by_path(data, path_str, val)
                elif operation == "remove":
                    parts = path_str.split('.')
                    cur: Any = data
                    for p in parts[:-1]:
                        if isinstance(cur, dict) and p in cur:
                            cur = cur[p]
                        else:
                            cur = None
                            break
                    if isinstance(cur, dict):
                        cur.pop(parts[-1], None)
            await store.save(data)
            return {"ok": True}

        if dotted_path is not None:
            if append is not None and remove_value is not None:
                raise ValueError("Specify only one of append or remove_value")
            if append is not None:
                data = store._list_append(data, dotted_path, append)
            elif remove_value is not None:
                data = store._list_remove_value(data, dotted_path, remove_value)
            else:
                data = store._set_by_path(data, dotted_path, value)
            await store.save(data)
            return {"ok": True}

        if patch is not None:
            if not isinstance(patch, dict):
                raise ValueError("patch must be an object")
            merged = store._deep_merge(data or {}, patch)
            await store.save(merged)
            return {"ok": True}

        raise ValueError("No valid update parameters provided")

    return impl


def make_search_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip().lower()
        limit = int(args.get("limit", 10))
        path = project_root / "data" / "household_preferences.json"
        try:
            def _read():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            data = await asyncio.to_thread(_read)
        except FileNotFoundError:
            return {"matches": []}
        flat = _flatten(data)
        matches = [(k, v) for k, v in flat if query in k.lower() or query in v.lower()]
        out = [{"path": k, "value": v} for k, v in matches[:limit]]
        return {"matches": out}

    return impl


def make_query_household_preferences(project_root: Path, llm_client) -> Callable[[dict], Awaitable[dict]]:
    """Query household preferences using available LLM and return a concise one-sentence response."""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "Query is required"}
        
        path = project_root / "data" / "household_preferences.json"
        try:
            def _read():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            data = await asyncio.to_thread(_read)
        except FileNotFoundError:
            return {"error": "Household preferences not found"}
        
        # Build the compact summary
        try:
            compact = build_preferences_context(data)
        except Exception:
            # Fallback to a simple flattened string if formatting fails
            flat = _flatten(data)
            compact = "; ".join(f"{k}: {v}" for k, v in flat[:100])
        
        # Choose model and selection from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(project_root, "worker")
        model = sel.get("model", "gpt-5-nano")
        
        # Prepare the prompt for the selected model
        system_message = {
            "role": "system",
            "content": "You are a helpful assistant that answers questions about household movie preferences. Based on the preferences provided, answer the user's question in exactly one sentence. Be concise and specific. Do not include explanations or additional context - just the direct answer."
        }
        
        user_message = {
            "role": "user", 
            "content": f"Preferences: {compact}\n\nQuestion: {query}\n\nAnswer in one sentence:"
        }
        
        try:
            # Call the async LLM client
            response = await llm_client.achat(
                model=model,
                messages=[system_message, user_message],
                reasoning=sel.get("reasoningEffort"),
                **(sel.get("params", {}) or {}),
            )
            print(response)
            # Extract the response content
            content = response.choices[0].message.content or ""
            # Clean up and ensure it's just one sentence
            content = content.strip()
            if content.endswith('.'):
                content = content[:-1]
            
            return {"answer": content}
            
        except Exception as e:
            return {"error": f"Failed to query preferences: {str(e)}"}

    return impl


def make_smart_recommendations(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """AI-powered recommendations via SubAgent using preferences and TMDb signals."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent

        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        # Get provider and API key from settings/config, not from args
        provider = (config.get("llm", {}) or {}).get("provider", "openai")
        api_key = settings.openai_api_key or (config.get("llm", {}) or {}).get("apiKey", "")

        sub_agent = SubAgent(api_key=api_key, project_root=project_root, provider=provider)
        try:
            seed_tmdb_id = args.get("seed_tmdb_id")
            seed_tmdb_id = int(seed_tmdb_id) if seed_tmdb_id is not None else None
            prompt = args.get("prompt")
            max_results = int(args.get("max_results", 3))
            media_type = str(args.get("media_type", "movie"))
            return await sub_agent.handle_smart_recommendations(
                seed_tmdb_id=seed_tmdb_id,
                prompt=prompt,
                max_results=max_results,
                media_type=media_type,
            )
        finally:
            # LLM client cleanup is handled automatically
            pass

    return impl


def make_intelligent_search(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Intelligent search that combines TMDb multi-search with Plex search via SubAgent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent

        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        # Get provider and API key from settings/config, not from args
        provider = (config.get("llm", {}) or {}).get("provider", "openai")
        api_key = settings.openai_api_key or (config.get("llm", {}) or {}).get("apiKey", "")

        sub_agent = SubAgent(api_key=api_key, project_root=project_root, provider=provider)
        try:
            query = str(args.get("query", "")).strip()
            limit = int(args.get("limit", 10))
            response_level = args.get("response_level")
            return await sub_agent.handle_intelligent_search(
                query=query,
                limit=limit,
                response_level=response_level,
            )
        finally:
            # LLM client cleanup is handled automatically
            pass

    return impl


def make_agent_early_terminate(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Allow the agent to signal early termination when it has sufficient information."""
    async def impl(args: dict) -> dict:
        try:
            reason = args.get("reason", "Agent determined sufficient information gathered")
            confidence = args.get("confidence", 0.8)
            summary = args.get("summary", "")
            
            # This is a special tool that signals the agent loop to terminate
            # The actual termination logic will be handled in the agent loop
            return {
                "ok": True,
                "termination_requested": True,
                "reason": reason,
                "confidence": confidence,
                "summary": summary,
                "message": f"Agent requests early termination: {reason}"
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return impl