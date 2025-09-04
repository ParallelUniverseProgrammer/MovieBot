from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import discord
import pytz


# =========================
# Logging
# =========================
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# =========================
# Limits
# =========================
class EmbedLimits:
    """Discord embed limits for compliance checking."""
    TITLE_MAX = 256
    DESCRIPTION_MAX = 4096
    FIELD_NAME_MAX = 256
    FIELD_VALUE_MAX = 1024
    FOOTER_MAX = 2048
    AUTHOR_NAME_MAX = 256
    TOTAL_CHARS_MAX = 6000
    MAX_FIELDS = 25
    MAX_EMBEDS = 10


# =========================
# Helpers
# =========================
class GenreMapper:
    """Maps TMDb genre IDs to human-readable names."""

    # TMDb genre mapping
    TMDB_GENRES = {
        28: "Action",
        12: "Adventure",
        16: "Animation",
        35: "Comedy",
        80: "Crime",
        99: "Documentary",
        18: "Drama",
        10751: "Family",
        14: "Fantasy",
        36: "History",
        27: "Horror",
        10402: "Music",
        9648: "Mystery",
        10749: "Romance",
        878: "Science Fiction",
        10770: "TV Movie",
        53: "Thriller",
        10752: "War",
        37: "Western",
    }

    @classmethod
    def map_genres(cls, genre_ids: List[int], max_genres: int = 3) -> str:
        """Map genre IDs to names, limiting to max_genres."""
        if not genre_ids:
            return "Unknown"

        genres = []
        for genre_id in genre_ids[:max_genres]:
            if genre_id in cls.TMDB_GENRES:
                genres.append(cls.TMDB_GENRES[genre_id])

        return ", ".join(genres) if genres else "Unknown"


class TextUtils:
    @staticmethod
    def strip_html(text: str) -> str:
        if not text:
            return text
        return re.sub(r"<.*?>", "", text)

    @staticmethod
    def normalize_ws(text: str) -> str:
        if not text:
            return text
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def human_join(items: List[str], max_items: int = 3) -> str:
        items = [i for i in items if i]
        if not items:
            return ""
        sliced = items[:max_items]
        return ", ".join(sliced)

    @staticmethod
    def format_money(value: Optional[Union[int, float]]) -> Optional[str]:
        if value is None or value == 0:
            return None
        try:
            return f"${int(value):,}"
        except Exception:
            return None

    @staticmethod
    def truncate(text: str, max_len: int, suffix: str = "...") -> str:
        if not text or len(text) <= max_len:
            return text
        return text[: max_len - len(suffix)] + suffix


class TimeUtils:
    @staticmethod
    def local_timestamp() -> datetime:
        try:
            local_tz = pytz.timezone("America/New_York")
            return datetime.now(local_tz)
        except Exception:
            return datetime.now()

    @staticmethod
    def parse_date(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except Exception:
                continue
        return None

    @staticmethod
    def format_date(date_obj: Optional[datetime]) -> Optional[str]:
        if not date_obj:
            return None
        try:
            return date_obj.strftime("%b %d, %Y")
        except Exception:
            return None

    @staticmethod
    def relative_date(date_obj: Optional[datetime]) -> Optional[str]:
        if not date_obj:
            return None
        now = datetime.utcnow()
        # Ensure naive comparison
        date_obj = date_obj.replace(tzinfo=None)
        delta = date_obj - now
        days = int(round(delta.total_seconds() / 86400.0))
        if days == 0:
            return "today"
        if days > 0:
            if days == 1:
                return "in 1 day"
            return f"in {days} days"
        days = abs(days)
        if days == 1:
            return "1 day ago"
        return f"{days} days ago"


class TMDBUtils:
    @staticmethod
    def tmdb_url(media_type: str, tmdb_id: Optional[Union[int, str]]) -> Optional[str]:
        if not tmdb_id:
            return None
        base = "https://www.themoviedb.org"
        if media_type.lower() == "tv":
            return f"{base}/tv/{tmdb_id}"
        return f"{base}/movie/{tmdb_id}"

    @staticmethod
    def tmdb_image(path: Optional[str], size: str = "w780") -> Optional[str]:
        if not path:
            return None
        if path.startswith("http"):
            return path
        return f"https://image.tmdb.org/t/p/{size}{path}"

    @staticmethod
    def youtube_url(video_key: Optional[str]) -> Optional[str]:
        if not video_key:
            return None
        return f"https://www.youtube.com/watch?v={video_key}"

    @staticmethod
    def extract_certification(movie_data: Dict[str, Any]) -> Optional[str]:
        # TMDb "release_dates" append_to_response structure
        rd = movie_data.get("release_dates") or movie_data.get("release_dates_results")
        if isinstance(rd, dict):
            results = rd.get("results", [])
        else:
            results = rd or []
        # Prefer US, else first non-empty
        target = None
        for entry in results:
            if entry.get("iso_3166_1") == "US":
                target = entry
                break
        if not target and results:
            target = results[0]
        if not target:
            # Fallback to content_rating key if provided directly
            fallback = movie_data.get("content_rating") or movie_data.get(
                "certification"
            )
            if fallback:
                return str(fallback)
            return None
        dates = target.get("release_dates", [])
        for d in dates:
            cert = d.get("certification")
            if cert:
                return cert
        return None

    @staticmethod
    def top_cast(movie_or_tv: Dict[str, Any], limit: int = 5) -> List[str]:
        credits = movie_or_tv.get("credits") or {}
        cast_list = credits.get("cast") or []
        names: List[str] = []
        for c in cast_list[:limit]:
            name = c.get("name")
            if name:
                names.append(name)
        return names

    @staticmethod
    def directors(movie_data: Dict[str, Any], limit: int = 2) -> List[str]:
        credits = movie_data.get("credits") or {}
        crew_list = credits.get("crew") or []
        names: List[str] = []
        for c in crew_list:
            if c.get("job") == "Director":
                nm = c.get("name")
                if nm and nm not in names:
                    names.append(nm)
        return names[:limit]

    @staticmethod
    def creators(tv_data: Dict[str, Any], limit: int = 3) -> List[str]:
        creators = tv_data.get("created_by") or []
        names = [c.get("name") for c in creators if c.get("name")]
        return names[:limit]

    @staticmethod
    def trailer_key(movie_or_tv: Dict[str, Any]) -> Optional[str]:
        videos = movie_or_tv.get("videos") or {}
        results = videos.get("results") if isinstance(videos, dict) else []
        if not results and isinstance(videos, list):
            results = videos
        # Prefer official YouTube Trailer
        for v in results or []:
            if (
                v.get("site") == "YouTube"
                and v.get("type") == "Trailer"
                and v.get("official", False)
            ):
                return v.get("key")
        for v in results or []:
            if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                return v.get("key")
        return None

    @staticmethod
    def watch_providers_text(
        data: Dict[str, Any], country_preference: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Returns a pretty string of watch providers and a link (if any).
        Accepts either TMDb append_to_response payload:
          { "watch/providers": { "results": {"US": {...}} } }
        or a flattened 'watch_providers': {"US": {...}} structure.
        """
        if country_preference is None:
            country_preference = ["US", "GB", "CA", "AU"]

        payload = data.get("watch/providers") or data.get("watch_providers") or {}
        results = payload.get("results") if isinstance(payload, dict) else {}
        if not results and isinstance(payload, dict):
            # Flattened form already country map
            results = payload

        region_key = None
        for c in country_preference:
            if c in results:
                region_key = c
                break
        if not region_key and isinstance(results, dict) and results:
            region_key = list(results.keys())[0]
        if not region_key:
            return None, None

        region = results.get(region_key, {})
        link = region.get("link")
        flatrate = [p.get("provider_name") for p in (region.get("flatrate") or [])]
        buy = [p.get("provider_name") for p in (region.get("buy") or [])]
        rent = [p.get("provider_name") for p in (region.get("rent") or [])]

        chunks: List[str] = []
        if flatrate:
            chunks.append(f"Stream: {TextUtils.human_join(flatrate, 5)}")
        if buy:
            chunks.append(f"Buy: {TextUtils.human_join(buy, 5)}")
        if rent:
            chunks.append(f"Rent: {TextUtils.human_join(rent, 5)}")

        if not chunks:
            return None, link
        return f"{' • '.join(chunks)} ({region_key})", link


class EmbedBuilder:
    """Reusable helpers for safe embed construction."""

    @staticmethod
    def safe_add_field(
        embed: discord.Embed,
        name: Optional[str],
        value: Optional[str],
        inline: bool = True,
    ) -> None:
        if not name or not value:
            return
        # Discord does not allow empty field values
        name = TextUtils.truncate(str(name), EmbedLimits.FIELD_NAME_MAX)
        value = TextUtils.truncate(str(value), EmbedLimits.FIELD_VALUE_MAX)
        try:
            embed.add_field(name=name, value=value, inline=inline)
        except Exception as e:
            logger.debug(f"Failed to add field {name}: {e}")

    @staticmethod
    def calc_total_chars(embed: discord.Embed) -> int:
        total = 0
        total += len(embed.title or "")
        total += len(embed.description or "")
        # Author and footer
        try:
            total += len(getattr(embed.author, "name", "") or "")
        except Exception:
            pass
        try:
            total += len(getattr(embed.footer, "text", "") or "")
        except Exception:
            pass
        for f in embed.fields:
            total += len(f.name or "") + len(f.value or "")
        return total


# =========================
# Main: MovieBotEmbeds
# =========================
class MovieBotEmbeds:
    """Rich embed utilities for MovieBot Discord responses with full Discord API compliance."""

    # Enhanced color palette with better contrast and visual appeal
    COLORS = {
        "movie": 0x00D4AA,  # Vibrant teal for movies
        "tv": 0x0099FF,  # Bright blue for TV shows
        "success": 0x00FF88,  # Success green
        "error": 0xFF4444,  # Error red
        "warning": 0xFFAA00,  # Warning orange
        "info": 0x00AAFF,  # Info blue
        "plex": 0xE5A00D,  # Plex orange
        "radarr": 0x264D73,  # Radarr blue
        "sonarr": 0x35C5F0,  # Sonarr cyan
        "tmdb": 0x01D277,  # TMDb green
        "premium": 0xFFD700,  # Gold for premium content
        "popular": 0xFF6B6B,  # Coral for popular content
        "new": 0x4ECDC4,  # Turquoise for new releases
    }

    # Status emojis for better visual feedback
    STATUS_EMOJIS = {
        "working": "⏳",
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
        "loading": "🔄",
        "complete": "🎉",
        "cancelled": "⏹️",
    }

    # Quality indicators
    QUALITY_EMOJIS = {
        "4K": "📺",
        "HDR": "✨",
        "Dolby Vision": "🎬",
        "Dolby Atmos": "🔊",
        "HD": "📱",
        "SD": "📺",
    }

    @staticmethod
    def _get_local_timestamp() -> datetime:
        """Get current local timestamp for Discord embeds."""
        return TimeUtils.local_timestamp()

    @staticmethod
    def _truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
        """Safely truncate text to fit Discord limits."""
        return TextUtils.truncate(text, max_length, suffix)

    @staticmethod
    def _validate_embed(embed: discord.Embed) -> discord.Embed:
        """Validate and fix embed to comply with Discord limits."""
        # Title and description
        if embed.title and len(embed.title) > EmbedLimits.TITLE_MAX:
            embed.title = TextUtils.truncate(embed.title, EmbedLimits.TITLE_MAX)

        if embed.description and len(embed.description) > EmbedLimits.DESCRIPTION_MAX:
            embed.description = TextUtils.truncate(
                embed.description, EmbedLimits.DESCRIPTION_MAX
            )

        # Footer
        try:
            footer_text = getattr(embed.footer, "text", None)
            if footer_text and len(footer_text) > EmbedLimits.FOOTER_MAX:
                embed.set_footer(
                    text=TextUtils.truncate(footer_text, EmbedLimits.FOOTER_MAX),
                    icon_url=getattr(embed.footer, "icon_url", discord.Embed.Empty),
                )
        except Exception:
            pass

        # Fields (limit and truncate values)
        if len(embed.fields) > EmbedLimits.MAX_FIELDS:
            trimmed = embed.fields[: EmbedLimits.MAX_FIELDS]
            # Rebuild fields to ensure we don't mutate proxies incorrectly
            old = embed
            embed = discord.Embed(
                title=old.title,
                description=old.description,
                color=old.color,
                timestamp=old.timestamp,
                url=old.url,
            )
            try:
                if getattr(old.author, "name", None):
                    embed.set_author(
                        name=old.author.name,
                        url=getattr(old.author, "url", discord.Embed.Empty),
                        icon_url=getattr(
                            old.author, "icon_url", discord.Embed.Empty
                        ),
                    )
            except Exception:
                pass
            try:
                if getattr(old.footer, "text", None):
                    embed.set_footer(
                        text=old.footer.text,
                        icon_url=getattr(
                            old.footer, "icon_url", discord.Embed.Empty
                        ),
                    )
            except Exception:
                pass
            # Re-add images
            try:
                if old.thumbnail and old.thumbnail.url:
                    embed.set_thumbnail(url=old.thumbnail.url)
            except Exception:
                pass
            try:
                if old.image and old.image.url:
                    embed.set_image(url=old.image.url)
            except Exception:
                pass

            # Re-add trimmed fields
            for f in trimmed:
                name = TextUtils.truncate(f.name or "", EmbedLimits.FIELD_NAME_MAX)
                value = TextUtils.truncate(f.value or "", EmbedLimits.FIELD_VALUE_MAX)
                try:
                    embed.add_field(name=name, value=value, inline=f.inline)
                except Exception:
                    continue

        # Truncate each field name/value
        fixed_fields: List[discord.EmbedProxy] = []
        if embed.fields:
            # Rebuild again to ensure safe truncation
            old = embed
            embed = discord.Embed(
                title=old.title,
                description=old.description,
                color=old.color,
                timestamp=old.timestamp,
                url=old.url,
            )
            try:
                if getattr(old.author, "name", None):
                    embed.set_author(
                        name=old.author.name,
                        url=getattr(old.author, "url", discord.Embed.Empty),
                        icon_url=getattr(
                            old.author, "icon_url", discord.Embed.Empty
                        ),
                    )
            except Exception:
                pass
            try:
                if getattr(old.footer, "text", None):
                    embed.set_footer(
                        text=old.footer.text,
                        icon_url=getattr(
                            old.footer, "icon_url", discord.Embed.Empty
                        ),
                    )
            except Exception:
                pass
            try:
                if old.thumbnail and old.thumbnail.url:
                    embed.set_thumbnail(url=old.thumbnail.url)
            except Exception:
                pass
            try:
                if old.image and old.image.url:
                    embed.set_image(url=old.image.url)
            except Exception:
                pass

            for f in old.fields:
                name = TextUtils.truncate(f.name or "", EmbedLimits.FIELD_NAME_MAX)
                value = TextUtils.truncate(f.value or "", EmbedLimits.FIELD_VALUE_MAX)
                if not name or not value:
                    continue
                try:
                    embed.add_field(name=name, value=value, inline=f.inline)
                except Exception:
                    continue

        # Ensure total char limit: if too long, trim from the end
        total = EmbedBuilder.calc_total_chars(embed)
        if total > EmbedLimits.TOTAL_CHARS_MAX:
            # Try reducing description first
            if embed.description:
                over_by = total - EmbedLimits.TOTAL_CHARS_MAX
                new_len = max(0, len(embed.description) - (over_by + 64))
                if new_len > 0:
                    embed.description = TextUtils.truncate(embed.description, new_len)
            # Recalc and trim fields from end if still too long
            total = EmbedBuilder.calc_total_chars(embed)
            while total > EmbedLimits.TOTAL_CHARS_MAX and embed.fields:
                # Remove the last field (least important)
                try:
                    embed._fields.pop()  # type: ignore
                except Exception:
                    # Rebuild without the last field
                    fields = embed.fields[:-1]
                    old = embed
                    embed = discord.Embed(
                        title=old.title,
                        description=old.description,
                        color=old.color,
                        timestamp=old.timestamp,
                        url=old.url,
                    )
                    try:
                        if getattr(old.author, "name", None):
                            embed.set_author(
                                name=old.author.name,
                                url=getattr(
                                    old.author, "url", discord.Embed.Empty
                                ),
                                icon_url=getattr(
                                    old.author,
                                    "icon_url",
                                    discord.Embed.Empty,
                                ),
                            )
                    except Exception:
                        pass
                    try:
                        if getattr(old.footer, "text", None):
                            embed.set_footer(
                                text=old.footer.text,
                                icon_url=getattr(
                                    old.footer,
                                    "icon_url",
                                    discord.Embed.Empty,
                                ),
                            )
                    except Exception:
                        pass
                    try:
                        if old.thumbnail and old.thumbnail.url:
                            embed.set_thumbnail(url=old.thumbnail.url)
                    except Exception:
                        pass
                    try:
                        if old.image and old.image.url:
                            embed.set_image(url=old.image.url)
                    except Exception:
                        pass
                    for f in fields:
                        embed.add_field(
                            name=f.name, value=f.value, inline=f.inline
                        )
                total = EmbedBuilder.calc_total_chars(embed)

        return embed

    @staticmethod
    def _format_rating(
        rating: Optional[Union[float, int]], vote_count: Optional[int] = None
    ) -> str:
        """Format rating with stars and vote count if available."""
        try:
            r = float(rating or 0.0)
        except Exception:
            r = 0.0
        if r <= 0:
            return "No rating"
        stars = "⭐" * max(1, min(5, int(round(r / 2))))
        rating_text = f"{stars} {r:.1f}/10"
        if vote_count and vote_count > 0:
            rating_text += f" ({vote_count:,} votes)"
        return rating_text

    @staticmethod
    def _format_runtime(runtime: Optional[int]) -> str:
        """Format runtime in minutes to hours and minutes."""
        if not runtime or runtime <= 0:
            return "Unknown"
        hours = runtime // 60
        minutes = runtime % 60
        if hours > 0:
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
        return f"{minutes}m"

    @staticmethod
    def _get_quality_indicators(media_data: Dict[str, Any]) -> List[str]:
        """Extract quality indicators from media data."""
        indicators = []

        # Check for 4K/HDR indicators in Plex or metadata-like dict
        if "videoResolution" in media_data:
            resolution = str(media_data["videoResolution"]).lower()
            if resolution == "4k" or resolution == "2160":
                indicators.append("4K")
            elif resolution in {"1080", "720", "sd"}:
                indicators.append("HD" if resolution != "sd" else "SD")

        if media_data.get("hasHDR") or any(
            "hdr" in str(media_data.get(k, "")).lower()
            for k in ("videoProfile", "videoDynamicRange")
        ):
            indicators.append("HDR")

        # Check Dolby Vision/Atmos
        if "videoCodec" in media_data:
            codec = str(media_data["videoCodec"]).lower()
            if "dolby" in codec and "vision" in codec:
                indicators.append("Dolby Vision")

        if "audioCodec" in media_data:
            acodec = str(media_data["audioCodec"]).lower()
            if "dolby" in acodec and "atmos" in acodec:
                indicators.append("Dolby Atmos")

        return indicators

    @staticmethod
    def _compose_description(
        tagline: Optional[str], overview: Optional[str]
    ) -> str:
        lines: List[str] = []
        if tagline:
            tagline = TextUtils.normalize_ws(tagline)
            lines.append(f"“{tagline}”")
        if overview:
            clean = TextUtils.normalize_ws(TextUtils.strip_html(overview))
            lines.append(clean)
        return "\n\n".join([l for l in lines if l])

    @staticmethod
    def create_movie_embed(
        movie_data: Dict[str, Any], include_actions: bool = False
    ) -> discord.Embed:
        """Create a rich embed for a movie with comprehensive metadata."""
        # Extract basic info
        title = (
            movie_data.get("title")
            or movie_data.get("original_title")
            or "Unknown Movie"
        )
        year = (
            movie_data.get("release_date", "????")[:4]
            if movie_data.get("release_date")
            else "????"
        )
        overview = movie_data.get("overview") or "No description available"
        tagline = movie_data.get("tagline") or None
        rating = movie_data.get("vote_average", 0)
        vote_count = movie_data.get("vote_count", 0)
        poster_path = movie_data.get("poster_path")
        backdrop_path = movie_data.get("backdrop_path")
        tmdb_id = movie_data.get("id", "N/A")
        runtime = movie_data.get("runtime")
        genres = movie_data.get("genres", [])
        genre_ids = movie_data.get("genre_ids", [])
        popularity = movie_data.get("popularity", 0)
        original_language = movie_data.get("original_language", "en")
        status = movie_data.get("status", None)
        budget = movie_data.get("budget")
        revenue = movie_data.get("revenue")
        belongs_to_collection = movie_data.get("belongs_to_collection")
        external_ids = movie_data.get("external_ids") or {}
        imdb_id = external_ids.get("imdb_id") or movie_data.get("imdb_id")
        spoken_languages = movie_data.get("spoken_languages") or []
        production_companies = movie_data.get("production_companies") or []
        production_countries = movie_data.get("production_countries") or []

        # Build description: tagline + overview
        description = MovieBotEmbeds._compose_description(tagline, overview)
        description = MovieBotEmbeds._truncate_text(description, 1000)

        # Create embed with proper title formatting
        embed_title = f"🎬 {title} ({year})"
        embed = discord.Embed(
            title=embed_title,
            description=description,
            color=MovieBotEmbeds.COLORS["movie"],
            timestamp=MovieBotEmbeds._get_local_timestamp(),
            url=TMDBUtils.tmdb_url("movie", tmdb_id),
        )

        # Thumbnail and image
        poster_url = TMDBUtils.tmdb_image(poster_path, size="w500")
        if poster_url:
            embed.set_thumbnail(url=poster_url)
        backdrop_url = TMDBUtils.tmdb_image(backdrop_path, size="w1280")
        if backdrop_url:
            embed.set_image(url=backdrop_url)

        # Rating
        EmbedBuilder.safe_add_field(
            embed, "⭐ Rating", MovieBotEmbeds._format_rating(rating, vote_count), True
        )

        # Runtime
        if runtime:
            EmbedBuilder.safe_add_field(
                embed, "⏱️ Runtime", MovieBotEmbeds._format_runtime(runtime), True
            )

        # Release info
        release_date = TimeUtils.parse_date(movie_data.get("release_date"))
        release_text_parts: List[str] = []
        pretty_date = TimeUtils.format_date(release_date)
        rel_rel = TimeUtils.relative_date(release_date)
        if pretty_date:
            release_text_parts.append(pretty_date)
        if status:
            release_text_parts.append(status)
        if rel_rel:
            release_text_parts.append(f"({rel_rel})")
        cert = TMDBUtils.extract_certification(movie_data)
        if cert:
            release_text_parts.append(f"Rated {cert}")
        if release_text_parts:
            EmbedBuilder.safe_add_field(
                embed, "🗓 Release", " • ".join(release_text_parts), True
            )

        # Genres
        if genres:
            genre_names = [
                g.get("name", "") for g in genres if isinstance(g, dict) and g.get("name")
            ]
            genre_text = ", ".join(genre_names[:3]) if genre_names else "Unknown"
        elif genre_ids:
            genre_text = GenreMapper.map_genres(genre_ids)
        else:
            genre_text = "Unknown"
        EmbedBuilder.safe_add_field(embed, "🎭 Genres", genre_text, True)

        # Directors and Cast
        directors = TMDBUtils.directors(movie_data)
        if directors:
            EmbedBuilder.safe_add_field(
                embed, "🎬 Director", TextUtils.human_join(directors, 2), True
            )

        cast_names = TMDBUtils.top_cast(movie_data, limit=5)
        if cast_names:
            EmbedBuilder.safe_add_field(
                embed, "👥 Cast", TextUtils.human_join(cast_names, 5), False
            )

        # Language(s)
        if original_language:
            langs = []
            orig = original_language.upper()
            langs.append(f"Original: {orig}")
            sl = [
                l.get("english_name") or l.get("name")
                for l in spoken_languages
                if isinstance(l, dict)
            ]
            if sl:
                langs.append(f"Spoken: {TextUtils.human_join(sl, 4)}")
            EmbedBuilder.safe_add_field(
                embed, "🌍 Language", " • ".join(langs), True
            )

        # Popularity
        try:
            pop = float(popularity)
            if pop > 0:
                flame = "🔥" if pop >= 100 else "📈"
                EmbedBuilder.safe_add_field(
                    embed, "Popularity", f"{flame} {pop:.0f}", True
                )
        except Exception:
            pass

        # Budget/Revenue
        money_bits: List[str] = []
        btxt = TextUtils.format_money(budget)
        rtxt = TextUtils.format_money(revenue)
        if btxt:
            money_bits.append(f"Budget: {btxt}")
        if rtxt:
            money_bits.append(f"Revenue: {rtxt}")
        if btxt and rtxt:
            try:
                profit = int(revenue) - int(budget)
                ptxt = TextUtils.format_money(profit)
                if ptxt:
                    arrow = "📈" if profit >= 0 else "📉"
                    money_bits.append(f"Profit: {arrow} {ptxt}")
            except Exception:
                pass
        if money_bits:
            EmbedBuilder.safe_add_field(
                embed, "💰 Box Office", " • ".join(money_bits), False
            )

        # Companies and Countries
        if production_companies:
            pc_names = [
                pc.get("name") for pc in production_companies if pc.get("name")
            ]
            if pc_names:
                EmbedBuilder.safe_add_field(
                    embed, "🏢 Companies", TextUtils.human_join(pc_names, 3), True
                )
        if production_countries:
            c_names = [
                c.get("iso_3166_1") or c.get("name")
                for c in production_countries
                if (c.get("iso_3166_1") or c.get("name"))
            ]
            if c_names:
                EmbedBuilder.safe_add_field(
                    embed, "🌎 Countries", TextUtils.human_join(c_names, 3), True
                )

        # Collection
        if isinstance(belongs_to_collection, dict):
            col_name = belongs_to_collection.get("name")
            if col_name:
                EmbedBuilder.safe_add_field(
                    embed, "🧩 Collection", col_name, True
                )

        # Watch providers
        wp_text, wp_link = TMDBUtils.watch_providers_text(movie_data)
        if wp_text:
            if wp_link:
                EmbedBuilder.safe_add_field(
                    embed, "📺 Where to Watch", f"{wp_text}\n{wp_link}", False
                )
            else:
                EmbedBuilder.safe_add_field(
                    embed, "📺 Where to Watch", wp_text, False
                )

        # Links
        links: List[str] = []
        tmdb_link = TMDBUtils.tmdb_url("movie", tmdb_id)
        if tmdb_link:
            links.append(f"[TMDb]({tmdb_link})")
        if imdb_id:
            links.append(f"[IMDb](https://www.imdb.com/title/{imdb_id}/)")
        if links:
            EmbedBuilder.safe_add_field(embed, "🔗 Links", " • ".join(links), True)

        # TMDb ID (retain original compatibility)
        EmbedBuilder.safe_add_field(embed, "🆔 TMDb ID", str(tmdb_id), True)

        # Quality (if provided from upstream metadata)
        quality_indicators = MovieBotEmbeds._get_quality_indicators(movie_data)
        if quality_indicators:
            quality_text = " ".join(
                [MovieBotEmbeds.QUALITY_EMOJIS.get(q, q) for q in quality_indicators]
            )
            EmbedBuilder.safe_add_field(embed, "✨ Quality", quality_text, True)

        # Footer with TMDb branding
        embed.set_footer(
            text="Powered by TMDb",
            icon_url=(
                "https://www.themoviedb.org/assets/2/v4/logos/v2/"
                "blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82"
                "bb2cd95f6c.svg"
            ),
        )

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_tv_embed(
        tv_data: Dict[str, Any], include_actions: bool = False
    ) -> discord.Embed:
        """Create a rich embed for a TV show with comprehensive metadata."""
        # Extract basic info
        title = tv_data.get("name") or tv_data.get("original_name") or "Unknown Show"
        year = (
            tv_data.get("first_air_date", "????")[:4]
            if tv_data.get("first_air_date")
            else "????"
        )
        overview = tv_data.get("overview") or "No description available"
        tagline = tv_data.get("tagline") or None
        rating = tv_data.get("vote_average", 0)
        vote_count = tv_data.get("vote_count", 0)
        poster_path = tv_data.get("poster_path")
        backdrop_path = tv_data.get("backdrop_path")
        tmdb_id = tv_data.get("id", "N/A")
        genres = tv_data.get("genres", [])
        genre_ids = tv_data.get("genre_ids", [])
        popularity = tv_data.get("popularity", 0)
        original_language = tv_data.get("original_language", "en")
        episode_run_time = tv_data.get("episode_run_time", [])
        number_of_seasons = tv_data.get("number_of_seasons", 0)
        number_of_episodes = tv_data.get("number_of_episodes", 0)
        status = tv_data.get("status", "Unknown")
        networks = tv_data.get("networks", [])
        next_ep = tv_data.get("next_episode_to_air")
        last_air_date = tv_data.get("last_air_date")
        external_ids = tv_data.get("external_ids") or {}
        imdb_id = external_ids.get("imdb_id") or tv_data.get("imdb_id")

        # Build description
        description = MovieBotEmbeds._compose_description(tagline, overview)
        description = MovieBotEmbeds._truncate_text(description, 1000)

        # Create embed
        embed_title = f"📺 {title} ({year})"
        embed = discord.Embed(
            title=embed_title,
            description=description,
            color=MovieBotEmbeds.COLORS["tv"],
            timestamp=MovieBotEmbeds._get_local_timestamp(),
            url=TMDBUtils.tmdb_url("tv", tmdb_id),
        )

        # Images
        poster_url = TMDBUtils.tmdb_image(poster_path, size="w500")
        if poster_url:
            embed.set_thumbnail(url=poster_url)
        backdrop_url = TMDBUtils.tmdb_image(backdrop_path, size="w1280")
        if backdrop_url:
            embed.set_image(url=backdrop_url)

        # Rating
        EmbedBuilder.safe_add_field(
            embed, "⭐ Rating", MovieBotEmbeds._format_rating(rating, vote_count), True
        )

        # Episode runtime
        if episode_run_time:
            avg_runtime = int(sum(episode_run_time) / len(episode_run_time))
            EmbedBuilder.safe_add_field(
                embed,
                "⏱️ Episode Runtime",
                MovieBotEmbeds._format_runtime(avg_runtime),
                True,
            )

        # Series info (seasons/episodes)
        if number_of_seasons > 0 or number_of_episodes > 0:
            seasons_text = f"{number_of_seasons} season{'s' if number_of_seasons != 1 else ''}"
            episodes_text = (
                f"{number_of_episodes} episode{'s' if number_of_episodes != 1 else ''}"
            )
            EmbedBuilder.safe_add_field(
                embed,
                "📊 Series Info",
                f"{seasons_text}\n{episodes_text}",
                True,
            )

        # Status and next episode
        if status and status != "Unknown":
            status_emoji = (
                "🟢"
                if status.lower() in ("returning series", "in production")
                else "🔴"
                if status.lower() in ("ended", "canceled")
                else "🟡"
            )
            status_text = f"{status_emoji} {status}"
            if next_ep and next_ep.get("air_date"):
                nd = TimeUtils.parse_date(next_ep.get("air_date"))
                pretty = TimeUtils.format_date(nd)
                rel = TimeUtils.relative_date(nd)
                ep_s = next_ep.get("season_number")
                ep_e = next_ep.get("episode_number")
                status_text += f"\nNext: S{ep_s:02}E{ep_e:02} – {pretty} ({rel})"
            elif last_air_date:
                ld = TimeUtils.parse_date(last_air_date)
                pretty = TimeUtils.format_date(ld)
                rel = TimeUtils.relative_date(ld)
                if pretty:
                    status_text += f"\nLast Aired: {pretty} ({rel})"
            EmbedBuilder.safe_add_field(embed, "📡 Status", status_text, True)

        # Creators
        creators = TMDBUtils.creators(tv_data, limit=3)
        if creators:
            EmbedBuilder.safe_add_field(
                embed, "🧠 Creator(s)", TextUtils.human_join(creators, 3), True
            )

        # Genres
        if genres:
            genre_names = [
                g.get("name", "") for g in genres if isinstance(g, dict) and g.get("name")
            ]
            genre_text = ", ".join(genre_names[:3]) if genre_names else "Unknown"
        elif genre_ids:
            genre_text = GenreMapper.map_genres(genre_ids)
        else:
            genre_text = "Unknown"
        EmbedBuilder.safe_add_field(embed, "🎭 Genres", genre_text, True)

        # Networks
        if networks:
            net_names = [n.get("name") for n in networks if n.get("name")]
            if net_names:
                EmbedBuilder.safe_add_field(
                    embed, "🛰 Networks", TextUtils.human_join(net_names, 3), True
                )

        # Popularity
        try:
            pop = float(popularity)
            if pop > 0:
                flame = "🔥" if pop >= 100 else "📈"
                EmbedBuilder.safe_add_field(
                    embed, "Popularity", f"{flame} {pop:.0f}", True
                )
        except Exception:
            pass

        # Watch providers
        wp_text, wp_link = TMDBUtils.watch_providers_text(tv_data)
        if wp_text:
            if wp_link:
                EmbedBuilder.safe_add_field(
                    embed, "📺 Where to Watch", f"{wp_text}\n{wp_link}", False
                )
            else:
                EmbedBuilder.safe_add_field(
                    embed, "📺 Where to Watch", wp_text, False
                )

        # Links
        links: List[str] = []
        tmdb_link = TMDBUtils.tmdb_url("tv", tmdb_id)
        if tmdb_link:
            links.append(f"[TMDb]({tmdb_link})")
        if imdb_id:
            links.append(f"[IMDb](https://www.imdb.com/title/{imdb_id}/)")
        if links:
            EmbedBuilder.safe_add_field(embed, "🔗 Links", " • ".join(links), True)

        # TMDb ID
        EmbedBuilder.safe_add_field(embed, "🆔 TMDb ID", str(tmdb_id), True)

        # Quality indicators (if present from upstream)
        quality_indicators = MovieBotEmbeds._get_quality_indicators(tv_data)
        if quality_indicators:
            quality_text = " ".join(
                [MovieBotEmbeds.QUALITY_EMOJIS.get(q, q) for q in quality_indicators]
            )
            EmbedBuilder.safe_add_field(embed, "✨ Quality", quality_text, True)

        # Footer
        embed.set_footer(
            text="Powered by TMDb",
            icon_url=(
                "https://www.themoviedb.org/assets/2/v4/logos/v2/"
                "blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82"
                "bb2cd95f6c.svg"
            ),
        )

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def _resolve_plex_url(plex_base_url: Optional[str], path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        if str(path).startswith("http"):
            return path
        if not plex_base_url:
            return path
        return plex_base_url.rstrip("/") + "/" + str(path).lstrip("/")

    @staticmethod
    def create_plex_media_embed(
        media_data: Any, media_type: str = "movie", plex_base_url: str = None
    ) -> discord.Embed:
        """Create a rich embed for Plex media with proper thumbnail URL construction."""
        # Extract basic info using getattr for safety
        title = getattr(media_data, "title", "Unknown")
        year = getattr(media_data, "year", "????")
        summary = getattr(media_data, "summary", "No description available")
        rating = getattr(media_data, "rating", 0)
        thumb = getattr(media_data, "thumb", None)
        art = getattr(media_data, "art", None)
        rating_key = getattr(media_data, "ratingKey", "N/A")
        duration = getattr(media_data, "duration", None)
        genres = getattr(media_data, "genres", [])
        studio = getattr(media_data, "studio", None)
        content_rating = getattr(media_data, "contentRating", None)
        view_count = getattr(media_data, "viewCount", 0)
        last_viewed_at = getattr(media_data, "lastViewedAt", None)

        # Additional media tracks/meta if present for quality indicators
        media_info = getattr(media_data, "media", None)
        extra_meta: Dict[str, Any] = {}
        try:
            # Best-effort extraction
            # Some libraries expose .media[0].videoResolution, .audioCodec, etc.
            if isinstance(media_info, list) and media_info:
                m0 = media_info[0]
                extra_meta["videoResolution"] = getattr(m0, "videoResolution", None)
                extra_meta["audioCodec"] = getattr(m0, "audioCodec", None)
                extra_meta["videoCodec"] = getattr(m0, "videoCodec", None)
                extra_meta["hasHDR"] = (
                    "hdr" in str(getattr(m0, "videoDynamicRange", "")).lower()
                )
        except Exception:
            pass

        # Truncate summary to fit Discord limits
        summary = MovieBotEmbeds._truncate_text(summary, 1000)

        # Determine color based on media type
        color = MovieBotEmbeds.COLORS.get(media_type.lower(), MovieBotEmbeds.COLORS["plex"])

        # Create embed
        media_emoji = "🎬" if media_type.lower() == "movie" else "📺"
        embed_title = f"{media_emoji} {title} ({year})"
        embed = discord.Embed(
            title=embed_title,
            description=summary,
            color=color,
            timestamp=MovieBotEmbeds._get_local_timestamp(),
        )

        # Add thumbnail and backdrop using robust URL resolution
        thumb_url = MovieBotEmbeds._resolve_plex_url(plex_base_url, thumb)
        if thumb_url:
            embed.set_thumbnail(url=thumb_url)
        art_url = MovieBotEmbeds._resolve_plex_url(plex_base_url, art)
        if art_url:
            embed.set_image(url=art_url)

        # Add rating if available
        if rating and float(rating) > 0:
            EmbedBuilder.safe_add_field(
                embed, "⭐ Rating", MovieBotEmbeds._format_rating(rating), True
            )

        # Add duration if available
        if duration:
            duration_minutes = int(duration) // 60000  # Convert from ms
            EmbedBuilder.safe_add_field(
                embed,
                "⏱️ Duration",
                MovieBotEmbeds._format_runtime(duration_minutes),
                True,
            )

        # Add genres if available
        if genres:
            # genres may be list of objects with .tag
            try:
                if hasattr(genres[0], "tag"):
                    genre_names = [g.tag for g in genres]
                else:
                    genre_names = [str(g) for g in genres]
            except Exception:
                genre_names = []
            genre_text = ", ".join(genre_names[:3]) if genre_names else "Unknown"
            EmbedBuilder.safe_add_field(embed, "🎭 Genres", genre_text, True)

        # Studio
        if studio:
            EmbedBuilder.safe_add_field(embed, "🏢 Studio", studio, True)

        # Content rating
        if content_rating:
            EmbedBuilder.safe_add_field(
                embed, "🔞 Content Rating", content_rating, True
            )

        # Views
        if view_count and int(view_count) > 0:
            EmbedBuilder.safe_add_field(
                embed, "👀 Views", f"{int(view_count)}", True
            )

        # Plex ID
        EmbedBuilder.safe_add_field(embed, "🔗 Plex ID", str(rating_key), True)

        # Last viewed
        if last_viewed_at:
            try:
                last_viewed = datetime.fromtimestamp(last_viewed_at / 1000)
                EmbedBuilder.safe_add_field(
                    embed, "🕒 Last Viewed", last_viewed.strftime("%Y-%m-%d"), True
                )
            except (ValueError, OSError):
                pass

        # Quality indicators if deduced
        q_meta = {
            k: v
            for k, v in extra_meta.items()
            if k in ("videoResolution", "audioCodec", "videoCodec", "hasHDR")
        }
        quality_indicators = MovieBotEmbeds._get_quality_indicators(q_meta)
        if quality_indicators:
            quality_text = " ".join(
                [MovieBotEmbeds.QUALITY_EMOJIS.get(q, q) for q in quality_indicators]
            )
            EmbedBuilder.safe_add_field(embed, "✨ Quality", quality_text, True)

        # Footer with Plex branding
        embed.set_footer(
            text="From your Plex library",
            icon_url="https://www.plex.tv/wp-content/themes/plex/assets/img/plex-logo.svg",
        )

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_progress_embed(
        title: str,
        description: str,
        progress: float = 0.0,
        status: str = "working",
        details: str = "",
        tool_name: str = None,
    ) -> discord.Embed:
        """Create an enhanced progress indicator embed."""
        # Choose color based on status
        color_map = {
            "working": MovieBotEmbeds.COLORS["info"],
            "success": MovieBotEmbeds.COLORS["success"],
            "error": MovieBotEmbeds.COLORS["error"],
            "warning": MovieBotEmbeds.COLORS["warning"],
            "loading": MovieBotEmbeds.COLORS["info"],
            "complete": MovieBotEmbeds.COLORS["success"],
            "cancelled": MovieBotEmbeds.COLORS["warning"],
        }

        # Truncate description
        description = MovieBotEmbeds._truncate_text(description, 2000)

        embed = discord.Embed(
            title=f"{MovieBotEmbeds.STATUS_EMOJIS.get(status, '⏳')} {title}",
            description=description,
            color=color_map.get(status, MovieBotEmbeds.COLORS["info"]),
            timestamp=MovieBotEmbeds._get_local_timestamp(),
        )

        # Progress bar
        if 0 <= progress <= 1:
            bar_length = 14
            filled_length = int(bar_length * progress)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            progress_emoji = (
                "🔄" if status in ("working", "loading") else "✅" if status == "success" else "❌"
            )
            progress_text = f"{progress_emoji} `{bar}` {progress:.1%}"
            EmbedBuilder.safe_add_field(embed, "Progress", progress_text, False)

        # Tool
        if tool_name:
            EmbedBuilder.safe_add_field(embed, "🔧 Tool", tool_name, True)

        # Status
        status_emoji = MovieBotEmbeds.STATUS_EMOJIS.get(status, "⏳")
        status_text = f"{status_emoji} {status.title()}"
        EmbedBuilder.safe_add_field(embed, "Status", status_text, True)

        # Details
        if details:
            details = MovieBotEmbeds._truncate_text(details, 500)
            EmbedBuilder.safe_add_field(embed, "Details", details, False)

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_search_results_embed(
        results: List[Dict[str, Any]], query: str, result_type: str = "movie"
    ) -> discord.Embed:
        """Create an enhanced embed for search results with better formatting."""
        result_count = len(results)
        result_type_l = (result_type or "").lower()
        if result_type_l == "movie":
            result_emoji = "🎬"
            color = MovieBotEmbeds.COLORS["movie"]
        elif result_type_l == "tv":
            result_emoji = "📺"
            color = MovieBotEmbeds.COLORS["tv"]
        else:
            result_emoji = "🔍"
            color = MovieBotEmbeds.COLORS["info"]

        embed = discord.Embed(
            title=f"{result_emoji} Results for “{query}”",
            description=f"Found {result_count} {result_type_l if result_type_l else 'result'}"
            f"{'' if result_count == 1 else 's'}",
            color=color,
            timestamp=MovieBotEmbeds._get_local_timestamp(),
        )

        # Add top results (limit to 8)
        for i, result in enumerate(results[:8]):
            media_type = result.get("media_type", result_type_l)
            title = result.get("title") or result.get("name") or "Unknown"
            date_key = (
                "release_date" if media_type == "movie" else "first_air_date"
            )
            year = (
                (result.get(date_key) or "????")[:4]
                if result.get(date_key)
                else "????"
            )
            rating = result.get("vote_average", 0.0) or 0.0
            tmdb_id = result.get("id", "N/A")
            poster_path = result.get("poster_path")
            tmdb_link = TMDBUtils.tmdb_url(
                "movie" if media_type == "movie" else "tv", tmdb_id
            )
            poster = TMDBUtils.tmdb_image(poster_path, "w342")

            rating_txt = f"{float(rating):.1f}/10"
            parts = [f"⭐ {rating_txt}", f"ID: {tmdb_id}"]
            if poster:
                parts.append(f"[Poster]({poster})")
            if tmdb_link:
                parts.append(f"[TMDb]({tmdb_link})")
            value = " | ".join(parts)

            embed.add_field(
                name=f"{i + 1}. {title} ({year})",
                value=value,
                inline=False,
            )

        # Footer
        if result_count > 8:
            embed.set_footer(
                text=f"Showing first 8 of {result_count} • Refine your search for more precise results"
            )
        else:
            embed.set_footer(
                text="Powered by TMDb",
                icon_url=(
                    "https://www.themoviedb.org/assets/2/v4/logos/v2/"
                    "blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82"
                    "bb2cd95f6c.svg"
                ),
            )

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_system_status_embed(status_data: Dict[str, Any]) -> discord.Embed:
        """Create an enhanced embed for system status."""
        embed = discord.Embed(
            title="🖥️ System Status",
            color=MovieBotEmbeds.COLORS["info"],
            timestamp=MovieBotEmbeds._get_local_timestamp(),
        )

        # Add service status with enhanced formatting
        for service, data in status_data.items():
            if not isinstance(data, dict):
                continue
            status = str(data.get("status", "unknown")).lower()
            emoji = "✅" if status in ("ok", "healthy", "up") else "❌" if status in ("error", "down") else "⚠️"
            response_time = data.get("response_time", None)
            uptime = data.get("uptime", None)
            version = data.get("version", None)

            parts: List[str] = [f"{emoji} {status.title()}"]
            if response_time not in (None, "N/A"):
                parts.append(f"{response_time}ms")
            if uptime:
                parts.append(f"uptime: {uptime}")
            if version:
                parts.append(f"v{version}")

            EmbedBuilder.safe_add_field(
                embed, service.title(), " • ".join(parts), True
            )

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_error_embed(
        title: str, error_message: str, error_type: str = "error", suggestion: str = None
    ) -> discord.Embed:
        """Create an enhanced error embed with suggestions."""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=error_message,
            color=MovieBotEmbeds.COLORS["error"],
            timestamp=MovieBotEmbeds._get_local_timestamp(),
        )

        # Add suggestion if provided
        if suggestion:
            EmbedBuilder.safe_add_field(
                embed, "💡 Suggestion", suggestion, False
            )

        embed.set_footer(
            text="If this persists, check configuration or contact support"
        )

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_success_embed(
        title: str, message: str, action: str = None
    ) -> discord.Embed:
        """Create an enhanced success embed."""
        embed = discord.Embed(
            title=f"✅ {title}",
            description=message,
            color=MovieBotEmbeds.COLORS["success"],
            timestamp=MovieBotEmbeds._get_local_timestamp(),
        )

        if action:
            EmbedBuilder.safe_add_field(
                embed, "Action Completed", action, False
            )

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_collection_embed(
        collection_data: Dict[str, Any], items: List[Dict[str, Any]] = None
    ) -> discord.Embed:
        """Create an embed for a collection or playlist."""
        title = collection_data.get("title", "Unknown Collection")
        summary = collection_data.get("summary", "No description available")
        count = collection_data.get("count", 0)
        collection_type = collection_data.get("type", "collection")
        poster_path = collection_data.get("poster_path")
        backdrop_path = collection_data.get("backdrop_path")

        # Truncate summary
        summary = MovieBotEmbeds._truncate_text(summary, 1000)

        # Choose emoji and color based on type
        if str(collection_type).lower() == "playlist":
            emoji = "📋"
            color = MovieBotEmbeds.COLORS["info"]
        else:
            emoji = "📚"
            color = MovieBotEmbeds.COLORS["plex"]

        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=summary,
            color=color,
            timestamp=MovieBotEmbeds._get_local_timestamp(),
        )

        # Images (if TMDb-like paths provided)
        poster_url = TMDBUtils.tmdb_image(poster_path, "w500")
        if poster_url:
            embed.set_thumbnail(url=poster_url)
        backdrop_url = TMDBUtils.tmdb_image(backdrop_path, "w1280")
        if backdrop_url:
            embed.set_image(url=backdrop_url)

        # Add item count
        EmbedBuilder.safe_add_field(embed, "📊 Items", f"{count} items", True)

        # Add sample items if provided
        if items and len(items) > 0:
            sample_items = items[:5]  # Show first 5 items
            item_list = []
            for item in sample_items:
                item_title = item.get("title", "Unknown")
                item_year = item.get("year", "")
                year_text = f" ({item_year})" if item_year else ""
                item_list.append(f"• {item_title}{year_text}")

            items_text = "\n".join(item_list)
            if len(items) > 5:
                items_text += f"\n• ... and {len(items) - 5} more"

            EmbedBuilder.safe_add_field(
                embed, "📝 Sample Items", items_text, False
            )

        return MovieBotEmbeds._validate_embed(embed)


# =========================
# Progress Views
# =========================
class ProgressIndicator:
    """Enhanced progress indicator utilities for Discord."""

    @staticmethod
    def create_progress_view(
        interaction: discord.Interaction, timeout: int = 300
    ) -> discord.ui.View:
        """Create a view with enhanced progress indicators and controls."""
        view = discord.ui.View(timeout=timeout)

        # Stop button
        stop_button = discord.ui.Button(
            label="Stop Operation",
            style=discord.ButtonStyle.danger,
            emoji="⏹️",
            custom_id="stop_operation",
        )

        async def stop_callback(interaction: discord.Interaction):
            try:
                await interaction.response.edit_message(
                    content="🛑 Operation cancelled by user.",
                    view=None,
                    embed=None,
                )
            except Exception as e:
                logger.debug(f"Stop callback edit_message failed: {e}")

        stop_button.callback = stop_callback
        view.add_item(stop_button)

        # Refresh button
        refresh_button = discord.ui.Button(
            label="Refresh Status",
            style=discord.ButtonStyle.secondary,
            emoji="🔄",
            custom_id="refresh_status",
        )

        async def refresh_callback(interaction: discord.Interaction):
            # Implement your actual refresh logic elsewhere
            try:
                await interaction.response.send_message(
                    "Status refreshed!", ephemeral=True
                )
            except Exception as e:
                logger.debug(f"Refresh callback send_message failed: {e}")

        refresh_button.callback = refresh_callback
        view.add_item(refresh_button)

        return view

    @staticmethod
    def update_progress_embed(
        embed: discord.Embed,
        progress: float,
        status: str = "working",
        details: str = "",
        tool_name: str = None,
    ) -> discord.Embed:
        """Update an existing progress embed with enhanced formatting."""
        try:
            embed.clear_fields()
        except Exception:
            # In rare cases, clear_fields might not exist; rebuild instead
            old = embed
            embed = discord.Embed(
                title=old.title,
                description=old.description,
                color=old.color,
                timestamp=old.timestamp,
                url=old.url,
            )
            try:
                if getattr(old.author, "name", None):
                    embed.set_author(
                        name=old.author.name,
                        url=getattr(old.author, "url", discord.Embed.Empty),
                        icon_url=getattr(
                            old.author, "icon_url", discord.Embed.Empty
                        ),
                    )
            except Exception:
                pass
            try:
                if getattr(old.footer, "text", None):
                    embed.set_footer(
                        text=old.footer.text,
                        icon_url=getattr(
                            old.footer, "icon_url", discord.Embed.Empty
                        ),
                    )
            except Exception:
                pass
            try:
                if old.thumbnail and old.thumbnail.url:
                    embed.set_thumbnail(url=old.thumbnail.url)
            except Exception:
                pass
            try:
                if old.image and old.image.url:
                    embed.set_image(url=old.image.url)
            except Exception:
                pass

        # Progress bar
        if 0 <= progress <= 1:
            bar_length = 14
            filled_length = int(bar_length * progress)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            progress_emoji = (
                "🔄" if status in ("working", "loading") else "✅" if status == "success" else "❌"
            )
            progress_text = f"{progress_emoji} `{bar}` {progress:.1%}"
            EmbedBuilder.safe_add_field(embed, "Progress", progress_text, False)

        # Tool
        if tool_name:
            EmbedBuilder.safe_add_field(embed, "🔧 Tool", tool_name, True)

        # Status
        status_emoji = MovieBotEmbeds.STATUS_EMOJIS.get(status, "⏳")
        status_text = f"{status_emoji} {status.title()}"
        EmbedBuilder.safe_add_field(embed, "Status", status_text, True)

        # Details
        if details:
            details = MovieBotEmbeds._truncate_text(details, 500)
            EmbedBuilder.safe_add_field(embed, "Details", details, False)

        return MovieBotEmbeds._validate_embed(embed)

    @staticmethod
    def create_loading_embed(
        title: str, description: str, tool_name: str = None
    ) -> discord.Embed:
        """Create a loading embed with animated progress."""
        return MovieBotEmbeds.create_progress_embed(
            title=title,
            description=description,
            progress=0.0,
            status="loading",
            tool_name=tool_name,
        )