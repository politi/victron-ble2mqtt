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
import os
import os.path
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

MAX_MQTT_PUBLISH_ATTEMPTS = 5

store_and_forward_directory = './store-and-forward/'


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
	#client.publish(mqtt_lwt, payload=1, qos=0, retain=True)
	if args.debug: 
		if rc == 0:
			logger.debug("Connected to MQTT Broker!")
		else:
			logger.debug("Failed to connect to MQTT Broker. Return code: %d\n", rc)

	forwardStoredMessages()


def mqtt_onlog(client, userdata, level, buf):
	logger.debug("mqtt log: ",buf)

def mqtt_pub(device_type, device_name, value, store = True):
	global client
	global config
	retain = False

	if value != "":
		topic = f'{config["mqtt"]["base_topic"]}/{device_type}/{device_name}'
		if type(value) is dict:
			data = json.dumps(value)
		else:
			data = value
	pub_success = False
	pub_attempts = 0
	store_and_forward_filename = f"{device_type}_{device_name}_{value['_timestamp']}"
	logger.debug(f"[MQTT_PUB] storeAndForwardFileName: {store_and_forward_filename} - store={store}") 
	while True:
		result = client.publish(topic, data, retain=retain)
		# result: [0, 1]
		status = result[0]
		if status == 0:
			#print(f"Send `{msg}` to topic `{topic}`")
			logger.debug(f"Data published to topic `{topic}`.")
			pub_success = True
			deleteStoredMessage(store_and_forward_filename)

		else:
			#print(f"Failed to send message to topic {topic}")
			logger.info(f"Failed to send message to topic {topic}")
			pub_attempts += 1
		if pub_attempts > MAX_MQTT_PUBLISH_ATTEMPTS or pub_success:
			if not pub_success and store:
				logger.warning(f"MQTT publish failed after {MAX_MQTT_PUBLISH_ATTEMPTS} attempts. Storing message into: {filename}")
				storeMessage(store_and_forward_filename, data)
			break
	time.sleep(4) # wait
	client.loop_stop() #stop the loop


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

def storeMessage(filename, data):
	# Store message to file for later send
	logger.debug(f"[storeMessage] Storing message into: {filename}")
	file_path = os.path.join(store_and_forward_directory, filename)
	if not os.path.isdir(store_and_forward_directory):
		os.mkdir(store_and_forward_directory)
	file = open(file_path, "w")
	file.write(data)
	file.close()

def deleteStoredMessage(filename): 
	# Delete stored file (if exists)
	logger.debug(f"[deleteStoredMessage] Deleting stored file: {filename}")
	file_path = os.path.join(store_and_forward_directory, filename)
	if os.path.exists(file_path) and os.path.isfile(file_path):
		os.remove(file_path)

def forwardStoredMessages():
	# Attempts to publish stored messages
	logger.debug("[forwardStoredMessages] Forwarding stored/unsent data...")
	for filename in os.scandir(store_and_forward_directory):
		if filename.is_file():
			#print(f"name: {filename.name}")
			parts = filename.name.split("_")
			device_type = parts[0]
			device_name = parts[1]
			with open(filename.path) as f:
				data = f.readline()	# we only have one line, so no need to loop or use readlines
				#print(f"data: {data}")
				data = json.loads(data)
				mqtt_pub(device_type, device_name, data, False)


def DataParser(data, encryptionKey):
	parser = detect_device_type(bytes.fromhex(data))
	parsed_data = SolarCharger(encryptionKey).parse(bytes.fromhex(data))
	#print("charge state: " + str(parsed_data.get_charge_state()))
	print("data: " + str(parsed_data))

	response = {
		"charge_state": parsed_data.get_charge_state().name,
		"battery_voltage": parsed_data.get_battery_voltage(),
		"battery_charging_current":  parsed_data.get_battery_charging_current(),
		"yield_today":    parsed_data.get_yield_today(),
		"solar_power": parsed_data.get_solar_power(),
		"external_device_load": parsed_data.get_external_device_load(),
		"_timestamp": int(time.time()*1000)
	}
	
	print("Victron Response: "+ str(response))

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
			
			# retrieve last data from Victron, and send it to MQTT
			mqtt_pub(self.device['type'], self.device['name'], values)

			# Forward old data (stored on file after publish error)

			logger.debug(f"Program terminated. Exiting")
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
	#client.on_log=mqtt_onlog
	client.on_connect=mqtt_onconnect
	client.loop_start()

	q = queue.Queue()

	loop = asyncio.get_event_loop()

	async def scan():
		scanner = VictronScanner(device_config)
		await scanner.start()
		await asyncio.sleep(60)

	asyncio.ensure_future(scan())
	loop.run_forever()
