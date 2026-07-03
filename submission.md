Mixtape Codebase Map (Milestone 1)


1. System Overview

Mixtape is a Flask-based social music application that allows users to share songs, rate songs, build collaborative playlists, and track listening activity and streaks.

The system follows a layered architecture:
routes → services → models (database)

    - routes/ handles HTTP requests
    - services/ contains business logic (where bugs exist)
    - models.py defines database schema and relationships
    - app.py initializes the application and registers routes


2. app.py (Application Setup)
    Implements Flask application factory (create_app)
    Configures SQLAlchemy database connection
    Initializes shared db object used by all models
    Registers blueprints:
        /songs
        /playlists
        /users
        /feed
    Creates database tables on startup


3. models.py (Data Layer)

    Core Models:
        User
            Stores user profile information
            Tracks listening streak (listening_streak)
            Stores last activity timestamp (last_listened_at)
            Relationships: songs shared, ratings, playlists, notifications, friends
        Song
            Represents shared music entries
            Contains metadata: title, artist, album, genre
            Linked to user via shared_by
            Supports tags, ratings, and listening events
        Rating
            Represents a user’s rating of a song (1–5 scale)
            Enforces uniqueness per user-song pair
        Playlist
            User-created collections of songs
            Supports collaborative playlists
            Uses ordered association table (playlist_entries) for song ordering
        Tag
            Labels for categorizing songs (many-to-many with Song)
        ListeningEvent
            Tracks when a user listens to a song
            Used for streak calculation and feed generation
        Notification
            Stores user notifications
            Includes type, message body, timestamp, and read status

    Relationships:
        User ↔ User: friendships (many-to-many)
        Song ↔ Tag: tagging system (many-to-many)
        Playlist ↔ Song: ordered many-to-many via playlist_entries
        User ↔ Song: ratings, shares, listening events


4. routes/songs.py (API Layer)

Handles all song-related HTTP endpoints.

    GET /songs/search
        Calls search_service.search_songs
        Returns filtered song results
    GET /songs/<song_id>
        Calls search_service.get_song
        Returns song metadata or 404 error
    POST /songs/<song_id>/rate
        Calls notification_service.rate_song
        Creates or updates a rating for a song
    POST /songs/<song_id>/listen
        Calls streak_service.record_listening_event
        Records listening activity and updates streak logic

Routes are intentionally thin and delegate all business logic to the services layer.



5. Services Layer (Business Logic)

    All core application logic is implemented in the services layer.

    streak_service.py
        Handles user listening streak calculation and updates
    feed_service.py
        Generates “friends listening now” feed
        Filters and formats recent listening activity
    search_service.py
        Handles song search and retrieval logic
        Responsible for filtering and ranking search results
    notification_service.py
        Creates and manages user notifications
        Also handles song rating logic (rate_song)
        Sends notifications when users interact with songs or playlists
    playlist_service.py
        Handles playlist retrieval and song ordering logic
        Manages playlist song relationships

    Design Observation:
        Services contain all business logic
        Routes only handle request validation and response formatting
        Some services mix responsibilities (e.g., notification + rating logic)



6. Example Data Flow: Song Rating → Notification
    1. Client sends request:
    POST /songs/<song_id>/rate
    2. Route handler:
    routes/songs.py validates input and extracts user_id and score
    3. Service layer:
    notification_service.rate_song(user_id, song_id, score)
    4. System actions:
    Creates or updates a Rating record in the database
    (Expected behavior: should trigger a notification for the song owner)
    5. Database:
    Stores rating + notification entries




7. Design Patterns Observed
    Clear separation of concerns:
        routes = API layer
        services = business logic
        models = database schema
    Use of SQLAlchemy ORM for all database operations
    UUIDs used as primary keys instead of incremental IDs
    Timestamp tracking for key user actions (listening, rating, notifications)
    Event-driven design patterns (ratings, playlist actions, listening events)
    Association tables used for many-to-many relationships with metadata (e.g., playlist order)















8. Overall Architecture Insight

Mixtape is designed as a modular service-oriented Flask application. All business logic is centralized in the services layer, making it the primary location for debugging and bug fixes. Routes remain lightweight and primarily handle request validation and delegation.





9. Codebase Review Summary (Pre-Bug Fix Analysis)

During initial codebase exploration, five functional issues were identified in the services layer:

Listening streak resets incorrectly under certain calendar conditions (streak_service.py)
Friends Listening Now feed includes outdated activity due to filtering and deduplication logic (feed_service.py)
Song search returns duplicate results due to unnecessary SQL joins (search_service.py)
Rating a song does not trigger notifications, unlike playlist interactions (notification_service.py)
Playlist retrieval incorrectly excludes the last song due to list slicing (playlist_service.py)

These issues are concentrated in the services layer, consistent with the architecture design where routes delegate business logic to services.





Bug #3 — Duplicate search results

Reproduction:

Called /songs/search?q=a
Observed search results returned multiple songs correctly without duplicates

Root cause (from initial design issue):

Original implementation used a JOIN with the song_tags table
One-to-many relationship between songs and tags could cause duplicate rows per song

Fix:

Removed unnecessary join logic
Query directly filters Song table using title and artist
Relies on ORM relationships to include tags in serialization

Result after fix: Search endpoint correctly returns matching songs based on title or artist using partial and case-insensitive matching

-----------------


Bug #5 — Playlist last song missing
📌 Reproduction
Started Flask app and seeded database using seed_data.py

Queried playlist endpoint:

GET /playlists/<playlist_id>/songs
Observed that the returned playlist was missing the final song in the ordered list
🧠 Expected behavior
All songs in a playlist should be returned
Songs should be ordered by their position field in ascending order
No songs should be omitted
❌ Root cause
In services/playlist_service.py, the query correctly retrieved all songs in the playlist using the playlist_entries association table
However, the return statement incorrectly sliced the result list:
return [song.to_dict() for song in songs[:-1]]
This removed the last element of the playlist due to Python list slicing ([:-1] excludes the final item)
🔧 Fix applied
Removed the slicing operation so all songs are returned:
return [song.to_dict() for song in songs]
✅ Result after fix
Playlist now returns all songs correctly
Ordering is preserved based on position
No missing entries in response


-----------------

✅ Bug #4 — Missing notification when rating a song
1. Issue description

Users receive a notification when someone adds their song to a playlist, but they do not receive a notification when someone rates their song.

2. Where the bug was found

services/notification_service.py → rate_song()

3. Root cause

The rate_song() function correctly creates or updates a Rating record in the database, but it does not trigger a notification after a rating is saved.

As a result, even though ratings are stored correctly, no notification is created for the song owner, breaking consistency with other user interactions (like playlist additions, which already trigger notifications).

4. How I reproduced it
Used a valid song_id and user_id
Sent a POST request to /songs/<song_id>/rate
Verified that:
Rating was saved in the database
No new Notification entry was created for the song owner
5. Fix implemented

Added a call to create_notification() inside rate_song() after the rating is saved and committed, and only if the rater is not the song owner.

song = db.session.get(Song, song_id)

if song and song.shared_by != user_id:
    rater = db.session.get(User, user_id)

    create_notification(
        user_id=song.shared_by,
        notification_type="song_rated",
        body=f"{rater.username} rated your song '{song.title}' {score} stars."
    )
6. Why this fix works

This ensures that every time a rating is created or updated:

The system checks who owns the song
Prevents self-notifications
Creates a Notification record for the song owner
Keeps notification behavior consistent across services



--------------------------

Bug #2 — Friends Listening Now shows incorrect or outdated activity
How I reproduced it

I opened the feed endpoint using a valid user ID:

GET /feed/<user_id>/listening-now

Example:

http://127.0.0.1:5000/feed/2c7aced5-4797-4274-8dd8-bb02c08001c9/listening-now

The endpoint returned friend listening activity, but some results included unexpected or incorrectly filtered entries, and the feed logic was inconsistent depending on timestamp comparisons.

Root cause

The issue was caused by a timezone mismatch in datetime comparisons:

cutoff = datetime.now(timezone.utc) is timezone-aware
event.listened_at from the database was timezone-naive

Python does not allow comparison between naive and aware datetimes, which caused incorrect filtering behavior (and could lead to crashes or invalid results depending on runtime path).

Fix applied

Normalized event.listened_at to UTC-aware before comparison:

event_time = event.listened_at

if event_time.tzinfo is None:
    event_time = event_time.replace(tzinfo=timezone.utc)

if event_time < cutoff:
    continue
Result after fix
Feed endpoint no longer throws datetime comparison errors
Only recent friend activity is returned correctly
Output is consistent and properly ordered by recency
Endpoint responds successfully with valid JSON


-----------------------------

Bug #1 — Friends Listening Now feed returns empty results

Issue:

The /feed/<user_id>/listening-now endpoint sometimes returned an empty feed ({"count":0,"feed":[]}) even though valid listening events existed in the database for friends of the user.

Root Cause:

The cutoff time used for filtering listening events was incorrectly set to the current time:

cutoff = datetime.now(timezone.utc)

This caused all listening events to be excluded during filtering logic, resulting in an empty feed.

Fix:

Updated the cutoff calculation to correctly include recent activity within the defined threshold:

cutoff = datetime.now(timezone.utc) - RECENT_THRESHOLD

Result:

The feed now correctly returns recent listening activity from friends, including valid songs and timestamps within the last 24 hours.


-----------------------------


AI Usage

During this project, I used AI tools as a debugging and code navigation assistant rather than as a direct code generator. I used AI to help trace execution flow across the Flask application, especially when following route → service → model interactions. It helped me understand where to look in the codebase when diagnosing bugs in the services layer.

I also used AI to clarify confusing behavior during debugging, such as differences in datetime handling (timezone-aware vs naive datetimes), SQLAlchemy query behavior, and Git workflow issues like commits vs working directory changes. In several cases, AI helped explain what specific code blocks were doing, but I verified all fixes manually by inspecting the code and testing endpoints through Flask shell or API requests.

For Git-related issues, I used AI to understand how to properly restore files, interpret git status/output, and ensure that commits were correctly pushed to the remote branch. However, I did not rely on AI to determine the root cause of bugs without first tracing the code myself.

Overall, AI was used as a support tool to accelerate understanding and debugging, but all final bug fixes were confirmed through direct code inspection and testing.












