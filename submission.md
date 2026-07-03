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

Bug #4 — Missing notification when rating a song

How I reproduced it

I used a valid song_id and user_id and sent a POST request:

POST /songs/<song_id>/rate

I confirmed that:

the rating was successfully created or updated in the database
no notification entry was created for the song owner afterward

This showed that rating actions were persisted correctly but did not trigger user notifications.

How I found the root cause (navigation strategy)

I traced execution starting from the route handler for /songs/<song_id>/rate, which calls rate_song() in services/notification_service.py. Inside this function, I inspected both the rating persistence logic and notification-related logic used in other functions (like add_to_playlist) for comparison.

This made it clear that unlike playlist actions, the rating flow never triggered create_notification().

Root cause

The rate_song() function correctly creates or updates a Rating record and commits it to the database, but it does not trigger a notification after the rating is saved.

As a result, even though ratings are stored correctly, the system never informs the song owner that their song was rated, creating inconsistency with other interaction types such as playlist additions.

Fix applied and side-effect check

I added a notification step after committing the rating, ensuring it only triggers when the rater is not the song owner:

song = db.session.get(Song, song_id)

if song and song.shared_by != user_id:
    rater = db.session.get(User, user_id)

    create_notification(
        user_id=song.shared_by,
        notification_type="song_rated",
        body=f"{rater.username} rated your song '{song.title}' {score} stars."
    )

After the fix, I verified:

rating creation still works correctly for new and existing ratings
notifications are generated only for valid external ratings
no self-notifications are created

--------------------------

Bug #2 — Friends Listening Now shows incorrect or outdated activity

How I reproduced it

I started the Flask application and queried the feed endpoint for a valid user with known friend activity:

GET /feed/<user_id>/listening-now

Example:
http://127.0.0.1:5000/feed/2c7aced5-4797-4274-8dd8-bb02c08001c9/listening-now

The endpoint returned inconsistent results: sometimes the feed was empty and other times it returned partial friend activity, even though database records clearly existed within the expected time window.

How I found the root cause (navigation strategy)

I traced the request flow starting from routes/feed.py, which calls get_friends_listening_now() in services/feed_service.py. Inside that function, I focused on the filtering logic around cutoff and event.listened_at. I confirmed the function was correctly retrieving events from the database, so the issue had to be in the time filtering step.

Root cause

The bug was caused by a mismatch between timezone-aware and timezone-naive datetime objects during comparison.

cutoff = datetime.now(timezone.utc) produces a timezone-aware datetime
event.listened_at from the database was stored as a naive datetime

Python does not allow reliable comparisons between aware and naive datetimes. This caused events to be incorrectly filtered out, since the comparison logic behaved inconsistently depending on runtime evaluation path.

Fix applied and side-effect check

I normalized event.listened_at to be timezone-aware before performing the comparison:

event_time = event.listened_at

if event_time.tzinfo is None:
    event_time = event_time.replace(tzinfo=timezone.utc)

if event_time < cutoff:
    continue

After applying the fix, I verified:

the endpoint consistently returns only recent friend activity
results are correctly ordered by recency
no valid events are incorrectly filtered out


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












