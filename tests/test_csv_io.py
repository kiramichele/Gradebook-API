import pytest

from app import csv_io
from app.csv_io import CSVError, format_number, parse_roster, safe_text


def parse(text: str, encoding: str = "utf-8"):
    return [(r.line, r.name, r.email) for r in parse_roster(text.encode(encoding))]


def errors(text: str):
    with pytest.raises(CSVError) as exc:
        parse_roster(text.encode())
    return exc.value.errors


def test_basic_roster():
    assert parse("name,email\nAda Lovelace,ada@example.edu\nAlan Turing,\n") == [
        (2, "Ada Lovelace", "ada@example.edu"),
        (3, "Alan Turing", None),
    ]


def test_header_aliases_and_messy_input():
    text = "  Student Name ,E-mail,Period\r\n  Grace Hopper , GRACE@Example.EDU ,3\r\n"
    assert parse(text) == [(2, "Grace Hopper", "grace@example.edu")]


def test_first_and_last_name_columns():
    text = "Last Name,First Name\nKim,Alex\nSolo,\n"
    assert parse(text) == [(2, "Alex Kim", None), (3, "Solo", None)]


def test_name_column_wins_over_first_last():
    assert parse("first,last,name\nA,B,Full Name\n") == [(2, "Full Name", None)]


def test_quoted_fields_and_multiline_cells():
    text = 'name,email\n"Kim, Alex",a@example.edu\n"Two\nLines",b@example.edu\nC,\n'
    assert parse(text) == [
        (2, "Kim, Alex", "a@example.edu"),
        (4, "Two\nLines", "b@example.edu"),
        (5, "C", None),
    ]


def test_blank_rows_skipped():
    assert parse("name\n\nAda\n,\n  \nAlan\n") == [(3, "Ada", None), (6, "Alan", None)]


def test_excel_utf8_bom():
    assert parse("\ufeffname,email\nJosé,jose@example.edu\n") == [(2, "José", "jose@example.edu")]


def test_windows_1252_fallback():
    assert parse("name\nJosé Núñez\n", encoding="cp1252") == [(2, "José Núñez", None)]


def test_short_rows_are_fine():
    assert parse("name,email\nAda\n") == [(2, "Ada", None)]


def test_all_errors_reported_by_line():
    text = "name,email\nOk,ok@example.edu\n,x@example.edu\nBad,not-an-email\nDup,OK@example.edu\n"
    assert errors(text) == [
        {"line": 3, "error": "Name is required"},
        {"line": 4, "error": "Invalid email: not-an-email"},
        {"line": 5, "error": "Duplicate email ok@example.edu (first seen on line 2)"},
    ]


def test_name_too_long():
    assert errors(f"name\n{'x' * 201}\n")[0]["error"].startswith("Name is over")


def test_missing_name_column():
    assert "Need a 'name' column" in errors("email\na@example.edu\n")[0]["error"]
    assert "Need a 'name' column" in errors("first_name\nAda\n")[0]["error"]


def test_empty_file_and_header_only():
    assert errors("") == [{"line": 1, "error": "File is empty"}]
    assert errors("name,email\n") == [{"line": 2, "error": "No students found"}]


def test_row_limit(monkeypatch):
    monkeypatch.setattr(csv_io, "MAX_ROWS", 3)
    assert len(parse("name\na\nb\nc\n")) == 3
    assert errors("name\na\nb\nc\nd\n")[-1] == {"line": 5, "error": "More than 3 rows"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('=HYPERLINK("http://evil")', '\'=HYPERLINK("http://evil")'),
        ("+1", "'+1"),
        ("-2", "'-2"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("Ada", "Ada"),
        ("", ""),
    ],
)
def test_safe_text(value, expected):
    assert safe_text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [("10.00", "10"), ("12.50", "12.5"), ("100", "100"), (9.25, "9.25")]
)
def test_format_number(value, expected):
    from decimal import Decimal

    number = Decimal(value) if isinstance(value, str) else value
    assert format_number(number) == expected
