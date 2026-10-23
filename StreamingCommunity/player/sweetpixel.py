# 20.09.23

import json
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# Internal utilities
from StreamingCommunity.utils.http_client import create_client, get_headers


class VideoSource:
    def __init__(self, site_url, episode, session_id, csrf_token):
        self.site_url = site_url
        self.episode = episode
        self.session_id = session_id
        self.csrf_token = csrf_token
        self.headers = get_headers()

    def get_playlist(self):
        try:
            url_info = f"{self.site_url}/api/episode/info?id={self.episode.id}&alt=0"
            client = create_client(
                cookies={"sessionId": self.session_id},
                headers={**self.headers, "csrf-token": self.csrf_token, "X-Requested-With": "XMLHttpRequest", "Referer": f"{self.site_url}/"},
                timeout=20,
            )
            try:
                response = client.get(url_info)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    if data.get("grabber"):
                        return data["grabber"]
                    if data.get("download"):
                        return data["download"]
                    if data.get("target"):
                        target = urljoin(self.site_url + "/", data["target"])
                        resp = client.get(target)
                        soup = BeautifulSoup(resp.text, "html.parser")
                        source = soup.find("source")
                        if source and source.get("src"):
                            return urljoin(self.site_url + "/", source.get("src"))
                        video = soup.find("video")
                        if video and video.get("src"):
                            return urljoin(self.site_url + "/", video.get("src"))
            finally:
                client.close()
        except Exception as e:
            logging.error(f"Error getting playlist: {e}")
        return None
