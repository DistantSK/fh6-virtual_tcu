from virtual_tcu.app import clutch_assist_enabled, toggle_clutch_assist
from virtual_tcu.config.store import ConfigStore


def test_toggle_clutch_assist_syncs_keyboard_and_vjoy():
    config = ConfigStore()
    config.set("feat_clutch_assist", False)
    config.set("vjoy_use_clutch", False)

    assert toggle_clutch_assist(config) is True
    assert clutch_assist_enabled(config) is True
    assert config.get("feat_clutch_assist") is True
    assert config.get("vjoy_use_clutch") is True

    assert toggle_clutch_assist(config) is False
    assert clutch_assist_enabled(config) is False
    assert config.get("feat_clutch_assist") is False
    assert config.get("vjoy_use_clutch") is False
