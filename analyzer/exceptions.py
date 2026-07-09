class BSAError(Exception):
    """Base class for all application-specific errors — lets the GUI
    catch 'expected' problems (bad file, missing parser) separately from
    truly unexpected bugs, and show the user a clean message either way."""


class ParserNotFoundError(BSAError):
    pass


class ParseError(BSAError):
    """Raised for a single unparsable row/cell. Carries context so the
    error shown to the user says *where* it happened, not just what."""
    def __init__(self, message, filepath=None, row=None, column=None):
        self.filepath, self.row, self.column = filepath, row, column
        context = [p for p in (
            f"file={filepath}" if filepath else None,
            f"row={row}" if row is not None else None,
            f"column={column}" if column else None,
        ) if p]
        full = message + (f" ({', '.join(context)})" if context else "")
        super().__init__(full)


class DuplicateImportError(BSAError):
    pass