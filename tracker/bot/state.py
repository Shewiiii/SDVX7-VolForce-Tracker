from dataclasses import dataclass

from tracker.music import MusicCatalog


@dataclass
class BotState:
    user_id: int
    music: MusicCatalog
