from services.session_manager import SessionManager


def test_import_from_manager_copies_cli_session_to_user_session(tmp_path):
    source = SessionManager(tmp_path / "cli_session.json")
    source.import_cookie_string("c_user=123; xs=abc")
    target = SessionManager(tmp_path / "user_session.json")

    target.import_from_manager(source)

    assert target.available
    assert target.account_id == "123"
    assert target.store.meta["imported_from"].endswith("cli_session.json")
