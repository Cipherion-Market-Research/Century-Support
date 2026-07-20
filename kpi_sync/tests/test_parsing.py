from kpi_sync.parsing import camel_to_snake, parse_sheet_response, parse_upstream_datetime


def test_camel_to_snake():
    assert camel_to_snake("totalContributions") == "total_contributions"
    assert camel_to_snake("percentStaked") == "percent_staked"
    assert camel_to_snake("cipherions") == "cipherions"
    assert camel_to_snake("lastUpdated") == "last_updated"


def test_camel_to_snake_collapses_acronym_runs():
    # A naive "underscore before every capital" conversion mangles this
    # into total_c_p_x_presold -- the acronym CPX must stay one word.
    assert camel_to_snake("totalCPXPresold") == "total_cpx_presold"


def test_parse_upstream_datetime_iso_with_millis_passthrough():
    raw = "2026-07-20T17:00:46.684Z"
    assert parse_upstream_datetime(raw) == raw


def test_parse_upstream_datetime_iso_without_millis_passthrough():
    raw = "2026-07-20T17:00:46Z"
    assert parse_upstream_datetime(raw) == raw


def test_parse_upstream_datetime_four_digit_year():
    assert parse_upstream_datetime("7-10-2026 3:00 PM") == "2026-07-10T15:00:00"


def test_parse_upstream_datetime_two_digit_year():
    assert parse_upstream_datetime("7-10-26 3:00 PM") == "2026-07-10T15:00:00"


def test_parse_upstream_datetime_unparseable_is_none_not_a_guess():
    assert parse_upstream_datetime("not a date") is None
    assert parse_upstream_datetime("") is None
    assert parse_upstream_datetime(None) is None


def test_parse_sheet_response_pads_short_rows():
    data = {
        "range": "'public-charts'!A1:V1000",
        "majorDimension": "ROWS",
        "values": [
            ["date", "totalReturn", "hitBuys"],
            ["5-25-25 2:00 PM", "--"],  # short row -- Sheets trims trailing empty cells
            ["8-22-25 2:00 PM", "-3.59%", "119"],
        ],
    }
    rows = parse_sheet_response(data)
    assert rows == [
        {"date": "5-25-25 2:00 PM", "totalReturn": "--", "hitBuys": None},
        {"date": "8-22-25 2:00 PM", "totalReturn": "-3.59%", "hitBuys": "119"},
    ]


def test_parse_sheet_response_empty_values():
    assert parse_sheet_response({"values": []}) == []
    assert parse_sheet_response({}) == []
