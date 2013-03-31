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

_config = None
_config_defaults = {
	'server':{
		'port':'8080',
		'address':'localhost'
	},
	'tracking':{
		'look_ahead_minutes':'90',
		'tick_interval_seconds':'10',
		'eclipsed_color':'5014F050',
		'daylight_color':'5014F0F0',
		'satellite_icon':'satellite_48_dis.png',
		'refresh_interval_seconds':'2',
		'satellites':'ISS',
		'show_footprints':'True',
		'footprint_color':'440000AA'
	},
	'keps':{
		'source':'amsat',
		'cache':'True',
		'use_cache':'True'
	},
	'amsat':{
		'url':'http://www.amsat.org/amsat/ftp/keps/current/nasabare.txt'
	},
	'spacetrack':{
		'auth_url':'https://www.space-track.org/ajaxauth/login',
		'keps_url':'https://www.space-track.org/basicspacedata/query/class/tle_latest/favorites/amateur/ORDINAL/1/EPOCH/%3Enow-30/format/3le',
		'identity':'MISSING',
		'password':'MISSING'
	},
	'ground':{
		'los_to_sats':'True',
		'los_line_color':'440000AA',
		'station_icon':'satellite_ground_32.png',
		'stations':'[]'
	}
}

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

_satellite_footprint_network_link = '''
<NetworkLink>
	<name>stations</name><visibility>1</visibility><open>0</open>
	<Link>
		<href>http://[SERVER_PORT]/footprints</href>
		<refreshMode>onInterval</refreshMode>
		<refreshInterval>[REFRESH_INTERVAL]</refreshInterval>
	</Link>
</NetworkLink>
'''

_satellite_footprint_polygon_template = '''
<Placemark>
	<name>[NAME]</name>
	<description>[DESCRIPTION]</description>
	<Polygon>
		<extrude>0</extrude>
		<tessellate>1</tessellate>
		<outerBoundaryIs>
			<LinearRing>
				<coordinates>
				[COORDS]
				</coordinates>
			</LinearRing>
		</outerBoundaryIs>
	</Polygon>
	<Style>
		<LineStyle>
			<width>3</width>
			<color>[COLOR]</color>
			<colorMode>normal</colorMode>
			<gx:labelVisibility>1</gx:labelVisibility>
		</LineStyle>
		<PolyStyle>
			<color>[COLOR]</color>
		</PolyStyle>
	</Style>
</Placemark>

'''

_satellite_footprint_template_main = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
	<Document>
		<name>[NAME]</name>
		<description>[DESCRIPTION]</description>
		[PLACEMARKS]
	</Document>
</kml>
'''

def swap(input, tokens):
	for key in tokens:
		input = input.replace(key, tokens[key])
	return input

def get_kml_for_path(sat_name, path):

	color = ''
	coords = ''
	kml_placemarks = ''

	daylight_color = _config.get('tracking','daylight_color')
	eclipsed_color = _config.get('tracking','eclipsed_color')
	refresh_interval = _config.get('tracking','refresh_interval_seconds')

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

	server = '%s:%d' % (_config.get('server','address'), _config.getint('server','port'))
	tokens = {'[PLACEMARKS]':kml_placemarks, '[REFRESH_INTERVAL]':str(refresh_interval), '[SATELLITE_NAME]':sat_name, '[DESCRIPTION]':'', '[SERVER]':server}

	return swap(_satellite_kml_template, tokens)

def get_satellite_path(keps):

	path = []

	kep_ephem = ephem.readtle(keps[0], keps[1], keps[2])

	idx_time = ephem.now() - (_config.getint('tracking','look_ahead_minutes') * ephem.minute)
	end_time = ephem.now() + (_config.getint('tracking','look_ahead_minutes') * ephem.minute)
	while(idx_time <= end_time): 

		kep_ephem.compute(idx_time)

		path.append([
			ephem.localtime(ephem.Date(idx_time)).strftime("%Y-%m-%d %H:%M:%S"),
			math.degrees(kep_ephem.sublong),
			math.degrees(kep_ephem.sublat),
			kep_ephem.elevation,
			kep_ephem.eclipsed])

		idx_time += (_config.getint('tracking','tick_interval_seconds') * ephem.second)

	return path

def get_network_link_kml(satellite_name, server, port, request_name):

	tokens = {
		'[SATELLITE_NAME]':  satellite_name,
		'[SERVER_PORT]' : '%s:%d' % (server, port),
		'[REQUEST_NAME]' : request_name,
		'[REFRESH_INTERVAL]' : _config.get('tracking', 'refresh_interval_seconds') }

	return swap(_network_link_kml, tokens)

def generate_satellites_kml(keps):

	log.info('generating satellites kml')

	source = _config.get('keps','source')
	server_port = _config.getint('server','port')
	server_address = _config.get('server','address')

	sats_of_interest = []
	if _config.has_section('tracking'):
		if _config.has_option('tracking','satellites'):
			sats_of_interest.extend([token.strip() for token in _config.get('tracking','satellites').split(',')])

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
			network_link_kmls += get_network_link_kml(sat_name, server_address, server_port, method_name)
			i += 1

	if _config.has_section('ground'):
		network_link_kmls += _ground_station_network_link 

	if _config.getboolean('tracking','show_footprints'):
		network_link_kmls += _satellite_footprint_network_link
		
	if _config.has_section('ground'):
		if _config.getboolean('ground','los_to_sats'):
			network_link_kmls += _los_network_link

	tokens = {
		'[NETWORK_LINKS]': network_link_kmls,
		'[REFRESH_INTERVAL]':_config.get('tracking','refresh_interval_seconds'),
        '[SERVER_PORT]': ('%s:%d' % (_config.get('server','address'), _config.getint('server','port')))
	}

	main_network_links_kml = swap(_network_link_main_kml, tokens)
	open('satellites.kml', 'w').write(main_network_links_kml)

def get_stations_kml(stations):

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
		'[SERVER]': ('%s:%d' % (_config.get('server','address'), _config.getint('server','port')))
	}

	return swap(_ground_station_point_template_main, tokens)

def get_los_kml(stations):

	los_placemarks = ''

	color = _config.get('ground','los_line_color')

	for station in stations:

		for kep in _keps.values():

			observer = ephem.Observer()

			observer.lon = math.radians(station[1])
			observer.lat = math.radians(station[2])
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

def get_footprint_points(lat, lon, elevation):

	radius = 6378137.0
	angle = math.acos(radius / (radius + elevation))

	points = []
	for angle_around_position in xrange(0, 360, 2):
		rad_angle = math.radians(angle_around_position)
		point = (math.degrees(lon + angle*math.cos(rad_angle)), math.degrees(lat + angle*math.sin(rad_angle)))
		points.append(point)

	return points

def get_footprints_kml():

	footprint_placemarks = ''

	color = _config.get('tracking','footprint_color')

	for kep in _keps.values():

		kep_ephem = ephem.readtle(kep[0], kep[1], kep[2])
		kep_ephem.compute(ephem.now())

		lon = kep_ephem.sublong
		lat = kep_ephem.sublat
		elevation = kep_ephem.elevation

		coords = ''
		for point in get_footprint_points(lat, lon, elevation):
			coords += '%lf,%lf\n' % (point[0], point[1])

		tokens = {
			'[NAME]':kep[0],
			'[DESCRIPTION]':'%s' % (kep[0]),
			'[COLOR]':color,
			'[COORDS]': coords
		}

		footprint_placemarks += swap(_satellite_footprint_polygon_template, tokens)

	tokens = {
		'[PLACEMARKS]':footprint_placemarks,
	}

	return swap(_satellite_footprint_template_main, tokens)


class request_handler(BaseHTTPServer.BaseHTTPRequestHandler):

	def log_message(s, format, *args):
		return


	def do_HEAD(s):
		s.send_response(200)
		s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
		s.end_headers()

	def do_GET(s):

		method = s.path[1:]
		source = _config.get('keps','source')

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

				path = get_satellite_path(kep)
				kml = get_kml_for_path(sat_name, path)
				s.wfile.write(kml)
			except Exception, e:
				log.error('error generating kml')
				log.error(str(e))
				s.wfile.write('error!')

		elif method == 'icon':

			if not hasattr(s, 'icon'):
				s.icon = open(_config.get('tracking','satellite_icon'),'rb').read()

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
				s.station_icon = open(_config.get('ground','station_icon'),'rb').read()

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
				s.station = open(_config.get('ground','station_icon'),'rb').read()
				stations = eval(_config.get('ground','stations'))
				s.stations = get_stations_kml(stations)

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
				s.station = open(_config.get('ground','station_icon'),'rb').read()
				stations = eval(_config.get('ground','stations'))
				s.stations = get_stations_kml(stations)

			s.send_response(200)
			s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
			s.end_headers()

			try:
				kml = get_los_kml(stations)
				s.wfile.write(kml)
			except Exception, e:
				log.error('error sending los')
				log.error(str(e))
				s.wfile.write('error!')

		elif method == 'footprints':

			s.send_response(200)
			s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
			s.end_headers()

			try:
				kml = get_footprints_kml()
				s.wfile.write(kml)
			except Exception, e:
				log.error('error sending footprints')
				log.error(str(e))
				s.wfile.write('error!')

		return

def display_satellite_names(keps):

	source = _config.get('keps','source')

	log.info('displaying satellite names from source: ', source)

	if source == 'amsat':
		for kep in keps:
			print kep[0]
	else:
		for kep in keps:
			print kep[0][2:]

def get_cache_filename(source):

	return source + '.tle'

def load_cached_keps():

	source = _config.get('keps','source')
	cache_filename = get_cache_filename(source)

	log.info('loading keps from cache %s' % (cache_filename))

	if os.path.exists(cache_filename):
		keps = open(cache_filename,'r').readlines()
		keps = [line.strip() for line in keps]
		return [ [keps[i], keps[i+1], keps[i+2]] for i in xrange(0, len(keps), 3)]

	log.error('unable to find cache with filename: %s', cache_filename)
	return None
	
def download_keps():

	source = _config.get('keps','source')
	cache = _config.getboolean('keps','cache')

	log.info('downloading keps from %s' % (source))

	try:
		if source == 'amsat':

			keps = urllib2.urlopen(_config.get('amsat','url')).readlines()

		elif source == 'spacetrack':

			credentials = {
				'identity':_config.get('spacetrack','identity'),
				'password':_config.get('spacetrack','password')
			}

			credentials = urllib.urlencode(credentials)

			request = urllib2.Request(_config.get('spacetrack','auth_url'), credentials)
			response = urllib2.urlopen(request)
			cookie = response.headers.get('Set-Cookie')

			request = urllib2.Request(_config.get('spacetrack','keps_url'))
			request.add_header('cookie', cookie)
			
			keps = urllib2.urlopen(request).readlines()

		if cache:
			cache_filename = get_cache_filename(source)
			log.info('caching downloaded keps to: %s', cache_filename)
			open(cache_filename, 'w').writelines(keps)

		keps = [line.strip() for line in keps]
		return [ [keps[i], keps[i+1], keps[i+2]] for i in xrange(0, len(keps), 3)]

	except Exception, e:
		log.error('unable to download keps')
		log.error(str(e))

	return None

def set_defaults(config, section, defaults):
	for key in defaults:
		config.set(section, key, defaults[key])
		log.info('using %s : %s' % (key, defaults[key]))

def read_config(filename):

	log.info('validating config file %s', filename)

	config = ConfigParser.ConfigParser()
	try:
		config.read(filename)
	except:
		log.warn('unable to find configuration file: ', filename)

	if not config.has_section('server'):
		log.warn('server section not found in configuration file, using defaults')
		config.add_section('server')
		set_defaults(config, 'server', _config_defaults['server'])

	if not config.has_section('tracking'):
		log.warn('tracking section was not found in configuration file, using defaults')
		config.add_section('tracking')
		set_defaults(config, 'tracking', _config_defaults['tracking'])

	if not config.has_section('keps'):
		log.warn('keps section was not found in configuration file, using deaults')
		config.add_section('keps')
		set_defaults(config, 'keps', _config_defaults['keps'])

	if not config.has_section('amsat'):
		log.warn('amsat section was not found in configuration file, using defaults')
		config.add_section('amsat')
		set_defaults(config, 'amsat', _config_defaults['amsat'])

	if not config.has_section('spacetrack'):
		log.warn('spacetrack section was not found in configuration file, using defaults')
		config.add_section('spacetrack')
		set_defaults(config, 'spacetrack', _config_defaults['spacetrack'])

	#
	# todo(joe) : add validation for each of the individual section fields
	#

	return config 

def usage():
	print ''' python getrack.cfg [ -c config_filename ] [-d] [-h]
Options and Arguments
-c arg : configuration file name
-d     : display satellite names obtain from the configured keps source 
-h     : display help '''


if __name__ == '__main__':

	dump_satellites = False
	config_filename = _default_configfile 

	try:
		opts, args = getopt.getopt(sys.argv[1:], "hc:dv", ["help", "config="])
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
		elif o in ('-d'):
			dump_satellites = True
		else:
			assert False, "unhandled option"

	_config = read_config(config_filename)
	if _config is None:
		quit()

	keps = None
	use_cache = _config.getboolean('keps','use_cache')
	if use_cache:
		keps = load_cached_keps()

		if keps is None:
			log.info('unable to find keps in cache')
		else:
			log.info('using %d cached keps' % (len(keps)))

	if keps is None:
		keps = download_keps()
		if keps is None:
			log.error('failed to download keps')
		else:
			log.info('downloaded %d keps' % (len(keps)))

	if keps is None:
		log.error('unable to obtain keps!')
		quit()

	if dump_satellites:
		display_satellite_names(keps)
		quit()

	generate_satellites_kml(keps)
	
	log.info('starting server')
	log.info('(drag satellites.kml into google earth and enjoy)')
	httpd = BaseHTTPServer.HTTPServer((_config.get('server','address'), _config.getint('server','port')), request_handler)
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		log.error('the server was interrupted!')
	httpd.server_close()

	log.error('complete')
