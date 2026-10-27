"""Compatibility facade delegating the former ODB2VTK interface to Converter."""

import os

from .converter import Converter
from .errors import SelectionError
from .models import Selection
from .outputs import OutputOptions, ensure_directory
from .source import AbaqusSource, ReadableOdb


def _console_progress(event):
    print("{0} file completed.".format(event.path))


class ODB2VTK(object):
    """Preserve script/library entry points while Converter owns export logic."""

    def __init__(self, fileFullName, suffix, source=None):
        self.fileFullName = fileFullName
        self.odbFileName = os.path.basename(fileFullName)
        self.odbPath = os.path.dirname(fileFullName)
        self._outputs = OutputOptions.from_odb(fileFullName, suffix, write_pvd=False)
        self.odbFileNameNoExt = self._outputs.run_name
        self._owns_source = source is None
        source = AbaqusSource.open(fileFullName) if source is None else source
        self._converter = Converter(source, progress=_console_progress)
        self._selection = None

    @property
    def source(self):
        return self._converter.source

    @property
    def odb(self):
        return ReadableOdb.from_source(self.source)

    def close(self):
        if self._owns_source:
            self.source.close()

    def __enter__(self):
        if self.source.closed:
            raise RuntimeError("ODB source is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def ReadArgs(self, instanceNames, stepsFramesDict):
        self._selection = Selection(instanceNames, stepsFramesDict)

    def _selected(self):
        if self._selection is None:
            raise SelectionError(
                "Provide a selection with ReadArgs before legacy export"
            )
        return self._selection

    def ConstructMap(self):
        """Validate the request; exports prepare their own mesh automatically."""
        self._converter.validate_frames(self._selected(), self._outputs)

    def ExtractHeader(self):
        return self._converter.export_header(self._outputs)

    def WriteVTUFiles(self):
        return self._converter.export_frames(self._selected(), self._outputs)

    def WriteVTUFile(self, args):
        step, frame = args
        selection = Selection(self._selected().instances, ((step, (frame,)),))
        return self._converter.export_frames(selection, self._outputs)

    def WritePVDFile(self):
        return self._converter.export_collection(self._selected(), self._outputs)

    def WriteCSVFILE(self):
        return self._converter.export_history(self._selected(), self._outputs)

    def GetExportFileName(self, filName):
        path = self._outputs.artifact_path(filName)
        ensure_directory(self._outputs.data_directory)
        return path
