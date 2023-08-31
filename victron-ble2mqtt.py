#!/usr/bin/env python3

import argparse
import copy
import faulthandler
import json
import logging
import json
import os
import queue
import subprocess
import sys
import threading
import time
import yaml
from collections import namedtuple
from datetime import datetime, timedelta
from enum import IntEnum
from time import sleep

import asyncio
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from victron_ble.devices import detect_device_type
from victron_ble.devices.solar_charger import SolarCharger, SolarChargerData
from victron_ble.devices.base import OperationMode
from victron_ble.scanner import DebugScanner, DiscoveryScanner, Scanner, BaseScanner

version = 0.1


def victron_thread(thread_count, config, vdevice_config, thread_q):
    from lib.victron import Victron
    v = Victron(config, vdevice_config, output, args, thread_count, thread_q)
    logger.debug("victron library loaded, start connect_diconnect_loop()")
    v.connect_disconnect_loop()


def output_print(device_name, category, value, hass_config=False, vunit=None):
    if type(value) == dict:
        map = {}
        map[category] = value
        print(json.dumps(map))
    else:
        print(f'{category}:{value}')


def output_json(device_name, category, value, hass_config=False, vunit=None):
    map = {}
    if type(value) == dict:
        map[category] = value
    else:
        map[category] = {
            'value': value,
            'unit': vunit
        }
    print(json.dumps(map))


def output_syslog(device_name, category, value, hass_config=False, vunit=None):
    if type(value) == dict:
        map = {}
        map[category] = value
        return_data = json.dumps(map)
    else:
        return_data = f"{device_name}|{category}:{value}"

    subprocess.run(
        [
            "/usr/bin/logger",
            f"--id={os.getpid()}",
            "-t",
            "victron",
            return_data,
        ]
    )


def mqtt_onconnect(client, userdata, flags, rc):
    lient.publish(mqtt_lwt, payload=1, qos=0, retain=True)


def mqtt_pub(device_type, device_name, value):
    global client
    global config
    retain = False

    if not value == "":
        pub = f'{config["mqtt"]["base_topic"]}/{device_type}/{device_name}'
        if type(value) is dict:
            data = json.dumps(value)
        else:
            data = value

    client.publish(pub, data, retain=retain)


def get_helper_string_device(devices):
    return_string = ""
    for count, device in enumerate(devices):
        return_string += f"{count}: {device['name']} | "
    return return_string


def check_if_required_device_argument():
    for x in ['-h', '--help', '-v', '--version']:
        if x in sys.argv:
            return False
    return True


def DataParser(data, encryptionKey):
	parser = detect_device_type(bytes.fromhex(data))
	parsed_data = SolarCharger(encryptionKey).parse(bytes.fromhex(data))
	print("charge state: " + str(parsed_data.get_charge_state()))
	print("data: " + str(parsed_data))

	response = {
		"charge_state": parsed_data.get_charge_state().name,
		"battery_voltage": parsed_data.get_battery_voltage(),
		"battery_charging_current":  parsed_data.get_battery_charging_current(),
		"yield_today":    parsed_data.get_yield_today(),
		"solar_power": parsed_data.get_solar_power(),
		"external_device_load": parsed_data.get_external_device_load()
	}
	
	print("Response: "+ str(response))

	return response


class VictronScanner(BaseScanner):
    def __init__(self, device):
        super().__init__()
        self.device = device

    async def start(self):
        logger.info(f"Dumping advertisements from {self.device['mac']}")
        await super().start()

    def callback(self, device: BLEDevice, data: bytes):
        if device.address.lower() == self.device['mac'].lower():
            values = DataParser(data.hex(), self.device['encryptionKey'])
            logger.debug(f"\n{json.dumps(values, indent=3)}")
            
			#send to MQTT
            mqtt_pub(self.device['type'], self.device['name'], values)
            sys.exit(0)


if __name__ == "__main__":
    if os.path.exists('config.yml'):
        with open('config.yml', 'r') as ymlfile:
            config = yaml.full_load(ymlfile)
    else:
        config = None

    parser = argparse.ArgumentParser(description="Victron (Bluetooth BLE) to MQTT \n\n"
                                                 "Default behavior:\n"
                                                 "  1. It will connect to given device\n"
                                                 "  2. Collect and log data summary\n"
                                                 "  3. Disconnects and exits",
                                     formatter_class=argparse.RawTextHelpFormatter)
    group01 = parser.add_argument_group()
    group01.add_argument("--debug", action="store_true", help="Set log level to debug")
    group01.add_argument("--quiet", action="store_true", help="Set log level to error")

    group02 = parser.add_argument_group()
    group02.add_argument(
        "-C",
        "--config-file",
        type=str,
        help="Specify different config file [Default: config.yml]",
        required=False,
    )
    # group02.add_argument(
    #     "-D",
    #     "--direct-disconnect",
    #     action="store_true",
    #     help="Disconnect direct after getting values",
    #     required=False,
    # )
    group02.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Show version and exit",
        required=False,
    )

    group03 = parser.add_argument_group()
    group03.add_argument(
        "-d",
        "--device",
        metavar="NUM / NAME",
        type=str,
        help=get_helper_string_device(config['devices']) if config is not None else "",
        required=check_if_required_device_argument(),
    )
    args = parser.parse_args()

    if args.version:
        print(version)
        sys.exit(0)

    if args.config_file:
        with open(args.config_file, 'r') as ymlfile:
            config = yaml.full_load(ymlfile)

    if config is None:
        print("config.yml missing. Please create or specify another config file with -C")
        sys.exit(1)

    try:
        dev_id = int(args.device)
    except ValueError:
        for count, device_config in enumerate(config['devices']):
            if device_config['name'] == args.device:
                dev_id = count
                break
            print(f'{args.device} not found in config')
            sys.exit(1)
    device_config = config['devices'][dev_id]

	
    logger_format = '[%(levelname)-7s] (%(asctime)s) %(filename)s::%(lineno)d %(message)s'
    logging.basicConfig(level=logging.INFO,
                        format=logger_format,
                        datefmt='%Y-%m-%d %H:%M:%S',
                        filename=f'logs/victron-{device_config["name"]}.log')
    logger = logging.getLogger()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(logger_format)
    handler.setFormatter(formatter)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        handler.setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
        handler.setLevel(logging.ERROR)

    logger.addHandler(handler)

    import paho.mqtt.client as mqtt
    client = mqtt.Client()
    if "username" in config['mqtt'] and "password" in config['mqtt']:
        client.username_pw_set(username=config['mqtt']['username'],password=config['mqtt']['password'])

    client.connect(config['mqtt']['host'], config['mqtt']['port'], 60)
    client.loop_start()

    q = queue.Queue()

    loop = asyncio.get_event_loop()

    async def scan():
        scanner = VictronScanner(device_config)
        await scanner.start()
        await asyncio.sleep(60)

    asyncio.ensure_future(scan())
    loop.run_forever()
