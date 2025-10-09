"""
Performance monitoring utilities for NFL Pick'em application
Provides decorators and context managers for performance tracking
"""

import functools
import time

from flask import current_app, g, request

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def timer(func):
    """
    Decorator to time function execution

    Args:
        func: Function to time

    Returns:
        Wrapped function with timing
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Log slow functions
            threshold = current_app.config.get("SLOW_FUNCTION_THRESHOLD", 1.0)
            if execution_time > threshold:
                logger.warning(
                    f"Slow function {func.__name__} took {execution_time:.2f}s "
                    f"(threshold: {threshold}s)"
                )
            else:
                logger.debug(
                    f"Function {func.__name__} executed in {execution_time:.2f}s"
                )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Function {func.__name__} failed after {execution_time:.2f}s: {str(e)}"
            )
            raise

    return wrapper


class PerformanceMonitor:
    """Context manager for monitoring performance of code blocks"""

    def __init__(self, operation_name, log_threshold=0.1):
        self.operation_name = operation_name
        self.log_threshold = log_threshold
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time

        if duration > self.log_threshold:
            if exc_type:
                logger.error(
                    f"Operation '{self.operation_name}' failed after {duration:.3f}s: {exc_val}"
                )
            else:
                logger.info(
                    f"Operation '{self.operation_name}' completed in {duration:.3f}s"
                )

        # Store in Flask's g for request-level aggregation
        if hasattr(g, "performance_metrics"):
            g.performance_metrics.append(
                {
                    "operation": self.operation_name,
                    "duration": duration,
                    "success": exc_type is None,
                }
            )
        else:
            g.performance_metrics = [
                {
                    "operation": self.operation_name,
                    "duration": duration,
                    "success": exc_type is None,
                }
            ]


def track_request_performance():
    """Track overall request performance"""
    g.request_start_time = time.time()


def log_request_performance():
    """Log request performance summary"""
    if not hasattr(g, "request_start_time"):
        return

    total_duration = time.time() - g.request_start_time

    # Log slow requests
    threshold = current_app.config.get("SLOW_REQUEST_THRESHOLD", 2.0)
    if total_duration > threshold:
        logger.warning(
            f"Slow request: {request.method} {request.path} "
            f"took {total_duration:.2f}s (threshold: {threshold}s)"
        )

        # Log individual operations if available
        if hasattr(g, "performance_metrics"):
            for metric in g.performance_metrics:
                logger.info(
                    f"  - {metric['operation']}: {metric['duration']:.3f}s "
                    f"({'success' if metric['success'] else 'failed'})"
                )


def cached_property(func):
    """
    Decorator that converts a method into a cached property
    Useful for expensive computations that shouldn't be repeated
    """
    attr_name = f"_cached_{func.__name__}"

    @functools.wraps(func)
    def wrapper(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, func(self))
        return getattr(self, attr_name)

    return property(wrapper)


class QueryProfiler:
    """Profile database queries for performance analysis"""

    def __init__(self):
        self.queries = []
        self.start_time = None

    def start_profiling(self):
        """Start query profiling"""
        self.queries = []
        self.start_time = time.time()
        logger.debug("Started query profiling")

    def log_query(self, query, duration):
        """Log a database query"""
        self.queries.append(
            {"query": str(query), "duration": duration, "timestamp": time.time()}
        )

        # Log slow queries immediately
        threshold = current_app.config.get("SLOW_QUERY_THRESHOLD", 1.0)
        if duration > threshold:
            logger.warning(f"Slow query ({duration:.3f}s): {query}")

    def stop_profiling(self):
        """Stop profiling and return results"""
        if self.start_time is None:
            return None

        total_time = time.time() - self.start_time
        query_count = len(self.queries)
        total_query_time = sum(q["duration"] for q in self.queries)

        result = {
            "total_time": total_time,
            "query_count": query_count,
            "total_query_time": total_query_time,
            "queries": self.queries,
        }

        logger.info(
            f"Query profiling complete: {query_count} queries, "
            f"{total_query_time:.3f}s total query time, "
            f"{total_time:.3f}s total time"
        )

        return result
