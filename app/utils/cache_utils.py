"""
Cache utilities for NFL Pick'em application
Provides caching decorators and helper functions for improved performance
"""

import functools

from flask import current_app, request

from app import cache


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


def cached_query(model_name, timeout=300):
    """
    Decorator for caching database query results

    Args:
        model_name: Name of the model for cache key generation
        timeout: Cache timeout in seconds
    """

    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            # Generate cache key from function name and arguments
            args_str = "_".join(str(arg) for arg in args)
            kwargs_str = "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
            cache_key = f"query_{model_name}_{f.__name__}_{args_str}_{kwargs_str}"

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                current_app.logger.debug(f"Query cache hit: {cache_key}")
                return result

            # Execute query and cache result
            result = f(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            current_app.logger.debug(f"Query cache set: {cache_key}")

            return result

        return wrapped

    return decorator


def invalidate_cache_pattern(pattern):
    """
    Invalidate cache keys matching a pattern

    Args:
        pattern: Pattern to match cache keys
    """
    try:
        # For simple cache, we need to track keys manually
        # This is a limitation of SimpleCache - consider Redis for production
        cache.clear()
        current_app.logger.info(f"Cache cleared for pattern: {pattern}")
    except Exception as e:
        current_app.logger.error(f"Failed to clear cache: {e}")


def invalidate_model_cache(model_name):
    """
    Invalidate all cache entries for a specific model

    Args:
        model_name: Name of the model to invalidate
    """
    invalidate_cache_pattern(f"*{model_name}*")


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
        # This is a basic implementation - Redis would provide better stats
        return {
            "type": current_app.config.get("CACHE_TYPE", "Unknown"),
            "timeout": current_app.config.get("CACHE_DEFAULT_TIMEOUT", 300),
        }
