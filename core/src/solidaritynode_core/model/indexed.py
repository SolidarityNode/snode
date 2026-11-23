"""Container for values indexed by the unit of analysis (Paper 4 §3; ADR 0003).

:class:`IndexedValues` is a thin, immutable, typed wrapper over :class:`xarray.DataArray`.
It allows only the named dimensions of :class:`~solidaritynode_core.model.notation.Dim`,
requires unique coordinate labels, supports dimensions being **absent** where a paper omits
them (for example ``SS_{i,g,s}`` has no time dimension), and refuses operations that the
specification forbids, such as summing over services (OQ-24).

It is a data structure only; it implements no model.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from types import MappingProxyType

import numpy as np
import numpy.typing as npt
import xarray as xr

from solidaritynode_core.model.notation import Dim

__all__ = ["DimensionMismatchError", "IndexedValues"]


class DimensionMismatchError(ValueError):
    """Raised when indexed values are not aligned on shared dimensions."""


class IndexedValues:
    """Immutable labelled array over a subset of :class:`Dim` (Paper 4 §3; ADR 0003).

    Args:
        values: Array whose axes follow ``coords`` in order.
        coords: Ordered mapping ``Dim -> labels``; its keys are the dimensions present.
        name: Name of the quantity, preferably a variable of the catalogue
            (:mod:`solidaritynode_core.model.catalogue`).
        attrs: Free metadata, for example ``{"unit": "visit", "period": "P1M"}``.

    Raises:
        ValueError: If a dimension is repeated, labels are not unique, or the shape does not
            match the coordinates.
    """

    __slots__ = ("_data",)

    _data: xr.DataArray

    def __init__(
        self,
        values: npt.ArrayLike,
        coords: Mapping[Dim, Sequence[Hashable]],
        *,
        name: str,
        attrs: Mapping[str, str] | None = None,
    ) -> None:
        """Build and validate the container."""
        dims = tuple(Dim(d) for d in coords)
        if len(set(dims)) != len(dims):
            raise ValueError("dimensions must be unique")
        array = np.array(values, copy=True)
        expected_shape = tuple(len(coords[d]) for d in dims)
        if array.shape != expected_shape:
            raise ValueError(f"shape {array.shape} does not match coordinates {expected_shape}")
        for dim in dims:
            labels = list(coords[dim])
            if len(set(labels)) != len(labels):
                raise ValueError(f"labels of dimension {dim.value!r} must be unique")
        array.setflags(write=False)
        data = xr.DataArray(
            array,
            dims=[d.value for d in dims],
            coords={d.value: list(coords[d]) for d in dims},
            name=name,
            attrs=dict(attrs or {}),
        )
        object.__setattr__(self, "_data", data)

    def __setattr__(self, key: str, value: object) -> None:
        """Forbid mutation."""
        raise AttributeError("IndexedValues is immutable")

    @classmethod
    def from_dataarray(cls, data: xr.DataArray) -> IndexedValues:
        """Wrap an existing DataArray after validating its dimensions.

        Args:
            data: Array whose dimension names are values of :class:`Dim`.

        Returns:
            A validated, independent copy.
        """
        coords = {Dim(str(d)): list(data.coords[d].values) for d in data.dims}
        return cls(
            data.values,
            coords,
            name=str(data.name) if data.name is not None else "",
            attrs={str(k): str(v) for k, v in data.attrs.items()},
        )

    @property
    def name(self) -> str:
        """Return the quantity name."""
        return str(self._data.name)

    @property
    def dims(self) -> tuple[Dim, ...]:
        """Return the dimensions present, in axis order."""
        return tuple(Dim(str(d)) for d in self._data.dims)

    @property
    def attrs(self) -> Mapping[str, str]:
        """Return read-only metadata."""
        return MappingProxyType(dict(self._data.attrs))

    def has(self, dim: Dim) -> bool:
        """Return whether ``dim`` is present."""
        return dim.value in self._data.dims

    def labels(self, dim: Dim) -> tuple[Hashable, ...]:
        """Return the labels of ``dim``.

        Raises:
            KeyError: If the dimension is absent.
        """
        if not self.has(dim):
            raise KeyError(dim.value)
        return tuple(self._data.coords[dim.value].values.tolist())

    def to_numpy(self) -> npt.NDArray[np.generic]:
        """Return a read-only NumPy view of the values."""
        return self._data.values

    def to_dataarray(self) -> xr.DataArray:
        """Return a deep copy as an :class:`xarray.DataArray` (for library interop)."""
        return self._data.copy(deep=True)

    def sel(self, **labels: Hashable) -> IndexedValues:
        """Select single labels by dimension name, dropping those dimensions.

        Example: ``values.sel(unit="U1", service="S1")``.
        """
        for key in labels:
            Dim(key)
        return IndexedValues.from_dataarray(self._data.sel(labels))

    def check_aligned(self, other: IndexedValues) -> None:
        """Check that shared dimensions carry identical labels in identical order.

        Raises:
            DimensionMismatchError: If any shared dimension differs.
        """
        for dim in set(self.dims) & set(other.dims):
            if self.labels(dim) != other.labels(dim):
                raise DimensionMismatchError(
                    f"dimension {dim.value!r} differs between {self.name!r} and {other.name!r}"
                )

    def sum_over(self, dim: Dim) -> IndexedValues:
        """Sum over one dimension.

        Summing over :attr:`Dim.SERVICE` is refused, because quantities of different services
        are never summed (OQ-24). Summing over :attr:`Dim.GROUP` is refused because groups may
        overlap and overlap handling is open (OQ-6).

        Raises:
            ValueError: For the forbidden dimensions above.
            KeyError: If the dimension is absent.
        """
        if dim is Dim.SERVICE:
            raise ValueError("quantities of different services are never summed (OQ-24)")
        if dim is Dim.GROUP:
            raise ValueError("groups may overlap; summing over groups is undefined (OQ-6)")
        if not self.has(dim):
            raise KeyError(dim.value)
        return IndexedValues.from_dataarray(self._data.sum(dim=dim.value, keep_attrs=True))

    def __repr__(self) -> str:
        """Return a short description."""
        shape = ", ".join(f"{d.value}={len(self.labels(d))}" for d in self.dims)
        return f"IndexedValues({self.name!r}, {shape})"
