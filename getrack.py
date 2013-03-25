import ephem
import getopt
import logging
import math
import os
import pickle
import sys
import time
import urllib
import urllib2
import BaseHTTPServer
import ConfigParser
from SimpleHTTPServer import SimpleHTTPRequestHandler

_keps = {}
_default_configfile = 'getrack.cfg'

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG)
log = logging.getLogger('getrack')

# TEMPLATE KMLS

_network_link_kml = '''
<NetworkLink>
	<name>[SATELLITE_NAME]</name><visibility>1</visibility><open>0</open>
	<Link>
		<href>http://[SERVER_PORT]/[REQUEST_NAME]</href>
		<refreshMode>onInterval</refreshMode>
		<refreshInterval>[REFRESH_INTERVAL]</refreshInterval>
	</Link>
</NetworkLink>
'''

_network_link_main_kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
[NETWORK_LINKS]
</Document>
</kml>
'''

_satellite_kml_template = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
	<Document>
		<name>[SATELLITE_NAME]</name>
		<description>[DESCRIPTION]</description>
		<Style id="sat">
			<IconStyle>
			<Icon>
				<href>http://[SERVER]/icon</href>
			</Icon>
		</IconStyle>
		</Style>
		[PLACEMARKS]
	</Document>
</kml>
'''

_satellite_line_placemark_template = '''
<Placemark>
	<name>[NAME]</name>
	<description>[DESCRIPTION]</description>
	<LineString>
		<extrude>0</extrude>
		<tessellate>1</tessellate>
		<altitudeMode>relativeToGround</altitudeMode>
		<coordinates>
		[COORDS]
		</coordinates>
	</LineString>
	<Style>
		<LineStyle>
			<width>3</width>
			<color>[COLOR]</color>
			<colorMode>normal</colorMode>
			<gx:labelVisibility>1</gx:labelVisibility>
		</LineStyle>
	</Style>
</Placemark>
'''

_satellite_point_template = '''
<Placemark> 
	<name>[NAME]</name>
	<styleUrl>#sat</styleUrl>
	<Point>
	<extrude>1</extrude>
	<altitudeMode>relativeToGround</altitudeMode>
	<coordinates>
	[COORD]
	</coordinates>
	</Point>
</Placemark>
'''

_ground_station_network_link = '''
<NetworkLink>
	<name>stations</name><visibility>1</visibility><open>0</open>
	<Link>
		<href>http://[SERVER_PORT]/stations</href>
		<refreshMode>onInterval</refreshMode>
		<refreshInterval>[REFRESH_INTERVAL]</refreshInterval>
	</Link>
</NetworkLink>
'''

_ground_station_point_template = '''
<Placemark> 
	<name>[NAME]</name>
	<styleUrl>#station</styleUrl>
	<Point>
	<coordinates>
	[COORD]
	</coordinates>
	</Point>
</Placemark>
'''

_ground_station_point_template_main = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
	<Document>
		<name>[NAME]</name>
		<description>[DESCRIPTION]</description>
		<Style id="station">
			<IconStyle>
			<Icon>
				<href>http://[SERVER]/stationicon</href>
			</Icon>
		</IconStyle>
		</Style>
		[PLACEMARKS]
	</Document>
</kml>
'''

_los_network_link = '''
<NetworkLink>
	<name>stations</name><visibility>1</visibility><open>0</open>
	<Link>
		<href>http://[SERVER_PORT]/los</href>
		<refreshMode>onInterval</refreshMode>
		<refreshInterval>[REFRESH_INTERVAL]</refreshInterval>
	</Link>
</NetworkLink>
'''

_los_network_link_main_kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
	<Document>
		<name>los</name>
		<description>los</description>
		[PLACEMARKS]
	</Document>
</kml>
'''

_los_placemark_kml = '''
<Placemark>
	<name>[NAME]</name>
	<description>[DESCRIPTION]</description>
	<LineString>
		<extrude>0</extrude>
		<tessellate>1</tessellate>
		<altitudeMode>relativeToGround</altitudeMode>
		<coordinates>
		[COORDS]
		</coordinates>
	</LineString>
	<Style>
		<LineStyle>
			<width>3</width>
			<color>[COLOR]</color>
			<colorMode>normal</colorMode>
			<gx:labelVisibility>1</gx:labelVisibility>
		</LineStyle>
	</Style>
</Placemark>
'''


def swap(input, tokens):
	for key in tokens:
		input = input.replace(key, tokens[key])
	return input

def get_kml_for_path(config, sat_name, path):

	color = ''
	coords = ''
	kml_placemarks = ''

	daylight_color = config.get('tracking','daylight_color')
	eclipsed_color = config.get('tracking','eclipsed_color')
	refresh_interval = config.get('tracking','refresh_interval_seconds')

	for i in xrange(len(path)-1):

		rec = path[i]
		next_rec = path[i+1]

		rec_eclipsed = rec[4]
		next_rec_eclipsed = next_rec[4]

		if rec_eclipsed and next_rec_eclipsed:
			color = daylight_color
			coords += '%lf,%lf,%lf\n' % (rec[1], rec[2], rec[3])
		elif rec_eclipsed and not next_rec_eclipsed:
			color = eclipsed_color 
			coords += '%lf,%lf,%lf\n%lf,%lf,%lf\n' % (rec[1], rec[2], rec[3], next_rec[1], next_rec[2], next_rec[3])
			tokens = { '[NAME]':sat_name, '[DESCRIPTION]':'', '[COORDS]':coords, '[COLOR]':color }
			kml_placemarks += swap(_satellite_line_placemark_template, tokens)
			coords = '%lf,%lf,%lf\n' % (next_rec[1], next_rec[2], next_rec[3])
		elif not rec_eclipsed and next_rec_eclipsed:
			color = daylight_color 
			coords += '%lf,%lf,%lf\n%lf,%lf,%lf\n' % (rec[1], rec[2], rec[3], next_rec[1], next_rec[2], next_rec[3])
			tokens = { '[NAME]':sat_name, '[DESCRIPTION]':'', '[COORDS]':coords, '[COLOR]':color }
			kml_placemarks += swap(_satellite_line_placemark_template, tokens)
			coords = '%lf,%lf,%lf\n' % (next_rec[1], next_rec[2], next_rec[3])
		else:
			color = eclipsed_color 
			coords += '%lf,%lf,%lf\n' % (rec[1], rec[2], rec[3])

	if len(coords) > 0:
		tokens = { '[NAME]':sat_name, '[DESCRIPTION]':'', '[COORDS]':coords, '[COLOR]':color }
		kml_placemarks += swap(_satellite_line_placemark_template, tokens)

	coord = path[len(path)/2]

	tokens = {'[COORD]':'%lf,%lf,%lf' % (coord[1], coord[2], coord[3]), '[NAME]':sat_name, '[DESCRIPTION]':''}
	kml_placemarks += swap(_satellite_point_template, tokens)

	server = '%s:%d' % (config.get('server','address'), config.getint('server','port'))
	tokens = {'[PLACEMARKS]':kml_placemarks, '[REFRESH_INTERVAL]':str(refresh_interval), '[SATELLITE_NAME]':sat_name, '[DESCRIPTION]':'', '[SERVER]':server}

	return swap(_satellite_kml_template, tokens)

def get_satellite_path(config, keps):

	path = []

	kep_ephem = ephem.readtle(keps[0], keps[1], keps[2])

	idx_time = ephem.now() - (config.getint('tracks','look_ahead_minutes') * ephem.minute)
	end_time = ephem.now() + (config.getint('tracks','look_ahead_minutes') * ephem.minute)
	while(idx_time <= end_time): 

		kep_ephem.compute(idx_time)

		path.append([
			ephem.localtime(ephem.Date(idx_time)).strftime("%Y-%m-%d %H:%M:%S"),
			math.degrees(kep_ephem.sublong),
			math.degrees(kep_ephem.sublat),
			kep_ephem.elevation,
			kep_ephem.eclipsed])

		idx_time += (config.getint('tracks','tick_interval_seconds') * ephem.second)

	return path

def get_network_link_kml(config, satellite_name, server, port, request_name):

	tokens = {
		'[SATELLITE_NAME]':  satellite_name,
		'[SERVER_PORT]' : '%s:%d' % (server, port),
		'[REQUEST_NAME]' : request_name,
		'[REFRESH_INTERVAL]' : config.get('tracking', 'refresh_interval_seconds') }

	return swap(_network_link_kml, tokens)

def generate_satellites_kml(config, keps):

	log.info('generating satellites kml')

	source = config.get('keps','source')
	server_port = config.getint('server','port')
	server_address = config.get('server','address')

	sats_of_interest = []
	if config.has_section('tracking'):
		if config.has_option('tracking','satellites'):
			sats_of_interest.extend([token.strip() for token in config.get('tracking','satellites').split(',')])

	if len(sats_of_interest) == 0:
		sats_of_interest.extend([kep[0] for kep in keps])

	i = 1 
	network_link_kmls = ''

	for kep in keps:

		if source == 'amsat': 
			sat_name = kep[0]

		elif source == 'spacetrack':
			sat_name = kep[0][2:]

		if sat_name in sats_of_interest:

			log.info('processing: ' + sat_name)
			method_name = 'satellite%d' % ( i )
			_keps[method_name] = kep
			network_link_kmls += get_network_link_kml(config, sat_name, server_address, server_port, method_name)
			i += 1

	if config.has_section('ground'):
		network_link_kmls += _ground_station_network_link 

	if config.has_section('ground'):
		if config.getboolean('ground','los_to_sats'):
			network_link_kmls += _los_network_link

	tokens = {
		'[NETWORK_LINKS]': network_link_kmls,
		'[REFRESH_INTERVAL]':config.get('tracking','refresh_interval_seconds'),
        '[SERVER_PORT]': ('%s:%d' % (config.get('server','address'), config.getint('server','port')))
	}

	main_network_links_kml = swap(_network_link_main_kml, tokens)
	open('satellites.kml', 'w').write(main_network_links_kml)

def get_stations_kml(config, stations):

	station_placemarks = ''
	for station in stations:
		tokens = {
			'[NAME]':station[0],
			'[COORD]': '%lf,%lf' % (station[1], station[2])
		}

		station_placemarks += swap(_ground_station_point_template, tokens)

	tokens = {
		'[NAME]':'ground stations',
		'[DESCRIPTION]':'(none)',
		'[PLACEMARKS]':station_placemarks,
		'[SERVER]': ('%s:%d' % (config.get('server','address'), config.getint('server','port')))
	}

	return swap(_ground_station_point_template_main, tokens)

def get_los_kml(config, stations):

	los_placemarks = ''

	color = config.get('ground','los_line_color')

	for station in stations:

		for kep in _keps.values():

			observer = ephem.Observer()
			observer.lon = str(station[1])
			observer.lat = str(station[2])
			observer.date = ephem.now()

			kep_ephem = ephem.readtle(kep[0], kep[1], kep[2])
			kep_ephem.compute(observer)

			alt = ephem.degrees(kep_ephem.alt)

			if alt > 0:

				sat_long = math.degrees(kep_ephem.sublong)
				sat_lat = math.degrees(kep_ephem.sublat)
				sat_elevation = kep_ephem.elevation

				tokens = {
					'[NAME]':station[0],
					'[DESCRIPTION]':'%s to %s' % (station[0], kep[0]),
					'[COLOR]':color,
					'[COORDS]': '%lf,%lf,%lf\n%lf,%lf,%lf' % (sat_long, sat_lat, sat_elevation, station[1], station[2], 0)
				}

				los_placemarks += swap(_los_placemark_kml, tokens)

	tokens = {
		'[PLACEMARKS]':los_placemarks,
	}

	return swap(_los_network_link_main_kml, tokens)

class request_handler(BaseHTTPServer.BaseHTTPRequestHandler):

	def log_message(s, format, *args):
		return


	def do_HEAD(s):
		s.send_response(200)
		s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
		s.end_headers()

	def do_GET(s):

		if not hasattr(s, 'config'):
			s.config = ConfigParser.ConfigParser()
			s.config.read(_default_configfile)

		method = s.path[1:]
		source = s.config.get('keps','source')

		if method.startswith('satellite'):
			s.send_response(200)
			s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
			s.end_headers()

			try:
				kep = _keps[method]

				if source == 'amsat': 
					sat_name = kep[0]
				elif source == 'spacetrack':
					sat_name = kep[0][2:]

				path = get_satellite_path(s.config, kep)
				kml = get_kml_for_path(s.config, sat_name, path)
				s.wfile.write(kml)
			except Exception, e:
				log.error('error generating kml')
				log.error(str(e))
				s.wfile.write('error!')

		elif method == 'icon':

			if not hasattr(s, 'icon'):
				s.icon = open(s.config.get('tracking','satellite_icon'),'rb').read()

			s.send_response(200)
			s.send_header('Content-type', 'image/png')
			s.end_headers()

			try:
				s.wfile.write(s.icon)
			except Exception, e:
				log.error('error sending icon')
				log.error(str(e))
				s.wfile.write('error!')

		elif method == 'stationicon':

			log.info('station icon method')

			if not hasattr(s, 'station_icon'):
				log.info('reading station icon')
				s.station_icon = open(s.config.get('ground','station_icon'),'rb').read()

			log.info('delivering station icon')
			s.send_response(200)
			s.send_header('Content-type', 'image/png')
			s.end_headers()

			try:
				s.wfile.write(s.station_icon)
			except Exception, e:
				log.error('error sending station icon')
				log.error(str(e))
				s.wfile.write('error!')

		elif method == 'stations':

			if not hasattr(s, 'station'):
				s.station = open(s.config.get('ground','station_icon'),'rb').read()
				stations = eval(s.config.get('ground','stations'))
				s.stations = get_stations_kml(s.config, stations)

			s.send_response(200)
			s.send_header('Content-type', 'image/png')
			s.end_headers()

			try:
				s.wfile.write(s.stations)
			except Exception, e:
				log.error('error sending station')
				log.error(str(e))
				s.wfile.write('error!')

		elif method == 'los':

			if not hasattr(s, 'station'):
				s.station = open(s.config.get('ground','station_icon'),'rb').read()
				stations = eval(s.config.get('ground','stations'))
				s.stations = get_stations_kml(s.config, stations)

			s.send_response(200)
			s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
			s.end_headers()

			try:
				kml = get_los_kml(config, stations)
				s.wfile.write(kml)
			except Exception, e:
				log.error('error sending los')
				log.error(str(e))
				s.wfile.write('error!')


		return

def display_satellite_names(keps):

	for kep in keps:
		print kep[0][2:]

def download_keps(config):

	source = config.get('keps','source')

	log.info('downloading keps from %s' % (source))

	try:
		if source == 'amsat':

			keps = urllib2.urlopen(config.get('amsat','url')).readlines()

		elif source == 'spacetrack':

			credentials = {
				'identity':config.get('spacetrack','identity'),
				'password':config.get('spacetrack','password')
			}

			credentials = urllib.urlencode(credentials)

			request = urllib2.Request(config.get('spacetrack','auth_url'), credentials)
			response = urllib2.urlopen(request)
			cookie = response.headers.get('Set-Cookie')

			request = urllib2.Request(config.get('spacetrack','keps_url'))
			request.add_header('cookie', cookie)
			
			keps = urllib2.urlopen(request).readlines()

		keps = [line.strip() for line in keps]
		return [ [keps[i], keps[i+1], keps[i+2]] for i in xrange(0, len(keps), 3)]

	except Exception, e:
		log.error('unable to download keps')
		log.error(str(e))

	return None

def validate_config_file(filename):

	log.info('validating config file %s', filename)

	if not os.path.exists(filename):
		log.error('unable to find configuration file')
		return None

	config = ConfigParser.ConfigParser()
	config.read(filename)

	if not config.has_section('server'):
		log.error('unable to find server section in configuration file')
		return None 

	if not config.has_section('tracks'):
		log.error('unable to find tracks section in configuration file')
		return None 

	if not config.has_section('tracking'):
		log.error('unable to find tracking section in configuration file')
		return None 

	if not config.has_section('keps'):
		log.error('unable to find keps section in configuration file')
		return None 

	if not config.has_section('amsat') and not config.has_section('spacetrack'):
		log.error('unable to find amsat or spacetrack sections in configuration file')
		return None 

	#
	# todo(joe) : add validation for each of the individual section fields
	#

	return config 

def usage():
	print '''python getrack.cfg -c config_filename'''

if __name__ == '__main__':

	config_filename = _default_configfile 

	try:
		opts, args = getopt.getopt(sys.argv[1:], "hc:v", ["help", "config="])
	except getopt.GetoptError as err:
		print str(err)
		usage()
		sys.exit(2)
	for o, a in opts:
		if o in ("-h", "--help"):
			usage()
			sys.exit()
		elif o in ("-c", "--config"):
			config_filename = a
		else:
			assert False, "unhandled option"

	config = validate_config_file(config_filename)
	if config is None:
		quit()

	keps = download_keps(config)

	log.info('obtained %d keps' % (len(keps)))

	#display_satellite_names(keps)

	generate_satellites_kml(config, keps)
	
	log.info('starting server')
	log.info('(drag satellites.kml into google earth and enjoy)')
	httpd = BaseHTTPServer.HTTPServer((config.get('server','address'), config.getint('server','port')), request_handler)
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		log.error('the server was interrupted!')
	httpd.server_close()

	log.error('complete')
