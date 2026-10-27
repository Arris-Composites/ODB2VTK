"""Immutable output policy and publication through temporary sibling files."""

from collections import namedtuple
from contextlib import contextmanager
import os
import re
import tempfile

from .errors import OutputError


def _leaf(name):
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or name.endswith((".", " "))
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or name.split(".")[0].upper()
        in (
            ("CON", "PRN", "AUX", "NUL")
            + tuple("COM{0}".format(i) for i in range(1, 10))
            + tuple("LPT{0}".format(i) for i in range(1, 10))
        )
    ):
        raise OutputError("Invalid output filename: {0!r}".format(name))
    return name


class OutputOptions(namedtuple("_OutputOptions", "directory name suffix write_pvd")):
    """Write data under directory/(name+suffix), matching the existing layout."""

    __slots__ = ()

    def __new__(cls, directory, name, suffix="", write_pvd=True):
        try:
            directory = os.path.abspath(os.fsdecode(os.fspath(directory)))
        except (TypeError, ValueError):
            raise OutputError("Output directory must be a filesystem path")
        if "\x00" in directory:
            raise OutputError("Output directory cannot contain NUL characters")
        _leaf(name)
        if not isinstance(suffix, str):
            raise OutputError("Output suffix must be a string")
        _leaf(name + suffix)
        if not isinstance(write_pvd, bool):
            raise OutputError("write_pvd must be a boolean")
        return super(OutputOptions, cls).__new__(
            cls, directory, name, suffix, write_pvd
        )

    @classmethod
    def from_odb(cls, path, suffix="", write_pvd=True):
        path = os.fsdecode(os.fspath(path))
        # Retain the existing first-dot naming policy during this migration.
        return cls(
            os.path.dirname(path) or os.curdir,
            os.path.basename(path).split(".")[0],
            suffix,
            write_pvd,
        )

    @property
    def run_name(self):
        return self.name + self.suffix

    @property
    def data_directory(self):
        return os.path.join(self.directory, self.run_name)

    @property
    def header_path(self):
        return os.path.join(self.directory, self.run_name + ".json")

    @property
    def collection_path(self):
        return self.artifact_path(self.run_name + ".pvd")

    @property
    def history_path(self):
        return self.artifact_path(self.run_name + ".csv")

    def artifact_path(self, filename):
        return os.path.join(self.data_directory, _leaf(filename))

    def frame_path(self, step, frame):
        return self.artifact_path(step + "_" + str(frame) + ".vtu")


def validate_destinations(paths):
    """Reject known path conflicts before conversion without creating files."""
    paths = tuple(paths)
    identities = [os.path.normcase(os.path.abspath(path)) for path in paths]
    if len(set(identities)) != len(identities):
        raise OutputError("Requested output filenames collide")
    for path in paths:
        if os.path.isdir(path):
            raise OutputError("Output file is a directory: {0}".format(path))
        parent = os.path.dirname(path)
        while parent and not os.path.exists(parent):
            previous = parent
            parent = os.path.dirname(parent)
            if parent == previous:
                break
        if parent and not os.path.isdir(parent):
            raise OutputError("Output parent is not a directory: {0}".format(parent))


def ensure_directory(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as error:
        raise OutputError("Cannot create output directory {0}: {1}".format(path, error))


@contextmanager
def atomic_output(path):
    """Publish a complete file or preserve the previous destination on failure.

    Publication is atomic per file, not a transaction across an export request.
    Temporary files live beside the destination so replacement stays on the
    same filesystem. Final paths are not truncated before serialization succeeds.
    """
    ensure_directory(os.path.dirname(path))
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".odb2vtk-",
            suffix=".tmp",
            dir=os.path.dirname(path),
        )
    except OSError as error:
        raise OutputError("Cannot prepare output {0}: {1}".format(path, error))
    try:
        with os.fdopen(descriptor, "w") as stream:
            yield stream
        try:
            os.replace(temporary, path)
        except OSError as error:
            raise OutputError("Cannot publish output {0}: {1}".format(path, error))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
