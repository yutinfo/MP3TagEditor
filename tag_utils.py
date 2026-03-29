import os
import re
from typing import Dict, Iterable, List, Sequence, Tuple

from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TCON, TDRC, TIT2, TPE1, TRCK


FRAME_MAP = {
    "title": ("TIT2", TIT2),
    "artist": ("TPE1", TPE1),
    "album": ("TALB", TALB),
    "year": ("TDRC", TDRC),
    "track": ("TRCK", TRCK),
    "genre": ("TCON", TCON),
}

# Thai Unicode block: U+0E00–U+0E7F
_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")


def _try_fix_thai_encoding(text: str) -> str:
    """Fix cp874/TIS-620 text incorrectly stored as Latin-1 in old ID3 tags.

    Some Thai software (e.g. old WinAMP players) writes tags with encoding=0
    (Latin-1) but stores cp874 bytes. Mutagen returns garbled Latin-1 strings.
    We detect this and re-decode from cp874.
    """
    if not text or _THAI_RE.search(text):
        return text  # already correct UTF-8/Unicode Thai, nothing to do
    try:
        raw = text.encode("latin-1")
        fixed = raw.decode("cp874")
        if _THAI_RE.search(fixed):
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text


def list_mp3_files(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        return []

    files = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.lower().endswith(".mp3") and os.path.isfile(os.path.join(folder, name))
    ]
    return sorted(files, key=lambda path: os.path.basename(path).lower())


def _frame_text(tags: ID3, frame_id: str) -> str:
    frame = tags.get(frame_id)
    if frame is None:
        return ""
    try:
        if hasattr(frame, "text") and frame.text:
            return _try_fix_thai_encoding(str(frame.text[0]).strip())
    except Exception:
        pass
    return ""


def load_mp3_tags(file_path: str) -> Dict[str, str]:
    """Read ID3 tags without writing to disk. Returns empty strings if no tags."""
    _empty: Dict[str, str] = {
        "title": "", "artist": "", "album": "", "year": "", "track": "", "genre": ""
    }
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        return _empty
    except Exception:
        return _empty
    return {
        "title": _frame_text(tags, "TIT2"),
        "artist": _frame_text(tags, "TPE1"),
        "album": _frame_text(tags, "TALB"),
        "year": _frame_text(tags, "TDRC"),
        "track": _frame_text(tags, "TRCK"),
        "genre": _frame_text(tags, "TCON"),
    }


def save_tags(file_path: str, form_data: Dict[str, str]) -> None:
    """Write non-empty fields to the file's ID3 tags using UTF-8 encoding."""
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()

    for key, value in form_data.items():
        if not value:
            continue
        frame_id, frame_cls = FRAME_MAP[key]
        tags.setall(frame_id, [frame_cls(encoding=3, text=[value])])

    tags.save(file_path)


def save_tags_to_files(
    file_paths: Sequence[str], form_data: Dict[str, str]
) -> Tuple[int, List[Tuple[str, str]]]:
    saved_count = 0
    errors: List[Tuple[str, str]] = []

    for file_path in file_paths:
        try:
            save_tags(file_path, form_data)
            saved_count += 1
        except Exception as exc:
            errors.append((file_path, str(exc)))

    return saved_count, errors


def build_title_from_filename(filename: str) -> str:
    stem, _ = os.path.splitext(filename)
    cleaned = re.sub(r"^\d+[\s\.\-_]+", "", stem).strip()
    return cleaned or stem.strip()


def fill_titles_from_filenames(
    file_paths: Iterable[str],
) -> Tuple[int, List[Tuple[str, str]]]:
    updated_count = 0
    errors: List[Tuple[str, str]] = []

    for file_path in file_paths:
        try:
            title = build_title_from_filename(os.path.basename(file_path))
            save_tags(file_path, {"title": title})
            updated_count += 1
        except Exception as exc:
            errors.append((file_path, str(exc)))

    return updated_count, errors
