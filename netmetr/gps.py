import math
import os
import serial


from .exceptions import ConfigError, RunError


class Location:
    def __init__(self, console_path):
        """ Measure GPS based on at command "at!gpsloc?"
        Example output:

            Lat: 49 Deg 44 Min 57.00 Sec N  (0x008D823D)
            Lon: 13 Deg 22 Min 48.54 Sec E  (0x00260F21)
            Time: 2018 11 21 2 10:10:02 (GPS)
            LocUncAngle: 0.0 deg  LocUncA: 192 m  LocUncP: 13 m  HEPE: 192.439 m
            3D Fix
            Altitude: 332 m  LocUncVe: 64.0 m
            Heading: 0.0 deg  VelHoriz: 0.0 m/s  VelVert: 0.0 m/s

            OK

        We are going to parse it line by line in this very order
        """
        if not os.path.exists(console_path):
            raise ConfigError("GPS special file not found!")

        with serial.Serial(console_path, timeout=5) as console:
            console.write(b"AT!GPSLOC?\r")
            console.readline()  # AT command echo

            self.lat = get_lat(console.readline().decode("utf-8"))
            self.lon = get_lon(console.readline().decode("utf-8"))
            console.readline()  # Time
            self.hepe = get_hepe(console.readline().decode("utf-8"))
            console.readline()  # 3DFix
            self.altitude = get_alt(console.readline().decode("utf-8"))
            self.bearing, self.velocity = get_heading_velocity(
                    console.readline().decode("utf-8"))


def get_lat(line):
    line_split = line.split(":")
    if line_split[0] == "Lat":
        line_split = line_split[1].split()
        lat = (float(line_split[0]) +
               float(line_split[2]) / 60 +
               float(line_split[4]) / 3600)
        if line_split[6] == "S":
            lat = -lat
        return lat
    else:
        raise RunError("Latitude measurement failed")


def get_lon(line):
    line_split = line.split(":")
    if line_split[0] == "Lon":
        line_split = line_split[1].split()
        lon = (float(line_split[0]) +
               float(line_split[2]) / 60 +
               float(line_split[4]) / 3600)
        if line_split[6] == "W":
            lon = -lon
        return lon
    else:
        raise RunError("Longitude measurement failed")


def get_hepe(line):
    line_split = line.split(":")
    if line_split[0] == "LocUncAngle":
        line_split = line_split[4].split()
        return float(line_split[0])
    else:
        raise RunError("HEPE measurement failed")


def get_alt(line):
    line_split = line.split(":")
    if line_split[0] == "Altitude":
        line_split = line_split[1].split()
        return float(line_split[0])
    else:
        raise RunError("Altitude measurement failed")


def get_heading_velocity(line):
    line_split = line.split(":")
    if line_split[0] == "Heading":
        split_h = line_split[1].split()
        bearing = float(split_h[0])
        # vertical and horizontal velocity measured in m/s
        split_vh = line_split[2].split()
        vh = float(split_vh[0])
        split_vv = line_split[3].split()
        vv = float(split_vv[0])
        velocity = math.sqrt(vv**2 + vh**2)
        return (bearing, velocity)
    else:
        raise RunError("Heading / velocity measurement failed")
