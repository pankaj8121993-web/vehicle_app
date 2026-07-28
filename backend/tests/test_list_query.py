from list_query import add_safe_search, page_response, pagination, sort_spec


def test_search_is_regex_escaped_and_bounded():
    query = add_safe_search({}, "vehicles", "MH.*(" + "x" * 200)
    regex = query["$or"][0]["vehicle_number"]["$regex"]
    assert r"\.\*\(" in regex
    assert len(regex) <= 110


def test_search_keeps_existing_tenant_scoped_filters():
    query = {"org_id": "org-a", "status": "active"}
    result = add_safe_search(query, "vehicles", "truck")
    assert result["org_id"] == "org-a"
    assert result["status"] == "active"
    assert "$or" in result


def test_pagination_boundaries_and_invalid_values():
    assert pagination({"page": "-1", "page_size": "9999"}) == (1, 200)
    assert pagination({"page": "bad", "page_size": "bad"}) == (1, 25)


def test_sort_is_allowlisted():
    assert sort_spec({"sort_by": "$where", "sort_dir": "desc"}, {"name"}, "name") == ("name", -1)
    assert sort_spec({"sort_by": "name", "sort_dir": "asc"}, {"name"}, "name") == ("name", 1)


def test_page_response_reports_exact_boundaries():
    response = page_response([{"id": "last"}], total=51, page=3, page_size=25)
    assert response == {
        "items": [{"id": "last"}],
        "total": 51,
        "page": 3,
        "page_size": 25,
        "total_pages": 3,
    }


def test_empty_page_has_zero_total_pages():
    assert page_response([], 0, 1, 25)["total_pages"] == 0
