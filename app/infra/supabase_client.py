from functools import lru_cache

from supabase import Client, create_client


@lru_cache
def get_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)
