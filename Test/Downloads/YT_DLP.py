# 21.08.26
# ruff: noqa: E402

import os
import sys


# Fix import
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(src_path)


from StreamingCommunity.services.youtube import (
    title_search,
    process_search_result,
    entries_manager,
)


query = "big buck bunny"
len_database = title_search(query)
print(f"Results found: {len_database}")

entries_manager.sort_by_fuzzy_score(query)
for i, media in enumerate(entries_manager.media_list):
    print(f"{i}. {media.name} [{media.size}] ({media.desc}) → {media.url}")

if len_database > 0:
    select_title = entries_manager.get(0)
    result = process_search_result(select_title)
    print(f"Download result: {result}")
