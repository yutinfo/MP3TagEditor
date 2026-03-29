import os
import re
from mimetypes import guess_type
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TCON, TDRC, TIT2, TPE1, TRCK


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


@dataclass(frozen=True)
class MP3TreeEntry:
    kind: str
    path: str
    relative_path: str
    parent_relative: str
    name: str
    depth: int


@dataclass(frozen=True)
class CoverArt:
    mime: str
    data: bytes
    description: str = "Cover"
    picture_type: int = 3


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


def list_mp3_tree(folder: str) -> List[MP3TreeEntry]:
    if not os.path.isdir(folder):
        return []
    return _walk_mp3_tree(folder, "", 0)


def _walk_mp3_tree(current_dir: str, relative_dir: str, depth: int) -> List[MP3TreeEntry]:
    entries: List[MP3TreeEntry] = []

    try:
        with os.scandir(current_dir) as scan:
            children = sorted(
                list(scan),
                key=lambda entry: (
                    not entry.is_dir(follow_symlinks=False),
                    entry.name.lower(),
                ),
            )
    except OSError:
        return entries

    directories = []
    mp3_files = []

    for child in children:
        try:
            if child.is_dir(follow_symlinks=False):
                directories.append(child)
            elif child.is_file(follow_symlinks=False) and child.name.lower().endswith(".mp3"):
                mp3_files.append(child)
        except OSError:
            continue

    for directory in directories:
        child_relative = os.path.join(relative_dir, directory.name) if relative_dir else directory.name
        descendant_entries = _walk_mp3_tree(directory.path, child_relative, depth + 1)
        if not descendant_entries:
            continue

        entries.append(
            MP3TreeEntry(
                kind="folder",
                path=directory.path,
                relative_path=child_relative,
                parent_relative=relative_dir,
                name=directory.name,
                depth=depth,
            )
        )
        entries.extend(descendant_entries)

    for mp3_file in mp3_files:
        file_relative = os.path.join(relative_dir, mp3_file.name) if relative_dir else mp3_file.name
        entries.append(
            MP3TreeEntry(
                kind="file",
                path=mp3_file.path,
                relative_path=file_relative,
                parent_relative=relative_dir,
                name=mp3_file.name,
                depth=depth,
            )
        )

    return entries


def get_cover_art(file_path: str) -> Optional[CoverArt]:
    try:
        tags = ID3(file_path)
    except (ID3NoHeaderError, Exception):
        return None

    pictures = tags.getall("APIC")
    if not pictures:
        return None

    picture = next((frame for frame in pictures if frame.type == 3), pictures[0])
    return CoverArt(
        mime=picture.mime or "image/jpeg",
        data=bytes(picture.data),
        description=picture.desc or "Cover",
        picture_type=int(picture.type),
    )


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


def _read_cover_image(image_path: str) -> Tuple[bytes, str]:
    mime, _ = guess_type(image_path)
    if mime not in {"image/jpeg", "image/png"}:
        raise ValueError("Only JPG and PNG cover images are supported")

    with open(image_path, "rb") as image_file:
        return image_file.read(), mime


def set_cover_art(file_path: str, image_data: bytes, mime: str) -> None:
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()

    tags.delall("APIC")
    tags.add(
        APIC(
            encoding=3,
            mime=mime,
            type=3,
            desc="Cover",
            data=image_data,
        )
    )
    tags.save(file_path)


def remove_cover_art(file_path: str) -> None:
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        return

    tags.delall("APIC")
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


def save_tag_drafts_to_files(
    file_drafts: Mapping[str, Dict[str, str]]
) -> Tuple[int, List[Tuple[str, str]]]:
    saved_count = 0
    errors: List[Tuple[str, str]] = []

    for file_path, form_data in file_drafts.items():
        try:
            save_tags(file_path, form_data)
            saved_count += 1
        except Exception as exc:
            errors.append((file_path, str(exc)))

    return saved_count, errors


def apply_cover_to_files(
    file_paths: Sequence[str], image_path: str
) -> Tuple[int, List[Tuple[str, str]]]:
    updated_count = 0
    errors: List[Tuple[str, str]] = []

    image_data, mime = _read_cover_image(image_path)

    for file_path in file_paths:
        try:
            set_cover_art(file_path, image_data, mime)
            updated_count += 1
        except Exception as exc:
            errors.append((file_path, str(exc)))

    return updated_count, errors


def remove_cover_from_files(file_paths: Sequence[str]) -> Tuple[int, List[Tuple[str, str]]]:
    updated_count = 0
    errors: List[Tuple[str, str]] = []

    for file_path in file_paths:
        try:
            remove_cover_art(file_path)
            updated_count += 1
        except Exception as exc:
            errors.append((file_path, str(exc)))

    return updated_count, errors


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


def rename_mp3_file(file_path: str, new_name: str) -> str:
    clean_name = new_name.strip()
    if not clean_name:
        raise ValueError("Rename value cannot be empty")

    invalid_chars = set('<>:"/\\|?*')
    if any(char in invalid_chars for char in clean_name):
        raise ValueError('Filename contains invalid characters: <>:"/\\|?*')

    folder = os.path.dirname(file_path)
    _, extension = os.path.splitext(file_path)
    extension = extension or ".mp3"
    new_path = os.path.join(folder, clean_name + extension)

    if os.path.normcase(new_path) == os.path.normcase(file_path):
        return file_path
    if os.path.exists(new_path):
        raise FileExistsError("A file with this name already exists")

    os.rename(file_path, new_path)
    return new_path
