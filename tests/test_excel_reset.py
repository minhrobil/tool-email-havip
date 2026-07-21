from src.excel.writer import ExcelWriter


def test_reset_removes_existing_workbook_and_restarts_sequence(tmp_path):
    writer = ExcelWriter(tmp_path, "report.xlsx")
    writer.append_data_row({"Ngày nhận công văn": 7})
    assert writer.next_sequence_number() == 8

    writer.reset()

    assert not writer.excel_path.exists()
    assert writer.next_sequence_number() == 1


def test_reset_is_idempotent_when_workbook_does_not_exist(tmp_path):
    writer = ExcelWriter(tmp_path, "report.xlsx")

    writer.reset()
    writer.reset()

    assert not writer.excel_path.exists()
