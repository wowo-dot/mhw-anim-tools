"""Small binary reader utilities used by format parsers."""

from __future__ import annotations

import struct

from ..diagnostics.errors import BinaryFormatError


class BinaryReader:
    """Minimal little-endian oriented reader over immutable bytes."""

    def __init__(self, data: bytes, source_name: str = "<memory>") -> None:
        self._data = memoryview(data)
        self._offset = 0
        self.source_name = source_name

    @property
    def size(self) -> int:
        return len(self._data)

    def tell(self) -> int:
        return self._offset

    def seek(self, offset: int) -> None:
        if offset < 0 or offset > self.size:
            raise BinaryFormatError(
                "Seek outside file bounds",
                source_name=self.source_name,
                offset=offset,
                file_size=self.size,
            )
        self._offset = offset

    def align(self, alignment: int) -> None:
        if alignment <= 0:
            raise ValueError("alignment must be positive")
        aligned = (self._offset + (alignment - 1)) & ~(alignment - 1)
        self.seek(aligned)

    def remaining(self) -> int:
        return self.size - self._offset

    def read(self, size: int) -> bytes:
        if size < 0:
            raise ValueError("size must be non-negative")
        end = self._offset + size
        if end > self.size:
            raise BinaryFormatError(
                "Unexpected end of file",
                source_name=self.source_name,
                offset=self._offset,
                requested_size=size,
                file_size=self.size,
            )
        chunk = self._data[self._offset:end].tobytes()
        self._offset = end
        return chunk

    def read_struct(self, fmt: struct.Struct):
        values = self._unpack_at(self._offset, fmt)
        self._offset += fmt.size
        return values

    def _unpack_at(self, offset: int, fmt: struct.Struct):
        if offset + fmt.size > len(self._data):
            raise BinaryFormatError(
                "Unexpected end of file",
                source_name=self.source_name,
                offset=offset,
                requested_size=fmt.size,
                file_size=len(self._data),
            )
        # unpack_from reads the existing buffer without allocating an intermediate
        # bytes object for each track header / interpolation basis.
        return fmt.unpack_from(self._data, offset)

    def read_struct_at(self, offset: int, fmt: struct.Struct):
        if offset < 0 or offset > len(self._data):
            raise BinaryFormatError(
                "Seek outside file bounds",
                source_name=self.source_name,
                offset=offset,
                file_size=len(self._data),
            )
        return self._unpack_at(offset, fmt)

    def slice(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > self.size:
            raise BinaryFormatError(
                "Slice outside file bounds",
                source_name=self.source_name,
                offset=offset,
                requested_size=size,
                file_size=self.size,
            )
        return self._data[offset:offset + size].tobytes()
