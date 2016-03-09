
import datetime
import ephem
import math


def define_ephem_observatory(config):
    ''' Define the Observatory in Pyephem '''
    OBS = ephem.Observer()
    OBS.lat = config._observatory_latitude*ephem.pi/180
    OBS.lon = config._observatory_longitude*ephem.pi/180
    OBS.elev = config._observatory_altitude
    return OBS


def read_datetime():
    # Get UTC datetime from the computer.
    utc_dt = datetime.datetime.utcnow()
    #utc_dt = datetime.datetime.now() - datetime.timedelta(hours=config._computer_timezone)
            #time.localtime(); daylight_saving=_.tm_isdst>0
    return utc_dt


def local_datetime(utc_dt, local_timezone):
    # Get Local datetime from the computer, without daylight saving.
    return utc_dt + datetime.timedelta(hours=local_timezone)


def calculate_sun_altitude(OBS,timeutc):
    # Calculate Sun altitude
    OBS.date = ephem.date(timeutc)
    Sun = ephem.Sun(OBS)
    return(Sun.alt)


def next_sunset(OBS, observatory_horizon):
    # Next sunset calculation
    previous_horizon = OBS.horizon
    OBS.horizon = str(observatory_horizon)
    next_setting = OBS.next_setting(ephem.Sun()).datetime()
    next_setting = next_setting.strftime("%Y-%m-%d %H:%M:%S")
    OBS.horizon = previous_horizon
    return(next_setting)


def is_nighttime(OBS, observatory_horizon):
    # Is nightime (sun below a given altitude)
    timeutc = read_datetime()
    if calculate_sun_altitude(OBS,timeutc)* 180.0 / math.pi > observatory_horizon:
        return False
    else:
        return True