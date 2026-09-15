from app.scripts.sensor_simulator import _RANGES, _metric_for_device_key, _pick_mode, generate_reading


def test_metric_inferred_from_device_key():
    assert _metric_for_device_key("soil-moisture-z1") == "soil_moisture_pct"
    assert _metric_for_device_key("weather-temp-01") == "temperature_c"
    assert _metric_for_device_key("weather-humidity-01") == "humidity_pct"
    assert _metric_for_device_key("weather-rain-01") == "rainfall_mm"


def test_pick_mode_respects_forced_mode():
    assert _pick_mode("warning") == "warning"
    assert _pick_mode("anomaly") == "anomaly"
    assert _pick_mode("normal") == "normal"


def test_pick_mode_auto_eventually_produces_every_band():
    seen = {_pick_mode("auto") for _ in range(200)}
    assert seen == {"normal", "warning", "anomaly"}


def test_generate_reading_matches_the_forced_bands_range():
    for device_key, metric in (
        ("soil-moisture-z1", "soil_moisture_pct"),
        ("weather-temp-01", "temperature_c"),
        ("weather-humidity-01", "humidity_pct"),
        ("weather-rain-01", "rainfall_mm"),
    ):
        for band in ("normal", "warning", "anomaly"):
            for _ in range(20):
                got_metric, value, got_band = generate_reading(device_key, band)
                assert got_metric == metric
                assert got_band == band
                low, high = _RANGES[metric][band]
                assert low <= value <= high


def test_worked_example_soil_moisture_bands_match_platform_brief():
    """Master prompt §47's own worked example: 48=normal, 18=warning, 5=critical."""
    normal_low, normal_high = _RANGES["soil_moisture_pct"]["normal"]
    warning_low, warning_high = _RANGES["soil_moisture_pct"]["warning"]
    anomaly_low, anomaly_high = _RANGES["soil_moisture_pct"]["anomaly"]
    assert normal_low <= 48 <= normal_high
    assert warning_low <= 18 <= warning_high
    assert anomaly_low <= 5 <= anomaly_high
