def test_epic_parser():
    sample_response = '''{
        "title": "Test",
        "description": "Test",
        "state": "To Do",
        "areaPath": "Test",
        "path": "Test",
        "assigneTo": "test@test.com",
        "tags": ["test"]
    }'''

    result = parse_epic_response(sample_response)
    assert result["title"] == "Test"
