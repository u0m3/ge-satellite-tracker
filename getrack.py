import ephem
import logging
import math
import os
import time
import urllib
import urllib2
import BaseHTTPServer
import ConfigParser
from SimpleHTTPServer import SimpleHTTPRequestHandler

_configfile = 'getrack.cfg'

log = logging.getLogger()
log.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
log.addHandler(stream_handler)

log.info('reading configuration file')
config = ConfigParser.ConfigParser()
config.read(_configfile)

log.info('reading kml templates')
_network_link_kml = open('network_link.txt').read()
_network_link_main_kml = open('network_links.txt').read()
_satellite_kml_template = open('satellite_kml.txt').read()
_satellite_placemark_template = open('satellite_line_placemark.txt').read()
_satellite_point_template = open('satellite_point_placemark.txt').read()

_methods = {}

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
			kml_placemarks += swap(_satellite_placemark_template, tokens)
			coords = '%lf,%lf,%lf\n' % (next_rec[1], next_rec[2], next_rec[3])
		elif not rec_eclipsed and next_rec_eclipsed:
			color = daylight_color 
			coords += '%lf,%lf,%lf\n%lf,%lf,%lf\n' % (rec[1], rec[2], rec[3], next_rec[1], next_rec[2], next_rec[3])
			tokens = { '[NAME]':sat_name, '[DESCRIPTION]':'', '[COORDS]':coords, '[COLOR]':color }
			kml_placemarks += swap(_satellite_placemark_template, tokens)
			coords = '%lf,%lf,%lf\n' % (next_rec[1], next_rec[2], next_rec[3])
		else:
			color = eclipsed_color 
			coords += '%lf,%lf,%lf\n' % (rec[1], rec[2], rec[3])

	if len(coords) > 0:
		tokens = { '[NAME]':sat_name, '[DESCRIPTION]':'', '[COORDS]':coords, '[COLOR]':color }
		kml_placemarks += swap(_satellite_placemark_template, tokens)

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
	sats_of_interest = [token.strip() for token in config.get('tracking','satellites').split(',')]

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
			_methods[method_name] = kep
			network_link_kmls += get_network_link_kml(config, sat_name, server_address, server_port, method_name)
			i += 1

	tokens = {
		'[NETWORK_LINKS]': network_link_kmls,
		'[REFRESH_INTERVAL]':config.get('tracking','refresh_interval_seconds')
	}

	main_network_links_kml = swap(_network_link_main_kml, tokens)
	open('satellites.kml', 'w').write(main_network_links_kml)

#	def log_message(s, format, *args):
#		return

class request_handler(BaseHTTPServer.BaseHTTPRequestHandler):

	def do_HEAD(s):
		s.send_response(200)
		s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
		s.end_headers()

	def do_GET(s):

		if not hasattr(s, 'config'):
			s.config = ConfigParser.ConfigParser()
			s.config.read(_configfile)

		method = s.path[1:]
		source = config.get('keps','source')

		if method.startswith('satellite'):
			s.send_response(200)
			s.send_header('Content-type', 'application/vnd.google-earth.kml+xml')
			s.end_headers()

			try:
				kep = _methods[method]

				if source == 'amsat': 
					sat_name = kep[0]
				elif source == 'spacetrack':
					sat_name = kep[0][2:]

				path = get_satellite_path(config, kep)
				kml = get_kml_for_path(config, sat_name, path)
				s.wfile.write(kml)
			except Exception, e:
				log.error('error generating kml')
				log.error(str(e))
				s.wfile.write('error!')

		elif method == 'icon':

			if not hasattr(s, 'icon'):
				s.config = ConfigParser.ConfigParser()
				s.config.read(_configfile)
				s.icon = open(config.get('tracking','satellite_icon'),'rb').read()

			print 'requesting icon'
			s.send_response(200)
			s.send_header('Content-type', 'image/png')
			s.end_headers()

			try:
				s.wfile.write(s.icon)
			except Exception, e:
				log.error('error sending icon')
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

	log.info('validating config file')

	config = ConfigParser.ConfigParser()
	config.read(filename)

	sections = config.sections()
	if not 'server' in sections:
		log.error('unable to find server section in configuration file')
		return None 

	if not 'tracks' in sections:
		log.error('unable to find tracks section in configuration file')
		return None 

	if not 'tracking' in sections:
		log.error('unable to find tracking section in configuration file')
		return None 

	if not 'keps' in sections:
		log.error('unable to find keps section in configuration file')
		return None 

	if not 'amsat' in sections and not 'spacetrack' in sections:
		log.error('unable to find amsat or spacetrack sections in configuration file')
		return None 

	#
	# todo(joe) : add validation for each of the individual section fields
	#

	return config 

if __name__ == '__main__':

	config_filename = _configfile 

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
