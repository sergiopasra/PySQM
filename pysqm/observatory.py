
import datetime
import ephem
import math


def define_ephem_observatory(config):
    """Define the Observatory in Pyephem"""
    obs = ephem.Observer()
    obs.lat = config._observatory_latitude * math.pi / 180.0
    obs.lon = config._observatory_longitude * math.pi / 180.0
    obs.elev = config._observatory_altitude
    return obs


def read_datetime():
    # Get UTC datetime from the computer.
    utc_dt = datetime.datetime.utcnow()
    return utc_dt


def local_datetime(utc_dt, local_timezone):
    # Get Local datetime from the computer, without daylight saving.
    return utc_dt + datetime.timedelta(hours=local_timezone)


def calculate_sun_altitude(obs, timeutc):
    # Calculate Sun altitude
    obs.date = ephem.date(timeutc)
    sun = ephem.Sun(obs)
    return sun.alt


def next_sunset(obs, observatory_horizon):
    # Next sunset calculation
    previous_horizon = obs.horizon
    obs.horizon = str(observatory_horizon)
    next_setting = obs.next_setting(ephem.Sun()).datetime()
    next_setting = next_setting.strftime("%Y-%m-%d %H:%M:%S")
    obs.horizon = previous_horizon
    return next_setting


def is_nighttime(obs, observatory_horizon):
    # Is nightime (sun below a given altitude)
    timeutc = read_datetime()
    if calculate_sun_altitude(obs, timeutc)* 180.0 / math.pi > observatory_horizon:
        return False
    else:
        return True