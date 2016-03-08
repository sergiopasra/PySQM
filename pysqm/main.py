
# PySQM main program
# ____________________________
#
# Copyright (c) Miguel Nievas <miguelnievas[at]ucm[dot]es>
#
# This file is part of PySQM.
#
# PySQM is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PySQM is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PySQM.  If not, see <http://www.gnu.org/licenses/>.
# ____________________________


import os,sys
import time
import datetime
import argparse

# Read input arguments (if any)

import pysqm.settings as settings
InputArguments = settings.ArgParser()
configfilename = InputArguments.config

# Load config contents into GlobalConfig
settings.GlobalConfig.read_config_file(configfilename)

# Get the actual config
config = settings.GlobalConfig.config

### Load now the rest of the modules
from pysqm.read import *
import pysqm.plot


# This import section is only for software build purposes.
# Dont worry if some of these are missing in your setup.

def relaxed_import(themodule):
    try: exec('import '+str(themodule))
    except: pass

relaxed_import('socket')
relaxed_import('serial')
relaxed_import('_mysql')
relaxed_import('pysqm.email')

# Conditional imports

# If the old format (SQM_LE/SQM_LU) is used, replace _ with -
config._device_type = config._device_type.replace('_','-')

if config._device_type == 'SQM-LE':
    import socket
elif config._device_type == 'SQM-LU':
    import serial
if config._use_mysql:
    import _mysql

# Create directories if needed
for directory in [config.monthly_data_directory,config.daily_data_directory,config.current_data_directory]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Select the device to be used based on user input
# and start the measures

if config._device_type=='SQM-LU':
    mydevice = SQMLU()
elif config._device_type=='SQM-LE':
    mydevice = SQMLE()
else:
    print('ERROR. Unknown device type '+str(config._device_type))
    exit(0)

def loop():
    '''
    Ephem is used to calculate moon position (if above horizon)
    and to determine start-end times of the measures
    '''
    observ = define_ephem_observatory()
    niter = 0
    DaytimePrint=True
    print('Starting readings ...')
    while True:
        # The programs works as a daemon
        utcdt = mydevice.read_datetime()
        #print (str(mydevice.local_datetime(utcdt))),
        if True or mydevice.is_nighttime(observ):
            # If we are in a new night, create the new file.
            config._send_to_datacenter = False ### Not enabled by default
            if config._send_to_datacenter and (niter == 0):
                mydevice.save_data_datacenter("NEWFILE")

            StartDateTime = datetime.datetime.now()
            niter += 1

            mydevice.define_filenames()

            # Get values from the photometer
            try:
                data = mydevice.read_photometer(Nmeasures=config._measures_to_promediate,
                                                PauseMeasures=10
                                                )
            except:
                print('Connection lost')
                if config._reboot_on_connlost:
                    time.sleep(600)
                    os.system('reboot.bat')

                time.sleep(1)
                mydevice.reset_device()
                continue

            (timeutc_mean, timelocal_mean, temp_sensor,
             freq_sensor, ticks_uC,sky_brightness) = data

            formatted_data = mydevice.format_content(
                timeutc_mean,
                timelocal_mean,
                temp_sensor,
                freq_sensor,
                ticks_uC,
                sky_brightness
            )

            if config._use_mysql:
                mydevice.save_data_mysql(formatted_data)

            if config._send_to_datacenter:
                mydevice.save_data_datacenter(formatted_data)


            mydevice.data_cache(formatted_data,
                                number_measures=config._cache_measures,
                                niter=niter)

            if niter % config._plot_each == 0:
                # Each X minutes, plot a new graph
                try:
                    pysqm.plot.make_plot(send_emails=False, write_stats=False)
                except:
                    print('Warning: Error plotting data.')
                    print(sys.exc_info())

            if not DaytimePrint:
                DaytimePrint = True

            MainDeltaSeconds = (datetime.datetime.now()-StartDateTime).total_seconds()
            time.sleep(max(1,config._delay_between_measures-MainDeltaSeconds))

        else:
            # Daytime, print info
            if DaytimePrint:
                utcdt = utcdt.strftime("%Y-%m-%d %H:%M:%S")
                print (utcdt),
                print('. Daytime. Waiting until '+str(mydevice.next_sunset(observ)))
                DaytimePrint = False
            if niter > 0:
                mydevice.flush_cache()
                if config._send_data_by_email:
                    try:
                        pysqm.plot.make_plot(send_emails=True,write_stats=True)
                    except:
                        print('Warning: Error plotting data / sending email.')
                        print(sys.exc_info())

                else:
                    try:
                        pysqm.plot.make_plot(send_emails=False,write_stats=True)
                    except:
                        print('Warning: Error plotting data.')
                        print(sys.exc_info())

                niter = 0

            # Send data that is still in the datacenter buffer
            if config._send_to_datacenter:
                mydevice.save_data_datacenter("")


            time.sleep(300)


