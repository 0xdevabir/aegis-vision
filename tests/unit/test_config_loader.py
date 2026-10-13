"""Tests for config loader utilities."""

from utils.config import expand_env, load_cameras_config


class TestExpandEnv:
    def test_plain_string(self):
        assert expand_env("hello") == "hello"

    def test_env_var_braces(self, monkeypatch):
        monkeypatch.setenv("RTSP_GATE_1", "rtsp://cam1/stream")
        assert expand_env("${RTSP_GATE_1}") == "rtsp://cam1/stream"

    def test_env_prefix(self, monkeypatch):
        monkeypatch.setenv("MY_CAM", "rtsp://x")
        assert expand_env("env:MY_CAM") == "rtsp://x"

    def test_nested_dict(self, monkeypatch):
        monkeypatch.setenv("FOO", "bar")
        result = expand_env({"source": "${FOO}"})
        assert result["source"] == "bar"


class TestLoadCamerasConfig:
    def test_loads_enabled_cameras(self, tmp_path):
        # Own config: the real cameras.yaml is edited at runtime (the dashboard toggles `enabled`).
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "cameras.yaml").write_text(
            "cameras:\n"
            "- {id: a, source: 0, enabled: true}\n"
            "- {id: b, source: 1, enabled: false}\n"
            "- {id: c, source: 'rtsp://x/y'}\n")
        cameras = load_cameras_config(str(tmp_path))
        assert [c["id"] for c in cameras] == ["a", "c"]              # disabled ones are filtered out

