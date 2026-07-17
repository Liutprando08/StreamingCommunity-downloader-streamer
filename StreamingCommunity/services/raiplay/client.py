# 16.03.25

import json


# Internal utilities
from StreamingCommunity.utils.http_client import create_client, get_headers


def generate_license_url(mpd_id: str):
    """
    Generates the URL to obtain the Widevine license.

    Args:
        mpd_id (str): The ID of the MPD (Media Presentation Description) file.

    Returns:
        str: The full license URL.
    """
    params = {
        'cont': mpd_id,
        'output': '62',
    }
    
    response = create_client(headers=get_headers()).get('https://mediapolisvod.rai.it/relinker/relinkerServlet.htm', params=params)
    response.raise_for_status()

    json_data = json.loads(response.content.decode('latin-1'))
    licence_map = json_data.get('licence_server_map', {}) if isinstance(json_data, dict) else {}
    values = licence_map.get('drmLicenseUrlValues', []) if isinstance(licence_map, dict) else []
    if not values:
        raise ValueError("No DRM license URL values found in response")
    license_url = values[0].get('licenceUrl') if isinstance(values[0], dict) else None
    if not license_url:
        raise ValueError("licenceUrl is missing from response")

    return license_url