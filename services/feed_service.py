"""
services/feed_service.py — Mixtape

Handles the "Friends Listening Now" feed and activity feed logic.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import desc
from app import db
from models import User, Song, ListeningEvent


RECENT_THRESHOLD = timedelta(hours=24)


def get_friends_listening_now(user_id: str) -> list[dict]:
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    cutoff = datetime.min.replace(tzinfo=timezone.utc)
    friend_ids = [f.id for f in user.friends]

    if not friend_ids:
        return []

    # STEP 1: filter FIRST in SQL
    recent_events = (
        db.session.query(ListeningEvent)
        .filter(ListeningEvent.user_id.in_(friend_ids))
        .order_by(desc(ListeningEvent.listened_at))
        .all()
    )

    # STEP 2: normalize + filter in Python
    
    
    filtered = []
    for event in recent_events:
        event_time = event.listened_at

        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)

        if event_time >= cutoff:
            filtered.append((event, event_time))

    # STEP 3: pick latest per friend correctly
    seen = set()
    result = []

    for event, event_time in filtered:
        if event.user_id in seen:
            continue

        seen.add(event.user_id)

        friend = db.session.get(User, event.user_id)
        song = db.session.get(Song, event.song_id)

        result.append({
            "friend": friend.to_dict(),
            "song": song.to_dict(),
            "listened_at": event_time.isoformat(),
        })

    return result


def get_activity_feed(user_id: str, limit: int = 20) -> list[dict]:
    """
    Return a general activity feed of recent listening events from all friends.

    Unlike get_friends_listening_now, this is not filtered by recency —
    it returns the most recent N events regardless of when they happened.

    Args:
        user_id: The ID of the current user.
        limit: Maximum number of events to return.

    Returns:
        A list of activity dicts ordered by most recent first.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    friend_ids = [f.id for f in user.friends]
    if not friend_ids:
        return []

    events = (
        db.session.query(ListeningEvent)
        .filter(ListeningEvent.user_id.in_(friend_ids))
        .order_by(desc(ListeningEvent.listened_at))
        .limit(limit)
        .all()
    )

    result = []
    for event in events:
        friend = db.session.get(User, event.user_id)
        song = db.session.get(Song, event.song_id)
        result.append({
            "friend": friend.to_dict(),
            "song": song.to_dict(),
            "listened_at": event.listened_at.isoformat(),
        })

    return result
