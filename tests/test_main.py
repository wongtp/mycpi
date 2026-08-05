"""Unit tests for the watchlist file reader — no DB or network."""
import main


def _write_list(tmp_path, monkeypatch, text):
    path = tmp_path / "productList.txt"
    path.write_text(text)
    monkeypatch.setattr(main, "PRODUCT_LIST_PATH", path)
    return path


def test_reads_upcs_in_file_order(tmp_path, monkeypatch):
    _write_list(tmp_path, monkeypatch, "0001\n0002\n0003\n")
    assert main.load_upc_list() == ["0001", "0002", "0003"]


def test_ignores_blank_lines_and_whitespace(tmp_path, monkeypatch):
    _write_list(tmp_path, monkeypatch, "0001\n\n  0002  \n\n")
    assert main.load_upc_list() == ["0001", "0002"]


def test_deduplicates_while_preserving_order(tmp_path, monkeypatch):
    # A UPC listed twice would be summed twice into the basket total and would
    # inflate the expected-item count the completeness check compares against.
    _write_list(tmp_path, monkeypatch, "0001\n0002\n0001\n")
    assert main.load_upc_list() == ["0001", "0002"]


def test_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PRODUCT_LIST_PATH", tmp_path / "nope.txt")
    assert main.load_upc_list() == []
