# Standard Library Imports
import asyncio
import json
import logging
import os
import serial_asyncio
from datetime import datetime, timedelta
from serial import SerialException

# Home Assistant Imports
from homeassistant.core import callback
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.entity import Entity

from homeassistant.const import (
    CONF_NAME,
    EVENT_HOMEASSISTANT_STOP
)

CONF_BAUDRATE = "baudrate"
CONF_SERIAL_PORT = "serial_port"


DEFAULT_NAME = "Serial Sensor"
DEFAULT_BAUDRATE = 4800
DEFAULT_BYTESIZE = serial_asyncio.serial.EIGHTBITS
DEFAULT_PARITY = serial_asyncio.serial.PARITY_NONE
DEFAULT_STOPBITS = serial_asyncio.serial.STOPBITS_ONE
DEFAULT_XONXOFF = False
DEFAULT_RTSCTS = False
DEFAULT_DSRDTR = False

# Setting up logging and configuring constants and default values

_LOGGER = logging.getLogger(__name__)


async def update_sensor_availability(hass,instance_name):
    """Update the availability of all sensors every 5 minutes."""
    
    created_sensors_key = f"{instance_name}_created_sensors"

    while True:
        _LOGGER.debug("Running update_sensor_availability")
        await asyncio.sleep(300)  # wait for 5 minutes

        for sensor in hass.data[created_sensors_key].values():
            sensor.update_availability()


# The main setup function to initialize the sensor platform

async def async_setup_entry(hass, entry, async_add_entities):
    # Retrieve configuration from entry
    name = entry.data[CONF_NAME]
    serial_port = entry.data[CONF_SERIAL_PORT]
    baudrate = entry.data[CONF_BAUDRATE]
    
    bytesize = DEFAULT_BYTESIZE
    parity = DEFAULT_PARITY
    stopbits = DEFAULT_STOPBITS
    xonxoff = DEFAULT_XONXOFF
    rtscts = DEFAULT_RTSCTS
    dsrdtr = DEFAULT_DSRDTR

    # Log the retrieved configuration values for debugging purposes
    _LOGGER.info(f"Configuring sensor with name: {name}, serial_port: {serial_port}, baudrate: {baudrate}")
    
    # Initialize unique dictionary keys based on the integration name
    add_entities_key = f"{name}_add_entities"
    created_sensors_key = f"{name}_created_sensors"
    smart0183serial_data_key = f"{name}_smart0183serial_data"


     # Save a reference to the add_entities callback
    _LOGGER.debug(f"Assigning async_add_entities to hass.data[{add_entities_key}].")
    hass.data[add_entities_key] = async_add_entities


    # Initialize a dictionary to store references to the created sensors
    hass.data[created_sensors_key] = {}

    # Load the Smart0183 json data 
    config_dir = hass.config.config_dir
    json_path = os.path.join(config_dir, 'custom_components', 'smart0183serial', 'Smart0183serial.json')
    try:
        with open(json_path, "r") as file:
            smart_data = json.load(file)

        result_dict = {}
        for sentence in smart_data:
            group = sentence["group"]  # Capture the group for all fields within this sentence
            for field in sentence["fields"]:
                result_dict[field["unique_id"]] = {
                    "full_description": field["full_description"],
                    "group": group,
                    "unit_of_measurement": field.get("unit_of_measurement", None)
                }


        hass.data[smart0183serial_data_key] = result_dict

    except Exception as e:
        _LOGGER.error(f"Error loading Smart0183serial.json: {e}")
        return

    _LOGGER.debug(f"Loaded smart data: {hass.data[smart0183serial_data_key]}")



    sensor = SerialSensor(
        name,
        serial_port,
        baudrate,
        bytesize,
        parity,
        stopbits,
        xonxoff,
        rtscts,
        dsrdtr,
    )
    
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, sensor.stop_serial_read)
    async_add_entities([sensor], True)

    # Start the task that updates the sensor availability every 5 minutes
    hass.loop.create_task(update_sensor_availability(hass,name))

async def set_smart_sensors(hass, line, instance_name):
    """Process the content of the line related to the smart sensors."""
    try:
        if not line or not line.startswith("$"):
            return

        # Splitting by comma and getting the data fields
        fields = line.split(',')
        if len(fields) < 1 or len(fields[0]) < 6:  # Ensure enough fields and length
            _LOGGER.error(f"Malformed line: {line}")
            return

        sentence_id = fields[0][1:6]  # Gets the 5-char word after the $

        _LOGGER.debug(f"Sentence_id: {sentence_id}")
        
        # Dynamically construct the keys based on the instance name
        smart0183serial_data_key = f"{instance_name}_smart0183serial_data"
        created_sensors_key = f"{instance_name}_created_sensors"
        add_entities_key = f"{instance_name}_add_entities"

        for idx, field_data in enumerate(fields[1:], 1):
            if idx == len(fields) - 1:  # Skip the last field since it's a check digit
                break

            sensor_name = f"{sentence_id}_{idx}"
            _LOGGER.debug(f"Sensor_name: {sensor_name}")

            short_sensor_name = f"{sentence_id[2:]}_{idx}"

            sensor_info = hass.data[smart0183serial_data_key].get(short_sensor_name)
            full_desc = sensor_info["full_description"] if sensor_info else sensor_name
            group = sensor_info["group"]
            unit_of_measurement = sensor_info.get("unit_of_measurement")

            if sensor_name not in hass.data[created_sensors_key]:
                _LOGGER.debug(f"Creating field sensor: {sensor_name}")
                sensor = SmartSensor(sensor_name, full_desc, field_data, group, unit_of_measurement)
                
                # Add Sensor to Home Assistant
                hass.data[add_entities_key]([sensor])
                
                # Update dictionary with added sensor
                hass.data[created_sensors_key][sensor_name] = sensor
            else:
                _LOGGER.debug(f"Updating field sensor: {sensor_name}")
                sensor = hass.data[created_sensors_key][sensor_name]
                sensor.set_state(field_data)

    except IndexError:
        _LOGGER.error(f"Index error for line: {line}")
    except KeyError as e:
        _LOGGER.error(f"Key error: {e}")
    except Exception as e:
        _LOGGER.error(f"An unexpected error occurred: {e}")


# SmartSensor class representing a basic sensor entity with state

class SmartSensor(Entity):
    def __init__(self, name, friendly_name, initial_state, group=None, unit_of_measurement=None):
        """Initialize the sensor."""
        _LOGGER.info(f"Initializing sensor: {name} with state: {initial_state}")

        self._unique_id = name.lower().replace(" ", "_")
        self.entity_id = f"sensor.{self._unique_id}"
        self._name = friendly_name if friendly_name else self._unique_id
        self._state = initial_state
        self._group = group if group is not None else "Other"
        self._unit_of_measurement = unit_of_measurement
        self._state_class = SensorStateClass.MEASUREMENT
        self._last_updated = datetime.now()
        if initial_state is None or initial_state == "":
            self._available = False
            _LOGGER.debug(f"Setting sensor: '{self._name}' with unavailable")
        else:
            self._available = True

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name
    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def device_info(self):
        """Return device information about this sensor."""
        return {
            "identifiers": {("Smart0183serial", self._group)},
            "name": self._group,
            "manufacturer": "Smart Boat Innovations",
            "model": "General",
        }

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return self._state_class


    @property
    def last_updated(self):
        """Return the last updated timestamp of the sensor."""
        return self._last_updated

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._available

    @property
    def should_poll(self) -> bool:
        """Return the polling requirement for this sensor."""
        return False


    def update_availability(self):
        """Update the availability status of the sensor."""

        new_availability = (datetime.now() - self._last_updated) < timedelta(minutes=4)

        self._available = new_availability

        try:
            self.async_schedule_update_ha_state()
        except RuntimeError as re:
            if "Attribute hass is None" in str(re):
                pass  # Ignore this specific error
            else:
                _LOGGER.warning(f"Could not update state for sensor '{self._name}': {re}")
        except Exception as e:  # Catch all other exception types
            _LOGGER.warning(f"Could not update state for sensor '{self._name}': {e}")

    def set_state(self, new_state):
        """Set the state of the sensor."""
        _LOGGER.debug(f"Setting state for sensor: '{self._name}' to {new_state}")
        self._state = new_state
        if new_state is None or new_state == "":
            self._available = False
            _LOGGER.debug(f"Setting sensor:'{self._name}' with unavailable")
        else:
            self._available = True
        self._last_updated = datetime.now()

        try:
            self.async_schedule_update_ha_state()
        except RuntimeError as re:
            if "Attribute hass is None" in str(re):
                pass  # Ignore this specific error
            else:
                _LOGGER.warning(f"Could not update state for sensor '{self._name}': {re}")
        except Exception as e:  # Catch all other exception types
            _LOGGER.warning(f"Could not update state for sensor '{self._name}': {e}")



# SerialSensor class representing a sensor entity interacting with a serial device

class SerialSensor(SensorEntity):
    """Representation of a Serial sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        name,
        port,
        baudrate,
        bytesize,
        parity,
        stopbits,
        xonxoff,
        rtscts,
        dsrdtr,
    ):
        """Initialize the Serial sensor."""
        self._name = name
        self._state = None
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        self._xonxoff = xonxoff
        self._rtscts = rtscts
        self._dsrdtr = dsrdtr
        self._serial_loop_task = None
        self._attributes = None

    async def async_added_to_hass(self) -> None:
        """Handle when an entity is about to be added to Home Assistant."""
        self._serial_loop_task = self.hass.loop.create_task(
            self.serial_read(
                self._port,
                self._baudrate,
                self._bytesize,
                self._parity,
                self._stopbits,
                self._xonxoff,
                self._rtscts,
                self._dsrdtr,
            )
        )






    async def serial_read(
        self,
        device,
        baudrate,
        bytesize,
        parity,
        stopbits,
        xonxoff,
        rtscts,
        dsrdtr,
        **kwargs,
    ):
        """Read the data from the port."""
        logged_error = False
        while True:
            try:
                reader, _ = await serial_asyncio.open_serial_connection(
                    url=device,
                    baudrate=baudrate,
                    bytesize=bytesize,
                    parity=parity,
                    stopbits=stopbits,
                    xonxoff=xonxoff,
                    rtscts=rtscts,
                    dsrdtr=dsrdtr,
                    **kwargs,
                )

            except SerialException as exc:
                if not logged_error:
                    _LOGGER.exception(
                        "Unable to connect to the serial device %s: %s. Will retry",
                        device,
                        exc,
                    )
                    logged_error = True
                await self._handle_error()
            else:
                _LOGGER.info("Serial device %s connected", device)


                while True:
                    try:
                        line = await reader.readline()
                    except SerialException as exc:
                        _LOGGER.exception("Error while reading serial device %s: %s", device, exc)
                        await self._handle_error()
                        break
                    else:
                        try:
                            line = line.decode("utf-8").strip()
                        except UnicodeDecodeError as exc:
                            _LOGGER.error("Failed to decode line from UTF-8: %s", exc)
                            continue

                        # _LOGGER.debug("Received: %s", line)
                        await set_smart_sensors(self.hass,line,self.name)





    async def _handle_error(self):
        """Handle error for serial connection."""
        self._state = None
        self._attributes = None
        self.async_write_ha_state()
        await asyncio.sleep(5)

    @callback
    def stop_serial_read(self, event):
        """Close resources."""
        if self._serial_loop_task:
            self._serial_loop_task.cancel()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def extra_state_attributes(self):
        """Return the attributes of the entity (if any JSON present)."""
        return self._attributes

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state
