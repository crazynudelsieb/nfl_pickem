"""
Cache utilities for NFL Pick'em application
Provides caching decorators and helper functions for improved performance
"""

import functools

from flask import current_app, request

from app import cache, db


def make_cache_key(*args, **kwargs):
    """Generate a cache key from request path and arguments"""
    path = request.path
    args_str = "_".join(str(arg) for arg in args)
    kwargs_str = "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
    return f"{path}_{args_str}_{kwargs_str}".replace("/", "_")


def cached_route(timeout=300, key_prefix="view"):
    """
    Decorator for caching route responses

    Args:
        timeout: Cache timeout in seconds (default 5 minutes)
        key_prefix: Prefix for cache key
    """

    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}_{make_cache_key(*args, **kwargs)}"

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                current_app.logger.debug(f"Cache hit for key: {cache_key}")
                return result

            # Execute function and cache result
            result = f(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            current_app.logger.debug(f"Cache set for key: {cache_key}")

            return result

        return wrapped

    return decorator


# Models that feed no cached route, so writing them needs no invalidation at
# all. This is the case that matters: picks are written constantly during live
# games, and none of the cached routes serve pick or user data.
UNCACHED_MODELS = {"pick", "user"}


def invalidate_model_cache(model_name):
    """
    Invalidate cached routes that serve a specific model's data.

    The in-process cache has no key-pattern support, so anything that isn't in
    UNCACHED_MODELS clears the whole cache. That is deliberately blunt: the
    cache only ever holds the handful of read-only reference routes decorated
    with cached_route, each of which costs a query or two to rebuild. Unknown
    models clear too - serving stale data is worse than a rebuild.

    Args:
        model_name: Name of the model to invalidate (case-insensitive)
    """
    if model_name.lower() in UNCACHED_MODELS:
        return

    try:
        cache.clear()
    except Exception as e:
        current_app.logger.error(f"Failed to invalidate cache for {model_name}: {e}")


def invalidate_pick_related_caches():
    """
    Invalidate all pick-related caches including Pick and User models

    This is a common operation after pick submissions or updates
    """
    invalidate_model_cache("Pick")
    invalidate_model_cache("User")


def commit_and_refresh():
    """
    Commit database changes and refresh all objects

    This is a common pattern to ensure fresh data is loaded after database writes.
    Combines db.session.commit() and db.session.expire_all() in one call.
    """
    db.session.commit()
    db.session.expire_all()


def commit_refresh_and_invalidate_picks():
    """
    Complete database commit with cache invalidation for pick-related data

    This combines three frequently-paired operations:
    1. Commit database changes
    2. Expire SQLAlchemy objects to force reload
    3. Invalidate pick-related caches

    Use after pick submissions, updates, or deletions
    """
    commit_and_refresh()
    invalidate_pick_related_caches()


class CacheManager:
    """Cache management utilities"""

    @staticmethod
    def warm_up_cache():
        """Pre-populate cache with frequently accessed data"""
        try:
            from app.models import Season, Team

            # Cache current season
            current_season = Season.get_current_season()
            if current_season:
                cache.set("current_season", current_season, timeout=3600)

                # Cache teams for current season
                teams = Team.get_all_for_season(current_season.id)
                cache.set(f"teams_season_{current_season.id}", teams, timeout=3600)

            current_app.logger.info("Cache warmed up successfully")

        except Exception as e:
            current_app.logger.error(f"Failed to warm up cache: {e}")

    @staticmethod
    def get_cache_stats():
        """Get cache statistics"""
        return {
            "type": current_app.config.get("CACHE_TYPE", "Unknown"),
            "timeout": current_app.config.get("CACHE_DEFAULT_TIMEOUT", 300),
        }
