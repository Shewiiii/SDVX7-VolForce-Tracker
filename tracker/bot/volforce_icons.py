import logging
import math
from bisect import bisect_right
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image

from config import GAME_ROOT

logger = logging.getLogger("sdvx_bot")

CLASS_THRESHOLDS = (0, 10, 12, 14, 15, 16, 17, 18, 19, 20)
CLASS_NAMES = (
    "Sienna",
    "Cobalt",
    "Dandelion",
    "Cyan",
    "Scarlet",
    "Coral",
    "Argento",
    "Eldora",
    "Crimson",
    "Imperial",
)
CLASS_RANK_STEPS = (2.5, 0.5, 0.5, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 1)


def get_volforce_class(value: float | None) -> tuple[int, str] | None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    index = bisect_right(CLASS_THRESHOLDS, value) - 1
    rank_index = min(
        3, int((value - CLASS_THRESHOLDS[index]) / CLASS_RANK_STEPS[index])
    )
    rank = ("I", "II", "III", "IV")[rank_index]
    return index + 1, f"{CLASS_NAMES[index]} {rank}"


def _center_icon(png: bytes) -> bytes:
    with Image.open(BytesIO(png)) as source:
        icon = source.convert("RGBA")
    bounds = icon.getchannel("A").getbbox()
    if bounds is None:
        return png
    icon = icon.crop(bounds)
    padding = max(1, round(max(icon.size) * 0.05))
    side = max(icon.size) + 2 * padding
    canvas = Image.new("RGBA", (side, side))
    canvas.paste(icon, ((side - icon.width) // 2, (side - icon.height) // 2))
    result = BytesIO()
    canvas.save(result, format="PNG")
    return result.getvalue()


@lru_cache(maxsize=30)
def _load_class_icon(
    path: Path, class_number: int, modified_ns: int, size: int
) -> bytes | None:
    """Cache decoded PNGs until the source archive changes."""
    try:
        from ifstools import IFS

        archive = IFS(str(path), super_disable=True)
        try:
            textures = {texture.name: texture for texture in archive.tree.all_files}
            for name in (
                f"em6_s{class_number:02d}_i_eab.png",
                f"em6_{class_number:02d}_i_eab.png",
                f"emblem_{class_number:02d}w_i_eab.png",
                f"emblem_{class_number:02d}_i_eab.png",
            ):
                if name in textures:
                    return _center_icon(textures[name].load(crop_to_uvrect=True))
        finally:
            archive.close()
    except ImportError:
        logger.warning("Install requirements.txt to read VolForce class icons.")
    except Exception as error:  # noqa: BLE001
        logger.warning("Could not read VolForce class icon from %s: %s", path, error)
    return None


def find_volforce_class_icon(value: float | None) -> bytes | None:
    volforce_class = get_volforce_class(value)
    if volforce_class is None:
        return None
    class_number = volforce_class[0]
    graphics = GAME_ROOT / "data" / "graphics"
    for folder in sorted(graphics.glob("ver[0-9][0-9]"), reverse=True):
        path = folder / "force.ifs"
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        except OSError as error:
            logger.debug("Could not inspect VolForce artwork %s: %s", path, error)
            continue
        icon = _load_class_icon(path, class_number, stat.st_mtime_ns, stat.st_size)
        if icon:
            return icon
    return None
