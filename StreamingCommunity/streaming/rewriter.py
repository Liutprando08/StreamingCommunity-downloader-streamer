import re
from urllib.parse import urljoin, quote


class M3U8Rewriter:
    def __init__(self, proxy_base_url: str, playlist_url: str):
        self.proxy_base = proxy_base_url.rstrip("/")
        self.playlist_url = playlist_url
        self.content_type = "master"

    def rewrite_playlist(self, content: str, content_type: str = "master") -> str:
        self.content_type = content_type
        lines = content.split("\n")
        rewritten = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#EXT-X-STREAM-INF:"):
                rewritten.append(line)
                continue
            if stripped.startswith("#EXT-X-MEDIA:"):
                rewritten.append(self._rewrite_media_tag(stripped))
                continue

            if stripped.startswith("#EXT-X-KEY:"):
                rewritten.append(self._rewrite_key_tag(stripped))
                continue
            if stripped.startswith("#EXT-X-MAP:"):
                rewritten.append(self._rewrite_map_tag(stripped))
                continue

            if stripped.startswith("#") or not stripped:
                rewritten.append(line)
                continue
            rewritten.append(self._rewrite_bare_uri(stripped))
        return "\n".join(rewritten)

    def _rewrite_bare_uri(self, uri: str) -> str:
        absolute = urljoin(self.playlist_url, uri)
        encoded = quote(absolute, safe=":/")
        if self.content_type == "master":
            return f"{self.proxy_base}/playlist/{encoded}"
        return f"{self.proxy_base}/segment/{encoded}"

    def _rewrite_media_tag(self, tag: str) -> str:
        def replace_uri(match):
            uri = match.group(1)
            absolute = urljoin(self.playlist_url, uri)
            encoded = quote(absolute, safe=":/")
            return f'URI="{self.proxy_base}/playlist/{encoded}"'

        return re.sub(r'URI="([^"]+)"', replace_uri, tag)

    def _rewrite_key_tag(self, tag: str) -> str:
        def replace_uri(match):
            uri = match.group(1)
            absolute = urljoin(self.playlist_url, uri)
            encoded = quote(absolute, safe=":/")
            return f'URI="{self.proxy_base}/key/{encoded}"'

        return re.sub(r'URI="([^"]+)"', replace_uri, tag)

    def _rewrite_map_tag(self, tag: str) -> str:
        def replace_uri(match):
            uri = match.group(1)
            absolute = urljoin(self.playlist_url, uri)
            encoded = quote(absolute, safe=":/")
            return f'URI="{self.proxy_base}/segment/{encoded}"'

        return re.sub(r'URI="([^"]+)"', replace_uri, tag)
