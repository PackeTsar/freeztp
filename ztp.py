#!/usr/bin/python


#####         FreeZTP Server v0.6.0          #####
#####        Written by John W Kerns         #####
#####       http://blog.packetsar.com        #####
##### https://github.com/convergeone/freeztp #####


##### Inform FreeZTP version here #####
version = "v0.6.0"


##### Try to import non-native modules, fail gracefully #####
try:
	import jinja2 as j2
	from jinja2 import Environment, meta
	import pysnmp.hlapi
	import tftpy
except ImportError:
	print("Had some import errors, may not have dependencies installed yet")


##### Import native modules #####
import os
import sys
import json
import time
import logging
import commands
import threading


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
		self.state = {}
		self.snmprequests = {}
		self.basefilename = config.running["initialfilename"]
		self.basesnmpcom = config.running["community"]
		self.snmpoid = config.running["snmpoid"]
		self.baseconfig = config.running["starttemplate"]
		self.uniquesuffix = config.running["suffix"]
		self.templates = config.running["templates"]
		self.keyvalstore = config.running["keyvalstore"]
		self.associations = config.running["associations"]
	def lookup(self, filename, ipaddr):
		log("cfact.lookup: Called. Checking filename (%s) and IP (%s)" % (filename, ipaddr))
		tempid = filename.replace(self.uniquesuffix, "")
		log("cfact.lookup: TempID is (%s)" % tempid)
		log("cfact.lookup: Current SNMP Requests: %s" % list(self.snmprequests))
		if filename == self.basefilename:
			log("cfact.lookup: TempID matches the initialfilename. Returning True")
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
			console("Enter each line of the template ending with '%s' on a line by itself" % args[3])
			newtemplate = self.multilineinput(args[4])
			if setting == "initial-template":
				self.running["starttemplate"] = newtemplate
			elif setting == "template":
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
	def show_config(self):
		cmdlist = []
		simplevals = ["suffix", "initialfilename", "community", "snmpoid"]
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
		###########
		console(configtext)
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
	defaultconfig = '''{\n    "associations": {\n        "MY_DEFAULT": "LONG_TEMPLATE", \n        "SERIAL100": "SHORT_TEMPLATE", \n        "STACK1": "LONG_TEMPLATE"\n    }, \n    "community": "secretcommunity", \n    "default-keystore": "MY_DEFAULT", \n    "idarrays": {\n        "STACK1": [\n            "SERIAL1", \n            "SERIAL2", \n            "SERIAL3"\n        ]\n    }, \n    "initialfilename": "network-confg", \n    "keyvalstore": {\n        "MY_DEFAULT": {\n            "hostname": "UNKNOWN_HOST", \n            "vl1_ip_address": "dhcp"\n        }, \n        "SERIAL100": {\n            "hostname": "SOMEDEVICE", \n            "vl1_ip_address": "10.0.0.201"\n        }, \n        "STACK1": {\n            "hostname": "CORESWITCH", \n            "vl1_ip_address": "10.0.0.200", \n            "vl1_netmask": "255.255.255.0"\n        }\n    }, \n    "snmpoid": "1.3.6.1.2.1.47.1.1.1.1.11.1000", \n    "starttemplate": "hostname {{ autohostname }}\\n!\\nsnmp-server community {{ community }} RO\\n!\\nend", \n    "suffix": "-confg", \n    "templates": {\n        "LONG_TEMPLATE": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} {{ vl1_netmask }}\\n no shut\\n!\\nip domain-name test.com\\n!\\nusername admin privilege 15 secret password123\\n!\\naaa new-model\\n!\\n!\\naaa authentication login CONSOLE local\\naaa authorization console\\naaa authorization exec default local if-authenticated\\n!\\ncrypto key generate rsa modulus 2048\\n!\\nip ssh version 2\\n!\\nline vty 0 15\\nlogin authentication default\\ntransport input ssh\\nline console 0\\nlogin authentication CONSOLE\\nend", \n        "SHORT_TEMPLATE": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} 255.255.255.0\\n no shut\\n!\\nend"\n    }\n}'''
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
		f = open(configfilepath + configfilename, "w")
		f.write(rawconfig)
		f.close()
		console("Config File Created at " + configfilepath + configfilename)
	def install_tftpy(self):
		console("Downloading tftpy library from https://github.com/PackeTsar/tftpy/archive/master.tar.gz...")
		os.system("curl -OL https://github.com/PackeTsar/tftpy/archive/master.tar.gz")
		console("Installing tftpy library...")
		os.system("tar -xzf master.tar.gz")
		os.system("cp -r tftpy-master/tftpy/ /usr/lib/python2.7/site-packages/")
		os.system("rm -rf tftpy-master")
		os.system("rm -rf master.tar.gz")
		console("Tftpy library installed")
	def disable_firewall(self):
		os.system("systemctl stop firewalld")
		os.system("systemctl disable firewalld")
		console("Firewalld stopped and disabled")
	def install_dependencies(self):
		os.system("yum -y install epel-release")
		os.system("yum -y install python2-pip")
		os.system("yum -y install gcc gmp python-devel")
		os.system("pip install pysnmp")
		os.system("pip install jinja2")
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

NAME=FreeZTP Server
DESC="ZTP Service"
PIDFILE=/var/run/$NAME.pid
SCRIPTNAME=/etc/init.d/$NAME

case "$1" in
start)
printf "%-50s" "Starting $NAME..."
cd $DAEMON_PATH
PID=`$DAEMON $DAEMONOPTS > /dev/null 2>&1 & echo $!`
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
			os.system('systemctl enable ztp')
			os.system('systemctl start ztp')
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
        COMPREPLY=( $(compgen -W "config run status version log" -- $cur) )
        ;;
      "set")
        COMPREPLY=( $(compgen -W "suffix initialfilename community snmpoid initial-template template keystore idarray association default-keystore" -- $cur) )
        ;;
      "clear")
        COMPREPLY=( $(compgen -W "keystore idarray template association log" -- $cur) )
        ;;
      "request")
        COMPREPLY=( $(compgen -W "merge-test initial-merge default-keystore-test, snmp-test" -- $cur) )
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





"""
Fire up the TFTP server referencing the dyn_file_func class
for dynamic file creations
"""


##### TFTP Server main entry. Starts the TFTP server listener and is the  #####
#####   main program loop. It is started with the ztp_dyn_file class      #####
#####   passed in as the dynamic file function.                           #####
def start_tftp():
	log("start_tftp: Starting Up TFTPy")
	tftpy.setLogLevel(logging.DEBUG)
	server = tftpy.TftpServer("/", dyn_file_func=interceptor)
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
	global cfact
	global logger
	config = config_manager()
	logger = log_management()
	try:
		cfact = config_factory()
	except AttributeError:
		console("Cannot mount cfact")
	##### TEST #####
	if arguments == "test":
		pass
	##### RUN #####
	elif arguments == "run":
		log("interpreter: Command to run received. Calling start_tftp")
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
			#inst.create_service()
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
	##### SHOW #####
	elif arguments == "show":
		console(" - show (config|run)                              |  Show the current ZTP configuration")
		console(" - show status                                    |  Show the status of the ZTP background service")
		console(" - show version                                   |  Show the current version of ZTP")
		console(" - show log (tail) (<num_of_lines>)               |  Show or tail the log file")
	elif arguments == "show config" or arguments == "show run":
		config.show_config()
	elif arguments == "show status":
		os.system('systemctl status ztp')
	elif arguments == "show version":
		console("FreeZTP %s" % version)
	elif arguments[:8] == "show log":
		logger.show(sys.argv)
	##### SET #####
	elif arguments == "set":
		console("--------------------------------------------------- SETTINGS YOU PROBABLY SHOULDN'T CHANGE ---------------------------------------------------")
		console(" - set suffix <value>                                          |  Set the file name suffix used by target when requesting the final config")
		console(" - set initialfilename <value>                                 |  Set the file name used by the target during the initial config request")
		console(" - set community <value>                                       |  Set the SNMP community you want to use for target ID identification")
		console(" - set snmpoid <value>                                         |  Set the SNMP OID to use to pull the target ID during identification")
		console(" - set initial-template <end_char>                             |  Set the initial configuration j2 template used for target identification")
		console("--------------------------------------------------------- SETTINGS YOU SHOULD CHANGE ---------------------------------------------------------")
		console(" - set template <template_name> <end_char>                     |  Create/Modify a named J2 tempate which is used for the final config push")
		console(" - set keystore <id/arrayname> <keyword> <value>               |  Create a keystore entry to be used when merging final configurations")
		console(" - set idarray <arrayname> <id's>                              |  Create an ID array to allow multiple real ids to match one keystore id")
		console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
		console(" - set default-keystore (none|keystore-id)                     |  Set a last-resort keystore and template for when target identification fails")
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
	elif arguments[:3] == "set" and len(sys.argv) >= 4:
		config.set(sys.argv)
	##### CLEAR #####
	elif arguments == "clear":
		console(" - clear template <template_name>                 |  Delete a named configuration template")
		console(" - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration")
		console(" - clear idarray <arrayname>                      |  Delete an ID array from the configuration")
		console(" - clear association <id/arrayname>               |  Delete an association from the configuration")
		console(" - clear log                                      |  Delete the logging info from the logfile")
	elif (arguments[:14] == "clear template" and len(sys.argv) < 4) or arguments == "clear template":
		console(" - clear template <template_name>                 |  Delete a named configuration template")
	elif (arguments[:14] == "clear keystore" and len(sys.argv) < 5) or arguments == "clear keystore":
		console(" - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration")
	elif (arguments[:13] == "clear idarray" and len(sys.argv) < 4) or arguments == "clear idarray":
		console(" - clear idarray <arrayname>                      |  Delete an ID array from the configuration")
	elif (arguments[:17] == "clear association" and len(sys.argv) < 4) or arguments == "clear association":
		console(" - clear association <id/arrayname>               |  Delete an association from the configuration")
	elif arguments[:14] == "clear template" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	elif arguments[:14] == "clear keystore" and len(sys.argv) >= 5:
		config.clear(sys.argv)
	elif arguments[:13] == "clear idarray" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	elif arguments[:17] == "clear association" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	elif arguments == "clear log":
		logger.clear()
		log("Log file has been cleared")
	##### REQUEST #####
	elif arguments == "request":
		console(" - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID")
		console(" - request initial-merge                          |  See the result of an auto-merge of the initial-template")
		console(" - request default-keystore-test                  |  Check that the default-keystore is fully configured to return a template")
		console(" - request snmp-test <ip-address>                 |  Run a SNMP test using the configured community and OID against an IP")
	elif arguments == "request merge-test":
		console(" - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID")
	elif arguments == "request initial-merge":
		console(cfact.request(config.running["initialfilename"], "10.0.0.1"))
	elif arguments == "request default-keystore-test":
		default = cfact._default_lookup()
		if default:
			cfact.merge_test(default, "final")
	elif arguments == "request snmp-test":
		console(" - request snmp-test <ip-address>                 |  Run a SNMP test using the configured community and OID against an IP")
	elif arguments[:18] == "request merge-test" and len(sys.argv) >= 4:
		cfact.merge_test(sys.argv[3], "final")
	elif arguments[:17] == "request snmp-test" and len(sys.argv) >= 4:
		community = config.running["community"]
		oid = config.running["snmpoid"]
		console("\n\nHit CTRL+C to kill the SNMP query test")
		console("\nQuerying %s using community (%s) and OID (%s)\n" % (sys.argv[3], community, oid))
		query = snmp_query(sys.argv[3], community, oid)
		while query.thread.isAlive():
			time.sleep(3)
	##### SERVICE #####
	elif arguments == "service":
		console(" - service (start|stop|restart|status)            |  Start, Stop, or Restart the installed ZTP service")
	elif arguments == "service start":
		log("#########################################################")
		log("Starting the ZTP Service")
		os.system('systemctl start ztp')
		os.system('systemctl status ztp')
		log("#########################################################")
	elif arguments == "service stop":
		log("#########################################################")
		log("Stopping the ZTP Service")
		os.system('systemctl stop ztp')
		os.system('systemctl status ztp')
		log("#########################################################")
	elif arguments == "service restart":
		log("#########################################################")
		log("Restarting the ZTP Service")
		os.system('systemctl restart ztp')
		os.system('systemctl status ztp')
		log("#########################################################")
	elif arguments == "service status":
		os.system('systemctl status ztp')
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
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console("--------------------------------------------------- SETTINGS YOU PROBABLY SHOULDN'T CHANGE ---------------------------------------------------")
		console(" - set suffix <value>                                          |  Set the file name suffix used by target when requesting the final config")
		console(" - set initialfilename <value>                                 |  Set the file name used by the target during the initial config request")
		console(" - set community <value>                                       |  Set the SNMP community you want to use for target ID identification")
		console(" - set snmpoid <value>                                         |  Set the SNMP OID to use to pull the target ID during identification")
		console(" - set initial-template <end_char>                             |  Set the initial configuration j2 template used for target identification")
		console("--------------------------------------------------------- SETTINGS YOU SHOULD CHANGE ---------------------------------------------------------")
		console(" - set template <template_name> <end_char>                     |  Create/Modify a named J2 tempate which is used for the final config push")
		console(" - set keystore <id/arrayname> <keyword> <value>               |  Create a keystore entry to be used when merging final configurations")
		console(" - set idarray <arrayname> <id_#1> <id_#2> ...                 |  Create an ID array to allow multiple real ids to match one keystore id")
		console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
		console(" - set default-keystore (none|keystore-id)                     |  Set a last-resort keystore and template for when target identification fails")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - clear template <template_name>                              |  Delete a named configuration template")
		console(" - clear keystore <id> (all|<keyword>)                         |  Delete an individual key or a whole keystore ID from the configuration")
		console(" - clear idarray <arrayname>                                   |  Delete an ID array from the configuration")
		console(" - clear association <id/arrayname>                            |  Delete an association from the configuration")
		console(" - clear log                                                   |  Delete the logging info from the logfile")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - request merge-test <id>                                     |  Perform a test jinja2 merge of the final template with a keystore ID")
		console(" - request initial-merge                                       |  See the result of an auto-merge of the initial-template")
		console(" - request default-keystore-test                               |  Check that the default-keystore is fully configured to return a template")
		console(" - request snmp-test <ip-address>                              |  Run a SNMP test using the configured community and OID against an IP")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - service (start|stop|restart|status)                         |  Start, Stop, or Restart the installed ZTP service")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")
		console(" - version                                                     |  Show the current version of ZTP")
		console("----------------------------------------------------------------------------------------------------------------------------------------------")


if __name__ == "__main__":
	interpreter()