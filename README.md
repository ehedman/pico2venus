# pico2venus
README March 2024

Pico Marine 2 Victron Venus Integration

This project is loosely based on source code from:
 - https://github.com/LHardwick-git/Victron-Service/tree/main with gratitude to LHardwick-git
 - https://github.com/htool/pico2signalk with gratitude to Hans htool


### Early commit
This is work in progress to be refined first half of 2024

The purpose of this project is to gather data from a Pico Marine system through the wifi network and feed the data to a victron venus system running on a raspberry pi

Currently this application supports reading of battery banks and tanks levels.

The result is presented from the remote console and VRM.

Two applications has to be running simoustainely: 
 - dbus-tank.py - to feed dbus data and read a json file created by:
 - pico.py - connects to the pico device and dump its data to a json file



