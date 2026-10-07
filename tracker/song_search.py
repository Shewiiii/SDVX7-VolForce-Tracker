import re
import unicodedata
from functools import lru_cache

from pykakasi import kakasi

from config import DIFF_NAMES
from tracker.music import MusicCatalog

_converter = kakasi()


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(
        chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char for char in text
    )
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if char.isalnum() or char in "\u3099\u309a"
    )


@lru_cache(maxsize=12000)
def _forms(text: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", text)
    forms = {_normalize(text)}
    # Only convert kana, the database supplies the readings of kanji names.
    for scheme in ("hepburn", "kunrei", "passport"):
        roman = re.sub(
            r"[\u3040-\u30ff]+",
            lambda match, scheme=scheme: "".join(
                part[scheme] for part in _converter.convert(match[0])
            ),
            text,
        )
        roman = _normalize(roman)
        forms.add(roman)
        forms.add(re.sub(r"aa|ii|uu|ee|oo|ou", lambda match: match[0][0], roman))
    return tuple(form for form in forms if form)


class SongSearch:
    def __init__(self, music: MusicCatalog):
        self.music = music
        self._signature = None
        self._entries = []

    def search(self, query: str, limit: int = 25) -> list[tuple[int, int]]:
        self.music.refresh()
        signature = tuple(
            id(mapping)
            for mapping in (
                self.music.titles,
                self.music.artists,
                self.music.levels,
                self.music.title_readings,
                self.music.artist_readings,
            )
        )
        if signature != self._signature:
            self._entries = [
                (
                    mid,
                    tuple(
                        _forms(mapping.get(mid, ""))
                        for mapping in (
                            self.music.titles,
                            self.music.title_readings,
                            self.music.artists,
                            self.music.artist_readings,
                        )
                    ),
                )
                for mid in self.music.levels
            ]
            self._signature = signature

        difficulty = None
        words = query.strip().split()
        if words:
            difficulty = next(
                (
                    index
                    for index, name in DIFF_NAMES.items()
                    if words[-1].casefold() == name.casefold()
                ),
                None,
            )
            if difficulty is not None:
                words.pop()
        tokens = [_normalize(word) for word in words if _normalize(word)]
        term = "".join(tokens)
        matches = []
        for mid, groups in self._entries:
            rank = (0, 0) if not tokens else None
            for priority, forms in enumerate(groups):
                matching = [
                    form for form in forms if all(token in form for token in tokens)
                ]
                if tokens and matching:
                    rank = (
                        priority,
                        min(
                            0 if form == term else 1 if form.startswith(term) else 2
                            for form in matching
                        ),
                    )
                    break
            if (
                rank is None
                and tokens
                and all(
                    any(token in form for forms in groups for form in forms)
                    for token in tokens
                )
            ):
                rank = (len(groups), 0)
            if rank is None:
                continue
            for index, level in self.music.levels[mid].items():
                if level > 0 and (difficulty is None or index == difficulty):
                    matches.append(
                        (rank, self.music.titles.get(mid, "").casefold(), mid, index)
                    )
        matches.sort(key=lambda item: (item[0], item[1], item[2], -item[3]))
        return [(mid, index) for _, _, mid, index in matches[:limit]]
