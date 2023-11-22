# Victron Bluetooth to MQTT bridge


**This repository is in no way approved by or affiliated with the official Victron Energy repository.**
**I am not responsible for any problems or damages with your devices or this code**

**Only run this script if you are sure you know what you are doing!**

This repository is based on [https://github.com/FloMaetschke/victron](https://github.com/FloMaetschke/victron).

But has been modified to use [victron_ble](https://github.com/keshavdv/victron-ble), a python library developed by [keshavdv](https://github.com/keshavdv) to parse Instant Readout advertisement data from Victron devices.

I use this repository remotely monitor Victron devices installed on the field, by sending the parsed data to an MQTT broker.  

More detail about the global Victron BLE Monitor, its architecture and the hardware and software components, can be found in its GitHub repository: [Victron BLE Monitor](https://github.com/politi/victron-ble-monitor)

***Note:*** this software has only been tested with Bluetooth communication. Serial communication has not been tested (yet).


## Ability of this repository
The script is tested with python > 3.7
### Supported/tested devices:
Bluetooth BLE: 
- Smart Shunt

Bluetooth:
- Smart Shunt
- Smart Solar 100/30
- Orion Smart 12/12-30

Serial:
- Phoenix Inverter 12 800VA 230V
- Smart Shunt
- Smart Solar 100/30

### Outputs (Single values or as collection of values)
- mqtt

### Autostart scripts (systemd)
These scripts are written for my specific config file. If you have your devices in different order, you may need to adjust them.


## Install

- Install Python and PIP
```bash
sudo apt update
sudo apt install python3.8
sudo apt install python3-pip
```
- Clone this repo
- install dependencies
```bash
pip install -r requirements.txt
```
- on raspberry pi os, the following libs are also required:
```bash
sudo apt install build-essential libdbus-glib-1-dev libgirepository1.0-dev libcairo2 libcairo2-dev
```
- copy files to `/opt` or other choosen directory
```bash
cd /opt
unzip victron-ble2mqtt.zip
```

## Configuration

To configure the software, you need to edit the config.yml file found in the same directory of the script, to match the parameters of both the Victron device and the MQTT broker.

```yaml
## Add your devices here:
#devices:
#    - name: Shunt1
#      type: smartshunt
#      protocol: bluetooth-ble
#      mac: fd:d4:50:0f:6c:1b
#    - name: Solar1
#      type: smartsolar
#      protocol: bluetooth
#      mac: F9:8E:1C:EC:9C:72
#    - name: Phoenix1
#      type: pheonix
#      protocol: serial
#      port: /dev/ttyUSB0
devices:
    - name: HQ123456NKZ
      type: smartsolar
      protocol: bluetooth
      mac: FA:AC:27:84:C6:6F
      encryptionKey: 28a2158cf5b76f78b539e4140567b36f


## MQTT server
## Mandatory:
##   host: IP or Hostname
##   port: 1883
##   base_topic: victron
## Optional:
##   username: MQTT_USER
##   password: PASSWORD
mqtt:
    #host: 127.0.0.1
    host: mydataserverip.com
    port: 1883
    base_topic: victron
    hass: False
    #username: USERNAME
    #password: PASSWORD
```

***Note***: the MQTT configuration should match the one set in the [Mosquitto MQTT Broker](#mosquitto-broker) on data server.


***<u>Command line arguments</u>***
```
./victron.py -h
usage: victron.py [-h] [--debug] [--quiet] [-c] [-C CONFIG_FILE] [-v] [-d NUM / NAME]

Victron Reader (Bluetooth, BLE and Serial) 

Current supported devices:
  Full: 
    - Smart Shunt (Bluetooth BLE)
    - Phoenix Inverter (Serial)
    - Smart Shunt (Serial)
    - Smart Solar (Serial)
    - Blue Solar (Serial)
  Partial: 
    - Smart Shunt (Bluetooth)
    - Smart Solar (Bluetooth)
    - Orion Smart (Bluetooth)
Default behavior:
  1. It will connect to given device
  2. Collect and log data summary as defined at the config file
  3. Disconnect and exit

options:
  -h, --help            show this help message and exit

  --debug               Set log level to debug
  --quiet               Set log level to error

  -C CONFIG_FILE, --config-file CONFIG_FILE
                        Specify different config file [Default: config.yml]
  -v, --version         Show version and exit

  -d NUM / NAME, --device NUM / NAME [MANDATORY]

```


## Running
Start the script for your desired device: `python3 victron.py -d 0`
Add any other command line parameters as needed


## Install as startup service
To install as a service using systemd, follow this procedure

```bash
sudo ln -s /opt/victron-ble2mqtt/victron-ble2mqtt.service /etc/systemd/system/victron-ble2mqtt.service

sudo systemctl enable victronMonitor.service

sudo systemctl start victronMonitor.service
```

***Note:*** keep in mind that the source code is set to only get read data once, sent it do MQTT, and exit. If you need to read data more than once, you have to either change the code or run it multiple times (i.e. using crontab)

## Install in crontab
Depending on you needs you can also (alternatively) configure it running at boot or periodically using cron.
```bash
crontab -e
```

Add/edit/comment/uncomment the following lines in the crontab as needed

```crontab
#*/5 * * * * /opt/victron-ble2mqtt/victron-ble2mqtt.sh  # Run every 5 minutes

# run at boot with a 10 second delay (Witty Pi is used to power OFF/ON periodically to reduce power consumption)
#@reboot sleep 10 && /opt/victron-ble2mqtt/victron-ble2mqtt.sh

# run every day at 20:20 and 20:40 (when the maintainance ON time window is active and the Pi is not rebooting every 20 minutes)
#20 20 * * *  /opt/victron-ble2mqtt/victron-ble2mqtt.sh
#20 40 * * *  /opt/victron-ble2mqtt/victron-ble2mqtt.sh


# run every 20 minutes (power scheduler will power on the Raspberry 2 minutes before execution, and turn it off 3 minute after)
*/20 * * * *  /opt/victron-ble2mqtt/victron-ble2mqtt.sh
```




### BLE pairing
If you are using bluetooth or bluetooth ble you must be pairing your devices via `bluetoothctl`.

```bash
# Open bluetoothctl from commandline
bluetoothctl

# Enable scanning
scan on
  
# Get the mac address of your device
# pair device and enter pin
pair MAC
```

### Fetching Device Encryption Keys
To be able to decrypt the contents of the advertisement, you'll need to first fetch the per-device encryption key from the official Victron application. The method to do this will vary per platform.
 
**OSX**

1. Install the Victron app from the Mac App Store
2. Pair with your device at least once to transfer keys
3. Run the following from Terminal to dump the known keys (install `sqlite3` via Homebrew)
```bash
sqlite3 ~/Library/Containers/com.victronenergy.victronconnect.mac/Data/Library/Application\ Support/Victron\ Energy/Victron\ Connect/d25b6546b47ebb21a04ff86a2c4fbb76.sqlite 'select address,advertisementKey from advertisementKeys inner join macAddresses on advertisementKeys.macAddress == macAddresses.macAddress'
```

**Linux**

1. Download the Victron AppImage app from the Victron website.
2. Pair with your device at least once to transfer keys
3. Run the following from a terminal to dump the known keys (install `sqlite3` via your package manager)
```bash
sqlite3 ~/.local/share/Victron\ Energy/Victron\ Connect/d25b6546b47ebb21a04ff86a2c4fbb76.sqlite 'select address,advertisementKey from advertisementKeys inner join macAddresses on advertisementKeys.macAddress == macAddresses.macAddress'
```

**Windows**

1. Download the VictronConnect installer from the Victron website and install.
2. Pair with your device at least once to transfer keys
3. Open Explorer, navigate to ```%AppData%\Local\Victron Energy\Victron Connect\```
4. Open [SQLite Viewer](https://inloop.github.io/sqlite-viewer/) in a web browser of your choice
5. Drag and drop the ```d25b6546b47ebb21a04ff86a2c4fbb76.sqlite``` file from Explorer into the SQLite Viewer window

**Android**

The procedure to extract the encryprion key form an Android device is a little more complicated and requires you to enable developer options
It does NON require you to root your device

##### *<ins>Prepare the PC (Windows) - ONE TIME ONLY</ins>*
1. Download ADB tools from [here](https://dl.google.com/android/repository/platform-tools-latest-windows.zip)
2. Extract the arcive in a choosen directory (ex. c:\platform-tools)

##### *<ins>Prepare Android Device - ONE TIME ONLY</ins>*
1. enable developer options 
	a. Go to *settings*  -> *device information* or *About phone* -> *software information*
    b. Touch the Build number field 7 times. You will begin seeing a message as you approach the 7 touches.
    c. Touch the back arrow once complete, and Developer options will now appear under Settings.
2. Enable debug permissions
	a. Go to *settings* -> *Developer options*
	b. Verify that the checkbox on the top of the screen is **enabled**
	c. Scroll down to **USB debug** option and enable it

##### *<ins>Close to the Victron (on the field)</ins>*
1. Just launche the *Victron Connect* app and connect to the victron device


##### *<ins>Download the data from the Android device (back at the PC)</ins>*
1. Connect the Android phone to the PC with a USB cable
2. Open a Windows command console (start -> cmd)
3. Go to to the <ins>platform-tools</ins> direcotry. (if the <ins>platform-tools</ins> software has been installed/extracted in a different directory, just write the right path)
```cmd
 cd c:\platform-tools
```
	
4. Verify that the Android device is recognized:
```cmd
adb devices
```
A list of connected devices should appear (you should see only one device)
```cmd
C:\platform-tools>adb devices
	List of devices attached
	R58M63EQGSV     device
```
  
**Note**: the first time you connect ADB to the device, you should see an authorization request on the device itself. 
> Tap on **Always allow from this computer** and press **OK**
		
5. Type in the following command to extract the data form the Victorn Connect app
```cmd
adb backup -noapk com.victronenergy.victronconnect -f victron-data.adb
```

6. on the phone, you will see a screen informing that a data backup has been requested.
> To proceed you may need to insert a password

8. Type in a password (es. 12345)

9. Press the button "Backup my data"

10. After a few seconds, on the PC, in the directory where you have installed the Android platform-tools (i.e. c:\platform-tools) a file **victron.data.adb** will be created.



##### *<ins>Decrypting the backup</ins>*

The backup has been encrypted with an AES256 key.

To decrypt it you can use a program called *Android Backup Extractor*.
You can download it fromn [here](https://github.com/nelenkov/android-backup-extractor)

1. Go to the project home page and download the latest availanle release (or you can compile the source code if you prefer)

2. Launch the following command (you need a Java RE installed on the PC)
```cmd
java -jar abe.jar unpack victron-data.adb victron-data.tar <password>

es.
java -jar abe.jar unpack victron-data.adb victron-data.tar 12345
```
   
3. A new file called <ins>victron-data.tar</ins> will be created

4. Extract the content of the unencrypted archive

5. Navigate to the actual data directory
```cmd
apps\com.victronenergy.victronconnect\f
```

6. Copy the <ins>.sqlite</ins> file (it has a long name that change for very device)
```cmd
es. 
d25b6546b47ebb21a04ff86a2c4fbb76.sqlite
```







