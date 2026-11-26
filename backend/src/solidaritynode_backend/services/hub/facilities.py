"""Facility import, validation, changesets and history (Spec 00 §3 Onboarding; DP-004).

Facilities are organisations, not people. An import is a file (CSV, XLSX or GeoPackage) in the
template of :data:`TEMPLATE` with **one row per facility and service**, for **one**
municipality whose base step is done. The flow:

1. **upload** (size, type and row limits) → the file is parsed; columns that look like personal
   data (names of staff or responsible persons, personal phone numbers or e-mails) are
   **dropped** and listed; other unknown columns are ignored and listed;
2. **validation report**: missing required fields, unknown services, wrong units, numbers,
   points outside the municipality, unknown ids, likely duplicates (same name in the
   municipality or within ``hub_duplicate_distance_m``), dropped columns and values;
3. **changeset preview**: facilities added, updated (field-level diff) and closed. Rows are
   matched by ``facility_id``, then by ``external_id``; otherwise a row is new. Facilities
   absent from the file are **not** closed unless the file is declared the complete list of the
   municipality (and the approval repeats how many will be closed);
4. **approve or reject** (administrators). Approval assigns stable ids (``HF-000001`` …, never
   reused), writes the curated features, closes with ``valid_to`` (never deletes) and writes a
   processing record. Every changeset keeps author, date, source and comment, so the history of
   every facility can be shown.

A manual edit through the admin form creates the same kind of changeset (kind ``manual``).
No external geocoding service is called: an address is stored as text only.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import sqlite3
import tempfile
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.gpkg import GeoPackageError, Srs, read_geopackage, write_geopackage
from solidaritynode_backend.messages import msg
from solidaritynode_backend.services.hub.common import (
    FACILITY_NOTE,
    QUALITY,
    Check,
    HubError,
    add_record,
    check,
    finish_record,
    jsonb,
    set_status,
)
from solidaritynode_backend.services.hub.sources import latest_sources, source_path
from solidaritynode_backend.services.hub.spreadsheet import Cell, csv_bytes, xlsx_bytes

__all__ = [
    "TEMPLATE",
    "DataVersionFeatureSource",
    "FeatureSource",
    "HubFeatureSource",
    "ImportRequest",
    "approve_changeset",
    "changeset_detail",
    "create_import",
    "facility_history",
    "list_changesets",
    "list_facilities",
    "manual_changeset",
    "manual_rows",
    "reject_changeset",
    "report_export",
    "template_file",
]


@dataclass(frozen=True)
class Column:
    """One column of the import template."""

    name: str
    required: bool
    en: str
    el: str
    facility_level: bool = True


TEMPLATE: tuple[Column, ...] = (
    Column(
        "facility_id",
        False,
        "Hub id of an existing facility (HF-…), to update it. Leave empty for a new facility.",
        "Κωδικός της κεντρικής εγκατάστασης για υπάρχουσα δομή (HF-…), για ενημέρωση. "
        "Κενό για νέα δομή.",
    ),
    Column(
        "external_id",
        False,
        "Your own or an official registry code of the facility (optional); used to match "
        "rows to facilities on later imports.",
        "Δικός σας ή επίσημος κωδικός μητρώου της δομής (προαιρετικό)· χρησιμοποιείται για "
        "την αντιστοίχιση σε επόμενες εισαγωγές.",
    ),
    Column(
        "name",
        True,
        "Name of the facility (an organisation, never a person).",
        "Όνομα της δομής (οργανισμός, ποτέ πρόσωπο).",
    ),
    Column(
        "municipality",
        True,
        "Municipality code, for example M-A. One municipality per file.",
        "Κωδικός δήμου, για παράδειγμα M-A. Ένας δήμος ανά αρχείο.",
    ),
    Column(
        "x",
        False,
        "Easting in the hub CRS (metres), with y. Or give lon and lat.",
        "Συντεταγμένη x στο σύστημα αναφοράς της κεντρικής εγκατάστασης (μέτρα), μαζί με y. "
        "Ή δώστε lon και lat.",
    ),
    Column(
        "y",
        False,
        "Northing in the hub CRS (metres), with x.",
        "Συντεταγμένη y (μέτρα), μαζί με x.",
    ),
    Column(
        "lon",
        False,
        "Longitude (WGS 84, degrees), with lat, if x and y are empty.",
        "Γεωγραφικό μήκος (WGS 84, μοίρες), μαζί με lat, αν τα x και y είναι κενά.",
    ),
    Column(
        "lat",
        False,
        "Latitude (WGS 84, degrees), with lon.",
        "Γεωγραφικό πλάτος (WGS 84, μοίρες), μαζί με lon.",
    ),
    Column(
        "address",
        False,
        "Street address, stored as text only (it is not geocoded: coordinates are required).",
        "Διεύθυνση, αποθηκεύεται μόνο ως κείμενο (δεν γεωκωδικοποιείται: οι συντεταγμένες "
        "είναι υποχρεωτικές).",
    ),
    Column(
        "facility_type",
        True,
        "Kind of facility, for example community_centre.",
        "Είδος δομής, για παράδειγμα community_centre.",
    ),
    Column(
        "service_id",
        True,
        "One service the facility offers (from the services list). One row per facility and "
        "service: repeat the facility columns on each row.",
        "Μία υπηρεσία που προσφέρει η δομή (από τον κατάλογο υπηρεσιών). Μία γραμμή ανά δομή "
        "και υπηρεσία: επαναλάβετε τα στοιχεία της δομής σε κάθε γραμμή.",
        facility_level=False,
    ),
    Column(
        "places",
        False,
        "Places for this service (a number, dot as decimal separator).",
        "Θέσεις για την υπηρεσία (αριθμός, τελεία για δεκαδικά).",
        facility_level=False,
    ),
    Column(
        "staff",
        False,
        "Staff for this service, in persons (a number).",
        "Προσωπικό για την υπηρεσία, σε άτομα (αριθμός).",
        facility_level=False,
    ),
    Column(
        "throughput",
        False,
        "Throughput for this service, in the service's unit per reference period (a number).",
        "Παραγωγικότητα για την υπηρεσία, στη μονάδα της υπηρεσίας ανά περίοδο αναφοράς (αριθμός).",
        facility_level=False,
    ),
    Column(
        "throughput_unit",
        False,
        "Unit of the throughput; must be the service's unit (for example appointment, hour). "
        "Required when throughput is given.",
        "Μονάδα της παραγωγικότητας· πρέπει να είναι η μονάδα της υπηρεσίας (για παράδειγμα "
        "appointment, hour). Υποχρεωτική όταν δίνεται παραγωγικότητα.",
        facility_level=False,
    ),
    Column(
        "operating_hours",
        False,
        "Opening hours as text, for example Mon-Fri 08:00-16:00.",
        "Ωράριο λειτουργίας ως κείμενο, για παράδειγμα Mon-Fri 08:00-16:00.",
    ),
    Column(
        "status",
        False,
        "open (default) or closed. closed closes an existing facility.",
        "open (προεπιλογή) ή closed. Το closed κλείνει μια υπάρχουσα δομή.",
    ),
    Column(
        "quality",
        True,
        "Data quality: open_data, estimated or verified_by_municipality.",
        "Ποιότητα δεδομένων: open_data (ανοιχτά δεδομένα), estimated (εκτίμηση) ή "
        "verified_by_municipality (επαληθευμένο από τον δήμο).",
    ),
    Column(
        "public_phone",
        False,
        "Public switchboard number of the facility. Never a personal or mobile number.",
        "Δημόσιο τηλέφωνο (τηλεφωνικό κέντρο) της δομής. Ποτέ προσωπικός ή κινητός αριθμός.",
    ),
    Column(
        "public_email",
        False,
        "Generic e-mail of the facility (for example info@…). Never a person's e-mail.",
        "Γενικό e-mail της δομής (για παράδειγμα info@…). Ποτέ e-mail προσώπου.",
    ),
    Column(
        "source",
        False,
        "Where the data comes from (register, survey, open data portal).",
        "Από πού προέρχονται τα στοιχεία (μητρώο, καταγραφή, πύλη ανοιχτών δεδομένων).",
    ),
    Column(
        "notes",
        False,
        "Free notes about the facility (no personal data).",
        "Ελεύθερες σημειώσεις για τη δομή (χωρίς προσωπικά δεδομένα).",
    ),
)
COLUMNS = tuple(c.name for c in TEMPLATE)
FACILITY_FIELDS = (
    "external_id",
    "name",
    "facility_type",
    "address",
    "operating_hours",
    "status",
    "quality",
    "public_phone",
    "public_email",
    "source",
    "notes",
)
NUMBERS = ("places", "staff", "throughput")
INSTRUCTIONS_EN = (
    "One row per facility and service. Facilities are organisations, not people: never enter "
    "names, personal phone numbers or personal e-mails of staff or responsible persons. "
    "Columns that look like personal data are dropped on import and listed in the validation "
    "report. Use a dot as decimal separator. Leave facility_id empty for new facilities; the "
    "hub assigns a permanent id. Facilities missing from a file are kept, unless you declare "
    "the file the complete list of the municipality."
)
INSTRUCTIONS_EL = (
    "Μία γραμμή ανά δομή και υπηρεσία. Οι δομές είναι οργανισμοί, όχι πρόσωπα: μην "
    "καταχωρίζετε ονόματα, προσωπικά τηλέφωνα ή προσωπικά e-mail εργαζομένων ή υπευθύνων. "
    "Στήλες που μοιάζουν με προσωπικά δεδομένα αφαιρούνται κατά την εισαγωγή και αναφέρονται "
    "στην αναφορά ελέγχου. Χρησιμοποιήστε τελεία για τα δεκαδικά. Αφήστε το facility_id κενό "
    "για νέες δομές· η κεντρική εγκατάσταση δίνει μόνιμο κωδικό. Δομές που λείπουν από ένα "
    "αρχείο διατηρούνται, εκτός αν δηλώσετε ότι το αρχείο είναι ο πλήρης κατάλογος του δήμου."
)

# Headers that look like personal data (normalised: lower case, no accents, "_" for spaces).
_PERSONAL = re.compile(
    r"(contact|responsible|director|manager|owner|staff_name|employee|person|first_?name|"
    r"last_?name|full_?name|surname|mobile|cell|personal|private|e_?mail|phone|tel|"
    r"υπευθυν|διευθυντ|προσωπ|υπαλληλ|ονομ|επωνυμ|επικοινων|κινητ|τηλεφων|ταυτοτ|αφμ|amka|afm)"
)
_MOBILE = re.compile(r"^(?:\+30|0030)?69\d{8}$")
_PERSONAL_EMAIL = re.compile(r"^[a-z]+[._][a-z]+@", re.IGNORECASE)
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_COMMA_DECIMAL = re.compile(r"^-?\d+,\d+$")
_ID = re.compile(r"^HF-\d{6}$")
EXTENSIONS = (".csv", ".xlsx", ".gpkg")


def _normalise_header(name: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(name).strip().lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", "_", plain)


def _normalise_name(name: str) -> str:
    return re.sub(r"\W+", " ", _normalise_header(name)).strip()


# --- Template ------------------------------------------------------------------------------


def _example_row(settings: Settings) -> list[Cell]:
    values = {
        "external_id": "REG-0001",
        "name": "Community centre (example)",
        "municipality": "M-A",
        "x": "133000.0",
        "y": "3881500.0",
        "facility_type": "community_centre",
        "service_id": "S-SD",
        "places": 10,
        "staff": 2,
        "throughput": 120,
        "throughput_unit": "appointment",
        "operating_hours": "Mon-Fri 08:00-16:00",
        "status": "open",
        "quality": "verified_by_municipality",
        "public_phone": "2100000000",
        "public_email": "info@example.org",
        "source": "Municipal register",
    }
    return [values.get(c, "") for c in COLUMNS]  # type: ignore[misc]


def template_file(settings: Settings, kind: str) -> tuple[bytes, str, str]:
    """Return the import template as ``(content, media type, file name)``.

    Args:
        settings: Settings (CRS of the GeoPackage template).
        kind: ``csv`` (header only), ``xlsx`` (header, an example row and an instructions
            sheet in Greek and English) or ``gpkg`` (an empty point table in the hub CRS).
    """
    if kind == "csv":
        return csv_bytes(COLUMNS, []), "text/csv", "facility-import-template.csv"
    if kind == "xlsx":
        instructions: list[Sequence[Cell]] = [
            ("(all)", "", INSTRUCTIONS_EN, INSTRUCTIONS_EL),
            *((c.name, "yes / ναι" if c.required else "no / όχι", c.en, c.el) for c in TEMPLATE),
        ]
        content = xlsx_bytes(
            [
                ("facilities", COLUMNS, [_example_row(settings)]),
                (
                    "instructions",
                    ("column / στήλη", "required / υποχρεωτικό", "description", "περιγραφή"),
                    instructions,
                ),
            ]
        )
        return (
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "facility-import-template.xlsx",
        )
    if kind == "gpkg":
        columns = [(c, "TEXT") for c in COLUMNS if c not in ("x", "y", "lon", "lat")]
        srs = Srs(settings.hub_crs, settings.hub_srid, "EPSG", settings.hub_srid, "undefined")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facilities.gpkg"
            write_geopackage(
                path,
                [srs],
                [
                    (
                        "facilities",
                        "POINT",
                        settings.hub_srid,
                        "Facility import template",
                        columns,
                        [],
                    )
                ],
                "2026-01-01T00:00:00.000Z",
            )
            return (
                path.read_bytes(),
                "application/geopackage+sqlite3",
                "facility-import-template.gpkg",
            )
    raise HubError("hub.import.unsupported_type", file=f"template.{kind}")


# --- Parsing -------------------------------------------------------------------------------


@dataclass
class Parsed:
    """Rows of an uploaded file, after dropping columns that are not in the template."""

    rows: list[tuple[int, dict[str, str]]]
    dropped: list[Check] = field(default_factory=list)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value).strip()


def _split_columns(header: Sequence[str]) -> tuple[dict[int, str], list[Check]]:
    keep: dict[int, str] = {}
    dropped: list[Check] = []
    for i, raw in enumerate(header):
        name = _normalise_header(raw)
        if not name:
            continue
        if name in COLUMNS:
            keep[i] = name
        elif _PERSONAL.search(name):
            dropped.append(check("hub.import.personal_column", "warning", column=str(raw).strip()))
        else:
            dropped.append(check("hub.import.unknown_column", "warning", column=str(raw).strip()))
    return keep, dropped


def _parse_table(table: Iterable[Sequence[object]], first_row: int = 2) -> Parsed:
    rows_iter = iter(table)
    header = next(rows_iter, None)
    if not header or not any(_cell(h) for h in header):
        raise HubError("hub.import.no_header")
    keep, dropped = _split_columns([_cell(h) for h in header])
    rows = []
    for n, values in enumerate(rows_iter, start=first_row):
        cells = {name: _cell(values[i]) if i < len(values) else "" for i, name in keep.items()}
        if any(cells.values()):
            rows.append((n, cells))
    return Parsed(rows, dropped)


def parse_file(settings: Settings, file_name: str, data: bytes) -> Parsed:
    """Parse an uploaded facility file (CSV, XLSX or GeoPackage).

    Raises:
        HubError: On an unsupported or unreadable file, a missing header, or too many rows.
    """
    suffix = Path(file_name).suffix.lower()
    if suffix not in EXTENSIONS:
        raise HubError("hub.import.unsupported_type", file=file_name)
    if not data:
        raise HubError("hub.source.empty")
    if suffix == ".csv":
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HubError("hub.import.not_utf8", file=file_name) from None
        header = content.splitlines()[0] if content else ""
        if ";" in header and "," not in header:
            raise HubError("hub.import.semicolon", file=file_name)
        try:
            parsed = _parse_table(csv.reader(io.StringIO(content, newline=""), strict=True))
        except csv.Error as exc:
            raise HubError("hub.import.unreadable", file=file_name, detail=str(exc)) from None
    elif suffix == ".xlsx":
        parsed = _parse_xlsx(file_name, data)
    else:
        parsed = _parse_gpkg(settings, file_name, data)
    if len(parsed.rows) > settings.hub_max_facility_rows:
        raise HubError("hub.import.too_many_rows", limit=settings.hub_max_facility_rows)
    if not parsed.rows:
        raise HubError("hub.import.no_rows", file=file_name)
    return parsed


def _parse_xlsx(file_name: str, data: bytes) -> Parsed:
    from openpyxl import load_workbook

    if not data.startswith(b"PK\x03\x04"):
        raise HubError("hub.import.unreadable", file=file_name, detail="not an XLSX workbook")
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many kinds of errors on a damaged file
        raise HubError("hub.import.unreadable", file=file_name, detail=type(exc).__name__) from None
    try:
        names = [n for n in workbook.sheetnames if n.lower() != "instructions"]
        sheet = (
            workbook["facilities"] if "facilities" in workbook.sheetnames else workbook[names[0]]
        )
        return _parse_table(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()


def _parse_gpkg(settings: Settings, file_name: str, data: bytes) -> Parsed:
    if not data.startswith(b"SQLite format 3\x00"):
        raise HubError("hub.import.unreadable", file=file_name, detail="not a GeoPackage")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.gpkg"
        path.write_bytes(data)
        try:
            layers = read_geopackage(path)
        except (GeoPackageError, sqlite3.Error) as exc:
            raise HubError("hub.import.unreadable", file=file_name, detail=str(exc)) from None
    layer = layers.get("facilities") or next(
        (lyr for lyr in layers.values() if lyr.geometry_type == "POINT"), None
    )
    if layer is None:
        raise HubError("hub.import.unreadable", file=file_name, detail="no point table")
    header = [c for c, _ in layer.columns]
    srid = layer.srs.organization_coordsys_id
    table: list[Sequence[object]] = [[*header, "x", "y", "_srid"]]
    for attrs, wkb in layer.rows:
        x = y = ""
        if wkb is not None and len(wkb) >= 21:
            import struct

            order = "<" if wkb[0] == 1 else ">"
            px, py = struct.unpack(f"{order}dd", wkb[5:21])
            x, y = repr(px), repr(py)
        table.append([*(attrs.get(c) for c in header), x, y, str(srid)])
    parsed = _parse_table(table)
    for (_, row), values in zip(parsed.rows, table[1:], strict=False):
        row["_srid"] = str(values[-1])
    return parsed


# --- Validation and changeset --------------------------------------------------------------


@dataclass(frozen=True)
class ImportRequest:
    """What a person states when uploading a facility file."""

    municipality_id: str
    source: str
    comment: str = ""
    licence: str = "CC-BY-4.0"
    attribution: str = ""
    complete_list: bool = False
    is_correction: bool = False


@dataclass
class _Facility:
    key: str
    rows: list[int]
    fields: dict[str, str]
    services: dict[str, dict[str, Any]]
    xy: tuple[float, float] | None = None
    facility_id: str | None = None
    matched_by: str | None = None
    unit_id: str | None = None
    node_id: str | None = None


def _number(value: str, row: int, column: str, report: list[Check]) -> float | None:
    if value == "":
        return None
    if _COMMA_DECIMAL.match(value):
        report.append(
            check("hub.import.comma_decimal", "error", row=row, column=column, value=value)
        )
        return None
    if not _NUMBER.match(value):
        report.append(check("hub.import.not_number", "error", row=row, column=column, value=value))
        return None
    number = float(value)
    if number < 0 or not math.isfinite(number):
        report.append(check("hub.import.negative", "error", row=row, column=column, value=value))
        return None
    return number


class FeatureSource(Protocol):
    """Where the validator reads municipalities, units, nodes, services and facilities.

    The same validation runs in both roles (ADR 0014 Part A, decision 23): the hub reads its
    curated features (:class:`HubFeatureSource`), a municipal installation the features of its
    active data version (:class:`DataVersionFeatureSource`). Only these reads differ.
    """

    srid: int

    def check_base(self, municipality: str) -> None:
        """Raise :class:`HubError` if facilities of ``municipality`` cannot be validated here."""
        ...

    def services(self) -> dict[str, str]:
        """Return the service unit of every known service."""
        ...

    def in_municipality(self, municipality: str, x: float, y: float) -> bool:
        """Return whether the point (in :attr:`srid`) lies in the municipality."""
        ...

    def unit_at(self, municipality: str, x: float, y: float) -> str | None:
        """Return the open spatial unit of the municipality that covers the point."""
        ...

    def nearest_node(self, x: float, y: float) -> str | None:
        """Return the nearest open network node."""
        ...

    def existing(self, municipality: str) -> dict[str, dict[str, Any]]:
        """Return the facilities of the municipality (open and closed), comparable state."""
        ...

    def municipality_of(self, facility_id: str) -> str | None:
        """Return the municipality of a facility anywhere in the source, or ``None``."""
        ...


_POINT = "ST_SetSRID(ST_MakePoint(:x, :y), :s)"


class HubFeatureSource:
    """The hub's curated features (``hub_features``) and its latest services source."""

    def __init__(self, db: Session, settings: Settings | None) -> None:
        """Read from ``db`` with the hub settings (``None``: only :meth:`existing` is used)."""
        self.db = db
        self.settings = settings
        self.srid = settings.hub_srid if settings is not None else 0

    def check_base(self, municipality: str) -> None:
        """The municipality must have base data (its base step succeeded)."""
        has_base = self.db.execute(
            text(
                "SELECT 1 FROM hub_features WHERE layer = 'municipalities' AND feature_id = :m "
                "AND EXISTS (SELECT 1 FROM hub_onboarding WHERE municipality_id = :m "
                "AND status <> 'not_started')"
            ),
            {"m": municipality},
        ).first()
        if not has_base:
            raise HubError("hub.error.not_onboarded", municipality=municipality)

    def services(self) -> dict[str, str]:
        """Services of the latest registered services source."""
        source = latest_sources(self.db).get("services")
        if source is None or self.settings is None:
            raise HubError("hub.base.missing_sources", layers="services")
        with source_path(self.settings, source).open(encoding="utf-8-sig", newline="") as handle:
            return {
                r["service_id"].strip(): r["service_unit"].strip()
                for r in csv.DictReader(handle)
                if r.get("service_id")
            }

    def _params(self, municipality: str, x: float, y: float) -> dict[str, Any]:
        return {"x": x, "y": y, "s": self.srid, "m": municipality}

    def in_municipality(self, municipality: str, x: float, y: float) -> bool:
        """Point in the curated boundary."""
        return bool(
            self.db.execute(
                text(
                    f"SELECT ST_Covers(geom, {_POINT}) FROM hub_features "
                    "WHERE layer = 'municipalities' AND feature_id = :m"
                ),
                self._params(municipality, x, y),
            ).scalar_one_or_none()
        )

    def unit_at(self, municipality: str, x: float, y: float) -> str | None:
        """Open unit covering the point."""
        found = self.db.execute(
            text(
                "SELECT feature_id FROM hub_features WHERE layer = 'spatial_units' "
                f"AND municipality_id = :m AND valid_to IS NULL AND ST_Covers(geom, {_POINT}) "
                "ORDER BY feature_id LIMIT 1"
            ),
            self._params(municipality, x, y),
        ).scalar_one_or_none()
        return None if found is None else str(found)

    def nearest_node(self, x: float, y: float) -> str | None:
        """Nearest open node."""
        found = self.db.execute(
            text(
                "SELECT feature_id FROM hub_features WHERE layer = 'network_nodes' "
                f"AND valid_to IS NULL ORDER BY geom <-> {_POINT} LIMIT 1"
            ),
            self._params("", x, y),
        ).scalar_one_or_none()
        return None if found is None else str(found)

    def existing(self, municipality: str) -> dict[str, dict[str, Any]]:
        """Curated facilities of the municipality."""
        out = {}
        for fid, props, quality, valid_to, x, y in self.db.execute(
            text(
                "SELECT feature_id, properties, quality, valid_to, ST_X(geom), ST_Y(geom) "
                "FROM hub_features WHERE layer = 'facilities' AND municipality_id = :m"
            ),
            {"m": municipality},
        ):
            out[str(fid)] = {
                **props,
                "quality": quality,
                "valid_to": valid_to.isoformat() if valid_to else None,
                "_xy": [round(float(x), 3), round(float(y), 3)],
            }
        return out

    def municipality_of(self, facility_id: str) -> str | None:
        """Municipality of any curated facility."""
        found = self.db.execute(
            text(
                "SELECT municipality_id FROM hub_features "
                "WHERE layer = 'facilities' AND feature_id = :f"
            ),
            {"f": facility_id},
        ).scalar_one_or_none()
        return None if found is None else str(found)


# Package columns that are not part of a facility's comparable state.
_PACKAGE_ONLY = ("municipality_id", "role", "processing_note", "valid_from", "_geometry_sha256")


class DataVersionFeatureSource:
    """The features of one imported data version of a municipal installation (ADR 0013).

    Facilities are made comparable with the hub's state: ``status`` from ``valid_to`` when the
    package has none, ``throughput_unit`` from the services table (packages carry no unit).
    Only the **core** municipalities of the version's study area can be validated (ADR 0014
    Part A, decision 25).
    """

    def __init__(self, db: Session, data_version_id: int) -> None:
        """Read the data version ``data_version_id``."""
        self.db = db
        self.dv = data_version_id
        row = db.execute(
            text("SELECT srid, manifest, created FROM data_versions WHERE id = :d"),
            {"d": data_version_id},
        ).one()
        self.srid = int(row.srid)
        self.created = row.created
        self.core = set(row.manifest.get("study_area", {}).get("core_municipalities", []))

    def check_base(self, municipality: str) -> None:
        """Only core municipalities of the installation's study area."""
        if municipality not in self.core:
            raise HubError("hub.submission.not_core", municipality=municipality)

    def services(self) -> dict[str, str]:
        """Services of the data version (``tables/services.csv``)."""
        return {
            str(p["service_id"]): str(p["service_unit"])
            for (p,) in self.db.execute(
                text(
                    "SELECT properties FROM data_records WHERE data_version_id = :d "
                    "AND table_name = 'services'"
                ),
                {"d": self.dv},
            )
        }

    def _open(self, alias: str = "f") -> str:
        return (
            f"({alias}.properties->>'valid_to' IS NULL OR "
            f"CAST({alias}.properties->>'valid_to' AS date) > :created)"
        )

    def _params(self, municipality: str, x: float, y: float) -> dict[str, Any]:
        return {
            "x": x,
            "y": y,
            "s": self.srid,
            "m": municipality,
            "d": self.dv,
            "created": self.created,
        }

    def in_municipality(self, municipality: str, x: float, y: float) -> bool:
        """Point in the package boundary."""
        return bool(
            self.db.execute(
                text(
                    f"SELECT ST_Covers(geom, {_POINT}) FROM data_features WHERE "
                    "data_version_id = :d AND layer = 'municipalities' AND feature_id = :m"
                ),
                self._params(municipality, x, y),
            ).scalar_one_or_none()
        )

    def unit_at(self, municipality: str, x: float, y: float) -> str | None:
        """Open unit covering the point."""
        found = self.db.execute(
            text(
                "SELECT feature_id FROM data_features f WHERE data_version_id = :d "
                "AND layer = 'spatial_units' AND properties->>'municipality_id' = :m "
                f"AND {self._open()} AND ST_Covers(geom, {_POINT}) ORDER BY feature_id LIMIT 1"
            ),
            self._params(municipality, x, y),
        ).scalar_one_or_none()
        return None if found is None else str(found)

    def nearest_node(self, x: float, y: float) -> str | None:
        """Nearest open node."""
        found = self.db.execute(
            text(
                "SELECT feature_id FROM data_features f WHERE data_version_id = :d "
                f"AND layer = 'network_nodes' AND {self._open()} "
                f"ORDER BY geom <-> {_POINT} LIMIT 1"
            ),
            self._params("", x, y),
        ).scalar_one_or_none()
        return None if found is None else str(found)

    def existing(self, municipality: str) -> dict[str, dict[str, Any]]:
        """Facilities of the municipality in the package, as the hub would describe them."""
        units = self.services()
        out = {}
        for fid, props, x, y in self.db.execute(
            text(
                "SELECT feature_id, properties, ST_X(geom), ST_Y(geom) FROM data_features "
                "WHERE data_version_id = :d AND layer = 'facilities' "
                "AND properties->>'municipality_id' = :m"
            ),
            {"d": self.dv, "m": municipality},
        ):
            state = {k: v for k, v in props.items() if k not in _PACKAGE_ONLY}
            services = {}
            for sid, inputs in (props.get("services") or {}).items():
                services[sid] = {c: inputs.get(c) for c in NUMBERS}
                services[sid]["throughput_unit"] = (
                    units.get(sid) if inputs.get("throughput") is not None else None
                )
            state["services"] = services
            state["status"] = props.get("status") or ("closed" if props.get("valid_to") else "open")
            for key in (*DIFF_FIELDS, "valid_to"):
                state.setdefault(key, None)
            state["_xy"] = [round(float(x), 3), round(float(y), 3)]
            out[str(fid)] = state
        return out

    def municipality_of(self, facility_id: str) -> str | None:
        """Municipality of any facility of the data version."""
        found = self.db.execute(
            text(
                "SELECT properties->>'municipality_id' FROM data_features "
                "WHERE data_version_id = :d AND layer = 'facilities' AND feature_id = :f"
            ),
            {"d": self.dv, "f": facility_id},
        ).scalar_one_or_none()
        return None if found is None else str(found)


def _group(rows: list[tuple[int, dict[str, str]]], report: list[Check]) -> list[_Facility]:
    facilities: dict[str, _Facility] = {}
    for n, row in rows:
        key = (
            f"id:{row['facility_id']}"
            if row.get("facility_id")
            else f"ext:{row['external_id']}"
            if row.get("external_id")
            else f"name:{_normalise_name(row.get('name', ''))}:{row.get('x', '')}"
            f":{row.get('y', '')}"
            f":{row.get('lon', '')}:{row.get('lat', '')}"
        )
        facility = facilities.get(key)
        fields = {
            f: row.get(f, "")
            for f in (
                *FACILITY_FIELDS,
                "facility_id",
                "municipality",
                "x",
                "y",
                "lon",
                "lat",
                "_srid",
            )
        }
        if facility is None:
            facility = _Facility(key, [], fields, {})
            facilities[key] = facility
        else:
            for name, value in fields.items():
                if value and facility.fields.get(name) and value != facility.fields[name]:
                    report.append(check("hub.import.inconsistent", "error", row=n, column=name))
                elif value and not facility.fields.get(name):
                    facility.fields[name] = value
        facility.rows.append(n)
        service = row.get("service_id", "")
        if service:
            if service in facility.services:
                report.append(
                    check("hub.import.duplicate_service", "error", row=n, service=service)
                )
            facility.services[service] = {
                "row": n,
                **{c: row.get(c, "") for c in (*NUMBERS, "throughput_unit")},
            }
    return list(facilities.values())


def _validate_rows(
    rows: list[tuple[int, dict[str, str]]],
    services: Mapping[str, str],
    municipality: str,
    report: list[Check],
) -> None:
    for n, row in rows:
        for column in (c.name for c in TEMPLATE if c.required):
            if not row.get(column):
                report.append(check("hub.import.required", "error", row=n, column=column))
        if row.get("municipality") and row["municipality"] != municipality:
            report.append(
                check(
                    "hub.import.other_municipality",
                    "error",
                    row=n,
                    value=row["municipality"],
                    municipality=municipality,
                )
            )
        service = row.get("service_id", "")
        if service and service not in services:
            report.append(check("hub.import.unknown_service", "error", row=n, service=service))
        for column in NUMBERS:
            _number(row.get(column, ""), n, column, report)
        unit = row.get("throughput_unit", "")
        if row.get("throughput") and not unit:
            report.append(check("hub.import.required", "error", row=n, column="throughput_unit"))
        elif unit and service in services and unit != services[service]:
            report.append(
                check(
                    "hub.import.wrong_unit",
                    "error",
                    row=n,
                    unit=unit,
                    service=service,
                    expected=services[service],
                )
            )
        if row.get("quality") and row["quality"] not in QUALITY:
            report.append(check("hub.import.bad_quality", "error", row=n, value=row["quality"]))
        if row.get("status") and row["status"] not in ("open", "closed"):
            report.append(check("hub.import.bad_status", "error", row=n, value=row["status"]))
        phone = re.sub(r"[\s\-()./]", "", row.get("public_phone", ""))
        if phone and _MOBILE.match(phone):
            row["public_phone"] = ""
            report.append(
                check("hub.import.personal_value", "warning", row=n, column="public_phone")
            )
        if row.get("public_email") and _PERSONAL_EMAIL.match(row["public_email"]):
            row["public_email"] = ""
            report.append(
                check("hub.import.personal_value", "warning", row=n, column="public_email")
            )


def _coordinates(
    db: Session, source: FeatureSource, facility: _Facility, report: list[Check]
) -> None:
    f = facility.fields
    first = facility.rows[0]
    srid = int(f.get("_srid") or source.srid)
    if f.get("x") and f.get("y"):
        xs, ys = f["x"], f["y"]
    elif f.get("lon") and f.get("lat"):
        xs, ys, srid = f["lon"], f["lat"], 4326
    else:
        report.append(check("hub.import.no_coordinates", "error", row=first))
        return
    if not (_NUMBER.match(xs) and _NUMBER.match(ys)):
        report.append(
            check("hub.import.not_number", "error", row=first, column="x/y", value=f"{xs} {ys}")
        )
        return
    x, y = db.execute(
        text(
            "SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), "
            ":s), :h) AS p) q"
        ),
        {"x": float(xs), "y": float(ys), "s": srid, "h": source.srid},
    ).one()
    facility.xy = (float(x), float(y))


def _locate(
    source: FeatureSource, facility: _Facility, municipality: str, report: list[Check]
) -> None:
    if facility.xy is None:
        return
    x, y = facility.xy
    if not source.in_municipality(municipality, x, y):
        report.append(
            check(
                "hub.import.outside_municipality",
                "error",
                row=facility.rows[0],
                municipality=municipality,
            )
        )
        return
    facility.unit_id = source.unit_at(municipality, x, y)
    if facility.unit_id is None:
        report.append(
            check("hub.import.no_unit", "error", row=facility.rows[0], municipality=municipality)
        )
    facility.node_id = source.nearest_node(x, y)


def _existing(db: Session, municipality: str) -> dict[str, dict[str, Any]]:
    """Curated facilities of a hub municipality (used by approval's stale check)."""
    return HubFeatureSource(db, None).existing(municipality)


def _state(facility: _Facility, current: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the facility's state after this import (the changeset's ``after``)."""
    f = facility.fields
    services = {}
    for sid, s in sorted(facility.services.items()):
        services[sid] = {
            c: (float(s[c]) if _NUMBER.match(s.get(c, "") or "") else None) for c in NUMBERS
        }
        services[sid]["throughput_unit"] = s.get("throughput_unit") or None
    state: dict[str, Any] = {
        "name": f.get("name", ""),
        "facility_type": f.get("facility_type", ""),
        "external_id": f.get("external_id") or None,
        "address": f.get("address") or None,
        "operating_hours": f.get("operating_hours") or None,
        "status": f.get("status") or "open",
        "quality": f.get("quality", ""),
        "public_phone": f.get("public_phone") or None,
        "public_email": f.get("public_email") or None,
        "source": f.get("source") or None,
        "notes": f.get("notes") or None,
        "services": services,
        "unit_id": facility.unit_id,
        "node_id": facility.node_id,
        "_xy": [round(facility.xy[0], 3), round(facility.xy[1], 3)] if facility.xy else None,
    }
    if current is not None and not services:
        state["services"] = current.get("services", {})
    return state


DIFF_FIELDS = (
    "name",
    "facility_type",
    "external_id",
    "address",
    "operating_hours",
    "status",
    "quality",
    "public_phone",
    "public_email",
    "source",
    "notes",
    "unit_id",
    "node_id",
)


def diff_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Return the fields that differ, services as ``services.<id>.<input>``."""
    out = [f for f in DIFF_FIELDS if before.get(f) != after.get(f)]
    if before.get("_xy") != after.get("_xy"):
        out.append("location")
    old, new = before.get("services") or {}, after.get("services") or {}
    for sid in sorted(set(old) | set(new)):
        if sid not in new:
            out.append(f"services.{sid} (removed)")
        elif sid not in old:
            out.append(f"services.{sid} (added)")
        else:
            out.extend(
                f"services.{sid}.{c}"
                for c in (*NUMBERS, "throughput_unit")
                if old[sid].get(c) != new[sid].get(c)
            )
    return out


def _public(props: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in props.items() if k not in ("facility_id", "valid_to")}


def _match_and_items(
    source: FeatureSource,
    settings: Settings,
    facilities: list[_Facility],
    request: ImportRequest,
    report: list[Check],
) -> list[dict[str, Any]]:
    existing = source.existing(request.municipality_id)
    by_external = {
        str(p["external_id"]): fid for fid, p in existing.items() if p.get("external_id")
    }
    items: list[dict[str, Any]] = []
    matched: set[str] = set()
    for facility in facilities:
        f = facility.fields
        first = facility.rows[0]
        if f.get("facility_id"):
            fid = f["facility_id"]
            if fid not in existing:
                other = source.municipality_of(fid)
                code = "hub.import.id_other_municipality" if other else "hub.import.unknown_id"
                report.append(
                    check(code, "error", row=first, id=fid, municipality=request.municipality_id)
                )
                continue
            facility.facility_id, facility.matched_by = fid, "facility_id"
        elif f.get("external_id") and f["external_id"] in by_external:
            facility.facility_id = by_external[f["external_id"]]
            facility.matched_by = "external_id"
            report.append(
                check(
                    "hub.import.matched_external",
                    "info",
                    row=first,
                    id=facility.facility_id,
                    external_id=f["external_id"],
                )
            )
        if facility.facility_id:
            if facility.facility_id in matched:
                report.append(
                    check("hub.import.matched_twice", "error", row=first, id=facility.facility_id)
                )
            matched.add(facility.facility_id)
        current = existing.get(facility.facility_id or "")
        after = _state(facility, current)
        label = after["name"] or facility.facility_id or f"row {first}"
        if current is None:
            if after["status"] == "closed":
                report.append(check("hub.import.new_closed", "error", row=first))
                continue
            items.append(
                {
                    "action": "add",
                    "facility_id": None,
                    "label": label,
                    "rows": facility.rows,
                    "before": None,
                    "after": after,
                    "fields": [],
                }
            )
            continue
        before = _public(current)
        if after["status"] == "closed" or current.get("valid_to"):
            if current.get("valid_to") is None:
                items.append(
                    {
                        "action": "close",
                        "facility_id": facility.facility_id,
                        "label": label,
                        "rows": facility.rows,
                        "before": before,
                        "after": None,
                        "fields": [],
                    }
                )
            continue
        fields = diff_fields(before, after)
        if fields:
            items.append(
                {
                    "action": "update",
                    "facility_id": facility.facility_id,
                    "label": label,
                    "rows": facility.rows,
                    "before": before,
                    "after": after,
                    "fields": fields,
                }
            )
    if request.complete_list:
        for fid, props in sorted(existing.items()):
            if fid not in matched and props.get("valid_to") is None:
                items.append(
                    {
                        "action": "close",
                        "facility_id": fid,
                        "label": props.get("name", fid),
                        "rows": [],
                        "before": _public(props),
                        "after": None,
                        "fields": [],
                    }
                )
    _duplicates(settings, items, existing, report)
    return items


def _duplicates(
    settings: Settings,
    items: list[dict[str, Any]],
    existing: Mapping[str, Mapping[str, Any]],
    report: list[Check],
) -> None:
    """Warn about likely duplicates: same name in the municipality, or closer than the limit."""
    others = [
        (fid, str(p.get("name", "")), p.get("_xy"))
        for fid, p in existing.items()
        if p.get("valid_to") is None
    ]
    new = [(i, it) for i, it in enumerate(items) if it["action"] == "add"]
    limit = settings.hub_duplicate_distance_m
    for i, item in new:
        name = _normalise_name(item["after"]["name"])
        xy = item["after"].get("_xy")
        candidates = [*others]
        candidates += [
            (f"row {other['rows'][0]}", other["after"]["name"], other["after"].get("_xy"))
            for j, other in new
            if j < i
        ]
        for other_id, other_name, other_xy in candidates:
            row = item["rows"][0] if item["rows"] else 0
            if name and _normalise_name(other_name) == name:
                report.append(
                    check("hub.import.duplicate_name", "warning", row=row, other=other_id)
                )
            elif xy and other_xy and math.dist(xy, other_xy) <= limit:
                report.append(
                    check(
                        "hub.import.duplicate_near",
                        "warning",
                        row=row,
                        other=other_id,
                        distance=round(math.dist(xy, other_xy), 1),
                    )
                )


def build_changeset(
    db: Session,
    settings: Settings,
    request: ImportRequest,
    parsed: Parsed,
    source: FeatureSource | None = None,
) -> tuple[list[dict[str, Any]], list[Check]]:
    """Validate parsed rows and return the changeset items and the report (nothing written).

    Args:
        db: Session.
        settings: Settings (duplicate distance).
        request: The municipality and options of the import.
        parsed: Rows of the file, personal-data columns already dropped.
        source: Where features are read: the hub's curated features (default) or a municipal
            installation's active data version (ADR 0014 Part A).
    """
    source = source or HubFeatureSource(db, settings)
    report: list[Check] = list(parsed.dropped)
    source.check_base(request.municipality_id)
    services = source.services()
    _validate_rows(parsed.rows, services, request.municipality_id, report)
    facilities = _group(parsed.rows, report)
    for facility in facilities:
        _coordinates(db, source, facility, report)
        _locate(source, facility, request.municipality_id, report)
    items = _match_and_items(source, settings, facilities, request, report)
    return items, report


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {a: sum(1 for i in items if i["action"] == a) for a in ("add", "update", "close")}


def create_import(
    db: Session,
    settings: Settings,
    request: ImportRequest,
    file_name: str,
    data: bytes,
    user_id: int | None,
    *,
    kind: str = "import",
    parsed: Parsed | None = None,
) -> int:
    """Validate a file and store the pending changeset with its report; return its id.

    Raises:
        HubError: If the file cannot be read at all (the report is shown otherwise).
    """
    if not request.source.strip():
        raise HubError("hub.source.field_required", field="source")
    if len(data) > settings.hub_max_facility_file_mb * 1024 * 1024:
        raise HubError("hub.source.too_large", status=413, limit=settings.hub_max_facility_file_mb)
    parsed = parsed or parse_file(settings, file_name, data)
    items, report = build_changeset(db, settings, request, parsed)
    sha = hashlib.sha256(data).hexdigest()
    summary = _summary(items)
    if request.complete_list:
        report.append(
            check(
                "hub.import.complete_list",
                "warning",
                count=summary["close"],
                municipality=request.municipality_id,
            )
        )
    errors = sum(1 for c in report if c["severity"] == "error")
    stored_report = {
        "file": file_name,
        "sha256": sha,
        "rows": len(parsed.rows),
        "facilities": len({tuple(i["rows"]) for i in items}),
        "entries": report,
        "errors": errors,
        "warnings": sum(1 for c in report if c["severity"] == "warning"),
        "summary": summary,
    }
    changeset_id = int(
        db.execute(
            text(
                "INSERT INTO hub_changesets (kind, municipality_id, source, comment, licence, "
                "attribution, file_name, file_sha256, complete_list, is_correction, report, "
                "created_by) VALUES (:k, :m, :s, :c, :l, :a, :f, :sha, :cl, :corr, "
                "CAST(:r AS jsonb), :u) RETURNING id"
            ),
            {
                "k": kind,
                "m": request.municipality_id,
                "s": request.source,
                "c": request.comment,
                "l": request.licence,
                "a": request.attribution or request.source,
                "f": file_name,
                "sha": sha,
                "cl": request.complete_list,
                "corr": request.is_correction,
                "r": jsonb(stored_report),
                "u": user_id,
            },
        ).scalar_one()
    )
    for n, item in enumerate(items, start=1):
        db.execute(
            text(
                "INSERT INTO hub_changeset_items (changeset_id, item_no, action, facility_id, "
                "label, rows, before, after, fields) VALUES (:c, :n, :a, :f, :l, :r, "
                "CAST(:b AS jsonb), CAST(:af AS jsonb), :fi)"
            ),
            {
                "c": changeset_id,
                "n": n,
                "a": item["action"],
                "f": item["facility_id"],
                "l": item["label"],
                "r": item["rows"],
                "b": jsonb(item["before"]) if item["before"] is not None else None,
                "af": jsonb(item["after"]) if item["after"] is not None else None,
                "fi": item["fields"],
            },
        )
    if kind == "import":
        target = (
            settings.hub_storage_dir
            / "imports"
            / f"{changeset_id:06d}-{sha[:12]}{Path(file_name).suffix.lower()}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return changeset_id


def manual_rows(
    current: Mapping[str, Any] | None,
    municipality_id: str,
    facility_id: str | None,
    values: Mapping[str, Any],
    services: Sequence[Mapping[str, Any]],
    close: bool,
) -> list[tuple[int, dict[str, str]]]:
    """Turn an edit form into template rows (one per service), in both roles.

    Every field the form leaves out keeps the facility's current value (``current``, a state
    from a :class:`FeatureSource`), including its location and services.
    """
    base = {c: "" for c in COLUMNS}
    current_services: dict[str, dict[str, Any]] = {}
    if current is not None:
        base.update({k: _cell(current.get(k)) for k in FACILITY_FIELDS})
        base["quality"] = str(current.get("quality") or "")
        xy = current.get("_xy") or ["", ""]
        base.update({"x": _cell(xy[0]), "y": _cell(xy[1])})
        current_services = dict(current.get("services") or {})
    base.update({k: _cell(v) for k, v in values.items() if k in COLUMNS})
    base["facility_id"] = facility_id or ""
    base["municipality"] = municipality_id
    if close:
        base["status"] = "closed"
    chosen = list(services) or [
        {"service_id": sid, **inputs} for sid, inputs in sorted(current_services.items())
    ]
    rows: list[tuple[int, dict[str, str]]] = []
    for n, service in enumerate(chosen or [{}], start=1):
        row = dict(base)
        row.update({k: _cell(v) for k, v in service.items() if k in COLUMNS})
        rows.append((n, row))
    return rows


def manual_changeset(
    db: Session,
    settings: Settings,
    municipality_id: str,
    facility_id: str | None,
    values: Mapping[str, Any],
    services: Sequence[Mapping[str, Any]],
    close: bool,
    comment: str,
    user_id: int,
) -> int:
    """Create a pending changeset from the admin form (add, update or close one facility).

    The form is turned into template rows and validated exactly like an imported file. For an
    existing facility, every field the form leaves out keeps its current value (including its
    location and services).

    Raises:
        HubError: If ``facility_id`` does not exist.
    """
    current = None
    if facility_id:
        current = HubFeatureSource(db, settings).existing(municipality_id).get(facility_id)
        if current is None:
            raise HubError("hub.error.facility_not_found", status=404, id=facility_id)
    rows = manual_rows(current, municipality_id, facility_id, values, services, close)
    request = ImportRequest(
        municipality_id, source="manual edit", comment=comment, attribution="Manual edit in the hub"
    )
    return create_import(
        db,
        settings,
        request,
        "manual-edit",
        b"manual",
        user_id,
        kind="manual",
        parsed=Parsed(rows),
    )


def _changeset_row(db: Session, changeset_id: int, lock: bool = False) -> RowMapping:
    row = (
        db.execute(
            text(
                "SELECT c.*, u.username AS created_by_name, d.username AS decided_by_name "
                "FROM hub_changesets c LEFT JOIN users u ON u.id = c.created_by "
                "LEFT JOIN users d ON d.id = c.decided_by WHERE c.id = :id"
                + (" FOR UPDATE OF c" if lock else "")
            ),
            {"id": changeset_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HubError("hub.error.changeset_not_found", status=404, id=changeset_id)
    return row


def changeset_detail(db: Session, changeset_id: int) -> dict[str, Any]:
    """Return a changeset with its report and items (the preview)."""
    row = dict(_changeset_row(db, changeset_id))
    row["summary"] = row["report"].get("summary")
    row["errors"] = row["report"].get("errors")
    row["items"] = [
        dict(i)
        for i in db.execute(
            text(
                "SELECT item_no, action, facility_id, label, rows, before, after, fields, "
                "conflict, resolution "
                "FROM hub_changeset_items WHERE changeset_id = :c ORDER BY item_no"
            ),
            {"c": changeset_id},
        ).mappings()
    ]
    return row


def list_changesets(db: Session, municipality_id: str | None = None) -> list[dict[str, Any]]:
    """Return changesets (newest first), optionally of one municipality."""
    return [
        dict(r)
        for r in db.execute(
            text(
                "SELECT c.id, c.kind, c.municipality_id, c.status, c.source, c.comment, "
                "c.file_name, c.complete_list, c.is_correction, c.created_at, c.decided_at, "
                "u.username AS created_by_name, d.username AS decided_by_name, "
                "c.report->'summary' AS summary, (c.report->>'errors')::int AS errors "
                "FROM hub_changesets c LEFT JOIN users u ON u.id = c.created_by "
                "LEFT JOIN users d ON d.id = c.decided_by "
                "WHERE (CAST(:m AS text) IS NULL OR c.municipality_id = :m) ORDER BY c.id DESC"
            ),
            {"m": municipality_id},
        ).mappings()
    ]


def approve_changeset(
    db: Session,
    settings: Settings,
    changeset_id: int,
    user_id: int,
    comment: str = "",
    confirm_close: int | None = None,
    resolutions: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    """Apply a pending changeset to the curated facilities (administrators).

    Args:
        db: Session (the caller commits).
        settings: Settings.
        changeset_id: The changeset.
        user_id: Hub administrator.
        comment: Decision comment (returned to a submitting municipality).
        confirm_close: Number of closures, required for a complete list.
        resolutions: For each conflicting item of a municipal submission (ADR 0014 A8), by
            item number: ``municipality`` (apply the proposed change) or ``hub`` (keep the
            hub's value: the item is not applied).

    Raises:
        HubError: If it is not pending, its report has errors, a "complete list" closure is not
            confirmed with the number of facilities to close, a conflict is not resolved, or a
            facility changed since the preview (upload the file again).
    """
    cs = _changeset_row(db, changeset_id, lock=True)
    if cs["status"] != "pending":
        raise HubError(
            "hub.error.changeset_decided", status=409, id=changeset_id, state=cs["status"]
        )
    if int(cs["report"].get("errors", 0)):
        raise HubError("hub.import.has_errors", status=409, id=changeset_id)
    items = changeset_detail(db, changeset_id)["items"]
    closing = sum(1 for i in items if i["action"] == "close")
    if cs["complete_list"] and confirm_close != closing:
        raise HubError(
            "hub.import.confirm_close",
            status=409,
            count=closing,
            municipality=cs["municipality_id"],
        )
    chosen = {int(k): v for k, v in (resolutions or {}).items()}
    for item in items:
        if not item.get("conflict"):
            continue
        choice = chosen.get(int(item["item_no"]))
        if choice not in ("municipality", "hub"):
            raise HubError("hub.submission.unresolved_conflicts", status=409, id=changeset_id)
        db.execute(
            text(
                "UPDATE hub_changeset_items SET resolution = :r "
                "WHERE changeset_id = :c AND item_no = :n"
            ),
            {"r": choice, "c": changeset_id, "n": item["item_no"]},
        )
        item["resolution"] = choice
    existing = _existing(db, str(cs["municipality_id"]))
    today = datetime.now(UTC).date()
    ids: dict[str, list[str]] = {"added": [], "updated": [], "closed": [], "kept": []}
    for item in items:
        fid = item["facility_id"]
        if item.get("resolution") == "hub":
            ids["kept"].append(fid)
            continue
        if item["action"] != "add" and _public(existing.get(fid, {})) != item["before"]:
            raise HubError("hub.import.stale", status=409, id=fid)
        if item["action"] == "add":
            n = int(db.execute(text("SELECT nextval('hub_facility_id_seq')")).scalar_one())
            fid = f"HF-{n:06d}"
            _write_facility(db, fid, str(cs["municipality_id"]), item["after"], today, insert=True)
            db.execute(
                text(
                    "UPDATE hub_changeset_items SET facility_id = :f "
                    "WHERE changeset_id = :c AND item_no = :n"
                ),
                {"f": fid, "c": changeset_id, "n": item["item_no"]},
            )
            ids["added"].append(fid)
        elif item["action"] == "update":
            _write_facility(db, fid, str(cs["municipality_id"]), item["after"], today, insert=False)
            ids["updated"].append(fid)
        else:
            db.execute(
                text(
                    "UPDATE hub_features SET valid_to = :d, updated_at = now(), "
                    "properties = jsonb_set(properties, '{status}', '\"closed\"') "
                    "WHERE layer = 'facilities' AND feature_id = :f"
                ),
                {"d": today, "f": fid},
            )
            ids["closed"].append(fid)
    record_id = add_record(
        db,
        "facility_changeset",
        note=FACILITY_NOTE,
        municipality_id=str(cs["municipality_id"]),
        inputs=[
            {
                "changeset_id": changeset_id,
                "kind": cs["kind"],
                "file_name": cs["file_name"],
                "sha256": cs["file_sha256"],
                "source": cs["source"],
                "licence": cs["licence"],
                "attribution": cs["attribution"],
            }
        ],
        parameters={
            "complete_list": cs["complete_list"],
            "is_correction": cs["is_correction"],
            "duplicate_distance_m": settings.hub_duplicate_distance_m,
            "crs": settings.hub_crs,
        },
        user_id=user_id,
    )
    changed = any(ids[k] for k in ("added", "updated", "closed"))
    finish_record(
        db,
        record_id,
        status="succeeded",
        outputs=ids,
        checks=[c for c in cs["report"].get("entries", []) if c["severity"] != "info"],
        affected=[str(cs["municipality_id"])] if changed else [],
        changed=changed,
        summary=msg(
            "hub.import.summary",
            changeset=changeset_id,
            municipality=cs["municipality_id"],
            added=len(ids["added"]),
            updated=len(ids["updated"]),
            closed=len(ids["closed"]),
        ),
    )
    db.execute(
        text(
            "UPDATE hub_changesets SET status = 'approved', decided_by = :u, decided_at = now(), "
            "decision_comment = :c, record_id = :r WHERE id = :id"
        ),
        {"u": user_id, "c": comment, "r": record_id, "id": changeset_id},
    )
    set_status(
        db,
        str(cs["municipality_id"]),
        "facilities_in_progress",
        user_id,
        msg("hub.import.status_note", changeset=changeset_id),
        only_from=("base_ready",),
    )
    return {"changeset_id": changeset_id, "record_id": record_id, **ids}


def _write_facility(
    db: Session,
    fid: str,
    municipality: str,
    after: Mapping[str, Any],
    today: date,
    *,
    insert: bool,
) -> None:
    props = {k: v for k, v in after.items() if k not in ("quality", "_xy")}
    props["facility_id"] = fid
    params = {
        "f": fid,
        "m": municipality,
        "p": jsonb(props),
        "q": after["quality"],
        "x": after["_xy"][0],
        "y": after["_xy"][1],
        "d": today,
        "n": FACILITY_NOTE,
    }
    geom = (
        "ST_SetSRID(ST_MakePoint(:x, :y), (SELECT ST_SRID(geom) FROM hub_features "
        "WHERE layer = 'municipalities' AND feature_id = :m))"
    )
    if insert:
        db.execute(
            text(
                "INSERT INTO hub_features (layer, feature_id, municipality_id, properties, geom, "
                f"quality, processing_note, valid_from) VALUES ('facilities', :f, :m, "
                f"CAST(:p AS jsonb), {geom}, :q, :n, :d)"
            ),
            params,
        )
    else:
        db.execute(
            text(
                "UPDATE hub_features SET properties = CAST(:p AS jsonb), "
                f"geom = {geom}, quality = :q, updated_at = now() "
                "WHERE layer = 'facilities' AND feature_id = :f"
            ),
            params,
        )


def reject_changeset(db: Session, changeset_id: int, user_id: int, comment: str) -> None:
    """Reject a pending changeset (nothing is applied; it stays in the history)."""
    cs = _changeset_row(db, changeset_id, lock=True)
    if cs["status"] != "pending":
        raise HubError(
            "hub.error.changeset_decided", status=409, id=changeset_id, state=cs["status"]
        )
    db.execute(
        text(
            "UPDATE hub_changesets SET status = 'rejected', decided_by = :u, decided_at = now(), "
            "decision_comment = :c WHERE id = :id"
        ),
        {"u": user_id, "c": comment, "id": changeset_id},
    )


def list_facilities(db: Session, municipality_id: str | None) -> list[dict[str, Any]]:
    """Return the curated facilities (open and closed), optionally of one municipality."""
    return [
        {
            **dict(r),
            "valid_from": r["valid_from"].isoformat(),
            "valid_to": r["valid_to"].isoformat() if r["valid_to"] else None,
        }
        for r in db.execute(
            text(
                "SELECT feature_id AS facility_id, municipality_id, properties, quality, "
                "valid_from, valid_to, ST_X(geom) AS x, ST_Y(geom) AS y FROM hub_features "
                "WHERE layer = 'facilities' AND (CAST(:m AS text) IS NULL OR municipality_id = :m) "
                "ORDER BY feature_id"
            ),
            {"m": municipality_id},
        ).mappings()
    ]


def facility_history(db: Session, facility_id: str) -> list[dict[str, Any]]:
    """Return every approved change of a facility, oldest first, with author, date and source.

    Raises:
        HubError: If the facility does not exist.
    """
    exists = db.execute(
        text("SELECT 1 FROM hub_features WHERE layer = 'facilities' AND feature_id = :f"),
        {"f": facility_id},
    ).first()
    if not exists:
        raise HubError("hub.error.facility_not_found", status=404, id=facility_id)
    return [
        dict(r)
        for r in db.execute(
            text(
                "SELECT c.id AS changeset_id, c.kind, i.action, i.fields, i.before, i.after, "
                "c.source, c.comment, c.file_name, c.created_at, u.username AS created_by_name, "
                "c.decided_at, d.username AS decided_by_name, c.decision_comment "
                "FROM hub_changeset_items i JOIN hub_changesets c ON c.id = i.changeset_id "
                "LEFT JOIN users u ON u.id = c.created_by LEFT JOIN users d ON d.id = c.decided_by "
                "WHERE i.facility_id = :f AND c.status = 'approved' "
                "AND i.resolution IS DISTINCT FROM 'hub' ORDER BY c.decided_at, c.id"
            ),
            {"f": facility_id},
        ).mappings()
    ]


# --- Exports -------------------------------------------------------------------------------

REPORT_COLUMNS = ("severity", "row", "column", "code", "message")


def report_export(db: Session, changeset_id: int, kind: str) -> tuple[bytes, str, str]:
    """Return the validation report of a changeset as CSV or XLSX (formulas escaped)."""
    cs = _changeset_row(db, changeset_id)
    rows: list[Sequence[Cell]] = [
        (
            e["severity"],
            e["params"].get("row", ""),
            e["params"].get("column", ""),
            e["code"],
            e["message"],
        )
        for e in cs["report"].get("entries", [])
    ]
    name = f"changeset-{changeset_id}-report"
    if kind == "xlsx":
        return (
            xlsx_bytes([("report", REPORT_COLUMNS, rows)]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{name}.xlsx",
        )
    return csv_bytes(REPORT_COLUMNS, rows), "text/csv", f"{name}.csv"


def facilities_export(db: Session, municipality_id: str, kind: str) -> tuple[bytes, str, str]:
    """Return the open facilities of a municipality in the import template (to extend them).

    Each facility and service is one row with its hub id, so the file can be edited and
    imported again. Text cells are escaped against formulas.
    """
    rows: list[Sequence[Cell]] = []
    for f in list_facilities(db, municipality_id):
        if f["valid_to"]:
            continue
        p = f["properties"]
        for sid, s in sorted((p.get("services") or {"": {}}).items()):
            values: dict[str, Cell] = {
                "facility_id": f["facility_id"],
                "municipality": municipality_id,
                "x": round(float(f["x"]), 1),
                "y": round(float(f["y"]), 1),
                "quality": f["quality"],
                "service_id": sid,
                **{k: p.get(k) for k in FACILITY_FIELDS if k != "quality"},
                **{k: s.get(k) for k in (*NUMBERS, "throughput_unit")},
            }
            rows.append([values.get(c) for c in COLUMNS])
    name = f"facilities-{municipality_id}"
    if kind == "xlsx":
        return (
            xlsx_bytes([("facilities", COLUMNS, rows)]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{name}.xlsx",
        )
    return csv_bytes(COLUMNS, rows), "text/csv", f"{name}.csv"
