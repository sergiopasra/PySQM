#!/usr/bin/env python

'''
PySQM reading program
____________________________

Copyright (c) Miguel Nievas <miguelnievas[at]ucm[dot]es>

This file is part of PySQM.

PySQM is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PySQM is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PySQM.  If not, see <http://www.gnu.org/licenses/>.

____________________________

Requirements:
 - Python 2.7
 - Pyephem
 - Numpy
 - Socket (for SQM-LE). It should be part of standard python install.
 - Serial (for SQM-LU)
 - python-mysql to enable DB datalogging [optional].

____________________________
'''

__author__ = "Miguel Nievas"
__copyright__ = "Copyright (c) 2014 Miguel Nievas"
__credits__ = [\
 "Miguel Nievas @ UCM",\
 "Jaime Zamorano @ UCM",\
 "Laura Barbas @ OAN",\
 "Pablo de Vicente @ OAN"\
 ]
__license__ = "GNU GPL v3"
__shortname__ = "PySQM"
__longname__ = "Python Sky Quality Meter pipeline"
__version__ = "2.4"
__maintainer__ = "Miguel Nievas"
__email__ = "miguelnr89[at]gmail[dot]com"
__status__ = "Development" # "Prototype", "Development", or "Production"


import os,sys
import inspect
import time,signal
import math
import datetime
import ephem
import numpy as np
import struct

from .common import *

# Default, to ignore the length of the read string.
_cal_len_  = None
_meta_len_ = None
_data_len_ = None

# Read the config variables from pysqm.config.py
import pysqm.config
import pysqm.plot
Options = pysqm.config.__dict__
#Options.pop('__builtins__')
Keys = Options.keys()
Values = Options.values()
Items = Options.items()

# Import config variables
for index in xrange(len(Items)):
	if "__" not in str(Items[index][0]):
		exec("from pysqm.config import "+str(Items[index][0]))


'''
This import section is only for software build purposes.
Dont worry if some of these are missing in your setup.
'''

def relaxed_import(themodule):
	try: exec('import '+str(themodule))
	except: pass

relaxed_import('socket')
relaxed_import('serial')
relaxed_import('_mysql')
relaxed_import('pysqm.email')

'''
Conditional imports
'''

# If the old format (SQM_LE/SQM_LU) is used, replace _ with -
_device_type = _device_type.replace('_','-')

if _device_type == 'SQM-LE':
	import socket
elif _device_type == 'SQM-LU':
	import serial
if _use_mysql == True:
	import _mysql


# Create directories if needed
for directory in [monthly_data_directory,daily_data_directory,current_data_directory]:
	if not os.path.exists(directory):
		os.makedirs(directory)



def filtered_mean(array,sigma=3):
	# Our data probably contains outliers, filter them
	# Notes:
	#   Median is more robust than mean
	#	Std increases if the outliers are far away from real values.
	#	We need to limit the amount of discrepancy we want in the data (20%?).

	# We will use data masking and some operations with arrays. Convert to numpy.
	array = np.array(array)

	# Get the median and std.
	data_median = np.median(array)
	data_std	= np.std(array)

	# Max discrepancy we allow.
	fixed_max_dev  = 0.2*data_median
	clip_deviation = np.min([fixed_max_dev,data_std*sigma])

	# Create the filter (10% flux + variable factor)
	filter_values_ok = np.abs(array-data_median)<=clip_deviation
	filtered_values = array[filter_values_ok]

	# Return the mean of filtered data or the median.
	if np.size(filtered_values)==0:
		print('Warning: High dispersion found on last measures')
		filtered_mean = data_median
	else:
		filtered_mean = np.mean(filtered_values)

	return(filtered_mean)


class device(observatory):
	def standard_file_header(self):
		# Data Header, at the end of this script.
		header_content=RAWHeaderContent

		# Update data file header with observatory data
		header_content = header_content.replace(\
		 '$DEVICE_TYPE',str(_device_type))
		header_content = header_content.replace(\
		 '$DEVICE_ID',str(_device_id))
		header_content = header_content.replace(\
		 '$DATA_SUPPLIER',str(_data_supplier))
		header_content = header_content.replace(\
		 '$LOCATION_NAME',str(_device_locationname))
		header_content = header_content.replace(\
		 '$OBSLAT',str(_observatory_latitude))
		header_content = header_content.replace(\
		 '$OBSLON',str(_observatory_longitude))
		header_content = header_content.replace(\
		 '$OBSALT',str(_observatory_altitude))
		header_content = header_content.replace(\
		 '$OFFSET',str(_offset_calibration))

		if _local_timezone==0:
			header_content = header_content.replace(\
			 '$TIMEZONE','UTC')
		elif _local_timezone>0:
			header_content = header_content.replace(\
			 '$TIMEZONE','UTC+'+str(_local_timezone))
		elif _local_timezone<0:
			header_content = header_content.replace(\
			 '$TIMEZONE','UTC'+str(_local_timezone))

		header_content = header_content.replace(\
		 '$PROTOCOL_NUMBER',str(self.protocol_number))
		header_content = header_content.replace(\
		 '$MODEL_NUMBER', str(self.model_number))
		header_content = header_content.replace(\
		 '$FEATURE_NUMBER', str(self.feature_number))
		header_content = header_content.replace(\
		 '$SERIAL_NUMBER', str(self.serial_number))

		header_content = header_content.replace(\
		 '$IXREADOUT', remove_linebreaks(self.ix_readout))
		header_content = header_content.replace(\
		 '$RXREADOUT', remove_linebreaks(self.rx_readout))
		header_content = header_content.replace(\
		 '$CXREADOUT', remove_linebreaks(self.cx_readout))

		return(header_content)

	def format_content(self,timeutc_mean,timelocal_mean,temp_sensor,\
	 freq_sensor,ticks_uC,sky_brightness):
		# Format a string with data
		date_time_utc_str   = str(\
		 timeutc_mean.strftime("%Y-%m-%dT%H:%M:%S"))+'.000'
		date_time_local_str = str(\
		 timelocal_mean.strftime("%Y-%m-%dT%H:%M:%S"))+'.000'
		temp_sensor_str	 = str('%.2f' %temp_sensor)
		ticks_uC_str		= str('%.3f' %ticks_uC)
		freq_sensor_str	 = str('%.3f' %freq_sensor)
		sky_brightness_str  = str('%.3f' %sky_brightness)

		formatted_data = \
		  date_time_utc_str+";"+date_time_local_str+";"+temp_sensor_str+";"+\
		  ticks_uC_str+";"+freq_sensor_str+";"+sky_brightness_str+"\n"

		return(formatted_data)

	def define_filenames(self):
		# Filenames should follow a standard based on observatory name and date.
		date_time_file = self.local_datetime(\
		 self.read_datetime())-datetime.timedelta(hours=12)
		date_file = date_time_file.date()
		yearmonth = str(date_file)[0:7]
		yearmonthday = str(date_file)[0:10]

		self.monthly_datafile = \
		 monthly_data_directory+"/"+_device_shorttype+\
		 "_"+_observatory_name+"_"+yearmonth+".dat"
		#self.daily_datafile = \
		# daily_data_directory+"/"+_device_shorttype+\
		# "_"+_observatory_name+"_"+yearmonthday+".dat"
		self.daily_datafile = \
		 daily_data_directory+"/"+\
		 yearmonthday.replace('-','')+'_120000_'+\
		 _device_shorttype+'-'+_observatory_name+'.dat'
		self.current_datafile = \
		 current_data_directory+"/"+_device_shorttype+\
		 "_"+_observatory_name+".dat"

	def save_data(self,formatted_data):
		'''
		Save data to file and duplicate to current
		data file (the one that will be ploted)
		'''
		for each_file in [self.monthly_datafile,self.daily_datafile]:
			if not os.path.exists(each_file):
				datafile = open(each_file,'w')
				datafile.write(self.standard_file_header())
				datafile.close()

			datafile = open(each_file,'a+')
			datafile.write(formatted_data)
			datafile.close()

		self.copy_file(self.daily_datafile,self.current_datafile)

	def save_data_mysql(self,formatted_data):
		'''
		Use the Python MySQL API to save the
		data to a database
		'''
		mydb = None
		values = formatted_data.split(';')
		try:
			''' Start database connection '''
			mydb = _mysql.connect(\
			 host = _mysql_host,
			 user = _mysql_user,
			 passwd = _mysql_pass,
			 db = _mysql_database,
			 port = _mysql_port)

			''' Insert the data '''
			mydb.query(\
			 "INSERT INTO "+str(_mysql_dbtable)+" VALUES (NULL,'"+\
			 values[0]+"','"+values[1]+"',"+\
			 values[2]+","+values[3]+","+\
			 values[4]+","+values[5]+")")
		except Exception, ex:
			print(str(inspect.stack()[0][2:4][::-1])+\
			 ' DB Error. Exception: %s' % str(ex))

		if mydb != None:
			mydb.close()

	def data_cache(self,formatted_data,number_measures=1):
		'''
		Append data to DataCache str.
		If len(data)>number_measures, write to file
		and flush the cache
		'''
		try:
			self.DataCache
		except:
			self.DataCache=""

		self.DataCache = self.DataCache+formatted_data

		if len(self.DataCache.split("\n"))>=number_measures+1:
			self.save_data(self.DataCache)
			self.DataCache = ""
			print(str(niter)+'\t'+formatted_data[:-1])

	def flush_cache(self):
		''' Flush the data cache '''
		self.save_data(self.DataCache)
		self.DataCache = ""

	def copy_file(self,source,destination):
		# Copy file content from source to dest.
		fichero_source = open(source,'r')
		contenido_source = fichero_source.read()
		fichero_source.close()
		# Create file and truncate it
		fichero_destination = open(destination,'w')
		fichero_destination.close()
		# Write content
		fichero_destination = open(destination,'r+')
		fichero_destination.write(contenido_source)
		fichero_destination.close()

	def remove_currentfile(self):
		# Remove a file from the host
		if os.path.exists(self.current_datafile):
			os.remove(self.current_datafile)


class SQM():
	def read_photometer(self,Nmeasures=1,PauseMeasures=2):
		# Initialize values
		temp_sensor   = []
		flux_sensor   = []
		freq_sensor   = []
		ticks_uC	  = []
		Nremaining = Nmeasures

		# Promediate N measures to remove jitter
		timeutc_initial = self.read_datetime()
		while(Nremaining>0):
			InitialDateTime = datetime.datetime.now()

			# Get the raw data from the photometer and process it.
			raw_data = self.read_data()
			temp_sensor_i,freq_sensor_i,ticks_uC_i,sky_brightness_i = \
			 self.data_process(raw_data)

			temp_sensor += [temp_sensor_i]
			freq_sensor += [freq_sensor_i]
			ticks_uC	+= [ticks_uC_i]
			flux_sensor += [10**(-0.4*sky_brightness_i)]
			Nremaining  -= 1
			DeltaSeconds = (datetime.datetime.now()-InitialDateTime).total_seconds()

			# Just to show on screen that the program is alive and running
			sys.stdout.write('.')
			sys.stdout.flush()

			if (Nremaining>0): time.sleep(max(1,PauseMeasures-DeltaSeconds))

		timeutc_final = self.read_datetime()
		timeutc_delta = timeutc_final - timeutc_initial

		timeutc_mean   = timeutc_initial+\
		 datetime.timedelta(seconds=int(timeutc_delta.seconds/2.+0.5))
		timelocal_mean = self.local_datetime(timeutc_mean)

		# Calculate the mean of the data.
		temp_sensor = filtered_mean(temp_sensor)
		freq_sensor = filtered_mean(freq_sensor)
		flux_sensor = filtered_mean(flux_sensor)
		ticks_uC	= filtered_mean(ticks_uC)
		sky_brightness = -2.5*math.log10(flux_sensor)

		# Correct from offset (if cover is installed on the photometer)
		#sky_brightness = sky_brightness+_offset_calibration

		return(\
		 timeutc_mean,timelocal_mean,\
		 temp_sensor,freq_sensor,\
		 ticks_uC,sky_brightness)

	def metadata_process(self,msg,sep=','):
		# Separate the output array in items
		msg = format_value(msg)
		msg_array = msg.split(sep)

		# Get Photometer identification codes
		self.protocol_number = int(format_value(msg_array[1]))
		self.model_number	= int(format_value(msg_array[2]))
		self.feature_number  = int(format_value(msg_array[3]))
		self.serial_number   = int(format_value(msg_array[4]))

	def data_process(self,msg,sep=','):
		# Separate the output array in items
		msg = format_value(msg)
		msg_array = msg.split(sep)

		# Output definition characters
		mag_char  = 'm'
		freq_char = 'Hz'
		perc_char = 'c'
		pers_char = 's'
		temp_char = 'C'

		# Get the measures
		sky_brightness = float(format_value(msg_array[1],mag_char))
		freq_sensor	= float(format_value(msg_array[2],freq_char))
		ticks_uC	   = float(format_value(msg_array[3],perc_char))
		period_sensor  = float(format_value(msg_array[4],pers_char))
		temp_sensor	= float(format_value(msg_array[5],temp_char))

		# For low frequencies, use the period instead
		if freq_sensor<30 and period_sensor>0:
			freq_sensor = 1./period_sensor

		return(temp_sensor,freq_sensor,ticks_uC,sky_brightness)

	def start_connection(self):
		''' Start photometer connection '''
		pass

	def close_connection(self):
		''' End photometer connection '''
		pass

	def reset_device(self):
		''' Restart connection'''
		self.close_connection()
		time.sleep(0.1)
		#self.__init__()
		self.start_connection()


class SQMLE(observatory,device,SQM):
	def __init__(self):
		'''
		Search the photometer in the network and
		read its metadata
		'''

		try:
			print('Trying fixed device address ...')
			self.addr = _device_addr
			self.port = 10001
			self.start_connection()
		except:
			print('Trying auto device address ...')
			self.addr = self.search()
			self.port = 10001
			self.start_connection()

		# Clearing buffer
		print('Clearing buffer ... |'),
		buffer_data = self.read_buffer()
		print(buffer_data),
		print('| ... DONE')
		self.ix_readout = self.read_metadata()
		self.cx_readout = self.read_calibration()
		self.rx_readout = self.read_data()
		#print('Reading metadata ... '),
		#print('DONE')

	def search(self):
		''' Search SQM LE in the LAN. Return its adress '''
		self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.s.setblocking(False)

		if hasattr(socket,'SO_BROADCAST'):
			self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

		self.s.sendto("000000f6".decode("hex"), ("255.255.255.255", 30718))
		buf=''
		starttime = time.time()

		print "Looking for replies; press Ctrl-C to stop."
		addr=[None,None]
		while True:
			try:
				(buf, addr) = self.s.recvfrom(30)
				if buf[3].encode("hex")=="f7":
					print "Received from %s: MAC: %s" % \
					 (addr, buf[24:30].encode("hex"))
			except:
				#Timeout in seconds. Allow all devices time to respond
				if time.time()-starttime > 3:
					break
				pass

		try:
			assert(addr[0]!=None)
		except:
			print('ERR. Device not found!')
			raise
		else:
			return(addr[0])

	def start_connection(self):
		''' Start photometer connection '''
		self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.s.settimeout(10)
		self.s.connect((self.addr,int(self.port)))
		#self.s.settimeout(1)

	def close_connection(self):
		''' End photometer connection '''
		self.s.setsockopt(\
		 socket.SOL_SOCKET,\
		 socket.SO_LINGER,\
		 struct.pack('ii', 1, 0))

		# Check until there is no answer from device
		request = ""
		r = True
		while r:
			r = self.read_buffer()
			request += str(r)
		self.s.close()

	def read_buffer(self):
		''' Read the data '''
		msg = None
		try: msg = self.s.recv(256)
		except: pass
		return(msg)

	def reset_device(self):
		''' Connection reset '''
		#print('Trying to reset connection')
		self.close_connection()
		self.start_connection()

	def read_metadata(self):
		''' Read the serial number, firmware version '''
		self.s.send('ix')
		time.sleep(1)
		msg = self.read_buffer()

		# Check metadata
		tries=10
		try:
			assert(msg!=None)
			# Sanity check
			assert(len(msg)==_meta_len_ or _meta_len_==None)
			assert(tries>0)
			assert(\
			 len([msg[index] for index in xrange(len(msg)-1)\
			 if msg[index:index+2]=="i,"])==1)

			self.metadata_process(msg)
		except:
			tries-=1
			self.reset_device()
			msg = self.read_metadata()
		else:
			# Check that msg contains data
			try: assert(tries>0)
			except: print('ERR. Reading the photometer!')
			else: print('Sensor info: '+msg)

		return(msg)

	def read_calibration(self):
		''' Read the calibration parameters '''
		self.s.send('cx')
		time.sleep(1)
		msg = self.read_buffer()

		# Check metadata
		tries=10
		try:
			assert(msg!=None)
			# Sanity check
			assert(len(msg)==_cal_len_ or _cal_len_==None)
			assert(tries>0)
			assert(\
			 len([msg[index] for index in xrange(len(msg)-1)\
			 if msg[index:index+2]=="c,"])==1)

		except:
			tries-=1
			self.reset_device()
			msg = self.calibration()
		else:
			# Check that msg contains data
			try: assert(tries>0)
			except: print('ERR. Reading the photometer!')
			#else: print('Calibration info: '+msg)

		return(msg)


	def read_data(self):
		''' Read the SQM and format the Temperature, Frequency and NSB measures '''
		self.s.send('rx')
		time.sleep(1)
		msg = self.read_buffer()

		# Check data
		tries=10
		try:
			assert(msg!=None)
			# Sanity check
			assert(len(msg)==_data_len_ or _data_len_==None)
			assert(tries>0)
			assert(\
			 len([msg[index] for index in xrange(len(msg)-1)\
			 if msg[index:index+2]=="r,"])==1)

			self.data_process(msg)
		except:
			tries-=1
			self.reset_device()
			msg = self.read_data()
		else:
			# Check that msg contains data
			try: assert(tries>0)
			except: print('ERR. Reading the photometer!')
			#else: print(msg)

		return(msg)

class SQMLU(observatory,device,SQM):
	def __init__(self):
		'''
		Search the photometer and
		read its metadata
		'''

		try:
			print('Trying fixed device address ...')
			self.addr = _device_addr
			self.bauds = 115200
			self.start_connection()
		except:
			print('Trying auto device address ...')
			self.addr = self.search()
			self.bauds = 115200
			self.start_connection()

		# Clearing buffer
		print('Clearing buffer ... |'),
		buffer_data = self.read_buffer()
		print(buffer_data),
		print('| ... DONE')
		self.ix_readout = self.read_metadata()
		self.cx_readout = self.read_calibration()
		self.rx_readout = self.read_data()
		print('Reading metadata ... '),
		print('DONE')


	def search(self):
		'''
		Photometer search.
		Name of the port depends on the platform.
		'''
		ports_unix = ['/dev/ttyUSB'+str(num) for num in range(100)]
		ports_win  = ['COM'+str(num) for num in range(100)]

		os_in_use = sys.platform

		if os_in_use == 'linux2':
			print('Detected Linux platform')
			ports = ports_unix
		elif os_in_use == 'win32':
			print('Detected Windows platform')
			ports = ports_win

		used_port = None
		for port in ports:
			conn_test = serial.Serial(port, 115200, timeout=1)
			conn_test.write('ix')
			if conn_test.readline()[0] == 'i':
				used_port = port
				break

		try:
			assert(used_port!=None)
		except:
			print('ERR. Device not found!')
			raise
		else:
			return(used_port)

	def start_connection(self):
		'''Start photometer connection '''

		self.s = serial.Serial(self.addr, 115200, timeout=1)

	def close_connection(self):
		''' End photometer connection '''
		# Check until there is no answer from device
		request = ""
		r = True
		while r:
			r = self.read_buffer()
			request += str(r)

		self.s.close()

	def reset_device(self):
		''' Connection reset '''
		print('Trying to reset connection')
		self.close_connection()
		self.start_connection()

	def read_buffer(self):
		''' Read the data '''
		msg = None
		try: msg = self.s.readline()
		except: pass
		return(msg)

	def read_metadata(self):
		''' Read the serial number, firmware version '''
		self.s.write('ix')
		time.sleep(1)
		msg = self.read_buffer()

		# Check metadata
		tries=10
		try:
			assert(msg!=None)
			assert(tries>0)
			# Sanity check
			assert(len(msg)==_meta_len_ or _meta_len_==None)
			assert(\
			 len([msg[index] for index in xrange(len(msg)-1)\
			 if msg[index:index+2]=="i,"])==1)

			self.metadata_process(msg)
		except:
			tries-=1
			self.reset_device()
			msg = self.read_metadata()
		else:
			# Check that msg contains data
			try: assert(tries>0)
			except: print('ERR. Reading the photometer!')
			else: print('Sensor info: '+msg)

		return(msg)

	def read_calibration(self):
		''' Read the calibration data '''
		self.s.write('cx')
		time.sleep(1)
		msg = self.read_buffer()

		# Check metadata
		tries=10
		try:
			assert(msg!=None)
			# Sanity check
			assert(len(msg)==_cal_len_ or _cal_len_==None)
			assert(tries>0)
			assert(\
			 len([msg[index] for index in xrange(len(msg)-1)\
			 if msg[index:index+2]=="c,"])==1)

		except:
			tries-=1
			self.reset_device()
			msg = self.read_calibration()
		else:
			# Check that msg contains data
			try: assert(tries>0)
			except: print('ERR. Reading the photometer!')
			#else: print('Sensor info: '+msg)

		return(msg)

	def read_data(self):
		''' Read the SQM and format the Temperature, Frequency and NSB measures '''
		self.s.write('rx')
		time.sleep(1)
		msg = self.read_buffer()

		# Check data
		tries=10
		try:
			assert(msg!=None)
			# Sanity check
			assert(len(msg)==_data_len_ or _data_len_==None)
			assert(tries>0)
			assert(\
			 len([msg[index] for index in xrange(len(msg)-1)\
			 if msg[index:index+2]=="r,"])==1)

			self.data_process(msg)
		except:
			tries-=1
			self.reset_device()
			msg = self.read_data()
		else:
			# Check that msg contains data
			try: assert(tries>0)
			except: print('ERR. Reading the photometer!')
			#else: print(msg)

		return(msg)


if __name__ == '__main__':
	'''
	Select the device to be used based on user input
	and start the measures
	'''

	if _device_type=='SQM-LU':
		mydevice = SQMLU()
	elif _device_type=='SQM-LE':
		mydevice = SQMLE()
	else:
		print('ERROR. Unknown device type '+str(_device_type))
		exit(0)

	'''
	Ephem is used to calculate moon position (if above horizon)
	and to determine start-end times of the measures
	'''
	observ = define_ephem_observatory()
	niter = 0
	DaytimePrint=True

	print('Starting readings ...')
	while 1<2:
		''' The programs works as a daemon '''
		utcdt = mydevice.read_datetime()
		#print (str(mydevice.local_datetime(utcdt))),
		if mydevice.is_nighttime(observ):
			StartDateTime = datetime.datetime.now()
			niter += 1

			mydevice.define_filenames()

			''' Get values from the photometer '''
			try:
				timeutc_mean,timelocal_mean,temp_sensor,\
				freq_sensor,ticks_uC,sky_brightness = \
					mydevice.read_photometer(\
					 Nmeasures=_measures_to_promediate,PauseMeasures=10)
			except:
				#raise
				print('Connection lost')
				if _reboot_on_connlost == True:
					sleep(600)
					os.system('reinicio_programado.bat')

				#print('Reseting device')
				mydevice.reset_device()
				continue

			formatted_data = mydevice.format_content(\
				timeutc_mean,timelocal_mean,temp_sensor,\
				freq_sensor,ticks_uC,sky_brightness)

			if _use_mysql == True: mydevice.save_data_mysql(formatted_data)
			mydevice.data_cache(formatted_data,number_measures=_cache_measures)

			if niter%_plot_each == 0:
				''' Each X minutes, plot a new graph '''
				try: pysqm.plot.make_plot(send_emails=False,write_stats=False)
				except:
					print('Warning: Error plotting data.')
					print(sys.exc_info())


			if DaytimePrint==False:
				DaytimePrint=True

			MainDeltaSeconds = (datetime.datetime.now()-StartDateTime).total_seconds()
			time.sleep(max(1,_delay_between_measures-MainDeltaSeconds))

		else:
			''' Daytime, print info '''
			if DaytimePrint==True:
				utcdt = utcdt.strftime("%Y-%m-%d %H:%M:%S")
				print (utcdt),
				print('. Daytime. Waiting until '+str(mydevice.next_sunset(observ)))
				DaytimePrint=False
			if niter>0:
				mydevice.flush_cache()
				if _send_data_by_email==True:
					try: pysqm.plot.make_plot(send_emails=True,write_stats=True)
					except:
						print('Warning: Error plotting data / sending email.')
						print(sys.exc_info())

				else:
					try: pysqm.plot.make_plot(send_emails=False,write_stats=True)
					except:
						print('Warning: Error plotting data.')
						print(sys.exc_info())

				niter = 0
			time.sleep(300)

