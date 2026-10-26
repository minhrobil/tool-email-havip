"""Kiểm tra lưu thư mục export và khôi phục khi tải lại cấu hình."""
import json

import pytest

from src.config import load_config, save_output_folder


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "azure": {"client_id": "test-client"},
        "output": {"root_folder": "old-folder", "excel_filename": "custom.xlsx"},
        "custom_setting": {"keep": True},
    }), encoding="utf-8")
    return path


@pytest.mark.parametrize("folder", [
    r"D:\Công văn\Export",
    r"\\server\shared\Công văn",
    "~/Công văn",
])
def test_export_folder_survives_reload_and_preserves_other_settings(config_path, folder):
    config = load_config(config_path)
    original = json.loads(config_path.read_text(encoding="utf-8"))

    save_output_folder(config, folder)

    expected = original
    expected["output"]["root_folder"] = folder
    assert json.loads(config_path.read_text(encoding="utf-8")) == expected
    assert load_config(config_path).output.root_folder == config.output.root_folder


def test_clearing_field_does_not_erase_saved_folder(config_path):
    config = load_config(config_path)
    save_output_folder(config, "   ")
    assert load_config(config_path).output.root_folder == "old-folder"


def test_failed_save_preserves_config_and_removes_temp_file(config_path, monkeypatch):
    config = load_config(config_path)
    original = config_path.read_bytes()

    def deny_replace(*args):
        raise PermissionError("Read only")

    monkeypatch.setattr("src.config.os.replace", deny_replace)
    with pytest.raises(PermissionError):
        save_output_folder(config, "new-folder")

    assert config_path.read_bytes() == original
    assert config.output.root_folder == "old-folder"
    assert list(config_path.parent.iterdir()) == [config_path]


def test_save_targets_loaded_config_after_working_directory_changes(config_path, tmp_path, monkeypatch):
    monkeypatch.chdir(config_path.parent)
    config = load_config(config_path.relative_to(config_path.parent))
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    save_output_folder(config, "new-folder")

    assert load_config(config_path).output.root_folder == "new-folder"
    assert not (other_dir / "config.json").exists()
