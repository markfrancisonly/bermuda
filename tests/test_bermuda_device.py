"""
Tests for BermudaDevice class in bermuda_device.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from homeassistant.components.bluetooth import BaseHaScanner, BaseHaRemoteScanner
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.bermuda.bermuda_device import BermudaDevice
from custom_components.bermuda.const import DOMAIN, ICON_DEFAULT_AREA, ICON_DEFAULT_FLOOR
from custom_components.bermuda.util import mac_math_offset


@pytest.fixture
def mock_coordinator():
    """Fixture for mocking BermudaDataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.options = {}
    coordinator.hass_version_min_2025_4 = True
    return coordinator


@pytest.fixture
def mock_scanner():
    """Fixture for mocking BaseHaScanner."""
    scanner = MagicMock(spec=BaseHaScanner)
    scanner.time_since_last_detection.return_value = 5.0
    scanner.source = "mock_source"
    return scanner


@pytest.fixture
def mock_remote_scanner():
    """Fixture for mocking BaseHaRemoteScanner."""
    scanner = MagicMock(spec=BaseHaRemoteScanner)
    scanner.time_since_last_detection.return_value = 5.0
    scanner.source = "mock_source"
    return scanner


@pytest.fixture
def bermuda_device(mock_coordinator):
    """Fixture for creating a BermudaDevice instance."""
    return BermudaDevice(address="AA:BB:CC:DD:EE:FF", coordinator=mock_coordinator)


@pytest.fixture
def bermuda_scanner(mock_coordinator):
    """Fixture for creating a BermudaDevice Scanner instance."""
    return BermudaDevice(address="11:22:33:44:55:66", coordinator=mock_coordinator)


def test_bermuda_device_initialization(bermuda_device):
    """Test BermudaDevice initialization."""
    assert bermuda_device.address == "aa:bb:cc:dd:ee:ff"
    assert bermuda_device.name.startswith("bermuda_")
    assert bermuda_device.area_icon == ICON_DEFAULT_AREA
    assert bermuda_device.floor_icon == ICON_DEFAULT_FLOOR
    assert bermuda_device.zone == "not_home"


def test_async_as_scanner_init(bermuda_scanner, mock_scanner):
    """Test async_as_scanner_init method."""
    bermuda_scanner.async_as_scanner_init(mock_scanner)
    assert bermuda_scanner._hascanner == mock_scanner
    assert bermuda_scanner.is_scanner is True
    assert bermuda_scanner.is_remote_scanner is False


def test_async_as_scanner_update(bermuda_scanner, mock_scanner):
    """Test async_as_scanner_update method."""
    bermuda_scanner.async_as_scanner_update(mock_scanner)
    assert bermuda_scanner.last_seen > 0


def test_async_as_scanner_get_stamp(bermuda_scanner, mock_scanner, mock_remote_scanner):
    """Test async_as_scanner_get_stamp method."""
    bermuda_scanner.async_as_scanner_init(mock_scanner)
    bermuda_scanner.stamps = {"AA:BB:CC:DD:EE:FF": 123.45}

    stamp = bermuda_scanner.async_as_scanner_get_stamp("AA:bb:CC:DD:EE:FF")
    assert stamp is None

    bermuda_scanner.async_as_scanner_init(mock_remote_scanner)

    stamp = bermuda_scanner.async_as_scanner_get_stamp("AA:bb:CC:DD:EE:FF")
    assert stamp == 123.45

    stamp = bermuda_scanner.async_as_scanner_get_stamp("AA:BB:CC:DD:E1:FF")
    assert stamp is None


def test_make_name(bermuda_device):
    """Test make_name method."""
    bermuda_device.name_by_user = "Custom Name"
    name = bermuda_device.make_name()
    assert name == "Custom Name"
    assert bermuda_device.name == "Custom Name"


def test_process_advertisement(bermuda_device, bermuda_scanner):
    """Test process_advertisement method."""
    advertisement_data = MagicMock()
    bermuda_device.process_advertisement(bermuda_scanner, advertisement_data)
    assert len(bermuda_device.adverts) == 1


# def test_process_manufacturer_data(bermuda_device):
#     """Test process_manufacturer_data method."""
#     mock_advert = MagicMock()
#     mock_advert.service_uuids = ["0000abcd-0000-1000-8000-00805f9b34fb"]
#     mock_advert.manufacturer_data = [{"004C": b"\x02\x15"}]
#     bermuda_device.process_manufacturer_data(mock_advert)
#     assert bermuda_device.manufacturer == "Apple Inc."


def test_to_dict(bermuda_device):
    """Test to_dict method."""
    device_dict = bermuda_device.to_dict()
    assert isinstance(device_dict, dict)
    assert device_dict["address"] == "aa:bb:cc:dd:ee:ff"


def test_repr(bermuda_device):
    """Test __repr__ method."""
    repr_str = repr(bermuda_device)
    assert repr_str == f"{bermuda_device.name} [{bermuda_device.address}]"


# ---------------------------------------------------------------------------
# Scanner resolution against the real registries
# ---------------------------------------------------------------------------

UNIFI_MAC = "02:aa:bb:cc:dd:13"  # another integration's entry inside the proxies' MAC windows


@pytest.fixture
def registry_coordinator(hass):
    """Coordinator mock backed by the real registries."""
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.dr = dr.async_get(hass)
    coordinator.er = er.async_get(hass)
    coordinator.config_entry = MockConfigEntry(domain=DOMAIN, entry_id="bermuda")
    coordinator.config_entry.add_to_hass(hass)
    coordinator.options = {}
    coordinator.hass_version_min_2025_4 = True
    return coordinator


def _init_scanner(address, coordinator):
    scanner = MagicMock(spec=BaseHaRemoteScanner)
    scanner.source = address
    scanner.name = f"scanner {address}"
    scanner.time_since_last_detection.return_value = 5.0
    device = BermudaDevice(address=address, coordinator=coordinator)
    device.async_as_scanner_init(scanner)
    return device


def _esphome_proxy(hass, name, entry_id, ble_mac, mac_connections, unique_id, bt_device=True):
    """An esphome entry that reports ble_mac as its scanner address, with its registry device(s)."""
    entry = MockConfigEntry(
        domain="esphome", data={"bluetooth_mac_address": ble_mac}, entry_id=entry_id, unique_id=unique_id
    )
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id, connections={("mac", m) for m in mac_connections}, name=name
    )
    if bt_device:
        registry.async_get_or_create(config_entry_id=entry.entry_id, connections={("bluetooth", ble_mac)}, name="bt")


def _unifi_device(hass, mac=UNIFI_MAC):
    entry = MockConfigEntry(domain="unifi", entry_id=f"unifi {mac}")
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, connections={("mac", mac)}, name="proxy")


def _distance_entities(hass, coordinator, scanner_mac):
    """A tracked device's distance entities as an earlier version keyed them, on scanner_mac."""
    registry = er.async_get(hass)
    return [
        registry.async_get_or_create(
            "sensor", DOMAIN, f"phone_{scanner_mac}{suffix}", config_entry=coordinator.config_entry
        ).entity_id
        for suffix in ("_range", "_range_raw")
    ]


def _unique_ids(hass, entity_ids):
    registry = er.async_get(hass)
    return [registry.async_get(entity_id).unique_id for entity_id in entity_ids]


async def test_scanner_resolves_through_esphome_entry(hass, registry_coordinator):
    """A proxy whose MACs don't follow the Espressif layout is linked through its esphome entry."""
    _esphome_proxy(hass, "Desk Tablet", "kiosk", "02:11:22:33:44:55", ["02:66:77:88:99:aa"], "02:66:77:88:99:aa")

    scanner = _init_scanner("02:11:22:33:44:55", registry_coordinator)

    assert scanner.address_wifi_mac == "02:66:77:88:99:aa"
    assert scanner.unique_id == "02:66:77:88:99:aa"
    assert scanner.address_ble_mac == "02:11:22:33:44:55"
    assert scanner.name == "Desk Tablet"


async def test_esphome_link_wins_over_other_device_in_mac_range(hass, registry_coordinator):
    """A UniFi entry in the MAC range no longer supplies the identity or name; entities keyed on it are re-keyed."""
    _esphome_proxy(
        hass, "Breakfast Bluetooth Proxy", "esp", "02:AA:BB:CC:DD:12", ["02:aa:bb:cc:dd:10"], "02:aa:bb:cc:dd:10"
    )
    _unifi_device(hass)
    entity_ids = _distance_entities(hass, registry_coordinator, UNIFI_MAC)

    scanner = _init_scanner("02:AA:BB:CC:DD:12", registry_coordinator)

    assert scanner.unique_id == scanner.address_wifi_mac == "02:aa:bb:cc:dd:10"
    assert scanner.name == "Breakfast Bluetooth Proxy"
    assert _unique_ids(hass, entity_ids) == ["phone_02:aa:bb:cc:dd:10_range", "phone_02:aa:bb:cc:dd:10_range_raw"]


async def test_scanner_without_matching_entry_resolves_by_mac_offset(hass, registry_coordinator):
    """Without a matching entry the Espressif-layout search still runs and keeps the WiFi-MAC unique_id."""
    _esphome_proxy(hass, "Kitchen Proxy", "esp", "AA:AA:AA:AA:AA:AA", ["02:aa:bb:cc:dd:20"], "02:aa:bb:cc:dd:20")

    scanner = _init_scanner("02:AA:BB:CC:DD:22", registry_coordinator)

    assert scanner.unique_id == scanner.address_wifi_mac == "02:aa:bb:cc:dd:20"


async def test_migration_never_overwrites_an_existing_entity(hass, registry_coordinator):
    """When both identities already have entities, neither is touched."""
    _esphome_proxy(
        hass, "Breakfast Bluetooth Proxy", "esp", "02:AA:BB:CC:DD:12", ["02:aa:bb:cc:dd:10"], "02:aa:bb:cc:dd:10"
    )
    _unifi_device(hass)
    old_ids = _distance_entities(hass, registry_coordinator, UNIFI_MAC)
    new_ids = _distance_entities(hass, registry_coordinator, "02:aa:bb:cc:dd:10")

    _init_scanner("02:AA:BB:CC:DD:12", registry_coordinator)

    assert _unique_ids(hass, old_ids) == [f"phone_{UNIFI_MAC}_range", f"phone_{UNIFI_MAC}_range_raw"]
    assert _unique_ids(hass, new_ids) == ["phone_02:aa:bb:cc:dd:10_range", "phone_02:aa:bb:cc:dd:10_range_raw"]


async def test_migration_leaves_another_scanners_entities_alone(hass, registry_coordinator):
    """A MAC in range that belongs to a different ESPHome device is another scanner's identity."""
    _esphome_proxy(
        hass, "Breakfast Bluetooth Proxy", "esp", "02:AA:BB:CC:DD:12", ["02:aa:bb:cc:dd:10"], "02:aa:bb:cc:dd:10"
    )
    _esphome_proxy(hass, "Neighbour", "esp2", "02:AA:BB:CC:DD:15", [UNIFI_MAC], UNIFI_MAC, bt_device=False)
    entity_ids = _distance_entities(hass, registry_coordinator, UNIFI_MAC)

    scanner = _init_scanner("02:AA:BB:CC:DD:12", registry_coordinator)

    assert scanner.address_wifi_mac == "02:aa:bb:cc:dd:10"
    assert _unique_ids(hass, entity_ids) == [f"phone_{UNIFI_MAC}_range", f"phone_{UNIFI_MAC}_range_raw"]


@pytest.mark.parametrize("first", ["02:AA:BB:CC:DD:12", "02:AA:BB:CC:DD:16"])
async def test_migration_skips_mac_two_scanners_could_have_claimed(hass, registry_coordinator, first):
    """A UniFi MAC inside two scanners' windows is left alone, whichever scanner initialises first."""
    _esphome_proxy(
        hass, "Breakfast Bluetooth Proxy", "esp", "02:AA:BB:CC:DD:12", ["02:aa:bb:cc:dd:10"], "02:aa:bb:cc:dd:10"
    )
    _esphome_proxy(
        hass, "Pantry Bluetooth Proxy", "esp2", "02:AA:BB:CC:DD:16", ["02:aa:bb:cc:dd:14"], "02:aa:bb:cc:dd:14"
    )
    _unifi_device(hass)
    entity_ids = _distance_entities(hass, registry_coordinator, UNIFI_MAC)

    for address in [first] + [a for a in ("02:AA:BB:CC:DD:12", "02:AA:BB:CC:DD:16") if a != first]:
        scanner = _init_scanner(address, registry_coordinator)
        assert scanner.address_wifi_mac == mac_math_offset(address.lower(), -2)

    assert _unique_ids(hass, entity_ids) == [f"phone_{UNIFI_MAC}_range", f"phone_{UNIFI_MAC}_range_raw"]


async def test_migrates_entities_keyed_on_another_connection_of_the_proxy(hass, registry_coordinator):
    """Entities keyed on another mac connection of the proxy's own device are re-keyed to the entry's MAC."""
    _esphome_proxy(
        hass,
        "Desk Tablet",
        "kiosk",
        "02:11:22:33:44:55",
        ["02:11:22:33:44:57", "02:66:77:88:99:aa"],
        "02:66:77:88:99:aa",
    )
    entity_ids = _distance_entities(hass, registry_coordinator, "02:11:22:33:44:57")

    scanner = _init_scanner("02:11:22:33:44:55", registry_coordinator)

    assert scanner.address_wifi_mac == "02:66:77:88:99:aa"
    assert _unique_ids(hass, entity_ids) == ["phone_02:66:77:88:99:aa_range", "phone_02:66:77:88:99:aa_range_raw"]
