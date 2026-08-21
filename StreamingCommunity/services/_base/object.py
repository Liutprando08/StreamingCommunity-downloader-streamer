# 23.11.24

from __future__ import annotations

import difflib
from datetime import UTC, datetime
from typing import Any

# Internal utilities
from StreamingCommunity.utils import config_manager, tmdb_client

# Variable
TMDB_KEY = config_manager.login.get("TMDB", "api_key", default="")


class Episode:
    def __init__(
        self,
        id: Any | None = None,
        video_id: str | None = None,
        number: Any | None = None,
        name: str | None = None,
        duration: Any | None = None,
        url: str | None = None,
        mpd_id: str | None = None,
        channel: str | None = None,
        category: str | None = None,
        description: str | None = None,
        image: str | None = None,
        poster: str | None = None,
        year: Any | None = None,
        is_special: bool | None = None,
        tmdb_id: str | None = None,
        **kwargs,
    ):
        self.id = id
        self.video_id = video_id
        self.number = number
        self.name = name
        self.duration = duration
        self.url = url
        self.mpd_id = mpd_id
        self.channel = channel
        self.category = category
        self.description = description
        self.image = image
        self.poster = poster
        self.year = year
        self.is_special = is_special
        self.tmdb_id = tmdb_id

        # [SERVICE-SPECIFIC] Allow additional attributes from different services (e.g., main_guid for Crunchyroll)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def to_dict(self) -> dict:
        """Convert the episode to a dictionary."""
        return self.__dict__.copy()

    def __str__(self):
        return f"Episode(id={self.id}, number={self.number}, name='{self.name}', duration={self.duration} min)"


class EpisodeManager:
    def __init__(self):
        self.episodes: list[Episode] = []

    def add(self, episode: Episode):
        """
        Add a new episode to the manager.
        """
        self.episodes.append(episode)

    def get(self, index: int) -> Episode:
        """
        Retrieve an episode by its index in the episodes list.
        """
        return self.episodes[index]

    def clear(self) -> None:
        """
        This method clears the episodes list.
        """
        self.episodes.clear()

    def __len__(self) -> int:
        """
        Get the number of episodes in the manager.
        """
        return len(self.episodes)

    def __str__(self):
        return f"EpisodeManager(num_episodes={len(self.episodes)})"


class Season:
    def __init__(
        self,
        id: int | str | None = None,
        number: int | None = None,
        name: str | None = None,
        slug: str | None = None,
        type: str | None = None,
        tmdb_id: str | None = None,
        **kwargs,
    ):
        self.id = id
        self.number = number
        self.name = name
        self.slug = slug
        self.type = type
        self.tmdb_id = tmdb_id
        self.episodes: EpisodeManager = EpisodeManager()

        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        return f"Season(id={self.id}, number={self.number}, name='{self.name}', episodes={self.episodes.__len__()})"


class SeasonManager:
    def __init__(self):
        self.seasons: list[Season] = []

    def add(self, season: Season) -> Season:
        """
        Add a new season to the manager and return it.
        """
        self.seasons.append(season)
        self.seasons.sort(key=lambda x: x.number or 0)
        return season

    def get_season_by_number(self, number: int) -> Season | None:
        """
        Get a season by its number.
        """
        if len(self.seasons) == 1:
            return self.seasons[0]

        for season in self.seasons:
            if season.number == number:
                return season

        return None

    def __len__(self) -> int:
        """
        Return the number of seasons managed.
        """
        return len(self.seasons)


class EntriesMeta(type):
    def __new__(cls, name, bases, dct):
        if "__init__" not in dct:

            def init(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

            dct["__init__"] = init

        def get_attr(self, item):
            return self.__dict__.get(item, None)

        dct["__getattr__"] = get_attr

        def set_attr(self, key, value):
            self.__dict__[key] = value

        dct["__setattr__"] = set_attr

        return super().__new__(cls, name, bases, dct)


class Entries(metaclass=EntriesMeta):
    def __init__(
        self,
        id: int | str | None = None,
        name: str | None = None,
        type: str | None = None,
        url: str | None = None,
        size: str | None = None,
        score: str | None = None,
        desc: str | None = None,
        slug: str | None = None,
        year: str | None = None,
        provider_language: str | None = None,
        tmdb_id: str | None = None,
        imdb_id: str | None = None,
        **kwargs,
    ):
        self.id = id
        self.name = name
        self.type = type
        self.url = url
        self.size = size
        self.score = score
        self.desc = desc
        self.slug = slug
        self.year = year
        self.provider_language = provider_language
        self.tmdb_id = tmdb_id
        self.imdb_id = imdb_id

        # [SERVICE-SPECIFIC] Allow additional attributes from different services (e.g., image, path_id)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def to_dict(self):
        """Convert the entries to a dictionary."""
        return self.__dict__.copy()

    @property
    def is_movie(self) -> bool:
        """Check if the entries is a movie."""
        return str(getattr(self, "type", "")).lower() in ["film", "movie", "ova"]

    @property
    def poster(self) -> str:
        """Get the poster image url."""
        return getattr(self, "image", "") or getattr(self, "poster_url", "")


class EntriesManager:
    def __init__(self):
        self.media_list: list[Entries] = []

    def add(self, media) -> None:
        """
        Add media to the list.

        Args:
            media (Entries): Media item to add.
        """
        # Logic to fetch year if 9999
        if media.year == "9999" and TMDB_KEY != "" and TMDB_KEY is not None:
            if media.slug and media.slug != "":
                print(f"Fetching year for slug: {media.slug}, type: {media.type}")
                media.year = str(
                    tmdb_client.get_year_by_slug_and_type(media.slug, media.type)
                    or "9999"
                )
                if media.year == "9999":
                    print("Cant fetch year setting current year.")
                    media.year = str(datetime.now(UTC).year)

            elif media.name and media.name != "":
                print(f"Fetching year for name: {media.name}, type: {media.type}")
                media.year = str(
                    tmdb_client.get_year_by_slug_and_type(
                        media.name.replace(" ", "-").lower(), media.type
                    )
                    or "9999"
                )
                if media.year == "9999":
                    print("Cant fetch year setting current year.")
                    media.year = str(datetime.now(UTC).year)

        self.media_list.append(media)

    def get(self, index: int) -> Entries:
        """
        Get a media item from the list by index.
        """
        return self.media_list[index]

    def __len__(self) -> int:
        """
        Get the numer of media items in the list.
        """
        return len(self.media_list)

    def clear(self) -> None:
        """
        This method clears the media list.
        """
        self.media_list.clear()

    def sort_by_fuzzy_score(self, query: str) -> None:
        """
        Calculate fuzzy match scores for each media item based on the query and sort by score descending.
        """
        query_lower = query.lower()
        for media in self.media_list:
            title = getattr(media, "name", "")
            score = (
                0
                if title is None
                else difflib.SequenceMatcher(None, query_lower, title.lower()).ratio()
            )
            media.score = str(score)
        self.media_list.sort(key=lambda x: getattr(x, "score", 0), reverse=True)

    def __str__(self):
        return f"EntriesManager(num_media={len(self.media_list)})"
