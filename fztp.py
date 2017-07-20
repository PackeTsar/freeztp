#!/usr/bin/python

'''
To Do:
	- Build installer (run as service)
	- Build service control
	- Build autocomplete




NEXT: Get app to find config file in /etc/ztp or local



'''

configfile = "fztp.cfg"

class ztp_dyn_file:
	closed = False
	def __init__(self, afile, raddress, rport):
		self.data = config.request(afile, raddress)
		pass
	def tell(self):
		return len(self.data)
	def read(self, size):
		return str(self.data[0:size])
	def seek(self, arg1, arg2):
		pass
	def close(self):
		self.closed = True


"""
Fire up the TFTP server referencing the dyn_file_func class
for dynamic file creations
"""
import tftpy
import logging

def start_tftp():
	tftpy.setLogLevel(logging.DEBUG)
	server = tftpy.TftpServer("/", dyn_file_func=ztp_dyn_file)
	server.listen(listenip="", listenport=69)


#################################################################
#################################################################
#################################################################

import time
import jinja2 as j2

class config_factory:
	def __init__(self):
		self.state = {}
		self.snmprequests = {}
		self.basefilename = basefilename
		self.basesnmpcom = basesnmpcom
		self.snmpoid = snmpoid
		self.baseconfig = baseconfig
		self.uniquesuffix = uniquesuffix
		self.finaltemplate = finaltemplate
		self.keyvalstore = keyvalstore
	def request(self, filename, ipaddr):
		if filename == self.basefilename:
			tempid = self._generate_name()
			self.create_snmp_request(tempid, ipaddr)
			return self.merge_base_config(tempid)
		else:
			tempid = filename.replace(self.uniquesuffix, "")
			if self.snmprequests[tempid].complete:
				print("SUCCESS!!!!!")
				return self.merge_final_config(tempid)
			else:
				print("ERRORRRRRR!!!!!!!")
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
		return template.render(hostname=tempid, basesnmpcom=self.basesnmpcom)
	def merge_final_config(self, tempid):
		template = j2.Template(self.finaltemplate)
		identifier = self.snmprequests[tempid].response
		vals = self.keyvalstore[identifier]
		return template.render(vals)



# # Jinja Example
#import jinja2 as j2
#template = j2.Template('Hello {{ name }}!')
#template.render(name='John Doe')



#config = config_factory()
# config.request("network-confg", "10.0.0.101")



#################################################################
#################################################################
#################################################################







"""
Create a unique temporary name for the device while the 
	device-specific info is discovered.
"""
import time













import time
import threading
import pysnmp.hlapi

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
				print("snmp_query._query_worker: Attempting SNMP Query")
				response = self._get_oid()
				self.response = response
				self.status = "success"
				self.complete = True
				print("snmp_query._query_worker: SNMP Query Successful")
			except IndexError:
				self.status = "retrying"
				print("snmp_query._query_worker: SNMP Query Timed Out")
			if (time.time() - starttime) > self.timeout:
				self.status = "failed"
				print("snmp_query._query_worker: Timeout Expired, Query Thread Terminating")
				break
			else:
				time.sleep(5)
	def _get_oid(self):
		errorIndication, errorStatus, errorIndex, varBinds = next(
			pysnmp.hlapi.getCmd(pysnmp.hlapi.SnmpEngine(),
				   pysnmp.hlapi.CommunityData(self.community, mpModel=0),
				   pysnmp.hlapi.UdpTransportTarget((self.host, 161)),
				   pysnmp.hlapi.ContextData(),
				   pysnmp.hlapi.ObjectType(pysnmp.hlapi.ObjectIdentity(self.oid)))
		)
		return str(varBinds[0][1])


#host = "10.0.0.101"
#community = "Sigma4290"
#oid = '1.3.6.1.2.1.47.1.1.1.1.11.1000'
#snmp = snmp_query(host, community, oid)

import json
import commands

class config_manager:
	def __init__(self):
		self._publish()
	def _find_config(self):
		pass
	def _file_exists(self, filepath):
		checkdata = commands.getstatusoutput("ls " + filepath)
		exists = True
		for line in checkdata:
			line = str(line)
			if "No such" in line:
				exists = False
		return exists
	def _publish(self):
		if self._file_exists(configfile):
			f = open(configfile, "r")
			self.rawconfig = f.read()
			f.close()
			self.running = json.loads(self.rawconfig)
			self.finalsuffix = self.running["finalsuffix"]
			self.finaltemplate = self.running["finaltemplate"]
			self.keyvalstore = self.running["keyvalstore"]
			self.startfilename = self.running["startfilename"]
			self.startsnmpcommunity = self.running["startsnmpcommunity"]
			self.startsnmpoid = self.running["startsnmpoid"]
			self.starttemplate = self.running["starttemplate"]
		else:
			print("No Config!")
	def save(self):
		self.rawconfig = self.json = json.dumps(self.running, indent=4, sort_keys=True)
		f = open(configfile, "w")
		self.rawconfig = f.write(self.rawconfig)
		f.close()
	def set(self, args):
		setting = args[2]
		value = args[3]
		exceptions = ["finaltemplate", "keyvalstore", "starttemplate"]
		if setting in exceptions:
			print("Cannot configure this way")
		elif "template" in setting:
			print("Enter each line of the template ending with '%s' on a line by itself" % value)
			newinitial = self.multilineinput(value)
			if setting == "initial-template":
				self.running["starttemplate"] = newinitial
			elif setting == "final-template":
				self.running["finaltemplate"] = newinitial
			self.save()
		elif setting == "keystore":
			self.set_keystore(args[3], args[4], args[5] )
		else:
			if setting in list(self.running):
				self.running[setting] = value
				self.save()
			else:
				print("Unknown Setting!")
	def clear(self, args):
		setting = args[2]
		if setting == "keystore":
			iden = args[3]
			key = args[4]
			if iden not in list(self.running["keyvalstore"]):
				print("ID does not exist in keystore: %s" % iden)
			else:
				if key == "all":
					del self.running["keyvalstore"][iden]
				else:
					if key not in list(self.running["keyvalstore"][iden]):
						print("Key does not exist under ID %s: %s" % (iden, key))
					else:
						del self.running["keyvalstore"][iden][key]
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
	def show_config(self):
		cmdlist = []
		simplevals = ["finalsuffix", "startfilename", "startsnmpcommunity", "startsnmpoid"]
		for each in simplevals:
			cmdlist.append("ztp set %s %s" % (each, self.running[each]))
		itemp = "ztp set initial-template ^\n%s\n^" % self.running["starttemplate"]
		ftemp = "ztp set final-template ^\n%s\n^" % self.running["finaltemplate"]
		keylist = []
		for iden in self.running["keyvalstore"]:
			for key in self.running["keyvalstore"][iden]:
				value = self.running["keyvalstore"][iden][key]
				keylist.append("ztp set keystore %s %s %s" % (iden, key, value))
		config = "!\n!\n!\n"
		for cmd in cmdlist:
			config += cmd + "\n!\n"
		config += "!\n!\n!\n"
		for cmd in keylist:
			config += cmd + "\n!\n"
		config += "\n#######################################################\n"
		config += itemp
		config += "\n#######################################################\n"
		config += ftemp
		print(config)

import sys

def cat_list(listname):
	result = ""
	counter = 0
	for word in listname:
		result = result + listname[counter].lower() + " "
		counter = counter + 1
	result = result[:len(result) - 1:]
	return result


def interpreter():
	arguments = cat_list(sys.argv[1:])
	config = config_manager()
	if arguments == "run":
		start_tftp()
		config = config_factory()
	##### SHOW #####
	elif arguments == "show initial-template":
		print(config.running["starttemplate"])
	elif arguments == "show final-template":
		print(config.running["finaltemplate"])
	elif arguments == "show config":
		config.show_config()
	##### SET #####
	elif arguments == "set":
		print " - set finalsuffix <value>                        |  Set the file name suffix used by target when requesting the final config"
		print " - set startfilename <value>                      |  Set the file name used by the target during the initial config request"
		print " - set startsnmpcommunity <value>                 |  Set the SNMP community you want to use for target ID identification"
		print " - set startsnmpoid <value>                       |  Set the SNMP OID to use to pull the target ID during identification"
		print " - set initial-template (<end char>)              |  Set the initial configuration j2 template used to prep target for identification"
		print " - set final-template (<end char>)                |  Set the final configuration j2 template pushed to host after discovery/identification"
		print " - set keystore <id> <keyword> <value>            |  Set the final configuration template pushed to host after discovery/identification"
	elif arguments == "set finalsuffix":
		print " - set finalsuffix <value>                        |  Set the file name suffix used by target when requesting the final config"
	elif arguments == "set startfilename":
		print " - set startfilename <value>                      |  Set the file name used by the target during the initial config request"
	elif arguments == "set startsnmpcommunity":
		print " - set startsnmpcommunity <value>                 |  Set the SNMP community you want to use for target ID identification"
	elif arguments == "set startsnmpoid":
		print " - set startsnmpoid <value>                       |  Set the SNMP OID to use to pull the target ID during identification"
	elif arguments[:3] == "set" and len(sys.argv) >= 4:
		config.set(sys.argv)
	##### CLEAR #####
	elif arguments == "clear":
		print " - clear keystore <id> (all|<keyword>)            |  Delete information from the keystore"
	elif arguments[:14] == "clear keystore" and len(sys.argv) >= 5:
		config.clear(sys.argv)
	else:
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print "                     ARGUMENTS                    |                                  DESCRIPTIONS"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - run                                            |  Run the ZTP main program in shell mode begin listening for TFTP requests"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - install                                        |  Run the ZTP installer"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - show config                                    |  Show the current ZTP configuration"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - set finalsuffix <value>                        |  Set the file name suffix used by target when requesting the final config"
		print " - set startfilename <value>                      |  Set the file name used by the target during the initial config request"
		print " - set startsnmpcommunity <value>                 |  Set the SNMP community you want to use for target ID identification"
		print " - set startsnmpoid <value>                       |  Set the SNMP OID to use to pull the target ID during identification"
		print "------------------------------------------------"
		print " - set initial-template (<end char>)              |  Set the initial configuration j2 template used to prep target for identification"
		print " - set final-template (<end char>)                |  Set the final configuration j2 template pushed to host after discovery/identification"
		print "------------------------------------------------"
		print " - set keystore <id> <keyword> <value>            |  Set the final configuration template pushed to host after discovery/identification"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - clear keystore <id> (all|<keyword>)            |  Delete information from the keystore"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - version                                        |  Show the current version of ZTP"
		print "-------------------------------------------------------------------------------------------------------------------------------"










if __name__ == "__main__":
	interpreter()


