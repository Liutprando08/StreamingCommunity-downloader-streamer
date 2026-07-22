# 26.11.25

import time

# External library
from rich.console import Console


# Internal utilities
from StreamingCommunity.utils.http_client import create_client, get_userAgent, get_headers


# Variable
console = Console()

_bearer_token_cache = {}
_BEARER_TOKEN_TTL = 300


def get_playback_url(video_id: str, bearer_token: str, get_dash: bool, channel: str = "") -> str:
    """
    Get the playback URL (HLS or DASH) for a given video ID.

    Parameters:
        - video_id (str): ID of the video.
    """
    headers = {
        'authorization': f"Bearer {bearer_token[channel]['key']}",
        'user-agent': get_userAgent()
    }

    json_data = {
        'deviceInfo': {
            "adBlocker": False,
            "drmSupported": True
        },
        'videoId': video_id,
    }
    response = create_client().post(bearer_token[channel]['endpoint'], headers=headers, json=json_data)

    if response.status_code == 403:
        console.print("[red]Set vpn to IT to download this content.")

    response.raise_for_status()

    if not get_dash:
        return response.json()['data']['attributes']['streaming'][0]['url']
    else:
        return response.json()['data']['attributes']['streaming'][1]['url']


def get_bearer_token(environment="realtime"):
    """
    Get the Bearer token required for authentication.

    Parameters:
        - environment (str): The Aurora environment name (default: "realtime").

    Returns:
        dict: Token Bearer
    """
    now = time.time()

    if environment in _bearer_token_cache:
        cached_token, cached_time = _bearer_token_cache[environment]
        if now - cached_time < _BEARER_TOKEN_TTL:
            return cached_token

    response = create_client(headers=get_headers()).get(f'https://public.aurora.enhanced.live/site/page/homepage/?include=default&filter[environment]={environment}&v=2')
    response.raise_for_status()

    response_data = response.json()
    token = {
        'X-REALM-IT': {
            'endpoint': 'https://public.aurora.enhanced.live/playback/v3/videoPlaybackInfo',
            'key': response_data['userMeta']['realm']['X-REALM-IT']
        }, 
        'X-REALM-DPLAY': {
            'endpoint': 'https://eu1-prod.disco-api.com/playback/v3/videoPlaybackInfo',
            'key': response_data['userMeta']['realm']['X-REALM-DPLAY']
        }
    }

    _bearer_token_cache[environment] = (token, now)
    return token
