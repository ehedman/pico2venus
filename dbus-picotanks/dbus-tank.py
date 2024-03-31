#!/usr/bin/env python3

# Copyright (c) 2021 LHardwick-git
# Licensed under the BSD 3-Clause license. See LICENSE file in the project root for full license information.
# Copyright (c) 2024 ehedman-git: Pico version

from dbus.mainloop.glib import DBusGMainLoop
import sys
if sys.version_info.major == 2:
    import gobject
    from gobject import idle_add
else:
    from gi.repository import GLib as gobject
import dbus
import dbus.service
import inspect
import platform
from threading import Timer
import argparse
import logging
import sys
import os
import math
import time
import signal
import json
from pprint import pprint

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-pump/ext/velib_python'))
from vedbus import VeDbusService, VeDbusItemExport, VeDbusItemImport 
from settingsdevice import SettingsDevice  # available in the velib_python repository

def signal_handler(sig, frame):
    print('SIGINT received')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

dbusservice = None

def update():
    update_values()
    return True

def update_values():

    try:
        # Retrieve JSON data from the file
        with open("/run/udev/data/pico-data.json", "r") as file:
            values = json.load(file)
            file.close()
            os.remove("/run/udev/data/pico-data.json")
    except:
        logging.info('update_values: No /run/udev/data/pico-data.json file yet')
        dbusservice['pico_srv-1']['/Connected'] = 0
        dbusservice['pico_srv-2']['/Connected'] = 0
        dbusservice['pico_srv-3']['/Connected'] = 0
        dbusservice['pico_srv-4']['/Connected'] = 0
        return

    if not values:
        logging.info('update_values: No new data from file /run/udev/data/pico-data.json')
        return

#    print(json.dumps(values, indent=2))

# NOTE: Custom Name (dbusservice /CustomName) must be set in the remote console to match the naming convention in the Pico device.
# Consequently, changing the name in the Pico device must be followed up with the corresponding change in the Venus system.

    try: 
        for item in range(0, len(values)):
            if "name" in values[str(item)]:
                if  values[str(item)]["name"] == dbusservice['pico_srv-1']['/CustomName']:
                    dbusservice['pico_srv-1']['/Level'] =               float(values[str(item)]["currentLevel"]*100)
                    dbusservice['pico_srv-1']['/Remaining'] =           float(values[str(item)]["currentVolume"])
                    dbusservice['pico_srv-1']['/Connected'] = 1

                elif values[str(item)]["name"] == "dbusservice['pico_srv-2']['/CustomName']":
                    dbusservice['pico_srv-2']['/Level'] =               float(values[str(item)]["currentLevel"]*100)
                    dbusservice['pico_srv-2']['/Remaining'] =           float(values[str(item)]["currentVolume"])
                    dbusservice['pico_srv-2']['/Connected'] = 1

                elif values[str(item)]["name"] == dbusservice['pico_srv-2']['/CustomName']:
                    dbusservice['pico_srv-3']['/Level'] =               float(values[str(item)]["currentLevel"]*100)
                    dbusservice['pico_srv-3']['/Remaining'] =           float(values[str(item)]["currentVolume"])
                    dbusservice['pico_srv-3']['/Connected'] = 1

                elif values[str(item)]["name"] == dbusservice['pico_srv-4']['/CustomName']:
                    dbusservice['pico_srv-4']['/Dc/0/Voltage'] =        round(float(values[str(item)]["voltage"]),2)
                    dbusservice['pico_srv-4']['/Dc/0/Current'] =        round(1- float(values[str(item)]["current"])-1,2)
                    dbusservice['pico_srv-4']['/Dc/0/Power'] =          round(1- float(values[str(item)]["voltage"]) * float(values[str(item)]["current"])-1,1)
                    dbusservice['pico_srv-4']['/TimeToGo'] =            int(values[str(item)]["capacity.timeRemaining"]*6)
                    dbusservice['pico_srv-4']['/Soc'] =                 float(values[str(item)]["stateOfCharge"]) * 100
                    dbusservice['pico_srv-4']['/Connected'] = 1

                elif  values[str(item)]["name"] == "Start Battery":
                    dbusservice['pico_srv-4']['/Dc/1/Voltage'] =        round(float(values[str(item)]["voltage"]),2)

                elif  values[str(item)]["name"] == "TM 1":
                    dbusservice['pico_srv-4']['/Dc/0/Temperature'] =    round(float(values[str(item)]["temperature"])-273.15,1)
                    
    except BaseException:
        logging.info("update_values: An exception was thrown!", exc_info=True)
        return

# =========================== Start of settings interface ================
#  The settings interface handles the persistent storage of changes to settings
#  This should probably be created as a new class extension to the settingDevice object
#  The complexity is because this python service handles temperature and humidity
#  Data for about 6 different service paths so we need different dBusObjects for each device
#
newSettings = {}     # Used to gather new settings to create/check as each dBus object is created
settingObjects = {}  # Used to identify the dBus object and path for each setting
                     # settingsObjects = {setting: [path,object],}
                     # each setting is the complete string e.g. /Settings/Tank/5/FluidType /FluidType

settingDefaults = { '/FluidType'            : [0, 0, 0],
                    '/CustomName'           : ['', 0, 0],
                    '/Alarms/Low/Active'    : [0, 0, 0],
                    '/Alarms/Low/Enable'    : [0, 0, 0],
                    '/Alarms/Low/Restore'   : [0, 0, 0],
                    '/Alarms/Low/Delay'     : [0, 0, 0],
                    '/Capacity'             : [0,2, 0, 1000]
                }

# Values changed in the GUI need to be updated in the settings
# Without this changes made through the GUI change the dBusObject but not the persistent setting
# (as tested in venus OS 2.54 August 2020)
def handle_changed_value(setting, path, value):
    global settings
    print("some value changed")
    # The callback to the handle value changes has been modified by using an anonymouse function (lambda)
    # the callback is declared each time a path is added see example here
    # self.add_path(path, 0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
    logging.info(" ".join(("Storing change to setting", setting+path, str(value) )) )
    settings[setting+path] = value
    return True

# Changes made to settings need to be reflected in the GUI and in the running service
def handle_changed_setting(setting, oldvalue, newvalue):
    logging.info('Setting changed, setting: %s, old: %s, new: %s' % (setting, oldvalue, newvalue))
    [path, object] = settingObjects[setting]
    object[path] = newvalue
    return True

# Add setting is called each time a new service path is created that needs a persistent setting
# If the setting already exists the existing recored is unchanged
# If the setting does not exist it is created when the serviceDevice object is created
def addSetting(base, path, dBusObject):
    global settingObjects
    global newSettings
    global settingDefaults
    setting = base + path
    logging.info(" ".join(("Add setting", setting, str(settingDefaults[path]) )) )
    settingObjects[setting] = [path, dBusObject]             # Record the dBus Object and path for this setting 
    newSettings[setting] = [setting] + settingDefaults[path] # Add the setting to the list to be created

# initSettings is called when all the required settings have been added
def initSettings(newSettings):
    global settings

#   settingsDevice is the library class that handles the reading and setting of persistent settings
    settings = SettingsDevice(
        bus=dbus.SystemBus() if (platform.machine() == 'aarch64') else dbus.SessionBus(),
        supportedSettings = newSettings,
        eventCallback     = handle_changed_setting)

# readSettings is called after init settings to read all the stored settings and
# set the initial values of each of the service object paths
# Note you can not read or set a setting if it has not be included in the newSettings
#      list passed to create the new settingsDevice class object

def readSettings(list):
    global settings
    for setting in list:
        [path, object] = list[setting]
        logging.info(" ".join(("Retreived setting", setting, path, str(settings[setting]))))
        object[path] = settings[setting]

# =========================== end of settings interface ======================

class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)

class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)

def dbusconnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()


# Argument parsing
parser = argparse.ArgumentParser(description='dbusMonitor.py demo run')
parser.add_argument("-d", "--debug", help="set logging level to debug", action="store_true")
args = parser.parse_args()

#args.debug = True

# Init logging
logging.basicConfig(level=(logging.DEBUG if args.debug else logging.INFO))
logging.info(__file__ + " is starting up")
logLevel = {0: 'NOTSET', 10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR'}
logging.info('Loglevel set to ' + logLevel[logging.getLogger().getEffectiveLevel()])

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

def new_pico_service(base, type, physical, connection, id, instance, settingId = False):
    self =  VeDbusService("{}.{}.{}_id{:02d}".format(base, type, physical, id), dbusconnection())
    # physical is the physical connection 
    # logical is the logical connection to allign with the numbering of the console display
    # Create the management objects, as specified in the ccgx dbus-api document
    self.add_path('/Mgmt/ProcessName', __file__)
    self.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
    self.add_path('/Mgmt/Connection', connection)

    # Create the mandatory objects, note these may need to be customised after object creation
    self.add_path('/DeviceInstance',    instance)
    self.add_path('/ProductId',         0)
    self.add_path('/ProductName',       '')
    self.add_path('/FirmwareVersion',   0)
    self.add_path('/HardwareVersion',   0)
    self.add_path('/Connected',         0)  # Mark devices as disconnected until they are confirmed
    self.add_path('/Status',            0)

    # Create device type specific objects set values to empty until connected
    if settingId :
        setting = "/Settings/" + type.capitalize() + "/" + str(settingId)
    else:
        print("no setting required")
        setting = "" 

    if type == 'tank':
        if settingId:
            addSetting(setting , '/FluidType',          self)
            addSetting(setting , '/CustomName',         self)
            addSetting(setting , '/Alarms/Low/Active',  self)
            addSetting(setting , '/Alarms/Low/Enable',  self)
            addSetting(setting , '/Alarms/Low/Restore', self)
            addSetting(setting , '/Alarms/Low/Delay',   self)
            addSetting(setting , '/Capacity', self)

        self.add_path('/Capacity',      0,      writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/FluidType',     0,      writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/Level',         0,      writeable=True)
        self.add_path('/Remaining',     0,      writeable=True)
        self.add_path('/CustomName',    '',     writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/Alarms/Low/Active', 0,  writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/Alarms/Low/Enable', 0,  writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/Alarms/Low/Restore', 0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/Alarms/Low/Delay',  0,  writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/Alarms/Low/State',  0)
    if type == 'battery':
        if settingId:
            addSetting(setting , '/CustomName', self)

        self.add_path('/Soc', 0,                writeable=True)
        self.add_path('/TimeToGo', 0,           writeable=True)
        self.add_path('/Dc/0/Voltage', 0,       writeable=True)
        self.add_path('/Dc/1/Voltage', 0,       writeable=True)
        self.add_path('/Dc/0/Current', 0,       writeable=True)
        self.add_path('/Dc/0/Power', 0,         writeable=True)
        self.add_path('/Dc/0/Temperature', 0,   writeable=True)
        self.add_path('/CustomName','',         writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/History/DischargedEnergy', 0)
        self.add_path('/History/ChargedEnergy', 0)

    return self

dbusservice = {} # Dictionary to hold the multiple services

base = 'com.victronenergy'

# Init setting - create setting object to read any existing settings
# Init is called again later to set anything that does not exist
# this gets round the Chicken and Egg bootstrap problem,

# service defined by (base*, type*, connection*, logial, id*, instance, settings ID):
# The setting iD is used with settingsDevice library to create a persistent setting
# Items marked with a (*) are included in the service name

dbusservice['pico_srv-1']   = new_pico_service(base, 'tank',    'pico-1',  'pico-1', 1, 30, 1)
dbusservice['pico_srv-2']   = new_pico_service(base, 'tank',    'pico-2',  'pico-2', 2, 31, 2)
dbusservice['pico_srv-3']   = new_pico_service(base, 'tank',    'pico-3',  'pico-3', 3, 32, 3)
dbusservice['pico_srv-4']   = new_pico_service(base, 'battery', 'pico-4',  'pico-4', 4, 33, 4)

# Tidy up custom or missing items
dbusservice['pico_srv-1']   ['/ProductName']   = 'Simarine Pico Tank sensor'
dbusservice['pico_srv-2']   ['/ProductName']   = 'Simarine Pico Tank sensor'
dbusservice['pico_srv-3']   ['/ProductName']   = 'Simarine Pico Tank sensor'
dbusservice['pico_srv-4']   ['/ProductName']   = 'BMV-700'

# Persistent settings obejects in settingsDevice will not exist before this is executed
initSettings(newSettings)
# Do something to read the saved settings and apply them to the objects
readSettings(settingObjects)

# Do a first update so that all the readings appear.
update()
# update every 5 seconds - values should move slowly so no need to demand too much CPU time
#
gobject.timeout_add(5000, update)

logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
mainloop = gobject.MainLoop()
mainloop.run()

