#!/usr/bin/python


#####             FreeZTP Server             #####
#####        Written by John W Kerns         #####
#####       http://blog.packetsar.com        #####
##### https://github.com/convergeone/freeztp #####

##### Inform FreeZTP version here #####
version = "v0.8.2"

# NEXT: Set up garbage collection of complete master sessions
# NEXT: Write in supression
# NEXT: Clean up output logging
# NEXT: Recognize client tracking (dhcp, upgrade, initial file, custom file)

##### Try to import non-native modules, fail gracefully #####
try:
	#import jinja2 as j2
	#from jinja2 import Environment, meta
	#import pysnmp.hlapi
	#import tftpy
	#import netaddr
	#import netifaces
	pass
except ImportError:
	print("Had some import errors, may not have dependencies installed yet")


##### Import native modules #####
import os
import sys
import json
import platform
import commands

import re
import time
import curses
import socket
import logging
import threading


class os_detect:
	def __init__(self):
		self._dist = self._dist_detect()
		self._systemd = self._systemd_detect()
		self._pkgmgr = self._pkgmgr_detect()
		self._make_names()
	def _systemd_detect(self):
		checksystemd = commands.getstatusoutput("systemctl")
		if len(checksystemd[1]) > 50 and "Operation not permitted" not in checksystemd[1]:
			return True
		else:
			return False
	def _pkgmgr_detect(self):
		checkpkgmgr = {}
		checknames = ["yum", "apt", "apt-get"]
		for mgr in checknames:
			checkpkgmgr.update({len(commands.getstatusoutput(mgr)[1]): mgr})
		pkgmgr = checkpkgmgr[sorted(list(checkpkgmgr), key=int)[len(sorted(list(checkpkgmgr), key=int)) - 1]]
		return pkgmgr
	def _dist_detect(self):
		distlist = platform.linux_distribution()
		if "centos" in distlist[0].lower():
			return "centos"
		if "ubuntu" in distlist[0].lower():
			return "ubuntu"
		if "debian" in distlist[0].lower():
			return "debian"
		else:
			return "unknown"
	def _make_names(self):
		if self._dist == "centos":
			self.DHCPSVC = "dhcpd"
			self.DHCPPKG = "dhcp"
			self.PIPPKG = "python2-pip"
			self.PKGDIR = "/usr/lib/python2.7/site-packages/"
		elif self._dist == "ubuntu":
			self.DHCPSVC = "isc-dhcp-server"
			self.DHCPPKG = "isc-dhcp-server"
			self.PIPPKG = "python-pip"
			self.PKGDIR = "/usr/local/lib/python2.7/dist-packages/"
		elif self._dist == "debian":
			self.DHCPSVC = "isc-dhcp-server"
			self.DHCPPKG = "isc-dhcp-server"
			self.PIPPKG = "python-pip"
			self.PKGDIR = "/usr/local/lib/python2.7/dist-packages/"
	def service_control(self, cmd, service):
		if self._systemd:
			os.system("sudo systemctl %s %s" % (cmd, service))
		else:
			os.system("sudo service %s %s" % (service, cmd))
	def install_pkg(self, pkg):
		cmd = "sudo %s install -y %s" % (self._pkgmgr, pkg)
		console("")
		os.system("sudo %s install -y %s" % (self._pkgmgr, pkg))


def interceptor(afile, raddress, rport):
	log("interceptor: Called. Running cfact.lookup procedure")
	lookup = cfact.lookup(afile, raddress)
	log("interceptor: cfact.lookup returned (%s)" % lookup)
	if lookup:
		log("interceptor: Returning ztp_dyn_file instantiated object")
		return ztp_dyn_file(afile, raddress, rport)
	else:
		log("interceptor: Returning None")
		return None


##### Dynamic file object: instantiated by the tftpy server to generate   #####
#####   TFTP files                                                        #####
class ztp_dyn_file:
	closed = False
	position = 0
	def __init__(self, afile, raddress, rport):
		log("ztp_dyn_file: Instantiated as (%s)" % str(self))
		self.data = cfact.request(afile, raddress)
		log("ztp_dyn_file: File size is %s bytes" % len(self.data))
		pass
	def tell(self):
		log("ztp_dyn_file.tell: Called")
		return len(self.data)
	def read(self, size):
		start = self.position
		end = self.position + size
		log("ztp_dyn_file.read: Called with size (%s)" % str(size))
		result = str(self.data[start:end])
		log("ztp_dyn_file.read: Returning position %s to %s:\n%s" % (str(start), str(end), result))
		self.position = end
		return result
	def seek(self, arg1, arg2):
		log("ztp_dyn_file.seek: Called with args (%s) and (%s)" % (str(arg1), str(arg1)))
		pass
	def close(self):
		log("ztp_dyn_file.close: Called")
		self.closed = True


##### Configuration factory: The main program which creates TFTP files    #####
#####   based on the ZTP configuration                                    #####
class config_factory:
	def __init__(self):
		global j2
		global Environment
		global meta
		#global tftpy
		import jinja2 as j2
		from jinja2 import Environment, meta
		#import tftpy
		self.state = {}
		self.snmprequests = {}
		try:
			self.basefilename = config.running["initialfilename"]
			self.imagediscoveryfile = config.running["imagediscoveryfile"]
			self.basesnmpcom = config.running["community"]
			self.snmpoid = config.running["snmpoid"]
			self.baseconfig = config.running["starttemplate"]
			self.uniquesuffix = config.running["suffix"]
			self.templates = config.running["templates"]
			self.keyvalstore = config.running["keyvalstore"]
			self.associations = config.running["associations"]
		except:
			console("cfact.__init__: Error pulling settings from config file")
	def lookup(self, filename, ipaddr):
		log("cfact.lookup: Called. Checking filename (%s) and IP (%s)" % (filename, ipaddr))
		tempid = filename.replace(self.uniquesuffix, "")
		log("cfact.lookup: TempID is (%s)" % tempid)
		log("cfact.lookup: Current SNMP Requests: %s" % list(self.snmprequests))
		if filename == self.basefilename:
			log("cfact.lookup: TempID matches the initialfilename. Returning True")
			return True
		if filename == self.imagediscoveryfile:
			log("cfact.lookup: TempID matches the imagediscoveryfile. Returning True")
			log("cfact.lookup: #############IOS UPGRADE ABOUT TO BEGIN!!!#############")
			return True
		elif self.uniquesuffix in filename and tempid in list(self.snmprequests):  # If the filname contains the suffix and it has an entry in the snmp request list
			log("cfact.lookup: Seeing the suffix in the filename and the TempID in the SNMPRequests")
			if self.snmprequests[tempid].complete:  # If the snmprequest has completed
				log("cfact.lookup: The SNMP is showing as completed")
				if self.id_configured(self.snmprequests[tempid].response):  # If the snmp id response is a configured IDArray or keystore
					log("cfact.lookup: The target ID is in the Keystore or in an IDArray")
					return True
				elif self._default_lookup():  # If there is a default keystore configured
					log("cfact.lookup: The target ID is NOT in the Keystore or in an IDArray, but a default is configured")
					return True
			elif self._default_lookup():  # If there is a default keystore configured
				log("cfact.lookup: The target ID is NOT in the Keystore or in an IDArray, but a default is configured")
				return True
		if "ztp-" in tempid.lower():
			log("cfact.lookup: Creating new SNMP request for %s: %s" % (str(tempid), str(ipaddr)))
			self.create_snmp_request(tempid, ipaddr)
		return False
	def _default_lookup(self):
		log("cfact._default_lookup: Checking if a default-keystore is configured and ready...")
		if config.running["default-keystore"]:  # If a default keystore ID is set
			kid = config.running["default-keystore"]
			log("cfact._default_lookup: A default keystore ID (%s) is configured" % kid)
			if kid in list(config.running["keyvalstore"]):  # If that default keystore ID has an actual configured keystore
				log("cfact._default_lookup: The keystore ID (%s) exists in the keystore" % kid)
				if kid in list(config.running["associations"]):  # If that keystore has an associated template name
					mtemp = config.running["associations"][kid]
					log("cfact._default_lookup: An association exists which maps keystore (%s) to template (%s)" % (kid, mtemp))
					if mtemp in list(config.running["templates"]):  # If that associated template is configured
						log("cfact._default_lookup: Template (%s) is a configured template" % mtemp)
						return kid
					else:
						log("cfact._default_lookup: The associated template (%s) does not exist. Returning none" % mtemp)
						return False
				else:
					log("cfact._default_lookup: The Keystore ID (%s) has no template association. Returning none" % kid)
					return False
			else:
				log("cfact._default_lookup: The default-keystore ID (%s) is not a configured keystore. Returning none" % kid)
				return False
		else:
			log("cfact._default_lookup: Default-keystore set to none. Returning none")
			return False
	def id_configured(self, serial):
		if serial in list(config.running["keyvalstore"]):
			return True
		else:
			arraykeys = []
			for array in config.running["idarrays"]:
				for iden in config.running["idarrays"][array]:
					arraykeys.append(iden)
			if serial in arraykeys:
				return True
			else:
				return False
	def request(self, filename, ipaddr):
		log("cfact.request: Called with filename (%s) and IP (%s)" % (filename, ipaddr))
		if filename == self.basefilename:
			log("cfact.request: Filename (%s) matches the configured initialfilename" % self.basefilename)
			tempid = self._generate_name()
			log("cfact.request: Generated a TempID with cfact._generate_name: (%s)" % tempid)
			self.create_snmp_request(tempid, ipaddr)
			log("cfact.request: Generated a SNMP Request with TempID (%s) and IP (%s)" % (tempid, ipaddr))
			result = self.merge_base_config(tempid)
			log("cfact.request: Returning below config to TFTPy:\n%s" % result)
			return result
		elif filename == self.imagediscoveryfile:
			log("cfact.request: Filename (%s) matches the configured imagediscoveryfile" % filename)
			result = config.running["imagefile"]
			log("cfact.request: Returning the value of the imagefile setting (%s)" % result)
			return result
		else:
			log("cfact.request: Filename (%s) does NOT the configured initialfilename" % self.basefilename)
			tempid = filename.replace(self.uniquesuffix, "")
			log("cfact.request: Stripped filename to TempID (%s)" % tempid)
			if self.uniquesuffix in filename and tempid in list(self.snmprequests):
				log("cfact.request: Seeing the suffix in the filename and the TempID in the SNMP Requests")
				if self.snmprequests[tempid].complete:
					log("cfact.request: SNMP Request says it has completed")
					identifier = self.snmprequests[tempid].response
					log("cfact.request: SNMP request returned target ID (%s)" % identifier)
					keystoreid = self.get_keystore_id(identifier)
					log("cfact.request: Keystore ID Lookup returned (%s)" % keystoreid)
					if keystoreid:
						result = self.merge_final_config(keystoreid)
						log("cfact.request: Returning the below config to TFTPy:\n%s" % result)
						return result
					else:
						log("cfact.request: SNMP request for (%s) returned an unknown ID, checking for default-keystore" % self.snmprequests[tempid].host)
						default = self._default_lookup()
						if default:
							log("cfact.request: default-keystore is configured. Returning default")
							result = self.merge_final_config(default)
							log("cfact.request: Returning the below config to TFTPy:\n%s" % result)
							return result
				else:
					log("cfact.request: SNMP request is not complete on host (%s), checking for default-keystore" % self.snmprequests[tempid].host)
					default = self._default_lookup()
					if default:
						log("cfact.request: default-keystore is configured. Returning default")
						result = self.merge_final_config(default)
						log("cfact.request: Returning the below config to TFTPy:\n%s" % result)
						return result
			#else:
			#	log("cfact.request: SNMP request is not complete, checking for default-keystore" % self.snmprequests[tempid].host)
			#	default = self._default_lookup()
			#	if default:
			#		log("cfact.request: default-keystore is configured. Returning default")
			#		return self.merge_final_config(default)
		log("cfact.request: Nothing else caught. Returning None")
		return None
	def create_snmp_request(self, tempid, ipaddr):
		newquery = snmp_query(ipaddr, self.basesnmpcom, self.snmpoid)
		self.snmprequests.update({tempid: newquery})
	def _generate_name(self):
		timeint = int(str(time.time()).replace(".", ""))
		timehex = hex(timeint)
		hname = timehex[2:12].upper()
		return("ZTP-"+hname)
	def merge_base_config(self, tempid):
		template = j2.Template(self.baseconfig)
		return template.render(autohostname=tempid, community=self.basesnmpcom)
	def merge_final_config(self, keystoreid):
		templatedata = self.get_template(keystoreid)
		template = j2.Template(templatedata)
		vals = config.running["keyvalstore"][keystoreid]
		return template.render(vals)
	def get_keystore_id(self, iden):
		if iden in list(config.running["keyvalstore"]):
			return iden
		else:
			identity = False
			for arrayname in list(config.running["idarrays"]):
				if iden in config.running["idarrays"][arrayname]:
					identity = arrayname
					log("ID '%s' resolved to arrayname '%s'" % (iden, identity))
					break
			return identity
	def get_template(self, identity):
		response = False
		for association in self.associations:
			if identity == association:
				templatename = self.associations[association]
				if templatename in self.templates:
					response = self.templates[templatename]
		return response
	def merge_test(self, iden, template):
		identity = self.get_keystore_id(iden)
		if not identity:
			log("ID '%s' does not exist in keystore!" % iden)
		else:
			env = Environment()
			if template == "final":
				templatedata = self.get_template(identity)
				if not templatedata:
					log("No tempate associated with identity %s" % iden)
					quit()
				else:
					j2template = j2.Template(templatedata)
					ast = env.parse(templatedata)
			elif template == "initial":
				j2template = j2.Template(self.baseconfig)
				ast = env.parse(self.baseconfig)
			templatevarlist = list(meta.find_undeclared_variables(ast))
			varsmissing = False
			missingvarlist = []
			for var in templatevarlist:
				if var not in config.running["keyvalstore"][identity]:
					varsmissing = True
					missingvarlist.append(var)
			if varsmissing:
				console("\nSome variables in jinja template do not exist in keystore:")
				for var in missingvarlist:
					console("\t-"+var)
				console("\n")
			console("##############################")
			console(j2template.render(config.running["keyvalstore"][identity]))
			console("##############################")


##### SNMP Querying object: It is instantiated by the config_factory      #####
#####   when the initial template is pulled down. A thread is             #####
#####   spawned which continuously tries to query the ID of the           #####
#####   switch. Once successfully queried, the querying object            #####
#####   retains the real ID of the switch which is mapped to a            #####
#####   keystore ID when the final template is requested                  #####
class snmp_query:
	def __init__(self, host, community, oid, timeout=30):
		global pysnmp
		import pysnmp.hlapi
		self.complete = False
		self.status = "starting"
		self.response = None
		self.host = host
		self.community = community
		self.oid = oid
		self.timeout = timeout
		self.thread = threading.Thread(target=self._query_worker)
		self.thread.daemon = True
		self.thread.start()
	def _query_worker(self):
		starttime = time.time()
		self.status = "running"
		while not self.complete:
			try:
				log("snmp_query._query_worker: Attempting SNMP Query")
				response = self._get_oid()
				self.response = response
				self.status = "success"
				self.complete = True
				log("snmp_query._query_worker: SNMP Query Successful. Host (%s) responded with (%s)" % (self.host, str(self.response)))
			except IndexError:
				self.status = "retrying"
				log("snmp_query._query_worker: SNMP Query Timed Out")
			if (time.time() - starttime) > self.timeout:
				self.status = "failed"
				log("snmp_query._query_worker: Timeout Expired, Query Thread Terminating")
				break
			else:
				time.sleep(3)
	def _get_oid(self):
		errorIndication, errorStatus, errorIndex, varBinds = next(
			pysnmp.hlapi.getCmd(pysnmp.hlapi.SnmpEngine(),
				   pysnmp.hlapi.CommunityData(self.community, mpModel=0),
				   pysnmp.hlapi.UdpTransportTarget((self.host, 161)),
				   pysnmp.hlapi.ContextData(),
				   pysnmp.hlapi.ObjectType(pysnmp.hlapi.ObjectIdentity(self.oid)))
		)
		return str(varBinds[0][1])


##### Configuration Manager: handles publishing of and changes to the ZTP #####
#####   configuration input by the administrator                          #####
class config_manager:
	def __init__(self):
		self.configfile = self._get_config_file()
		self._publish()
	def _get_config_file(self):
		configfilename = "ztp.cfg"
		pathlist = ["/etc/ztp", os.getcwd()]
		for path in pathlist:
			filepath = path + "/" + configfilename
			if os.path.isfile(filepath):
				return filepath
		return None
	def _publish(self):
		if self.configfile:
			f = open(self.configfile, "r")
			self.rawconfig = f.read()
			f.close()
			self.running = json.loads(self.rawconfig)
			self.suffix = self.running["suffix"]
			self.templates = self.running["templates"]
			self.keyvalstore = self.running["keyvalstore"]
			self.initialfilename = self.running["initialfilename"]
			self.community = self.running["community"]
			self.snmpoid = self.running["snmpoid"]
			self.starttemplate = self.running["starttemplate"]
			self.associations = self.running["associations"]
		else:
			print("No Config File Found! Please install app!")
			#quit()
	def save(self):
		self.rawconfig = self.json = json.dumps(self.running, indent=4, sort_keys=True)
		f = open(self.configfile, "w")
		self.rawconfig = f.write(self.rawconfig)
		f.close()
	def set(self, args):
		setting = args[2]
		value = args[3]
		exceptions = ["keyvalstore", "starttemplate"]
		if setting in exceptions:
			console("Cannot configure this way")
		elif "template" in setting:
			if setting == "initial-template":
				console("Enter each line of the template ending with '%s' on a line by itself" % args[3])
				newtemplate = self.multilineinput(args[3])
				self.running["starttemplate"] = newtemplate
			elif setting == "template":
				console("Enter each line of the template ending with '%s' on a line by itself" % args[4])
				newtemplate = self.multilineinput(args[4])
				if "templates" not in list(self.running):
					self.running.update({"templates": {}})
				self.running["templates"][value] = newtemplate
			self.save()
		elif setting == "keystore":
			self.set_keystore(args[3], args[4], args[5] )
		elif setting == "idarray":
			self.set_idarray(value, args[4:])
		elif setting == "association":
			iden = args[4]
			template = args[6]
			self.set_association(iden, template)
		elif setting == "default-keystore":
			if value.lower() == "none":
				value = None
			self.running[setting] = value
			self.save()
		elif setting == "dhcpd":
			self.set_dhcpd(args)
		else:
			if setting in list(self.running):
				self.running[setting] = value
				self.save()
			else:
				console("Unknown Setting!")
	def clear(self, args):
		setting = args[2]
		iden = args[3]
		if setting == "keystore":
			key = args[4]
			if iden not in list(self.running["keyvalstore"]):
				console("ID does not exist in keystore: %s" % iden)
			else:
				if key == "all":
					del self.running["keyvalstore"][iden]
				else:
					if key not in list(self.running["keyvalstore"][iden]):
						console("Key does not exist under ID %s: %s" % (iden, key))
					else:
						del self.running["keyvalstore"][iden][key]
						if self.running["keyvalstore"][iden] == {}: # No keys left
							del self.running["keyvalstore"][iden]
		elif setting == "idarray":
			if iden not in list(self.running["idarrays"]):
				console("ID does not exist in the idarrays: %s" % iden)
			else:
				del self.running["idarrays"][iden]
		elif setting == "template":
			if "templates" not in list(self.running):
				console("No templates are currently configured")
			elif iden not in list(self.running["templates"]):
				console("Template '%s' is not currently configured" % iden)
			else:
				del self.running["templates"][iden] 
		elif setting == "association":
			if "associations" not in list(self.running):
				console("No associations are currently configured")
			elif iden not in list(self.running["associations"]):
				console("Association '%s' is not currently configured" % iden)
			else:
				del self.running["associations"][iden]
		elif setting == "dhcpd":
			if "dhcpd" not in list(self.running):
				console("No DHCP scopes are currently configured")
			elif iden not in list(self.running["dhcpd"]):
				console("DHCP Scope '%s' is not currently configured" % iden)
			else:
				del self.running["dhcpd"][iden]
		else:
			console("Unknown Setting!")
		self.save()
	def multilineinput(self, ending):
		result = ""
		for line in iter(raw_input, ending):
			result += line+"\n"
		return result[0:len(result)-1]
	def set_keystore(self, iden, keyword, value):
		if iden in list(self.running["keyvalstore"]):
			self.running["keyvalstore"][iden].update({keyword: value})
		else:
			self.running["keyvalstore"].update({iden: {keyword: value}})
		self.save()
	def set_idarray(self, arrayname, idlist):
		if arrayname in list(self.running["idarrays"]):
			self.running["idarrays"][arrayname] = idlist
		else:
			self.running["idarrays"].update({arrayname: idlist})
		self.save()
	def set_association(self, iden, template):
		if "associations" not in list(self.running):
			self.running.update({"associations": {}})
		self.running["associations"].update({iden: template})
		self.save()
	def set_dhcpd(self, args):
		global netaddr
		import netaddr
		if len(args) < 6:
			print("ERROR: Incomplete Command!")
			quit()
		scope = args[3]
		setting = args[4]
		value = args[5]
		checks = {"subnet": self.is_net, "first-address": self.is_ip, "last-address": self.is_ip, "gateway": self.is_ip, "ztp-tftp-address": self.is_ip, "imagediscoveryfile-option": self.make_true, "domain-name": self.make_true}
		#### Build Path
		if "dhcpd" not in list(self.running):
			self.running.update({"dhcpd": {}})
		if scope not in self.running["dhcpd"]:
			self.running["dhcpd"].update({scope: {"imagediscoveryfile-option": "enable"}})
		###############
		if setting in checks:
			check = checks[setting](value)
			if check == True:
				self.running["dhcpd"][scope].update({setting: value})
			else:
				print(check)
		elif setting == "dns-servers":
			value = ", ".join(args[5:])
			self.running["dhcpd"][scope].update({setting: value})
		else:
			print("BAD COMMAND!")
		self.save()
	def is_ip(self, data):
		try:
			netaddr.IPAddress(data)
			return True
		except Exception as err:
			return err
	def is_net(self, data):
		try:
			ipobj = netaddr.IPNetwork(data)
			if str(ipobj.cidr) == data:
				return True
			else:
				return "Please provide a CIDR address (ie: 10.0.0.0/24)"
		except ValueError as err:
			return err
	def make_true(self, data):
		return True
	def show_config(self):
		cmdlist = []
		simplevals = ["suffix", "initialfilename", "community", "snmpoid", "tftproot", "imagediscoveryfile"]
		for each in simplevals:
			cmdlist.append("ztp set %s %s" % (each, self.running[each]))
		itemp = "ztp set initial-template ^\n%s\n^" % self.running["starttemplate"]
		###########
		templatetext = ""
		for template in self.running["templates"]:
			templatetext += "ztp set template %s ^\n%s\n^" % (template, self.running["templates"][template])
			templatetext += "\n!\n!\n!\n#######################################################\n"
		###########
		idarraylist = []
		for arrayname in self.running["idarrays"]:
			command = "ztp set idarray " + arrayname
			for iden in self.running["idarrays"][arrayname]:
				command += " " + iden
			idarraylist.append(command)
		###########
		keylist = []
		for iden in self.running["keyvalstore"]:
			for key in self.running["keyvalstore"][iden]:
				value = self.running["keyvalstore"][iden][key]
				keylist.append("ztp set keystore %s %s %s" % (iden, key, value))
			keylist.append("!")
		############
		associationlist = []
		for association in self.running["associations"]:
			template = self.running["associations"][association]
			associationlist.append("ztp set association id %s template %s" % (association, template))
		############
		dkeystore = "ztp set default-keystore %s"  % str(self.running["default-keystore"])
		imagefile = "ztp set imagefile %s"  % str(self.running["imagefile"])
		############
		scopelist = []
		for scope in self.running["dhcpd"]:
			for option in self.running["dhcpd"][scope]:
				value = self.running["dhcpd"][scope][option]
				command = "ztp set dhcpd %s %s %s" % (scope, option, value)
				command = command.replace(",", "")
				scopelist.append(command)
			scopelist.append("!")
		scopelist = scopelist[:len(scopelist)-1] # Remove last !
		############
		configtext = "!\n!\n!\n"
		for cmd in cmdlist:
			configtext += cmd + "\n"
		configtext += "!\n!\n"
		configtext += itemp
		configtext += "\n!\n#######################################################\n"
		configtext += "#######################################################\n"
		###########
		###########
		configtext += "\n!\n!\n!\n#######################################################\n"
		configtext += templatetext
		###########
		configtext += "!\n!\n!\n"
		for cmd in keylist:
			configtext += cmd + "\n"
		configtext += "!\n"
		for cmd in idarraylist:
			configtext += cmd + "\n"
		configtext += "!\n!\n"
		for cmd in associationlist:
			configtext += cmd + "\n"
		configtext += "!\n!\n"
		configtext += dkeystore
		configtext += "\n"
		configtext += imagefile
		###########
		configtext += "\n!\n"
		for cmd in scopelist:
			configtext += cmd + "\n"
		###########
		console(configtext)
	def calcopt125hex(self):
		# Basedata meaning as follows:
		### 00 00 00 09 = Cisco vendor specific code
		basedata = "000000090a05"
		filenamedata = self.running["imagediscoveryfile"].encode("hex")
		lenval = hex(len(filenamedata)/2).replace("0x", "")
		if len(lenval) < 2:
			lenval = "0"+lenval
		return basedata+lenval+filenamedata
	def ciscohex(self, hexdata):
		last = 0
		current = 1
		templist = []
		for char in hexdata:
			if (len(hexdata) - last) < 4:
				templist.append(hexdata[last:len(hexdata)])
				break
			elif current%4 == 0:
				templist.append(hexdata[last:current])
				last = current
			current += 1
		result = ""
		for quad in templist:
			result += quad + "."
		return result[:len(result)-1]
	def isc_hex(self, hexdata):
		return ":".join(map(''.join, zip(*[iter(hexdata)]*2))).upper()
	def opt125(self, mode):
		if mode == "windows":
			console("""
	Follow the below Instructions:
		- Open the Windows DHCP Server admin window
		- Right click on the "IPv4" object under the DHCP server name
			- Select "Set Predefined Options"
		- Click the "Add" button
			- Set the following values
				- Name        = Cisco Image Discovery File
				- Data Type   = Encapsulated
				- Code        = 125
				- Description = Used by FreeZTP for IOS upgrade
			- Click OK
		- Click OK again
		
		- Find the DHCP scope serving ZTP devices
		- Expand the scope and right click "Scope Options"
			- Click "Configure Options"
		- Scroll down and check the box for option "125 Cisco Image Discovery File"
		- Place the typing cursor into the data field under "Binary"
		- Copy and paste the below hex code into the firewalld
			- Hex code between quotes - "%s"
		- You should see the ZTP configured imagediscoveryfile name under the "ASCII" field
		- Click OK
		- Close the Windows DHCP Server admin window
			""" % self.calcopt125hex())
		elif mode == "cisco":
			optiondata = self.running["imagediscoveryfile"].encode("hex")
			console("\n\nAdd the below line to your 'ip dhcp pool XXXX' config:\n")
			console("option 125 hex %s\n\n" % self.ciscohex(self.calcopt125hex()))
		elif mode == "isc":
			return self.isc_hex(self.calcopt125hex())
	def hidden_list_ids(self):
		for iden in list(self.running["keyvalstore"]):
			console(iden)
	def hidden_list_keys(self, iden):
		try:
			for key in list(self.running["keyvalstore"][iden]):
				console(key)
		except KeyError:
			pass
	def hidden_list_arrays(self):
		for arrayname in list(self.running["idarrays"]):
			console(arrayname)
	def hidden_list_templates(self):
		for template in self.running["templates"]:
			console(template)
	def hidden_list_associations(self):
		for association in self.running["associations"]:
			console(association)
	def hidden_list_all_ids(self):
		allids = {}  # Using a dict to automatically remove duplicates
		for iden in list(self.running["keyvalstore"]):
			allids.update({iden: None})
		for arrayname in list(self.running["idarrays"]):
			allids.update({arrayname: None})
		for association in self.running["associations"]:
			allids.update({association: None})
		for each in list(allids):
			console(each)
	def hidden_list_image_files(self):
		for each in os.listdir(self.running["tftproot"]):
			print(each)
	def hidden_list_dhcpd_scopes(self):
		for scope in self.running["dhcpd"]:
			console(scope)
	def dhcpd_compile(self):
		result = "########### FREEZTP DHCP SCOPES ###########\n"
		result += "############## DO NOT MODIFY ##############\n"
		result += "option ztp-tftp-address code 150 = { ip-address };\n"
		result += "option imagediscoveryfile-option code 125 = string;\n"
		result += "#\n"
		result += "#"
		mappings = {
		"gateway": " option routers <value>;",
		"dns-servers": " option domain-name-servers <value>;",
		"domain-name": ' option domain-name "<value>";',
		"ztp-tftp-address": " option ztp-tftp-address <value>;"
		}
		for scope in self.running["dhcpd"]:
			### Run Basic Checks
			if "subnet" not in self.running["dhcpd"][scope]:
				console("ERROR: DHCP Scope %s has no subnet defined. A subnet is required!. Compiling stopped." % scope)
				quit()
			elif "first-address" in self.running["dhcpd"][scope] and "last-address" not in self.running["dhcpd"][scope]:
				console("ERROR: Need to define a 'last-address' in scope %s. Compiling stopped." % scope)
				quit()
			elif "last-address" in self.running["dhcpd"][scope] and "first-address" not in self.running["dhcpd"][scope]:
				console("ERROR: Need to define a 'first-address' in scope %s. Compiling stopped." % scope)
				quit()
			else:
				### Start Compiling
				scopetext = "#### Scope: %s ####" % scope
				ending = " }\n" + "#" * len(scopetext)
				scopetext = "\n#\n" + scopetext + "\n"
				##
				subnet = netaddr.IPNetwork(self.running["dhcpd"][scope]["subnet"])
				net = str(subnet.network)
				mask = str(subnet.netmask)
				scopetext += "subnet %s netmask %s {\n" % (net, mask)
				##
				for option in self.running["dhcpd"][scope]:
					if option in mappings:
						value = self.running["dhcpd"][scope][option]
						txt = mappings[option].replace("<value>", value)
						scopetext += txt + "\n"
					elif option == "first-address":
						first = self.running["dhcpd"][scope]["first-address"]
						last = self.running["dhcpd"][scope]["last-address"]
						txt = " range %s %s;" % (first, last)
						scopetext += txt + "\n"
				if self.running["dhcpd"][scope]["imagediscoveryfile-option"] == "enable":
					opt125val = self.opt125("isc")
					txt = " send imagediscoveryfile-option %s;" % opt125val
					scopetext += txt + "\n"
				##
				scopetext += ending
				result += scopetext
		return result
		# option ztp-tftp-address code 150 = { ip-address };
	def dhcpd_commit(self):
		global netaddr
		import netaddr
		dhcpdata = self.dhcpd_compile()
		filedatalist = open("/etc/dhcp/dhcpd.conf").readlines()
		index = 1
		for line in filedatalist:
			if line == '########### FREEZTP DHCP SCOPES ###########\n':
				break
			else:
				index += 1
		strippeddata = ""
		for line in filedatalist[:index-1]:
			strippeddata += line
		strippeddata += dhcpdata
		console("\n################## Writing the below to the DHCP config file ##################")
		console("###############################################################################")
		console(strippeddata)
		console("###############################################################################")
		console("###############################################################################")
		f = open("/etc/dhcp/dhcpd.conf", "w")
		f.write(strippeddata)
		f.close()
		console("\nWrite Complete. Restarting DHCP Service...\n")
		#os.system('systemctl restart dhcpd')
		#os.system('systemctl status dhcpd')
		osd.service_control("restart", osd.DHCPSVC)
		osd.service_control("status", osd.DHCPSVC)
	def get_addresses(self):
		import netifaces
		result = []
		for iface in netifaces.interfaces():
			addressdict = netifaces.ifaddresses(iface)
			for addid in addressdict:
				for d in addressdict[addid]:
					if "addr" in d:
						addr = d["addr"]
					addr = d["addr"] if "addr" in d else "none"
					netmask = d["netmask"] if "netmask" in d else "none"
					result.append((iface, addr, netmask))
		return result
	def filter_ips(self, iplist):
		result = []
		for adtup in iplist:
			try:
				bits = netaddr.IPAddress(adtup[2]).netmask_bits()
				ip = adtup[1] + "/" + str(bits)
				i = netaddr.IPNetwork(ip)
				uni = i.is_unicast()
				loc = i.is_link_local()
				loop = i.is_loopback()
				multi = i.is_multicast()
				priv = i.is_private()
				res = i.is_reserved()
				if (uni, loc, loop, multi, priv, res) == (True, False, False, False, True, False):
					# Is a private IPv4 address
					result.append((adtup[0], adtup[1], adtup[2], str(i.cidr)))
				elif (uni, loc, loop, multi, priv, res) == (True, False, False, False, False, False):
					# Is a public IPv4 address
					result.append((adtup[0], adtup[1], adtup[2], str(i.cidr)))
			except Exception as e:
				pass
		return result
	def _write_interfaces(self, iflist):
		if os.path.isfile("/etc/default/isc-dhcp-server"):
			ifstr = " ".join(iflist)
			newfilelines = []
			filedatalist = open("/etc/default/isc-dhcp-server").readlines()
			for line in filedatalist:
				if "INTERFACESv4=" in line:
					newfilelines.append('INTERFACESv4="%s"\n' % ifstr)
				elif "INTERFACES=" in line:
					newfilelines.append('INTERFACES="%s"\n' % ifstr)
				else:
					newfilelines.append(line)
			newfile = ""
			for line in newfilelines:
				newfile += line
			f = open("/etc/default/isc-dhcp-server", "w")
			f.write(newfile)
			f.close()
	def auto_dhcpd(self):
		global netaddr
		import netaddr
		console("INFO: Autodetection can often detect an incorrect subnet mask. You may need to correct the subnet on auto built scopes")
		console("INFO: You will need to set the 'first-address' and 'last-address' settings on any auto-built scope for it to actually serve IP addresses ")
		console("Detecting interfaces and determining usable IP addresses...")
		ips = self.filter_ips(self.get_addresses())
		iflist = []
		console("  Found: %s\nCreating Scopes..." % ips)
		for net in ips:
			scopename = "INTERFACE-" + net[0].encode().upper()
			console("  Building Scope %s" % scopename)
			if net[2].encode() == "255.255.255.255":
				console("    WARNING: Scope %s has a /32 subnet size. You may need to adjust it if you want to serve IP addresses on that subnet" % scopename)
			subnet = net[3].encode()
			myip = net[1].encode()
			cmd1 = "ztp set dhcpd %s subnet %s" % (scopename, subnet)
			api1 = ['ztp', 'set', 'dhcpd', scopename, 'subnet', subnet]
			cmd2 = "ztp set dhcpd %s ztp-tftp-address %s" % (scopename, myip)
			api2 = ['ztp', 'set', 'dhcpd', scopename, 'ztp-tftp-address', myip]
			console("    Injecting Command: %s" % cmd1)
			self.set_dhcpd(api1)
			console("    Injecting Command: %s" % cmd2)
			self.set_dhcpd(api2)
			iflist.append(net[0])
		self._write_interfaces(iflist)
		console("\n\nComplete!\n\nRemember to commit the new DHCP config using the command 'ztp request dhcpd-commit'\n")


##### Log Management Class: Handles all prnting to console and logging    #####
#####   to the logfile                                                     #####
class log_management:
	def __init__(self):
		self.logfile = "/etc/ztp/ztp.log"
		self._publish_methods()
		self.can_log = True
	def _logger(self, data):
		logdata = time.strftime("%Y-%m-%d %H:%M:%S") + ":   " + data + "\n"
		if self.can_log:
			try:
				f = open(self.logfile, 'a')
				f.write(logdata)
				f.close()
			except IOError:
				self._console("Unable to log to logfile %s. Make sure FreeZTP is installed. Disabling logging to logfile" % self.logfile)
				self.can_log = False
		self._console(logdata)
	def _console(self, data, timestamp=False):
		if timestamp:
			logdata = time.strftime("%Y-%m-%d %H:%M:%S") + ":   " + data + "\n"
		else:
			logdata = data
		print(logdata)
	def _publish_methods(self):
		global log
		global console
		log = self._logger
		console = self._console
	def show(self, args):
		if len(args) == 3:
			os.system("more " + self.logfile)
		else:
			if args[3].lower() == "tail":
				if len(args) == 4:
					self.tail()
				else:
					try:
						int(args[4])
						self._console("\nUse CTRL + C to exit from the tail\n\n")
						self.tail(args[4])
					except ValueError:
						self._console("Invalid input '%s'. Must be an integer" % args[4])
			else:
				self._console("Invalid input '%s'" % args[3])
	def tail(self, length="25"):
		os.system("tail -fn %s %s" % (length, self.logfile))
	def clear(self):
		f = open(self.logfile, 'w')
		f.write("")
		f.close()


##### Installer class: A simple holder class which contains all of the    #####
#####   installation scripts used to install/upgrade the ZTP server       #####
class installer:
	defaultconfig = '''{\n    "associations": {\n        "MY_DEFAULT": "LONG_TEMPLATE", \n        "SERIAL100": "SHORT_TEMPLATE", \n        "STACK1": "LONG_TEMPLATE"\n    }, \n    "community": "secretcommunity", \n    "default-keystore": "MY_DEFAULT", \n    "idarrays": {\n        "STACK1": [\n            "SERIAL1", \n            "SERIAL2", \n            "SERIAL3"\n        ]\n    }, \n    "imagediscoveryfile": "freeztp_ios_upgrade", \n    "imagefile": "cat3k_caa-universalk9.SPA.03.06.06.E.152-2.E6.bin", \n    "initialfilename": "network-confg", \n    "keyvalstore": {\n        "MY_DEFAULT": {\n            "hostname": "UNKNOWN_HOST", \n            "vl1_ip_address": "dhcp"\n        }, \n        "SERIAL100": {\n            "hostname": "SOMEDEVICE", \n            "vl1_ip_address": "10.0.0.201"\n        }, \n        "STACK1": {\n            "hostname": "CORESWITCH", \n            "vl1_ip_address": "10.0.0.200", \n            "vl1_netmask": "255.255.255.0"\n        }\n    }, \n    "snmpoid": "1.3.6.1.2.1.47.1.1.1.1.11.1000", \n    "starttemplate": "hostname {{ autohostname }}\\n!\\nsnmp-server community {{ community }} RO\\n!\\nend", \n    "suffix": "-confg", \n    "templates": {\n        "LONG_TEMPLATE": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} {{ vl1_netmask }}\\n no shut\\n!\\nip domain-name test.com\\n!\\nusername admin privilege 15 secret password123\\n!\\naaa new-model\\n!\\n!\\naaa authentication login CONSOLE local\\naaa authorization console\\naaa authorization exec default local if-authenticated\\n!\\ncrypto key generate rsa modulus 2048\\n!\\nip ssh version 2\\n!\\nline vty 0 15\\nlogin authentication default\\ntransport input ssh\\nline console 0\\nlogin authentication CONSOLE\\nend", \n        "SHORT_TEMPLATE": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} 255.255.255.0\\n no shut\\n!\\nend"\n    }, \n    "tftproot": "/etc/ztp/tftproot/"\n}'''
	def minor_update_script(self):
		os.system('mkdir -p ' + "/etc/ztp/tftproot/")  # Create new tftproot dir
		newconfigkeys = {
		"imagediscoveryfile": "autoinstall_dhcp",
		"imagefile": "cat3k_caa-universalk9.SPA.03.06.06.E.152-2.E6.bin",
		"tftproot": "/etc/ztp/tftproot/"
		}
		for key in newconfigkeys:
			if key not in list(config.running):
				console("Adding (%s) to config schema" % key)
				config.running.update({key: newconfigkeys[key]})
		config.save()
		try:
			import netifaces
		except ImportError:
			#### DHCPD Install Process
			console("\n\nInstalling some new dependencies...\n")
			os.system("pip install netaddr")
			os.system("pip install netifaces")
			#os.system("yum -y install telnet")
			osd.install_pkg("telnet")
			self.dhcp_setup()
	def copy_binary(self):
		binpath = "/bin/"
		binname = "ztp"
		os.system('cp ztp.py ' + binpath + binname)
		os.system('chmod 777 ' + binpath + binname)
		console("Binary file installed at " + binpath + binname)
	def create_configfile(self):
		config = json.loads(self.defaultconfig)
		rawconfig = json.dumps(config, indent=4, sort_keys=True)
		configfilepath = "/etc/ztp/"
		configfilename = "ztp.cfg"
		os.system('mkdir -p ' + configfilepath)
		os.system('mkdir -p ' + "/etc/ztp/tftproot/")
		f = open(configfilepath + configfilename, "w")
		f.write(rawconfig)
		f.close()
		console("Config File Created at " + configfilepath + configfilename)
	def install_tftpy(self):
		console("Downloading tftpy library from https://github.com/PackeTsar/tftpy/archive/master.tar.gz...")
		os.system("curl -OL https://github.com/PackeTsar/tftpy/archive/master.tar.gz")
		console("Installing tftpy library...")
		os.system("tar -xzf master.tar.gz")
		os.system("cp -r tftpy-master/tftpy/ " + osd.PKGDIR)
		os.system("rm -rf tftpy-master")
		os.system("rm -rf master.tar.gz")
		console("Tftpy library installed")
	def disable_firewall(self):
		os.system("systemctl stop firewalld")
		os.system("systemctl disable firewalld")
		console("Firewalld stopped and disabled")
	def install_dependencies(self):
		if osd._pkgmgr == "apt-get":  # If using apt-get, update the repos
			os.system("sudo apt-get update -y")
		#os.system("yum -y install epel-release")
		osd.install_pkg("epel-release")
		#os.system("yum -y install python2-pip")
		osd.install_pkg(osd.PIPPKG)
		#os.system("yum -y install gcc gmp python-devel telnet")
		osd.install_pkg("gcc gmp python-devel")
		osd.install_pkg("telnet")
		os.system("pip install pysnmp")
		os.system("pip install jinja2")
		os.system("pip install netaddr")
		os.system("pip install netifaces")
	def dhcp_setup(self):
		console("\n\nInstalling DHCPD...\n")
		#os.system("yum -y install dhcp")
		osd.install_pkg(osd.DHCPPKG)
		#os.system('systemctl enable dhcpd')
		osd.service_control("enable", osd.DHCPSVC)
		console("\n\nSucking in config file...\n")
		global config
		config = config_manager()
		console("\n\nRetrying Module Imports...")
		try:
			global netaddr
			global netifaces
			import netaddr
			import netifaces
			console("Success!\n")
			console("\n\nPerforming DHCPD Auto-Setup...\n")
			time.sleep(2)
			config.auto_dhcpd()
			time.sleep(2)
			config.dhcpd_commit()
			console("\n\nDHCPD Auto-Setup Complete\n")
		except ImportError:
			console("Failed!\n")
	def create_service(self):
		systemd_startfile = '''[Unit]
Description=FreeZTP Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/bin/bash -c 'cd /bin; python ztp run'
Restart=on-abort


[Install]
WantedBy=multi-user.target'''

		nonsystemd_startfile = '''#!/bin/bash
# radiuid daemon
# chkconfig: 345 20 80
# description: ZTP Engine
# processname: ztp

DAEMON_PATH="/bin/"

DAEMON=ztp
DAEMONOPTS="run"
STDOUTFILE=/etc/ztp/stdout.log
STDERR=/etc/ztp/stderr.log

NAME=FreeZTP Server
DESC="ZTP Service"
PIDFILE=/var/run/$NAME.pid
SCRIPTNAME=/etc/init.d/$NAME

case "$1" in
start)
printf "%-50s" "Starting $NAME..."
cd $DAEMON_PATH
PID=`$DAEMON $DAEMONOPTS >> $STDOUTFILE 2>>$STDERR & echo $!`
#echo "Saving PID" $PID " to " $PIDFILE
	if [ -z $PID ]; then
		printf "%s\n" "Fail"
	else
		echo $PID > $PIDFILE
		printf "%s\n" "Ok"
	fi
;;
status)
	if [ -f $PIDFILE ]; then
		PID=`cat $PIDFILE`
		if [ -z "`ps axf | grep ${PID} | grep -v grep`" ]; then
			printf "%s\n" "Process dead but pidfile exists"
		else
			echo "$DAEMON (pid $PID) is running..."
		fi
	else
		printf "%s\n" "$DAEMON is stopped"
	fi
;;
stop)
	printf "%-50s" "Stopping $NAME"
		PID=`cat $PIDFILE`
		cd $DAEMON_PATH
	if [ -f $PIDFILE ]; then
		kill -HUP $PID
		printf "%s\n" "Ok"
		rm -f $PIDFILE
	else
		printf "%s\n" "pidfile not found"
	fi
;;

restart)
$0 stop
$0 start
;;

*)
	echo "Usage: $0 {status|start|stop|restart}"
	exit 1
esac'''
		systemdpath = '/etc/systemd/system/ztp.service'
		nonsystemdpath = '/etc/init.d/ztp'
		systemd = True
		if systemd:
			installpath = systemdpath
			installfile = systemd_startfile
		elif not systemd:
			installpath = nonsystemdpath
			installfile = nonsystemd_startfile
		f = open(installpath, 'w')
		f.write(installfile)
		f.close()
		if systemd:
			#os.system('systemctl enable ztp')
			osd.service_control("enable", "ztp")
			#os.system('systemctl start ztp')
			osd.service_control("start", "ztp")
		elif not systemd:
			os.system('chmod 777 /etc/init.d/radiuid')
			os.system('chkconfig radiuid on')
		console("ZTP service installed at /etc/systemd/system/ztp.service")
	def install_completion(self):
		##### BASH SCRIPT DATA START #####
		bash_complete_script = """#!/bin/bash

#####     ZTP Server BASH Complete Script   #####
#####        Written by John W Kerns        #####
#####       http://blog.packetsar.com       #####
#####  https://github.com/PackeTsar/radiuid #####

_ztp_complete()
{
  local cur prev
  COMPREPLY=()
  cur=${COMP_WORDS[COMP_CWORD]}
  prev=${COMP_WORDS[COMP_CWORD-1]}
  prev2=${COMP_WORDS[COMP_CWORD-2]}
  if [ $COMP_CWORD -eq 1 ]; then
	COMPREPLY=( $(compgen -W "run install upgrade show set clear request service version" -- $cur) )
  elif [ $COMP_CWORD -eq 2 ]; then
	case "$prev" in
	  show)
		COMPREPLY=( $(compgen -W "config run status version log downloads" -- $cur) )
		;;
	  "set")
		COMPREPLY=( $(compgen -W "suffix initialfilename community snmpoid initial-template tftproot imagediscoveryfile template keystore idarray association default-keystore imagefile dhcpd" -- $cur) )
		;;
	  "clear")
		COMPREPLY=( $(compgen -W "keystore idarray template association dhcpd log downloads" -- $cur) )
		;;
	  "request")
		COMPREPLY=( $(compgen -W "merge-test initial-merge default-keystore-test snmp-test dhcp-option-125 dhcpd-commit auto-dhcpd ipc-console" -- $cur) )
		;;
	  "service")
		COMPREPLY=( $(compgen -W "start stop restart status" -- $cur) )
		;;
	  *)
		;;
	esac
  elif [ $COMP_CWORD -eq 3 ]; then
	case "$prev" in
	  suffix)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
		fi
		;;
	  log)
		if [ "$prev2" == "show" ]; then
		  COMPREPLY=( $(compgen -W "tail -" -- $cur) )
		fi
		;;
	  downloads)
		if [ "$prev2" == "show" ]; then
		  COMPREPLY=( $(compgen -W "live -" -- $cur) )
		fi
		;;
	  initialfilename)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
		fi
		;;
	  community)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
		fi
		;;
	  snmpoid)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
		fi
		;;
	  initial-template)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "<deliniation_character> -" -- $cur) )
		fi
		;;
	  tftproot)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "<tftp_root_directory> -" -- $cur) )
		fi
		;;
	  imagediscoveryfile)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "<filename> -" -- $cur) )
		fi
		;;
	  template)
		local templates=$(for k in `ztp show templates`; do echo $k ; done)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "${templates} <template_name> -" -- $cur) )
		fi
		if [ "$prev2" == "clear" ]; then
		  COMPREPLY=( $(compgen -W "${templates}" -- $cur) )
		fi
		;;
	  keystore)
		local ids=$(for id in `ztp show ids`; do echo $id ; done)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "${ids} <new_id_or_arrayname> -" -- $cur) )
		fi
		if [ "$prev2" == "clear" ]; then
		  COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
		fi
		;;
	  idarray)
		local ids=$(for id in `ztp show arrays`; do echo $id ; done)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "${ids} <new_array_name> -" -- $cur) )
		fi
		if [ "$prev2" == "clear" ]; then
		  COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
		fi
		;;
	  association)
		if [ "$prev2" == "set" ]; then
		  COMPREPLY=( $(compgen -W "id" -- $cur) )
		fi
		if [ "$prev2" == "clear" ]; then
		  local ids=$(for id in `ztp show associations`; do echo $id ; done)
		  COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
		fi
		;;
	  default-keystore)
		if [ "$prev2" == "set" ]; then
		  local ids=$(for id in `ztp show ids`; do echo $id ; done)
		  COMPREPLY=( $(compgen -W "${ids} <keystore-id> None -" -- $cur) )
		fi
		;;
	  imagefile)
		if [ "$prev2" == "set" ]; then
		  local ids=$(for id in `ztp show imagefiles`; do echo $id ; done)
		  COMPREPLY=( $(compgen -W "${ids} <binary_image_file_name> -" -- $cur) )
		fi
		;;
	  dhcpd)
		if [ "$prev2" == "set" ]; then
		  local ids=$(for id in `ztp show dhcpd`; do echo $id ; done)
		  COMPREPLY=( $(compgen -W "${ids} <new_dhcp_scope_name> -" -- $cur) )
		fi
		if [ "$prev2" == "clear" ]; then
		  local ids=$(for id in `ztp show dhcpd`; do echo $id ; done)
		  COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
		fi
		;;
	  merge-test)
		local ids=$(for id in `ztp show ids`; do echo $id ; done)
		if [ "$prev2" == "request" ]; then
		  COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
		fi
		;;
	  snmp-test)
		if [ "$prev2" == "request" ]; then
		  COMPREPLY=( $(compgen -W "<ip-address> -" -- $cur) )
		fi
		;;
	  dhcp-option-125)
		if [ "$prev2" == "request" ]; then
		  COMPREPLY=( $(compgen -W "cisco windows" -- $cur) )
		fi
		;;
	  *)
		;;
	esac
  elif [ $COMP_CWORD -eq 4 ]; then
	prev3=${COMP_WORDS[COMP_CWORD-3]}
	if [ "$prev2" == "keystore" ]; then
	  local idkeys=$(for k in `ztp show keys $prev`; do echo $k ; done)
	  if [ "$prev3" == "set" ]; then
		COMPREPLY=( $(compgen -W "${idkeys} <new_key> -" -- $cur) )
	  fi
	  if [ "$prev3" == "clear" ]; then
		COMPREPLY=( $(compgen -W "${idkeys} all" -- $cur) )
	  fi
	fi
	if [ "$prev2" == "idarray" ]; then
	  if [ "$prev3" == "set" ]; then
		COMPREPLY=( $(compgen -W "<num_of_lines> -" -- $cur) )
	  fi
	fi
	if [ "$prev2" == "log" ]; then
	  if [ "$prev3" == "show" ]; then
		COMPREPLY=( $(compgen -W "<id's_seperated_by_spaces> -" -- $cur) )
	  fi
	fi
	if [ "$prev2" == "template" ]; then
	  if [ "$prev3" == "set" ]; then
		COMPREPLY=( $(compgen -W "<end_char> -" -- $cur) )
	  fi
	fi
	if [ "$prev2" == "association" ]; then
	  if [ "$prev3" == "set" ]; then
		local allids=$(for k in `ztp show all_ids`; do echo $k ; done)
		COMPREPLY=( $(compgen -W "<id/arrayname> ${allids} -" -- $cur) )
	  fi
	fi
	if [ "$prev2" == "dhcpd" ]; then
	  if [ "$prev3" == "set" ]; then
		COMPREPLY=( $(compgen -W "subnet first-address last-address gateway ztp-tftp-address imagediscoveryfile-option dns-servers domain-name" -- $cur) )
	  fi
	fi
  elif [ $COMP_CWORD -eq 5 ]; then
	prev3=${COMP_WORDS[COMP_CWORD-3]}
	prev4=${COMP_WORDS[COMP_CWORD-4]}
	if [ "$prev4" == "set" ]; then
	  if [ "$prev3" == "keystore" ]; then
		COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
	  fi
	fi
	if [ "$prev4" == "set" ]; then
	  if [ "$prev3" == "association" ]; then
		COMPREPLY=( $(compgen -W "template" -- $cur) )
	  fi
	fi
	if [ "$prev4" == "set" ]; then
	  if [ "$prev3" == "dhcpd" ]; then
		if [ "$prev" == "subnet" ]; then
		  COMPREPLY=( $(compgen -W "<ipv4_subnet_value> -" -- $cur) )
		fi
		if [ "$prev" == "first-address" ]; then
		  COMPREPLY=( $(compgen -W "<first_address_to_lease> -" -- $cur) )
		fi
		if [ "$prev" == "last-address" ]; then
		  COMPREPLY=( $(compgen -W "<last_address_to_lease> -" -- $cur) )
		fi
		if [ "$prev" == "gateway" ]; then
		  COMPREPLY=( $(compgen -W "<gateway_ipv4_address> -" -- $cur) )
		fi
		if [ "$prev" == "ztp-tftp-address" ]; then
		  COMPREPLY=( $(compgen -W "<ztp_server_ipv4_address> -" -- $cur) )
		fi
		if [ "$prev" == "imagediscoveryfile-option" ]; then
		  COMPREPLY=( $(compgen -W "enable disable" -- $cur) )
		fi
		if [ "$prev" == "dns-servers" ]; then
		  COMPREPLY=( $(compgen -W "<first_dns_ipv4_address> 8.8.8.8" -- $cur) )
		fi
		if [ "$prev" == "domain-name" ]; then
		  COMPREPLY=( $(compgen -W "<dns_search_domain> -" -- $cur) )
		fi
	  fi
	fi
  elif [ $COMP_CWORD -eq 6 ]; then
	prev4=${COMP_WORDS[COMP_CWORD-4]}
	prev5=${COMP_WORDS[COMP_CWORD-5]}
	if [ "$prev5" == "set" ]; then
	  if [ "$prev4" == "association" ]; then
		local templates=$(for k in `ztp show templates`; do echo $k ; done)
		COMPREPLY=( $(compgen -W "<template_name> ${templates} -" -- $cur) )
	  fi
	fi
  fi
  return 0
} &&
complete -F _ztp_complete ztp &&
bind 'set show-all-if-ambiguous on'"""
		##### BASH SCRIPT DATA STOP #####
		##### Place script file #####
		installpath = '/etc/profile.d/ztp-complete.sh'
		f = open(installpath, 'w')
		f.write(bash_complete_script)
		f.close()
		os.system('chmod 777 /etc/profile.d/ztp-complete.sh')
		console("Auto-complete script installed to /etc/profile.d/ztp-complete.sh")


# Overwrite of a TFTPY function to notify when downloads complete
def end(self):
	"""Finish up the context."""
	tftpy.TftpContext.end(self)
	self.metrics.end_time = time.time()
	#### BEGIN CHANGES ####
	#cfact.file_closed(self.file_to_transfer, self.host)  # Notify
	#print("################### ENDING %s %s %s #############################" % (self.host, str(self.port), self.file_to_transfer) * 10)
	tracking.report({
		"ipaddr": self.host,
		"port": self.port,
		"block": None,
		"filename": self.file_to_transfer,
		"source": "end"})
	#print(" ENDING %s %s %s" % (self.host, str(self.port), self.file_to_transfer))
	#### END CHANGES ####
	tftpy.log.debug("Set metrics.end_time to %s", self.metrics.end_time)
	self.metrics.compute()


# Overwrite of a TFTPY function to notify when downloads start
def start(self, buffer):
	"""Start the state cycle. Note that the server context receives an
	initial packet in its start method. Also note that the server does not
	loop on cycle(), as it expects the TftpServer object to manage
	that."""
	tftpy.log.debug("In TftpContextServer.start")
	self.metrics.start_time = time.time()
	tftpy.log.debug("Set metrics.start_time to %s", self.metrics.start_time)
	# And update our last updated time.
	self.last_update = time.time()
	pkt = self.factory.parse(buffer)
	tftpy.log.debug("TftpContextServer.start() - factory returned a %s", pkt)
	# Call handle once with the initial packet. This should put us into
	# the download or the upload state.
	#### BEGIN CHANGES ####
	#print("################### STARTING %s %s %s #############################" % (self.host, str(self.port), pkt.filename) * 10)
	#print(pkt.filename)
	tracking.report({
		"ipaddr": self.host,
		"port": self.port,
		"block": None,
		"filename": pkt.filename,
		"source": "start"})
	#print(" STARTING %s %s %s" % (self.host, str(self.port), self.file_to_transfer))
	#### END CHANGES ####
	self.state = self.state.handle(pkt,
									self.host,
									self.port)



def handle(self, pkt, raddress, rport):
	"Handle a packet, hopefully an ACK since we just sent a DAT."
	if isinstance(pkt, tftpy.TftpPacketACK):
		tftpy.log.debug("Received ACK for packet %d" % pkt.blocknumber)
		#### BEGIN CHANGES ####
		#print("################### PACKET %s %s %s #############################" % (pkt.blocknumber, raddress, rport) * 10)
		#print(self.context.fileobj.tell())
		tracking.report({
			"ipaddr": raddress,
			"port": rport,
			"block": pkt.blocknumber,
			"filename": None,
			"source": "handle"})
		#print(tracking._working)
		#for each in tracking._working:
		#	print tracking._working[each].active
		#print(tracking._master)
		#for each in tracking._master:
		#	filesize = tracking._master[each].filesize
		#	if not tracking._master[each].lastblock:
		#		sent = 0
		#	else:
		#		sent = tracking._master[each].lastblock*512
		#	#print(str(filesize-sent)+" --> "+str(sent)+"/"+str(filesize))
		#	print tracking._master[each].active
		#	print tracking._master[each].lastblock
		#	print tracking._master[each].sessionports
		#### END CHANGES ####
		# Is this an ack to the one we just sent?
		if self.context.next_block == pkt.blocknumber:
			if self.context.pending_complete:
				tftpy.log.info("Received ACK to final DAT, we're done.")
				return None
			else:
				tftpy.log.debug("Good ACK, sending next DAT")
				self.context.next_block += 1
				tftpy.log.debug("Incremented next_block to %d",
					self.context.next_block)
				self.context.pending_complete = self.sendDAT()
		elif pkt.blocknumber < self.context.next_block:
			tftpy.log.warn("Received duplicate ACK for block %d"
				% pkt.blocknumber)
			self.context.metrics.add_dup(pkt)
		else:
			tftpy.log.warn("Oooh, time warp. Received ACK to packet we "
					 "didn't send yet. Discarding.")
			self.context.metrics.errors += 1
		return self
	elif isinstance(pkt, tftpy.TftpPacketERR):
		tftpy.log.error("Received ERR packet from peer: %s" % str(pkt))
		raise tftpy.TftpException("Received ERR packet from peer: %s" % str(pkt))
	else:
		tftpy.log.warn("Discarding unsupported packet: %s" % str(pkt))
		return self


def sendDAT(self):
	"""This method sends the next DAT packet based on the data in the
	context. It returns a boolean indicating whether the transfer is
	finished."""
	finished = False
	blocknumber = self.context.next_block
	# Test hook
	if tftpy.TftpShared.DELAY_BLOCK and tftpy.TftpShared.DELAY_BLOCK == blocknumber:
		import time
		log.debug("Deliberately delaying 10 seconds...")
		time.sleep(10)
	dat = None
	blksize = self.context.getBlocksize()
	buffer = self.context.fileobj.read(blksize)
	tftpy.log.debug("Read %d bytes into buffer", len(buffer))
	if len(buffer) < blksize:
		tftpy.log.info("Reached EOF on file %s"
			% self.context.file_to_transfer)
		finished = True
	dat = tftpy.TftpPacketDAT()
	dat.data = buffer
	dat.blocknumber = blocknumber
	self.context.metrics.bytes += len(dat.data)
	tftpy.log.debug("Sending DAT packet %d", dat.blocknumber)
	self.context.sock.sendto(dat.encode().buffer,
		(self.context.host, self.context.tidport))
	if self.context.packethook:
		self.context.packethook(dat)
	self.context.last_pkt = dat
	#print(self.context.fileobj.tell())
	#print(dir(self.context))
	#print(self.context.address)
	#print(self.context.port)
	#print(self.context.file_to_transfer)
	tracking.report({
		"ipaddr": self.context.address,
		"port": self.context.port,
		"position": self.context.fileobj.tell(),
		"filename": self.context.file_to_transfer,
		"source": "sendDAT"})
	return finished


class tracking_class:
	def __init__(self, client=False):
		self._master = {}
		self.store = persistent_store("tracking")
		#self._working = {}
		if not client:
			self.status = self.store.recall()
			self.mthread = threading.Thread(target=self._maintenance)
			self.mthread.daemon = True
			self.mthread.start()
			self.ipc_server()
	def find_session(self, args):
		for session in self._master:
			if args["filename"]:
				if args["filename"] == self._master[session].filename:
					if self._master[session].active:
						return session
			else:
				if args["port"] in self._master[session].ports:
					if self._master[session].active:
						return session
		return False
	def report(self, args):
		session = self.find_session(args)
		if session:
			self._master[session].update(args)  # Send update to session
		if not session:
			if args["source"] != "end":
				self._master.update({time.time(): self.request_class(args, self)})
		#portpair = args["ipaddr"]+":"+str(args["port"])
		#if portpair in self._working:  # If init session exists
		#	self._working[portpair].update(args)  # Update the session
		#else:
		#	# Create a new session
		#	self._working.update({portpair: self.request_class(args, self)})
	def _maintenance(self):
		self.sthread = threading.Thread(target=self._maintain_store)
		self.sthread.daemon = True
		self.sthread.start()
		while True:
			time.sleep(1)
			if not self.sthread.is_alive():
				self.sthread = threading.Thread(target=self._maintain_store)
				self.sthread.daemon = True
				self.sthread.start()
	def _maintain_store(self):
		while True:
			time.sleep(1)
			#print("LOOPING")
			#print(self._working)
			### Update tracking status ###
			##############################
			for session in self._master:
				#key = self._master[session].ipaddr+":"+str(self._master[session].filename)
				self._master[session].update_percent()
				#try:
				#	bytessent = self._master[session].lastblock*512
				#except TypeError:
				#	bytessent = 0
				data = {
					"time": self._master[session].friendlytime,
					"ipaddr": self._master[session].ipaddr,
					"ports": self._master[session].ports,
					"filename": self._master[session].filename,
					"position": self._master[session].position,
					"bytessent": self._master[session].position,
					"active": self._master[session].active,
					"filesize": self._master[session].filesize,
					"percent": self._master[session].percent
				}
				self.status.update({session: data})
			self.store(self.status)
			##############################
			##############################
	class request_class:
		def __init__(self, args, parent):
			self.ipaddr = None
			self.ports = {}
			self.filename = None
			#self.lastblock = None
			self.position = 0
			#self.redirect = redirect
			self.parent = parent
			#self.sessionports = []
			#self.children = {}  # Child sessions created during TFTP start
			#self.master = master
			self.active = True
			self.threads = []
			self.filesize = None
			self.percent = None
			self.creation = time.time()
			self.friendlytime = time.strftime("%Y-%m-%d %H:%M:%S")
			self.lastupdate = self.creation
			self._inactivity_timeout(30)
			self.update(args)
			#if self.master:
			#	self.init_master()
		def update(self, args): # Update this object from a report
			self.lastupdate = time.time()
			if args["port"]:
				if args["port"] not in self.ports:
					self.ports.update({args["port"]: time.time()})
			for arg in args:  # For each passed attrib
				if args[arg]:  # If it has a value
					if arg == "ipaddr":
						self.ipaddr = args[arg]
					elif arg == "filename":
						if not self.filename:
							self.filename = args[arg]
							self.check_file()
					elif arg == "position":
						self.position = args[arg]
			#print(self.ipaddr, self.ports, self.filename, self.active, self.position, self.filesize)
		def _inactivity_timeout(self, seconds, thread=False):
			if not thread:  #If not started in a thread, restart in a thread
				thread = threading.Thread(target=self._inactivity_timeout, 
					args=(seconds, True))
				thread.daemon = True
				thread.start()
				self.threads.append(thread)  # Add to list of session threads
				return None
			else:
				while True:
					if not self.active:  # If this session is no longer inactive
						return None  # Return and stop the thread
					else:  # If it is still active
						if time.time() - self.lastupdate > seconds:
							# If there has been no activity 
							# in the timeout period
							self.active = False  # Mark session as inactive
					time.sleep(0.1)  # Sleep for .1 seconds
			#if type(self.redirect) != type(True):  # If we are redirecting updates
			#	target = self.redirect  # Setup to send the updates
			#	print("Forwarding Update")
			#else:  # Otherwise
			#	target = self  # Update outselves
			#for arg in args:  # For each passed attrib
			#	if args[arg]:  # If it has a value
			#		if arg == "ipaddr":
			#			target.ipaddr = args[arg]
			#		elif arg == "port":
			#			target.port = args[arg]
			#		elif arg == "filename":
			#			target.filename = args[arg]
			#		elif arg == "block":
			#			target.lastblock = args[arg]
			#		elif arg == "source":
			#			if args[arg] == "end":  # If called by end()
			#				self.active = False  # Unset active for cleanup
			#				if target.lastblock:
			#					if target.lastblock*512 >= target.filesize:
			#						target.active = False  # Unset active for cleanup
			#						target.clean_working()
			#if not self.redirect and self.filename:  # If transferring
			#	self.transfer()
		#def transfer(self):
		#	filepair = self.ipaddr+":"+self.filename
		#	if filepair in self.parent._master:
		#		self.redirect = self.parent._master[filepair]
		#		self.redirect.sessionports.append(self.port)
		#	else:
		#		args = {"ipaddr":self.ipaddr, "port":self.port, "filename": self.filename}
		#		newsession = self.parent.request_class(args, self.parent, True, True)
		#		newsession.sessionports.append(self.port)
		#		#newsession.redirect = newsession
		#		#self.redirect = newsession
		#		self.parent._master.update({filepair: newsession})
		#		self.redirect = newsession
		def check_file(self):
			path = config.running["tftproot"]+self.filename
			if os.path.isfile(path):
				self.filesize = os.path.getsize(path)
		#def init_master(self):
		#	self.check_file()
		#def clean_working(self):
		#	print("Cleaning!")
		#	for session in self.sessionports:
		#		key = self.ipaddr+":"+str(session)
		#		if key in self.parent._working:
		#			del self.parent._working[key]
		def update_percent(self):
			if self.filesize:
				percent = round(100.0*self.position/self.filesize, 4)
				if percent > 100:
					self.percent = 100.00
				else:
					self.percent = percent
	########################################################################
	########################################################################
	########################################################################
	########################################################################
	########################################################################
	########################################################################
	########################################################################
	########################################################################
	########################################################################
	def make_table(self, columnorder, tabledata):
		##### Check and fix input type #####
		if type(tabledata) != type([]): # If tabledata is not a list
			tabledata = [tabledata] # Nest it in a list
		##### Set seperators and spacers #####
		tablewrap = "#" # The character used to wrap the table
		headsep = "=" # The character used to seperate the headers from the table values
		columnsep = "|" # The character used to seperate each value in the table
		columnspace = "  " # The amount of space between the largest value and its column seperator
		##### Generate a dictionary which contains the length of the longest value or head in each column #####
		datalengthdict = {} # Create the dictionary for storing the longest values
		for columnhead in columnorder: # For each column in the columnorder input
			datalengthdict.update({columnhead: len(columnhead)}) # Create a key in the length dict with a value which is the length of the header
		for row in tabledata: # For each row entry in the tabledata list of dicts
			for item in columnorder: # For column entry in that row
				if len(re.sub(r'\x1b[^m]*m', "",  str(row[item]))) > datalengthdict[item]: # If the length of this column entry is longer than the current longest entry
					datalengthdict[item] = len(str(row[item])) # Then change the value of entry
		##### Calculate total table width #####
		totalwidth = 0 # Initialize at 0
		for columnwidth in datalengthdict: # For each of the longest column values
			totalwidth += datalengthdict[columnwidth] # Add them all up into the totalwidth variable
		totalwidth += len(columnorder) * len(columnspace) * 2 # Account for double spaces on each side of each column value
		totalwidth += len(columnorder) - 1 # Account for seperators for each row entry minus 1
		totalwidth += 2 # Account for start and end characters for each row
		##### Build Header #####
		result = tablewrap * totalwidth + "\n" + tablewrap # Initialize the result with the top header, line break, and beginning of header line
		columnqty = len(columnorder) # Count number of columns
		for columnhead in columnorder: # For each column header value
			spacing = {"before": 0, "after": 0} # Initialize the before and after spacing for that header value before the columnsep
			spacing["before"] = int((datalengthdict[columnhead] - len(columnhead)) / 2) # Calculate the before spacing
			spacing["after"] = int((datalengthdict[columnhead] - len(columnhead)) - spacing["before"]) # Calculate the after spacing
			result += columnspace + spacing["before"] * " " + columnhead + spacing["after"] * " " + columnspace # Add the header entry with spacing
			if columnqty > 1: # If this is not the last entry
				result += columnsep # Append a column seperator
			del spacing # Remove the spacing variable so it can be used again
			columnqty -= 1 # Remove 1 from the counter to keep track of when we hit the last column
		del columnqty # Remove the column spacing variable so it can be used again
		result += tablewrap + "\n" + tablewrap + headsep * (totalwidth - 2) + tablewrap + "\n" # Add bottom wrapper to header
		##### Build table contents #####
		result += tablewrap # Add the first wrapper of the value table
		for row in tabledata: # For each row (dict) in the tabledata input
			columnqty = len(columnorder) # Set a column counter so we can detect the last entry in this row
			for column in columnorder: # For each value in this row, but using the correct order from column order
				spacing = {"before": 0, "after": 0} # Initialize the before and after spacing for that header value before the columnsep
				spacing["before"] = int((datalengthdict[column] - len(re.sub(r'\x1b[^m]*m', "",  str(row[column])))) / 2) # Calculate the before spacing
				spacing["after"] = int((datalengthdict[column] - len(re.sub(r'\x1b[^m]*m', "",  str(row[column])))) - spacing["before"]) # Calculate the after spacing
				result += columnspace + spacing["before"] * " " + str(row[column]) + spacing["after"] * " " + columnspace # Add the entry to the row with spacing
				if columnqty == 1: # If this is the last entry in this row
					result += tablewrap + "\n" + tablewrap # Add the wrapper, a line break, and start the next row
				else: # If this is not the last entry in the row
					result += columnsep # Add a column seperator
				del spacing # Remove the spacing settings for this entry 
				columnqty -= 1 # Keep count of how many row values are left so we know when we hit the last one
		result += tablewrap * (totalwidth - 1) # When all rows are complete, wrap the table with a trailer
		return result
	def show_downloads(self, args):
		data = []
		d = self.store.recall()
		dlist = list(d)
		dlist.sort()
		for dload in dlist:
			data.append(d[dload])
		return self.make_table([u'time', u'ipaddr', u'filename', u'filesize', u'bytessent', u'percent', u'active'], data)
	class screen:
		def __init__(self):
			self.win = curses.initscr()
			curses.noecho()
			curses.cbreak()
		def write(self, data):
			linelist = data.split("\n")
			index = 0
			for line in linelist:
				self.win.addstr(index, 0, line)
				index += 1
			self.win.refresh()
	#def show_downloads_live(self, args):
	#	s = self.screen()
	#	try:
	#		index = 0
	#		while True:
	#			s.write(self.show_downloads(None))
	#			time.sleep(0.1)
	#	except:
	#		curses.echo()
	#		curses.nocbreak()
	#		curses.endwin()
	#		quit()
	def clear_downloads(self):
		self._master = {}
		self.status = {}
		client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
		client.connect(('localhost', 10000))
		client.send("clear downloads\n")
		self.store({})
		client.close()
	def ipc_server(self):
		self.ipcthread = threading.Thread(target=self._status_ipc)
		self.ipcthread.daemon = True
		self.ipcthread.start()
	def _status_ipc(self):
		while True:
			sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)  # v6 family
			sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			sock.bind(("", 10000))
			sock.listen(1024)
			client, addr = sock.accept()
			thread = threading.Thread(target=self._status_ipc_talker, args=(client,))
			thread.start() # Start talker thread to listen to port
	def _status_ipc_talker(self, client):
		while True:
			recieve = client.recv(1024)
			if len(recieve) > 0:
				if "?" in recieve:
					table = """
- threads
- clear downloads
- get downloads
- exit
"""
					client.send(table)
				elif "exit" in recieve:
					client.close()
					return None
				elif "threads" in recieve:
					client.send(str(threading.activeCount()))  # Send the query response
					client.send(str(threading.enumerate()))
				elif "clear downloads" in recieve:
					self.clear_downloads()
					client.send(json.dumps(self.status, indent=4, sort_keys=True)+"\n")  # Send the query response
				elif "get downloads" in recieve:
					client.send(json.dumps(self.status, indent=4, sort_keys=True)+"\n")  # Send the query response
				else:
					client.send("ZTP#")  # Send the query response
	def _gen_animation(self):
		l = ["\\", "|", "/", "-"]
		index = 0
		while True:
			if index == 3:
				yield l[index]
				index = 0
			else:
				yield l[index]
				index += 1
	def get_live_status(self, client):
		data = []
		#d = self.store.recall()
		client.send("get downloads\n")
		time.sleep(0.1)
		d = client.recv(100000)
		d = json.loads(d)
		dlist = list(d)
		dlist.sort()
		for dload in dlist:
			data.append(d[dload])
		return self.make_table([u'time', u'ipaddr', u'filename', u'filesize', u'bytessent', u'percent', u'active'], data)
	def show_downloads_live(self, args):
		s = self.screen()
		ani = self._gen_animation()
		client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
		client.connect(('localhost', 10000))
		try:
			index = 0
			while True:
				table = self.get_live_status(client)
				s.write(table+next(ani))
		except:
			curses.echo()
			curses.nocbreak()
			curses.endwin()
			quit()

#t = tracking_class()
#t.report({"ipaddr": "10.0.0.1", "port": 65000, "filename": None, "block": None})
#t._working
#t._master
#
#t.report({"ipaddr": "10.0.0.1", "port": 65000, "filename": "test", "block": None})
#t._working
#t._master
#t._working[list(t._working)[0]].lastblock
#t._master[list(t._master)[0]].lastblock
#
#t.report({"ipaddr": "10.0.0.1", "port": 65000, "filename": "test", "block": 100})
#t._master[list(t._master)[0]].lastblock
#t._working[list(t._working)[0]].lastblock
#
#t.report({"ipaddr": "10.0.0.1", "port": 65000, "filename": "test", "block": 200})
#t._master[list(t._master)[0]].lastblock
#t._working[list(t._working)[0]].lastblock
#
#t.report({"ipaddr": "10.0.0.1", "port": 65100, "filename": None, "block": None})
#t._working
#t._master
#t.report({"ipaddr": "10.0.0.1", "port": 65100, "filename": "test", "block": 5000})


class persistent_store:
	def __init__(self, dbid):
		self._file = "/etc/ztp/pdb"
		self._dbid = dbid
		self._running = {}
		self._read()
	def __call__(self, data):
		self._read()
		self._running = data
		self._write()
	def recall(self):
		self._read()
		return self._running
	def _write(self):
		fulldb = self._pull_full_db()  # Pull a full copy of the db
		fulldb.update({self._dbid: self._running})  # Update it
		rawout = json.dumps(fulldb, indent=4, sort_keys=True)
		f = open(self._file, "w")
		f.write(rawout)
		f.close()
	def _create_blank(self):
		f = open(self._file, "w")
		f.write("{}")
		f.close()
	def _read(self):
		data = self._pull_full_db()
		try:
			self._running = data[self._dbid]
		except KeyError:
			self._write()
	def _pull_full_db(self):
		try:
			f = open(self._file, "r")
		except IOError as e:
			self._create_blank()
			f = open(self._file, "r")
		rawdata = f.read()
		f.close()
		result = json.loads(rawdata)
		return result

#s = persistent_store("tracking")
#s("something here")
#s.recall()


##### TFTP Server main entry. Starts the TFTP server listener and is the  #####
#####   main program loop. It is started with the ztp_dyn_file class      #####
#####   passed in as the dynamic file function.                           #####
def start_tftp():
	global tftpy
	import tftpy
	try:
		tftpy.TftpContextServer.start = start  # Overwrite the function
		tftpy.TftpContextServer.end = end  # Overwrite the function
		#tftpy.TftpStateExpectACK.handle = handle
		tftpy.TftpStateExpectACK.sendDAT = sendDAT
	except NameError:
		pass
	log("start_tftp: Starting Up TFTPy")
	#tftpy.setLogLevel(logging.DEBUG)
	try:
		server = tftpy.TftpServer(config.running["tftproot"], dyn_file_func=interceptor)
	except tftpy.TftpShared.TftpException:
		log("start_tftp: ERROR: TFTP Root path doesn't exist. Creating...")
		os.system('mkdir -p ' + config.running["tftproot"])
		server = tftpy.TftpServer(config.running["tftproot"], dyn_file_func=interceptor)
	server.listen(listenip="", listenport=69)
	log("start_tftp: Started up successfully")


##### Concatenate a list of words into a space-seperated string           #####
def cat_list(listname):
	result = ""
	counter = 0
	for word in listname:
		result = result + listname[counter].lower() + " "
		counter = counter + 1
	result = result[:len(result) - 1:]
	return result


##### Main CLI interpreter and helper function. Entry point for the app.  #####
def interpreter():
	arguments = cat_list(sys.argv[1:])
	global config
	#global cfact
	global logger
	global osd
	osd = os_detect()
	config = config_manager()
	logger = log_management()
	#try:
	#	cfact = config_factory()
	#except AttributeError:
	#	console("Cannot mount cfact")
	##### TEST #####
	if arguments == "test":
		pass
	##### RUN #####
	elif arguments == "run":
		global cfact
		cfact = config_factory()
		#global tftpy
		#global j2
		#global Environment
		#global meta
		#import tftpy
		#import jinja2 as j2
		#from jinja2 import Environment, meta
		log("interpreter: Command to run received. Calling start_tftp")
		global tracking
		tracking = tracking_class()
		start_tftp()
	##### INSTALL #####
	elif arguments == "install":
		console("***** Are you sure you want to install FreeZTP using version %s?*****" % version)
		answer = raw_input(">>>>> If you are sure you want to do this, type in 'CONFIRM' and hit ENTER >>>>")
		if answer.lower() == "confirm":
			inst = installer()
			inst.copy_binary()
			inst.create_configfile()
			inst.install_completion()
			inst.install_tftpy()
			inst.disable_firewall()
			inst.install_dependencies()
			inst.create_service()
			inst.dhcp_setup()
			console("\nInstall complete! Logout and log back into SSH to activate auto-complete")
		else:
			console("Install/upgrade cancelled")
	elif arguments == "upgrade":
		console("***** Are you sure you want to upgrade FreeZTP using version %s?*****" % version)
		answer = raw_input(">>>>> If you are sure you want to do this, type in 'CONFIRM' and hit ENTER >>>>")
		if answer.lower() == "confirm":
			inst = installer()
			inst.copy_binary()
			#inst.create_configfile()
			inst.install_completion()
			#inst.install_tftpy()
			#inst.disable_firewall()
			#inst.install_dependencies()
			inst.create_service()
			inst.minor_update_script()
			console("\nInstall complete! Logout and log back into SSH to activate auto-complete")
			console("\nMake sure to run 'ztp service restart' to restart the service for the new software to take effect")
		else:
			console("Install/upgrade cancelled")
	##### HIDDEN SHOW #####
	elif arguments == "show ids":
		config.hidden_list_ids()
	elif arguments[:9] == "show keys" and len(sys.argv) >= 4:
		config.hidden_list_keys(sys.argv[3])
	elif arguments == "show arrays":
		config.hidden_list_arrays()
	elif arguments == "show templates":
		config.hidden_list_templates()
	elif arguments == "show associations":
		config.hidden_list_associations()
	elif arguments == "show all_ids":
		config.hidden_list_all_ids()
	elif arguments == "show imagefiles":
		config.hidden_list_image_files()
	elif arguments == "show dhcpd":
		config.hidden_list_dhcpd_scopes()
	##### SHOW #####
	elif arguments == "show":
		console(" - show (config|run)                              |  Show the current ZTP configuration")
		console(" - show status                                    |  Show the status of the ZTP background service")
		console(" - show version                                   |  Show the current version of ZTP")
		console(" - show log (tail) (<num_of_lines>)               |  Show or tail the log file")
		console(" - show downloads (live)                          |  Show list of TFTP downloads")
	elif arguments == "show config" or arguments == "show run":
		config.show_config()
	elif arguments == "show status":
		console("\n")
		#os.system('systemctl status ztp')
		osd.service_control("status", "ztp")
		console("\n\n")
		#os.system('systemctl status dhcpd')
		osd.service_control("status", osd.DHCPSVC)
		console("\n")
	elif arguments == "show version":
		console("FreeZTP %s" % version)
	elif arguments[:8] == "show log":
		logger.show(sys.argv)
	elif arguments[:19] == "show downloads live":
		tracking = tracking_class(client=True)
		tracking.show_downloads_live(sys.argv)
	elif arguments[:14] == "show downloads":
		tracking = tracking_class(client=True)
		console(tracking.show_downloads(sys.argv))
	##### SET #####
	elif arguments == "set":
		console("--------------------------------------------------- SETTINGS YOU PROBABLY SHOULDN'T CHANGE ---------------------------------------------------")
		console(" - set suffix <value>                                          |  Set the file name suffix used by target when requesting the final config")
		console(" - set initialfilename <value>                                 |  Set the file name used by the target during the initial config request")
		console(" - set community <value>                                       |  Set the SNMP community you want to use for target ID identification")
		console(" - set snmpoid <value>                                         |  Set the SNMP OID to use to pull the target ID during identification")
		console(" - set initial-template <end_char>                             |  Set the initial configuration j2 template used for target identification")
		console(" - set tftproot <tftp_root_directory>                          |  Set the root directory for TFTP files")
		console(" - set imagediscoveryfile <filename>                           |  Set the name of the IOS image discovery file used for IOS upgrades")
		console("--------------------------------------------------------- SETTINGS YOU SHOULD CHANGE ---------------------------------------------------------")
		console(" - set template <template_name> <end_char>                     |  Create/Modify a named J2 tempate which is used for the final config push")
		console(" - set keystore <id/arrayname> <keyword> <value>               |  Create a keystore entry to be used when merging final configurations")
		console(" - set idarray <arrayname> <id's>                              |  Create an ID array to allow multiple real ids to match one keystore id")
		console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
		console(" - set default-keystore (none|keystore-id)                     |  Set a last-resort keystore and template for when target identification fails")
		console(" - set imagefile <binary_image_file_name>                      |  Set the image file name to be used for upgrades (must be in tftp root dir)")
		console(" - set dhcpd <scope-name> [parameters]                         |  Configure DHCP scope(s) to serve IP addresses to ZTP clients")
	elif arguments == "set suffix":
		console(" - set suffix <value>                             |  Set the file name suffix used by target when requesting the final config")
	elif arguments == "set initialfilename":
		console(" - set initialfilename <value>                    |  Set the file name used by the target during the initial config request")
	elif arguments == "set community":
		console(" - set community <value>                          |  Set the SNMP community you want to use for target ID identification")
	elif arguments == "set snmpoid":
		console(" - set snmpoid <value>                            |  Set the SNMP OID to use to pull the target ID during identification")
	elif arguments == "set initial-template":
		console(" - set initial-template <end_char>                |  Set the initial configuration j2 template used for target identification")
	elif arguments == "set tftproot":
		console(" - set tftproot <tftp_root_directory>             |  Set the root directory for TFTP files")
	elif arguments == "set imagediscoveryfile":
		console(" - set imagediscoveryfile <filename>              |  Set the name of the IOS image discovery file used for IOS upgrades")
	elif (arguments[:12] == "set template" and len(sys.argv) < 5) or arguments == "set template":
		console(" - set template <template_name> <end_char>        |  Set the final configuration j2 template pushed to host after discovery/identification")
	elif (arguments[:12] == "set keystore" and len(sys.argv) < 6) or arguments == "set keystore":
		console(" - set keystore <id/arrayname> <keyword> <value>  |  Create a keystore entry to be used when merging final configurations")
	elif (arguments[:11] == "set idarray" and len(sys.argv) < 5) or arguments == "set idarray":
		console(" - set idarray <arrayname> <id_#1> <id_#2> ...    |  Create an ID array to allow multiple real ids to match one keystore id")
	elif (arguments[:15] == "set association" and len(sys.argv) < 7) or arguments == "set association":
		console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
	elif (arguments[:20] == "set default-keystore" and len(sys.argv) < 4) or arguments == "default-keystore":
		console(" - set default-keystore (none|keystore-id)        |  Set a last-resort keystore and template for when target identification fails")
	elif arguments == "set imagefile":
		console(" - set imagefile <binary_image_file_name>         |  Set the image file name to be used for upgrades (must be in tftp root dir)")
	elif arguments == "set dhcpd":
		console(" - set dhcpd <scope-name> [parameters]            |  Configure DHCP scope(s) to serve IP addresses to ZTP clients")
	elif arguments[:3] == "set" and len(sys.argv) >= 4:
		config.set(sys.argv)
	##### CLEAR #####
	elif arguments == "clear":
		console(" - clear template <template_name>                 |  Delete a named configuration template")
		console(" - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration")
		console(" - clear idarray <arrayname>                      |  Delete an ID array from the configuration")
		console(" - clear association <id/arrayname>               |  Delete an association from the configuration")
		console(" - clear dhcpd <scope-name>                       |  Delete a DHCP scope")
		console(" - clear log                                      |  Delete the logging info from the logfile")
		console(" - clear downloads                                |  Delete the list of TFTP downloads")
	elif (arguments[:14] == "clear template" and len(sys.argv) < 4) or arguments == "clear template":
		console(" - clear template <template_name>                 |  Delete a named configuration template")
	elif (arguments[:14] == "clear keystore" and len(sys.argv) < 5) or arguments == "clear keystore":
		console(" - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration")
	elif (arguments[:13] == "clear idarray" and len(sys.argv) < 4) or arguments == "clear idarray":
		console(" - clear idarray <arrayname>                      |  Delete an ID array from the configuration")
	elif (arguments[:17] == "clear association" and len(sys.argv) < 4) or arguments == "clear association":
		console(" - clear association <id/arrayname>               |  Delete an association from the configuration")
	elif (arguments[:11] == "clear dhcpd" and len(sys.argv) < 4) or arguments == "clear dhcpd":
		console(" - clear dhcpd <scope-name>                       |  Delete a DHCP scope")
	elif arguments[:14] == "clear template" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	elif arguments[:14] == "clear keystore" and len(sys.argv) >= 5:
		config.clear(sys.argv)
	elif arguments[:13] == "clear idarray" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	elif arguments[:17] == "clear association" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	elif arguments[:11] == "clear dhcpd" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	elif arguments == "clear log":
		logger.clear()
		log("Log file has been cleared")
	elif arguments == "clear downloads":
		tracking = tracking_class(client=True)
		tracking.clear_downloads()
		log("Downloads have been cleared")
	##### REQUEST #####
	elif arguments == "request":
		console(" - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID")
		console(" - request initial-merge                          |  See the result of an auto-merge of the initial-template")
		console(" - request default-keystore-test                  |  Check that the default-keystore is fully configured to return a template")
		console(" - request snmp-test <ip-address>                 |  Run a SNMP test using the configured community and OID against an IP")
		console(" - request dhcp-option-125 (windows|cisco)        |  Show the DHCP Option 125 Hex value to use on the DHCP server for OS upgrades")
		console(" - request dhcpd-commit                           |  Compile the DHCP config, write to config file, and restart the DHCP service")
		console(" - request auto-dhcpd                             |  Automatically detect local interfaces and build DHCP scopes accordingly")
		console(" - request ipc-console                            |  Connect to the IPC console to run commands (be careful)")
	elif arguments == "request merge-test":
		console(" - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID")
	elif arguments == "request dhcp-option-125":
		console(" - request dhcp-option-125 (windows|cisco)        |  Show the DHCP Option 125 Hex value to use on the DHCP server for OS upgrades")
	elif arguments == "request initial-merge":
		cfact = config_factory()
		console(cfact.request(config.running["initialfilename"], "10.0.0.1"))
	elif arguments == "request default-keystore-test":
		cfact = config_factory()
		default = cfact._default_lookup()
		if default:
			cfact.merge_test(default, "final")
	elif arguments == "request snmp-test":
		console(" - request snmp-test <ip-address>                 |  Run a SNMP test using the configured community and OID against an IP")
	elif arguments[:18] == "request merge-test" and len(sys.argv) >= 4:
		cfact = config_factory()
		cfact.merge_test(sys.argv[3], "final")
	elif arguments[:17] == "request snmp-test" and len(sys.argv) >= 4:
		community = config.running["community"]
		oid = config.running["snmpoid"]
		console("\n\nHit CTRL+C to kill the SNMP query test")
		console("\nQuerying %s using community (%s) and OID (%s)\n" % (sys.argv[3], community, oid))
		query = snmp_query(sys.argv[3], community, oid)
		while query.thread.isAlive():
			time.sleep(3)
	elif arguments[:23] == "request dhcp-option-125" and (sys.argv[3] == "cisco" or sys.argv[3] == "windows"):
		config.opt125(sys.argv[3])
	elif arguments == "request dhcpd-commit":
		config.dhcpd_commit()
	elif arguments == "request auto-dhcpd":
		config.auto_dhcpd()
	elif arguments == "request ipc-console":
		os.system('telnet localhost 10000')
	##### SERVICE #####
	elif arguments == "service":
		console(" - service (start|stop|restart|status)            |  Start, Stop, or Restart the installed ZTP service")
	elif arguments == "service start":
		log("#########################################################")
		log("Starting the ZTP Service")
		#os.system('systemctl start ztp')
		#os.system('systemctl status ztp')
		osd.service_control("start", "ztp")
		osd.service_control("status", "ztp")
		log("#########################################################")
	elif arguments == "service stop":
		log("#########################################################")
		log("Stopping the ZTP Service")
		#os.system('systemctl stop ztp')
		#os.system('systemctl status ztp')
		osd.service_control("stop", "ztp")
		osd.service_control("status", "ztp")
		log("#########################################################")
	elif arguments == "service restart":
		log("#########################################################")
		log("Restarting the ZTP Service")
		#os.system('systemctl restart ztp')
		#os.system('systemctl status ztp')
		osd.service_control("restart", "ztp")
		osd.service_control("status", "ztp")
		log("#########################################################")
	elif arguments == "service status":
		#os.system('systemctl status ztp')
		osd.service_control("status", "ztp")
		osd.service_control("status", osd.DHCPSVC)
	##### VERSION #####
	elif arguments == "version":
		console("FreeZTP %s" % version)
	else:
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console("                     ARGUMENTS                                 |                                  DESCRIPTIONS")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - run                                                         |  Run the ZTP main program in shell mode begin listening for TFTP requests")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - install                                                     |  Run the ZTP installer")
		console(" - upgrade                                                     |  Run the ZTP upgrade process to update the software")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - show (config|run)                                           |  Show the current ZTP configuration")
		console(" - show status                                                 |  Show the status of the ZTP background service")
		console(" - show version                                                |  Show the current version of ZTP")
		console(" - show log (tail) (<num_of_lines>)                            |  Show or tail the log file")
		console(" - show downloads (live)                                       |  Show list of TFTP downloads")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console("--------------------------------------------------- SETTINGS YOU PROBABLY SHOULDN'T CHANGE ---------------------------------------------------")
		console(" - set suffix <value>                                          |  Set the file name suffix used by target when requesting the final config")
		console(" - set initialfilename <value>                                 |  Set the file name used by the target during the initial config request")
		console(" - set community <value>                                       |  Set the SNMP community you want to use for target ID identification")
		console(" - set snmpoid <value>                                         |  Set the SNMP OID to use to pull the target ID during identification")
		console(" - set initial-template <end_char>                             |  Set the initial configuration j2 template used for target identification")
		console(" - set tftproot <tftp_root_directory>                          |  Set the root directory for TFTP files")
		console(" - set imagediscoveryfile <filename>                           |  Set the name of the IOS image discovery file used for IOS upgrades")
		console("--------------------------------------------------------- SETTINGS YOU SHOULD CHANGE ---------------------------------------------------------")
		console(" - set template <template_name> <end_char>                     |  Create/Modify a named J2 tempate which is used for the final config push")
		console(" - set keystore <id/arrayname> <keyword> <value>               |  Create a keystore entry to be used when merging final configurations")
		console(" - set idarray <arrayname> <id_#1> <id_#2> ...                 |  Create an ID array to allow multiple real ids to match one keystore id")
		console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
		console(" - set default-keystore (none|keystore-id)                     |  Set a last-resort keystore and template for when target identification fails")
		console(" - set imagefile <binary_image_file_name>                      |  Set the image file name to be used for upgrades (must be in tftp root dir)")
		console(" - set dhcpd <scope-name> [parameters]                         |  Configure DHCP scope(s) to serve IP addresses to ZTP clients")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - clear template <template_name>                              |  Delete a named configuration template")
		console(" - clear keystore <id> (all|<keyword>)                         |  Delete an individual key or a whole keystore ID from the configuration")
		console(" - clear idarray <arrayname>                                   |  Delete an ID array from the configuration")
		console(" - clear association <id/arrayname>                            |  Delete an association from the configuration")
		console(" - clear dhcpd <scope-name>                                    |  Delete a DHCP scope")
		console(" - clear log                                                   |  Delete the logging info from the logfile")
		console(" - clear downloads                                             |  Delete the list of TFTP downloads")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - request merge-test <id>                                     |  Perform a test jinja2 merge of the final template with a keystore ID")
		console(" - request initial-merge                                       |  See the result of an auto-merge of the initial-template")
		console(" - request default-keystore-test                               |  Check that the default-keystore is fully configured to return a template")
		console(" - request snmp-test <ip-address>                              |  Run a SNMP test using the configured community and OID against an IP")
		console(" - request dhcp-option-125 (windows|cisco)                     |  Show the DHCP Option 125 Hex value to use on the DHCP server for OS upgrades")
		console(" - request dhcpd-commit                                        |  Compile the DHCP config, write to config file, and restart the DHCP service")
		console(" - request auto-dhcpd                                          |  Automatically detect local interfaces and build DHCP scopes accordingly")
		console(" - request ipc-console                                         |  Connect to the IPC console to run commands (be careful)")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - service (start|stop|restart|status)                         |  Start, Stop, or Restart the installed ZTP service")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - version                                                     |  Show the current version of ZTP")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")


if __name__ == "__main__":
	interpreter()