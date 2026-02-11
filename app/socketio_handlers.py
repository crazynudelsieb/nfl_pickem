"""
SocketIO Event Handlers for Real-time Updates

This module handles WebSocket connections for real-time score updates,
pick notifications, and other live features.
"""

import logging
from datetime import datetime, timezone

from flask import request
from flask_login import current_user
from flask_socketio import disconnect, emit, join_room, leave_room

from app import db, socketio
from app.models import Game, Pick, Season

logger = logging.getLogger(__name__)

# Track connected users and their subscriptions
connected_users = {}


@socketio.on("connect", namespace="/scores")
def on_connect():
    """Handle client connection to scores namespace"""
    try:
        user_id = current_user.id if current_user.is_authenticated else None
        client_id = request.sid

        logger.info(f"Client connected to /scores: {client_id} (user: {user_id})")

        connected_users[client_id] = {"user_id": user_id, "subscriptions": set()}

        # Send current live games status (for real-time updates)
        current_season = Season.get_current_season()
        if current_season:
            # Get all games for current season and filter in-progress games in Python
            # (Game.status is a @property, can't be used in SQL queries)
            all_games = Game.query.filter(
                Game.season_id == current_season.id, Game.is_final.is_(False)
            ).all()

            # Filter for in-progress games using the status property
            live_games = [game for game in all_games if game.status == "in_progress"]

            # Emit live games data for potential use (removed indicator)
            emit("live_games_data", {"games": [game.to_dict() for game in live_games]})

    except Exception as e:
        logger.error(f"Error in scores connect: {e}")


@socketio.on("disconnect", namespace="/scores")
def on_disconnect():
    """Handle client disconnection from scores namespace"""
    try:
        client_id = request.sid
        if client_id in connected_users:
            user_id = connected_users[client_id]["user_id"]
            logger.info(
                f"Client disconnected from /scores: {client_id} (user: {user_id})"
            )
            del connected_users[client_id]
    except Exception as e:
        logger.error(f"Error in scores disconnect: {e}")


@socketio.on("subscribe_game", namespace="/scores")
def on_subscribe_game(data):
    """Subscribe to updates for a specific game"""
    try:
        client_id = request.sid
        game_id = data.get("game_id")

        if client_id in connected_users and game_id:
            room_name = f"game_{game_id}"
            
            # Skip if already subscribed (avoid duplicate joins/emits)
            if room_name in connected_users[client_id]["subscriptions"]:
                return
                
            connected_users[client_id]["subscriptions"].add(room_name)
            join_room(room_name)

            # Send current game state
            game = Game.query.get(game_id)
            if game:
                emit("game_update", game.to_dict())

            logger.debug(f"Client {client_id} subscribed to game {game_id}")
    except Exception as e:
        logger.error(f"Error in subscribe_game: {e}")


@socketio.on("unsubscribe_game", namespace="/scores")
def on_unsubscribe_game(data):
    """Unsubscribe from updates for a specific game"""
    try:
        client_id = request.sid
        game_id = data.get("game_id")

        if client_id in connected_users and game_id:
            connected_users[client_id]["subscriptions"].discard(f"game_{game_id}")
            leave_room(f"game_{game_id}")

            logger.debug(f"Client {client_id} unsubscribed from game {game_id}")
    except Exception as e:
        logger.error(f"Error in unsubscribe_game: {e}")


@socketio.on("subscribe_user_picks", namespace="/scores")
def on_subscribe_user_picks(data):
    """Subscribe to updates for user's picks"""
    try:
        if not current_user.is_authenticated:
            disconnect()
            return

        client_id = request.sid
        user_id = current_user.id

        if client_id in connected_users:
            connected_users[client_id]["subscriptions"].add(f"user_picks_{user_id}")
            join_room(f"user_picks_{user_id}")

            logger.debug(
                f"Client {client_id} subscribed to user picks for user {user_id}"
            )
    except Exception as e:
        logger.error(f"Error in subscribe_user_picks: {e}")


# Broadcast functions (called from scheduler service)
def broadcast_score_update(game):
    """Broadcast score update to subscribers"""
    try:
        game_data = game.to_dict()

        # Emit to game subscribers
        socketio.emit(
            "score_update", game_data, room=f"game_{game.id}", namespace="/scores"
        )

        logger.debug(f"Broadcasted score update for game {game.id}")

    except Exception as e:
        logger.error(f"Error broadcasting score update: {e}")


def broadcast_game_final(game):
    """Broadcast when a game becomes final"""
    try:
        game_data = game.to_dict()

        # Emit to game subscribers
        socketio.emit(
            "game_final", game_data, room=f"game_{game.id}", namespace="/scores"
        )

        # Notify users of their pick results
        # NOTE: Picks are already scored by scheduler's Pick.recalculate_for_game()
        # We just need to broadcast the results to connected clients
        affected_picks = Pick.query.filter_by(game_id=game.id).all()
        for pick in affected_picks:
            # Notify user of pick result (no update needed, just broadcast)
            socketio.emit(
                "pick_result",
                {
                    "pick_id": pick.id,
                    "game_id": pick.game_id,
                    "is_correct": pick.is_correct,
                    "points_earned": pick.points_earned,
                    "tiebreaker_points": pick.tiebreaker_points,
                },
                room=f"user_picks_{pick.user_id}",
                namespace="/scores",
            )

        logger.info(
            f"Broadcasted game final for game {game.id}, notified {len(affected_picks)} picks"
        )

    except Exception as e:
        logger.error(f"Error broadcasting game final: {e}")
        db.session.rollback()


def broadcast_pick_update(pick, action="updated"):
    """Broadcast pick update to relevant users"""
    try:
        pick_data = pick.to_dict()
        pick_data["action"] = action

        # Notify the user who made the pick
        socketio.emit(
            "pick_update",
            pick_data,
            room=f"user_picks_{pick.user_id}",
            namespace="/scores",
        )

        # Notify group members if needed (for admin actions)
        if hasattr(pick, "group_id"):
            socketio.emit(
                "group_pick_update",
                pick_data,
                room=f"group_{pick.group_id}",
                namespace="/scores",
            )

        logger.debug(f"Broadcasted pick {action} for pick {pick.id}")

    except Exception as e:
        logger.error(f"Error broadcasting pick update: {e}")


# General notifications namespace
@socketio.on("connect", namespace="/notifications")
def on_notifications_connect():
    """Handle connection to notifications namespace"""
    try:
        if not current_user.is_authenticated:
            disconnect()
            return

        user_id = current_user.id

        # Join user's personal notification room
        join_room(f"user_{user_id}")

        logger.info(f"User {user_id} connected to notifications")

    except Exception as e:
        logger.error(f"Error in notifications connect: {e}")


@socketio.on("disconnect", namespace="/notifications")
def on_notifications_disconnect():
    """Handle disconnection from notifications namespace"""
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
            leave_room(f"user_{user_id}")
            logger.info(f"User {user_id} disconnected from notifications")
    except Exception as e:
        logger.error(f"Error in notifications disconnect: {e}")


def notify_user(user_id, notification_type, message, data=None):
    """Send notification to a specific user"""
    try:
        socketio.emit(
            "notification",
            {
                "type": notification_type,
                "message": message,
                "data": data or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            room=f"user_{user_id}",
            namespace="/notifications",
        )

        logger.debug(f"Sent {notification_type} notification to user {user_id}")

    except Exception as e:
        logger.error(f"Error sending notification to user {user_id}: {e}")


def get_connected_users_count():
    """Get count of connected users"""
    return len(connected_users)


def get_connection_stats():
    """Get detailed connection statistics"""
    stats = {
        "total_connections": len(connected_users),
        "authenticated_users": len(
            [u for u in connected_users.values() if u["user_id"]]
        ),
        "anonymous_users": len(
            [u for u in connected_users.values() if not u["user_id"]]
        ),
        "total_subscriptions": sum(
            len(u["subscriptions"]) for u in connected_users.values()
        ),
    }
    return stats
