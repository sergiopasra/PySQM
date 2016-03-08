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

import os
import datetime
import time
import logging

# Read input arguments (if any)

logging.basicConfig(level=logging.DEBUG)

import pysqm.settings as settings

InputArguments = settings.ArgParser()
configfilename = InputArguments.config

# Load config contents into GlobalConfig
settings.GlobalConfig.read_config_file(configfilename)

# Get the actual config
config = settings.GlobalConfig.config

### Load now the rest of the modules
import pysqm.read
import pysqm.plot
import pysqm.common

# Conditional imports

# If the old format (SQM_LE/SQM_LU) is used, replace _ with -
config._device_type = config._device_type.replace('_', '-')

if config._device_type == 'SQM-LE':
    pass
elif config._device_type == 'SQM-LU':
    pass
if config._use_mysql:
    pass

# Create directories if needed
for directory in [config.monthly_data_directory, config.daily_data_directory, config.current_data_directory]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Select the device to be used based on user input
# and start the measures

if config._device_type == 'SQM-LU':
    try:
        logging.info('Trying fixed device address %s ... ', config._device_addr)
        mydevice = pysqm.read.SQMLU(addr=config._device_addr)
    except StandardError:
        logging.warn('Device not found in %s', config._device_addr)

    logging.info('Trying auto device address ...')
    autodev = pysqm.read.SQMLU.search(bauds=115200)
    if autodev is None:
        logging.error('Device not found!')
        exit(0)

    logging.info('Found address %s ... ', autodev)

    try:
        mydevice = pysqm.read.SQMLU(addr=autodev)
    except StandardError:
        logging.error('Device not found!')
        exit(0)

elif config._device_type == 'SQM-LE':
    mydevice = pysqm.read.SQMLE()
else:
    logging.error('Unknown device type %s', config._device_type)
    exit(0)


def loop():

    # Ephem is used to calculate moon position (if above horizon)
    # and to determine start-end times of the measures
    logging.basicConfig(level=logging.DEBUG)
    observ = pysqm.common.define_ephem_observatory()
    niter = 0
    DaytimePrint = True
    logging.info('Starting readings ...')
    while True:
        # The programs works as a daemon
        utcdt = mydevice.read_datetime()
        # print (str(mydevice.local_datetime(utcdt))),
        if True or mydevice.is_nighttime(observ):
            # If we are in a new night, create the new file.
            config._send_to_datacenter = False  ### Not enabled by default
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
                logging.info('Connection lost')
                # FIXME: not appropriated in all cases
                if config._reboot_on_connlost:
                    time.sleep(600)
                    os.system('reboot.bat')

                time.sleep(1)
                mydevice.reset_device()
                continue

            (timeutc_mean, timelocal_mean, temp_sensor,
             freq_sensor, ticks_uC, sky_brightness) = data

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
                    logging.warn('Problem plotting data.', exc_info=True)

            if not DaytimePrint:
                DaytimePrint = True

            MainDeltaSeconds = (datetime.datetime.now() - StartDateTime).total_seconds()
            time.sleep(max(1, config._delay_between_measures - MainDeltaSeconds))

        else:
            # Daytime, print info
            if DaytimePrint:
                utcdt = utcdt.strftime("%Y-%m-%d %H:%M:%S")
                logging.info("%s", utcdt)
                logging.info('Daytime. Waiting until %s', mydevice.next_sunset(observ))
                DaytimePrint = False
            if niter > 0:
                mydevice.flush_cache()
                if config._send_data_by_email:
                    try:
                        pysqm.plot.make_plot(send_emails=True, write_stats=True)
                    except:
                        logging.warn('Error plotting data / sending email.',exc_info=True)

                else:
                    try:
                        pysqm.plot.make_plot(send_emails=False, write_stats=True)
                    except:
                        logging.warn('Problem plotting data.', exc_info=True)

                niter = 0

            # Send data that is still in the datacenter buffer
            if config._send_to_datacenter:
                mydevice.save_data_datacenter("")

            time.sleep(300)
