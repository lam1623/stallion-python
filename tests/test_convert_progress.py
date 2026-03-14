from core.convert import _build_update, _parse_progress_line


def test_parse_progress_line_valid():
    assert _parse_progress_line("fps=48.0\n") == ("fps", "48.0")


def test_parse_progress_line_invalid():
    assert _parse_progress_line("not-a-progress-line") is None


def test_build_update_calculates_percent():
    data = {
        "out_time_us": "5000000",
        "speed": "1.50x",
        "fps": "30.0",
        "progress": "continue",
    }
    update = _build_update(data, duration_s=10.0, job_id="job-1")

    assert update.job_id == "job-1"
    assert update.percent == 50.0
    assert update.out_time_s == 5.0
    assert update.speed == "1.50x"
    assert update.fps == 30.0
