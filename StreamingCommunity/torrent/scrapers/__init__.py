# 2026

from StreamingCommunity.torrent.scrapers.base import BaseScraper
from StreamingCommunity.torrent.scrapers.yts import YtsScraper
from StreamingCommunity.torrent.scrapers.eztv import EztvScraper
from StreamingCommunity.torrent.scrapers.nyaa import NyaaScraper
from StreamingCommunity.torrent.scrapers.limetorrent import LimeTorrentScraper
from StreamingCommunity.torrent.scrapers.rutracker import RutrackerScraper
from StreamingCommunity.torrent.scrapers.torrentgalaxy import TorrentGalaxyScraper
from StreamingCommunity.torrent.scrapers.jackett import JackettScraper

SCRAPERS = {
    "yts": YtsScraper,
    "eztv": EztvScraper,
    "nyaa": NyaaScraper,
    "limetorrent": LimeTorrentScraper,
    "rutracker": RutrackerScraper,
    "torrentgalaxy": TorrentGalaxyScraper,
    "jackett": JackettScraper,
}
