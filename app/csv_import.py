"""Bounded RFC-style comma-separated import with explicit schema conversion."""

import csv
import io
from math import isfinite
from pydantic import BaseModel, ConfigDict, Field


class CSVPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_text: str = Field(min_length=1, max_length=2097152)


def parse_csv(text):
    try:
        reader = csv.reader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        headers = next(reader, None)
        if not headers:
            raise ValueError("CSV needs a header and at least one data row.")
        headers = [header.strip() for header in headers]
        if len(headers) > 50 or any(not h or len(h) > 200 for h in headers):
            raise ValueError("Use 1–50 named columns, each at most 200 characters.")
        if len(set(headers)) != len(headers):
            raise ValueError("Column names must be unique after trimming spaces.")
        rows = []
        for line, values in enumerate(reader, start=2):
            if not values:
                continue
            if len(values) != len(headers):
                raise ValueError(
                    f"CSV record {line} has {len(values)} cells; expected {len(headers)}. Check quoting and commas."
                )
            if any(len(v) > 10000 for v in values):
                raise ValueError(
                    f"CSV record {line} has a cell exceeding 10000 characters."
                )
            rows.append(dict(zip(headers, values)))
            if len(rows) > 10000:
                raise ValueError(
                    "CSV has more than 10000 data records. Split your dataset."
                )
        if not rows:
            raise ValueError(
                "CSV needs at least one data record; a header alone is not enough."
            )
        return headers, rows
    except csv.Error as exc:
        raise ValueError("Invalid CSV quoting: " + str(exc)) from exc


def convert_rows(rows, schema):
    result = []
    for row in rows:
        converted = {}
        for name, value in row.items():
            value = value.strip()
            kind = schema.get(name, "string")
            if not value:
                converted[name] = None
            elif kind == "number":
                try:
                    number = float(value)
                except ValueError:
                    converted[name] = value
                    continue
                if not isfinite(number) or abs(number) > 1e100:
                    raise ValueError(
                        f"Column {name} has a nonfinite or out-of-range number."
                    )
                converted[name] = number
            elif kind == "boolean":
                converted[name] = (
                    True
                    if value.lower() == "true"
                    else False
                    if value.lower() == "false"
                    else value
                )
            else:
                converted[name] = value
        result.append(converted)
    return result
