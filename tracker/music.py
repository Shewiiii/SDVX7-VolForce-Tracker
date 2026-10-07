import logging
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

DIFFICULTY_TAGS = (
    ("novice",),
    ("advanced",),
    ("exhaust",),
    ("infinite", "gravity", "heaven", "vivid", "exceed", "nabla"),
    ("maximum",),
    ("ultimate",),
)
JACKET_INDICES = ((1,), (2, 1), (3, 2, 1), (4, 3, 1), (5, 4, 3, 1), (5, 4, 3, 1))


def _read_database(path: Path) -> tuple[dict, dict, dict, dict, dict]:
    raw = path.read_bytes()
    declaration = re.search(rb'encoding=[\'"]([^\'"]+)', raw[:200], re.IGNORECASE)
    encoding = declaration[1].decode("ascii").lower() if declaration else "utf-8-sig"
    if encoding in ("shift-jis", "shift_jis", "sjis", "windows-31j"):
        encoding = "cp932"
    text = raw.decode(encoding)
    root = ET.fromstring(re.sub(r"<\?xml[^>]*\?>", "", text, count=1))
    if root.tag != "mdb":
        raise ValueError("Expected an mdb music database")
    titles, artists, levels = {}, {}, {}
    title_readings, artist_readings = {}, {}
    for music in root.findall("music"):
        try:
            mid = int(music.get("id", "0"))
            if mid <= 0:
                continue
            title = music.findtext("info/title_name", "").strip()
            artist = music.findtext("info/artist_name", "").strip()
            if title:
                titles[mid] = title
            if artist:
                artists[mid] = artist
            title_reading = music.findtext("info/title_yomigana", "").strip()
            artist_reading = music.findtext("info/artist_yomigana", "").strip()
            if title_reading:
                title_readings[mid] = title_reading
            if artist_reading:
                artist_readings[mid] = artist_reading
            charts = {}
            for index, tags in enumerate(DIFFICULTY_TAGS):
                for tag in tags:
                    chart = music.find(f"difficulty/{tag}")
                    if chart is None:
                        continue
                    value = float(chart.findtext("difnum", "0"))
                    if math.isfinite(value) and value >= 0:
                        charts[index] = value / 10 if value > 20 else value
                    break
            levels[mid] = charts
        except (ValueError, TypeError, AttributeError) as error:
            logger.debug("Skipping invalid music entry in %s: %s", path, error)
    return titles, artists, levels, title_readings, artist_readings


class MusicCatalog:
    def __init__(self, base_database: str | Path, custom_root: str | Path | None):
        self.base_root = Path(base_database).parent.parent
        self.custom_root = Path(custom_root) if custom_root is not None else None
        self.paths = [Path(base_database)]
        if self.custom_root is not None:
            self.paths.append(self.custom_root / "others" / "music_db.merged.xml")
        self._signatures = {}
        self._sources = {}
        self.titles, self.artists, self.levels = {}, {}, {}
        self.title_readings, self.artist_readings = {}, {}

    def refresh(self) -> None:
        """Reload changed files: retain a last good source during a failed sync."""
        changed = False
        for path in self.paths:
            try:
                stat = path.stat()
            except FileNotFoundError:
                if path in self._sources:
                    del self._sources[path]
                    self._signatures.pop(path, None)
                    changed = True
                continue
            except OSError as error:
                logger.warning("Cannot inspect music database %s: %s", path, error)
                continue
            signature = (stat.st_mtime_ns, stat.st_size)
            if self._signatures.get(path) == signature:
                continue
            try:
                data = _read_database(path)
            except (
                OSError,
                UnicodeError,
                LookupError,
                ET.ParseError,
                ValueError,
            ) as error:
                logger.warning("Cannot load music database %s: %s", path, error)
                continue
            self._sources[path] = data
            self._signatures[path] = signature
            changed = True
        if changed:
            titles, artists, levels = {}, {}, {}
            title_readings, artist_readings = {}, {}
            for path in self.paths:
                (
                    source_titles, source_artists, source_levels,
                    source_title_readings, source_artist_readings,
                ) = self._sources.get(
                    path, ({}, {}, {}, {}, {})
                )
                titles.update(source_titles)
                artists.update(source_artists)
                title_readings.update(source_title_readings)
                artist_readings.update(source_artist_readings)
                for mid, charts in source_levels.items():
                    levels.setdefault(mid, {}).update(charts)
            self.titles, self.artists, self.levels = titles, artists, levels
            self.title_readings, self.artist_readings = title_readings, artist_readings
            logger.info(
                "Loaded %d songs from original/custom music databases", len(levels)
            )

    def find_jacket(self, mid: int, difficulty: int) -> bytes | None:
        """Resolve jacket files with mod precedence, then original-game fallback."""
        roots = ([self.custom_root] if self.custom_root is not None else []) + [
            self.base_root
        ]
        folders = []
        for root in roots:
            music_dir = root / "music"
            song_dirs = sorted(
                folder
                for folder in music_dir.glob(f"{mid}*")
                if folder.is_dir()
                and (folder.name == str(mid) or folder.name.startswith(f"{mid}_"))
            )
            graphics_dirs = sorted(
                folder
                for folder in (root / "graphics").glob("*jacket*_ifs")
                if folder.is_dir()
            )
            folders.append(song_dirs + graphics_dirs)
        indices = (
            JACKET_INDICES[difficulty]
            if 0 <= difficulty < len(JACKET_INDICES)
            else (1,)
        )
        candidates = []
        for index in indices:
            for source in folders:
                for folder in source:
                    candidates.extend(
                        folder / f"jk_{mid}_{index}{suffix}.png"
                        for suffix in ("", "_b", "_s", "_t")
                    )
        for source in folders:
            for folder in source:
                candidates.extend(sorted(folder.glob(f"jk_{mid}_*.png")))
        for candidate in candidates:
            try:
                return candidate.read_bytes()
            except FileNotFoundError:
                continue
            except OSError as error:
                logger.debug("Cannot read jacket %s: %s", candidate, error)
        return None
