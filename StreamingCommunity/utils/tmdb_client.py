# 24.08.24

import os
import re
import time
import unicodedata
from difflib import SequenceMatcher


# External libraries
from curl_cffi.requests.exceptions import RequestException

# Internal utilities
from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.console.shared import console
from StreamingCommunity.utils.http_client import create_client_curl, get_userAgent


# Variable
api_key = config_manager.login.get("TMDB", "api_key", default="")


class TMDBClient:
    def __init__(self, api_key: str):
        """
        Initialize the class with the API key.
        """
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"

    def _make_request(self, endpoint, params=None, retries=3):
        """
        Make a request to the given API endpoint with optional parameters.
        """
        if params is None:
            params = {}

        if self.api_key is None or self.api_key == "":
            console.log(
                "[red]TMDB API key is not set. Please provide a valid API key in the configuration."
            )
            return {}

        params["api_key"] = self.api_key
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries + 1):
            try:
                response = create_client_curl(
                    headers={"User-Agent": get_userAgent()}
                ).get(url, params=params)
                response.raise_for_status()
                return response.json()

            except RequestException as e:
                if attempt < retries:
                    if hasattr(e, "response") and e.response:
                        status_code = e.response.status_code
                        if status_code in [429, 500, 502, 503, 504]:
                            wait_time = 2**attempt
                            console.log(
                                f"[yellow]TMDB API error {status_code}, retrying in {wait_time}s... ({attempt + 1}/{retries})[/yellow]"
                            )
                            time.sleep(wait_time)
                            continue

                console.log(f"[red]Error making request to {endpoint}: {e}[/red]")
                return {}

        return {}

    def _slugify(self, text):
        """
        Normalize and slugify a given text.
        """
        text = (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        text = re.sub(r"[^\w\s-]", "", text).strip().lower()
        text = re.sub(r"[-\s]+", "-", text)
        return text

    def _slugs_match(self, slug1: str, slug2: str, threshold: float = 0.85) -> bool:
        """
        Check if two slugs are similar enough using fuzzy matching.
        """
        ratio = SequenceMatcher(None, slug1, slug2).ratio()
        return ratio >= threshold

    def get_type_and_id_by_slug_year(
        self,
        slug: str,
        year: str | None = None,
        media_type: str | None = None,
        language_preference: str = "it",
    ):
        """
        Get the type (movie or tv) and ID from TMDB based on slug and year.
        """

        # Anime often dont have a year, so we should be flexible with it
        if year:
            year_int = int(year)

        if media_type == "movie":
            movie_results = self._make_request(
                "search/movie",
                {"query": slug.replace("-", " "), "language": language_preference},
            ).get("results", [])

            # 1 result
            if len(movie_results) == 1:
                return {"type": "movie", "id": movie_results[0]["id"]}

            # Multiple results
            for movie in movie_results:
                title = movie.get("title")
                release_date = movie.get("release_date")

                if release_date:
                    movie_year = int(release_date[:4])
                else:
                    continue

                movie_slug = self._slugify(title)

                # Use fuzzy matching instead of exact comparison
                if self._slugs_match(movie_slug, slug) and (
                    not year_int or movie_year == year_int
                ):
                    return {"type": "movie", "id": movie["id"]}

        elif media_type == "tv":
            tv_results = self._make_request(
                "search/tv",
                {"query": slug.replace("-", " "), "language": language_preference},
            ).get("results", [])

            # 1 result
            if len(tv_results) == 1:
                return {"type": "tv", "id": tv_results[0]["id"]}

            # Multiple results
            for show in tv_results:
                name = show.get("name")
                first_air_date = show.get("first_air_date")

                if first_air_date:
                    show_year = int(first_air_date[:4])
                else:
                    continue

                show_slug = self._slugify(name)

                # Use fuzzy matching instead of exact comparison
                if self._slugs_match(show_slug, slug) and (
                    not year_int or show_year == year_int
                ):
                    return {"type": "tv", "id": show["id"]}

        else:
            print("Media type not specified. Searching both movie and tv.")
            return None

    def get_year_by_slug_and_type(
        self, slug: str, media_type: str, language_preference: str = "it"
    ):
        """
        Returns the year from the first search result that matches the slug.
        """
        if media_type == "movie":
            results = self._make_request(
                "search/movie",
                {"query": slug.replace("-", " "), "language": language_preference},
            ).get("results", [])

            # 1 result
            if len(results) == 1:
                return int(results[0]["release_date"][:4])

            # Multiple results
            for movie in results:
                title = movie.get("title")
                release_date = movie.get("release_date")

                if not release_date:
                    continue

                movie_slug = self._slugify(title)

                # Use fuzzy matching
                if self._slugs_match(movie_slug, slug):
                    return int(release_date[:4])

        elif media_type == "tv":
            results = self._make_request(
                "search/tv",
                {"query": slug.replace("-", " "), "language": language_preference},
            ).get("results", [])

            # 1 result
            if len(results) == 1:
                return int(results[0]["first_air_date"][:4])

            # Multiple results
            for show in results:
                name = show.get("name")
                first_air_date = show.get("first_air_date")

                if not first_air_date:
                    continue

                show_slug = self._slugify(name)

                # Use fuzzy matching
                if self._slugs_match(show_slug, slug):
                    return int(first_air_date[:4])

        return None

    def get_backdrop_url(self, media_type: str, tmdb_id: int, size: str = "w1280"):
        """
        Get the backdrop URL for a movie or TV show.
        """
        try:
            print(f"[TMDB] Getting backdrop for {media_type} with TMDB ID {tmdb_id}")
            details = self._make_request(f"{media_type}/{tmdb_id}", {"language": "it"})
            backdrop_path = details.get("backdrop_path")
            if backdrop_path:
                return f"https://image.tmdb.org/t/p/{size}{backdrop_path}"
        except Exception as e:
            console.log(
                f"[red]Error getting backdrop for {media_type} {tmdb_id}: {e}[/red]"
            )
        return None

    def search_movie(self, query: str):
        """
        Search for a movie and return the TMDB ID of the first result.
        """
        results = self._make_request(
            "search/movie", {"query": query, "language": "it"}
        ).get("results", [])
        if results:
            return results[0]["id"]
        return None

    def get_movie_details(self, tmdb_id: int):
        """
        Get movie details including title and IMDB ID.
        """
        details = self._make_request(f"movie/{tmdb_id}", {"language": "it"})
        return {"title": details.get("title"), "imdb_id": details.get("imdb_id")}

    def get_full_details(self, media_type: str, tmdb_id: int, language: str = "it"):
        """
        Fetch full movie or TV show details from TMDB including credits and ratings.

        Args:
            media_type: 'movie' or 'tv'
            tmdb_id: TMDB ID
            language: Language code for results

        Returns:
            dict with title, original_title, plot, year, rating, votes, mpaa,
            genres, director, cast, imdb_id, poster_path, backdrop_path
        """
        details = self._make_request(
            f"{media_type}/{tmdb_id}",
            {
                "language": language,
                "append_to_response": "credits,external_ids,content_ratings,release_dates",
            },
        )
        if not details:
            return None

        result = {
            "title": details.get("title") or details.get("name"),
            "original_title": details.get("original_title")
            or details.get("original_name"),
            "plot": details.get("overview", ""),
            "year": None,
            "rating": details.get("vote_average"),
            "votes": details.get("vote_count"),
            "mpaa": None,
            "genres": [g["name"] for g in details.get("genres", []) if g.get("name")],
            "director": None,
            "cast": [],
            "imdb_id": None,
            "poster_path": details.get("poster_path"),
            "backdrop_path": details.get("backdrop_path"),
            "runtime": details.get("runtime"),
        }

        if media_type == "movie":
            release_date = details.get("release_date")
            if release_date:
                result["year"] = int(release_date[:4])
            # MPAA from release_dates
            for rd in details.get("release_dates", {}).get("results", []):
                if rd.get("iso_3166_1") == "US":
                    for cert in rd.get("release_dates", []):
                        if cert.get("certification"):
                            result["mpaa"] = cert["certification"]
                            break
        elif media_type == "tv":
            first_air = details.get("first_air_date")
            if first_air:
                result["year"] = int(first_air[:4])

        # Content ratings (fallback for TV)
        if not result["mpaa"]:
            for cr in details.get("content_ratings", {}).get("results", []):
                if cr.get("iso_3166_1") == "US":
                    result["mpaa"] = cr.get("rating")
                    break

        # Credits
        credits = details.get("credits", {})
        for crew in credits.get("crew", []):
            if crew.get("job") == "Director":
                result["director"] = crew["name"]
                break
        for actor in credits.get("cast", [])[:10]:
            result["cast"].append(
                {
                    "name": actor.get("name"),
                    "role": actor.get("character"),
                    "order": actor.get("order"),
                }
            )

        # External IDs
        ext_ids = details.get("external_ids", {})
        result["imdb_id"] = ext_ids.get("imdb_id")

        return result

    def get_images(self, media_type: str, tmdb_id: int):
        """
        Fetch poster and backdrop image URLs for a movie or TV show.

        Args:
            media_type: 'movie' or 'tv'
            tmdb_id: TMDB ID

        Returns:
            dict with 'posters' and 'backdrops' lists of URL strings
        """
        data = self._make_request(f"{media_type}/{tmdb_id}/images", {})
        if not data:
            return {"posters": [], "backdrops": []}

        base = "https://image.tmdb.org/t/p"
        posters = []
        for p in data.get("posters", []):
            if p.get("file_path"):
                posters.append(f"{base}/w500{p['file_path']}")

        backdrops = []
        for b in data.get("backdrops", []):
            if b.get("file_path"):
                backdrops.append(f"{base}/w1280{b['file_path']}")

        return {"posters": posters, "backdrops": backdrops}

    def download_image(self, url: str, output_path: str) -> bool:
        """
        Download an image from a URL to a local file path.

        Args:
            url: Image URL to download
            output_path: Local filesystem path to save the image

        Returns:
            True if download succeeded, False otherwise
        """
        try:
            response = create_client_curl(headers={"User-Agent": get_userAgent()}).get(
                url
            )
            response.raise_for_status()
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        except Exception as e:
            console.log(f"[yellow]Failed to download image {url}: {e}[/yellow]")
            return False


tmdb_client = TMDBClient(api_key)
tmdb = tmdb_client

