"""Dataclasses representing Jellyfin API objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MediaItem:
    """A single media item returned from the Jellyfin API."""

    id: str
    name: str
    type: str  # "Movie", "Series", "Episode", "Audio", etc.
    year: Optional[int] = None
    genres: list[str] = field(default_factory=list)
    image_url: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict, base_url: str = "") -> "MediaItem":
        """Construct a MediaItem from a Jellyfin API response dict."""
        item_id = data.get("Id", "")
        image_url: Optional[str] = None
        if item_id and base_url:
            image_tag = (data.get("ImageTags") or {}).get("Primary")
            if image_tag:
                image_url = (
                    f"{base_url}/Items/{item_id}/Images/Primary"
                    f"?tag={image_tag}&maxWidth=300"
                )
        return cls(
            id=item_id,
            name=data.get("Name", ""),
            type=data.get("Type", ""),
            year=data.get("ProductionYear"),
            genres=data.get("Genres", []),
            image_url=image_url,
        )


@dataclass
class Library:
    """A Jellyfin virtual library / collection folder."""

    id: str
    name: str
    type: str  # "movies", "tvshows", "music", "books", etc.

    @classmethod
    def from_api(cls, data: dict) -> "Library":
        """Construct a Library from a /Library/VirtualFolders item."""
        return cls(
            id=data.get("ItemId", data.get("Id", "")),
            name=data.get("Name", ""),
            type=data.get("CollectionType", "mixed"),
        )


@dataclass
class PlaybackSession:
    """An active Jellyfin playback session."""

    id: str
    user_id: str
    item: Optional[MediaItem]
    position_ticks: int = 0  # 100-nanosecond ticks
    is_paused: bool = False

    @property
    def position_seconds(self) -> float:
        """Return position in seconds."""
        return self.position_ticks / 10_000_000

    @classmethod
    def from_api(cls, data: dict, base_url: str = "") -> "PlaybackSession":
        """Construct a PlaybackSession from a /Sessions response item."""
        now_playing = data.get("NowPlayingItem")
        item: Optional[MediaItem] = None
        if now_playing:
            item = MediaItem.from_api(now_playing, base_url)

        play_state = data.get("PlayState", {})
        return cls(
            id=data.get("Id", ""),
            user_id=data.get("UserId", ""),
            item=item,
            position_ticks=play_state.get("PositionTicks", 0),
            is_paused=play_state.get("IsPaused", False),
        )
