"""
Supabase client singleton — service-role client for engine writes.
"""
import logging
from supabase import create_client, Client
from engine.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    """
    Returns a cached Supabase client using the service role key.
    Must be called after .env is loaded (config.py handles this).
    """
    global _client
    if _client is None:
        if not SUPABASE_SERVICE_KEY:
            raise RuntimeError("SUPABASE_SERVICE_KEY is not set in .env")
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        _logger.info("Supabase client initialized (service role)")
    return _client
