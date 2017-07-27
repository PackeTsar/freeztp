#!/usr/bin/python


#####         FreeZTP Server v0.1.0          #####
#####        Written by John W Kerns         #####
#####       http://blog.packetsar.com        #####
##### https://github.com/convergeone/freeztp #####


##### Inform FreeZTP version here #####
version = "v0.1.0"


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
	if cfact.lookup(afile, raddress):
		return ztp_dyn_file(afile, raddress, rport)
	else:
		return None

##### Dynamic file object: instantiated by the tftpy server to generate   #####
#####   TFTP files                                                        #####
class ztp_dyn_file:
	closed = False
	def __init__(self, afile, raddress, rport):
		self.data = cfact.request(afile, raddress)
		pass
	def tell(self):
		return len(self.data)
	def read(self, size):
		return str(self.data[0:size])
	def seek(self, arg1, arg2):
		pass
	def close(self):
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
		self.finaltemplate = config.running["finaltemplate"]
		self.keyvalstore = config.running["keyvalstore"]
	def lookup(self, filename, ipaddr):
		tempid = filename.replace(self.uniquesuffix, "")
		if filename == self.basefilename:
			return True
		elif self.uniquesuffix in filename and tempid in list(self.snmprequests):
			if self.snmprequests[tempid].complete:
				if self.id_configured(self.snmprequests[tempid].response):
					return True
		if "ztp-" in tempid.lower():
			print("Creating new SNMP request for %s: %s" % (str(tempid), str(ipaddr)))
			self.create_snmp_request(tempid, ipaddr)
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
		if filename == self.basefilename:
			tempid = self._generate_name()
			self.create_snmp_request(tempid, ipaddr)
			return self.merge_base_config(tempid)
		else:
			tempid = filename.replace(self.uniquesuffix, "")
			if self.uniquesuffix in filename and tempid in list(self.snmprequests):
				if self.snmprequests[tempid].complete:
					print("SUCCESS!!!!!")
					return self.merge_final_config(tempid)
				else:
					print("ERRORRRRRR!!!!!!!")
			else:
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
	def merge_final_config(self, tempid):
		template = j2.Template(self.finaltemplate)
		identifier = self.snmprequests[tempid].response
		keystoreid = self.get_keystore_id(identifier)
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
					print("ID '%s' resolved to arrayname '%s'" % (iden, identity))
					break
			return identity
	def merge_test(self, iden, template):
		env = Environment()
		if template == "final":
			j2template = j2.Template(self.finaltemplate)
			ast = env.parse(self.finaltemplate)
		elif template == "initial":
			j2template = j2.Template(self.baseconfig)
			ast = env.parse(self.finaltemplate)
		identity = self.get_keystore_id(iden)
		if not identity:
			print("ID '%s' does not exist in keystore!" % iden)
		else:
			templatevarlist = list(meta.find_undeclared_variables(ast))
			varsmissing = False
			missingvarlist = []
			for var in templatevarlist:
				if var not in config.running["keyvalstore"][identity]:
					varsmissing = True
					missingvarlist.append(var)
			if varsmissing:
				print("\nSome variables in jinja template do not exist in keystore:")
				for var in missingvarlist:
					print("\t-"+var)
				print("\n")
			print("##############################")
			print(j2template.render(config.running["keyvalstore"][identity]))
			print("##############################")


##### SNMP Querying object: It is instantiated by the config_factory      #####
#####   when the initial template is pulled down. A thread is             #####
#####   spawned which continuously tries to query the ID of the           #####
#####   switch. Once successfully queried, the querying object            #####
#####   retains the real ID of the switch which is mapped to a            #####
#####   keystore ID when the final template is requested                  #####
class snmp_query:
	def __init__(self, host, community, oid, timeout=10):
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
			self.finaltemplate = self.running["finaltemplate"]
			self.keyvalstore = self.running["keyvalstore"]
			self.initialfilename = self.running["initialfilename"]
			self.community = self.running["community"]
			self.snmpoid = self.running["snmpoid"]
			self.starttemplate = self.running["starttemplate"]
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
		elif setting == "idarray":
			self.set_idarray(value, args[4:])
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
						if self.running["keyvalstore"][iden] == {}: # No keys left
							del self.running["keyvalstore"][iden]
		elif setting == "idarray":
			iden = args[3]
			if iden not in list(self.running["idarrays"]):
				print("ID does not exist in the idarrays: %s" % iden)
			else:
				del self.running["idarrays"][iden]
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
	def show_config(self):
		cmdlist = []
		simplevals = ["suffix", "initialfilename", "community", "snmpoid"]
		for each in simplevals:
			cmdlist.append("ztp set %s %s" % (each, self.running[each]))
		itemp = "ztp set initial-template ^\n%s\n^" % self.running["starttemplate"]
		ftemp = "ztp set final-template ^\n%s\n^" % self.running["finaltemplate"]
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
		configtext = "!\n"
		for cmd in cmdlist:
			configtext += cmd + "\n"
		configtext += "!\n!\n!\n"
		for cmd in idarraylist:
			configtext += cmd + "\n!\n"
		configtext += "!\n!\n!\n"
		for cmd in keylist:
			configtext += cmd + "\n"
		###########
		configtext += "!\n#######################################################\n"
		configtext += itemp
		configtext += "\n!\n!\n!\n#######################################################\n"
		configtext += ftemp
		print(configtext)
	def hidden_list_ids(self):
		for iden in list(self.running["keyvalstore"]):
			print(iden)
	def hidden_list_keys(self, iden):
		try:
			for key in list(self.running["keyvalstore"][iden]):
				print(key)
		except KeyError:
			pass
	def hidden_list_arrays(self):
		for arrayname in list(self.running["idarrays"]):
			print(arrayname)


##### Installer class: A simple holder class which contains all of the    #####
#####   installation scripts used to install/upgrade the ZTP server       #####
class installer:
	defaultconfig = '''{\n    "suffix": "-confg", \n    "finaltemplate": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} 255.255.255.0\\n no shut\\n!\\nip domain-name test.com\\n!\\nusername admin privilege 15 secret password123\\n!\\naaa new-model\\n!\\n!\\naaa authentication login CONSOLE local\\naaa authorization console\\naaa authorization exec default local if-authenticated\\n!\\ncrypto key generate rsa modulus 2048\\n!\\nip ssh version 2\\n!\\nline vty 0 15\\nlogin authentication default\\ntransport input ssh\\nline console 0\\nlogin authentication CONSOLE\\nend", \n    "idarrays": {\n        "STACK1": [\n            "SERIAL1", \n            "SERIAL2", \n            "SERIAL3"\n        ]\n    }, \n    "keyvalstore": {\n        "SERIAL100": {\n            "hostname": "ACCESSSWITCH", \n            "vl1_ip_address": "10.0.0.201"\n        }, \n        "STACK1": {\n            "hostname": "CORESWITCH", \n            "vl1_ip_address": "10.0.0.200"\n        }\n    }, \n    "initialfilename": "network-confg", \n    "community": "secretcommunity", \n    "snmpoid": "1.3.6.1.2.1.47.1.1.1.1.11.1000", \n    "starttemplate": "hostname {{ autohostname }}\\n!\\nsnmp-server community {{ community }} RO\\n!\\nend"\n}'''
	def copy_binary(self):
		binpath = "/bin/"
		binname = "ztp"
		os.system('cp ztp.py ' + binpath + binname)
		os.system('chmod 777 ' + binpath + binname)
		print("Binary file installed at " + binpath + binname)
	def create_configfile(self):
		config = json.loads(self.defaultconfig)
		rawconfig = json.dumps(config, indent=4, sort_keys=True)
		configfilepath = "/etc/ztp/"
		configfilename = "ztp.cfg"
		os.system('mkdir -p ' + configfilepath)
		f = open(configfilepath + configfilename, "w")
		f.write(rawconfig)
		f.close()
		print("Config File Created at " + configfilepath + configfilename)
	def install_tftpy(self):
		print("Downloading tftpy library from https://github.com/PackeTsar/tftpy/archive/master.tar.gz...")
		os.system("curl -OL https://github.com/PackeTsar/tftpy/archive/master.tar.gz")
		print("Installing tftpy library...")
		os.system("tar -xzf master.tar.gz")
		os.system("cp -r tftpy-master/tftpy/ /usr/lib/python2.7/site-packages/")
		os.system("rm -rf tftpy-master")
		os.system("rm -rf master.tar.gz")
		print("Tftpy library installed")
	def disable_firewall(self):
		os.system("systemctl stop firewalld")
		os.system("systemctl disable firewalld")
		print("Firewalld stopped and disabled")
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
		print("ZTP service installed at /etc/systemd/system/ztp.service")
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
    COMPREPLY=( $(compgen -W "run install show set clear request service version" -- $cur) )
  elif [ $COMP_CWORD -eq 2 ]; then
    case "$prev" in
      show)
        COMPREPLY=( $(compgen -W "config run status version" -- $cur) )
        ;;
      "set")
        COMPREPLY=( $(compgen -W "suffix initialfilename community snmpoid initial-template final-template keystore idarray" -- $cur) )
        ;;
      "clear")
        COMPREPLY=( $(compgen -W "keystore idarray" -- $cur) )
        ;;
      "request")
        COMPREPLY=( $(compgen -W "merge-test initial-merge" -- $cur) )
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
      final-template)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "<deliniation_character> -" -- $cur) )
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
      merge-test)
        local ids=$(for id in `ztp show ids`; do echo $id ; done)
        if [ "$prev2" == "request" ]; then
          COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
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
        COMPREPLY=( $(compgen -W "<id's_seperated_by_spaces> -" -- $cur) )
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
		print("Auto-complete script installed to /etc/profile.d/ztp-complete.sh")





"""
Fire up the TFTP server referencing the dyn_file_func class
for dynamic file creations
"""


##### TFTP Server main entry. Starts the TFTP server listener and is the  #####
#####   main program loop. It is started with the ztp_dyn_file class      #####
#####   passed in as the dynamic file function.                           #####
def start_tftp():
	tftpy.setLogLevel(logging.DEBUG)
	server = tftpy.TftpServer("/", dyn_file_func=interceptor)
	server.listen(listenip="", listenport=69)


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
	config = config_manager()
	try:
		cfact = config_factory()
	except AttributeError:
		print("Cannot mount cfact")
	##### RUN #####
	if arguments == "run":
		start_tftp()
		config = config_factory()
	##### INSTALL #####
	elif arguments == "install":
		print("***** Are you sure you want to install/upgrade FreeZTP using version %s?*****" % version)
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
			print("Install complete! Logout and log back into SSH to activate auto-complete")
		else:
			print("Install/upgrade cancelled")
	##### HIDDEN SHOW #####
	elif arguments == "show ids":
		config.hidden_list_ids()
	elif arguments[:9] == "show keys" and len(sys.argv) >= 4:
		config.hidden_list_keys(sys.argv[3])
	elif arguments == "show arrays":
		config.hidden_list_arrays()
	##### SHOW #####
	elif arguments == "show":
		print " - show (config|run)                              |  Show the current ZTP configuration"
		print " - show status                                    |  Show the status of the ZTP background service"
		print " - show version                                   |  Show the current version of ZTP"
	elif arguments == "show config" or arguments == "show run":
		config.show_config()
	elif arguments == "show status":
		os.system('systemctl status ztp')
	elif arguments == "show version":
		print("FreeZTP %s" % version)
	##### SET #####
	elif arguments == "set":
		print " - set suffix <value>                             |  Set the file name suffix used by target when requesting the final config"
		print " - set initialfilename <value>                      |  Set the file name used by the target during the initial config request"
		print " - set community <value>                          |  Set the SNMP community you want to use for target ID identification"
		print " - set snmpoid <value>                            |  Set the SNMP OID to use to pull the target ID during identification"
		print " - set initial-template <end_char>                |  Set the initial configuration j2 template used to prep target for identification"
		print " - set final-template <end_char>                  |  Set the final configuration j2 template pushed to host after discovery/identification"
		print " - set keystore <id/arrayname> <keyword> <value>  |  Create a keystore entry to be used when merging final configurations"
		print " - set idarray <arrayname> <id's>                 |  Create an ID array to allow multiple real ids to match one keystore id"
	elif arguments == "set suffix":
		print " - set suffix <value>                             |  Set the file name suffix used by target when requesting the final config"
	elif arguments == "set initialfilename":
		print " - set initialfilename <value>                    |  Set the file name used by the target during the initial config request"
	elif arguments == "set community":
		print " - set community <value>                          |  Set the SNMP community you want to use for target ID identification"
	elif arguments == "set snmpoid":
		print " - set snmpoid <value>                            |  Set the SNMP OID to use to pull the target ID during identification"
	elif arguments == "set initial-template":
		print " - set initial-template <end_char>                |  Set the initial configuration j2 template used to prep target for identification"
	elif arguments == "set final-template":
		print " - set final-template <end_char>                  |  Set the final configuration j2 template pushed to host after discovery/identification"
	elif (arguments[:12] == "set keystore" and len(sys.argv) < 6) or arguments == "set keystore":
		print " - set keystore <id/arrayname> <keyword> <value>  |  Create a keystore entry to be used when merging final configurations"
	elif (arguments[:11] == "set idarray" and len(sys.argv) < 5) or arguments == "set idarray":
		print " - set idarray <arrayname> <id_#1> <id_#2> ...    |  Create an ID array to allow multiple real ids to match one keystore id"
	elif arguments[:3] == "set" and len(sys.argv) >= 4:
		config.set(sys.argv)
	##### CLEAR #####
	elif arguments == "clear":
		print " - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration"
		print " - clear idarray <arrayname>                      |  Delete an ID array from the configuration"
	elif (arguments[:14] == "clear keystore" and len(sys.argv) < 5) or arguments == "clear keystore":
		print " - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration"
	elif (arguments[:13] == "clear idarray" and len(sys.argv) < 4) or arguments == "clear idarray":
		print " - clear idarray <arrayname>                      |  Delete an ID array from the configuration"
	elif arguments[:14] == "clear keystore" and len(sys.argv) >= 5:
		config.clear(sys.argv)
	elif arguments[:13] == "clear idarray" and len(sys.argv) >= 4:
		config.clear(sys.argv)
	##### REQUEST #####
	elif arguments == "request":
		print " - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID"
		print " - request initial-merge                          |  See the result of an auto-merge of the initial-template"
	elif arguments == "request merge-test":
		print " - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID"
	elif arguments == "request initial-merge":
		print(cfact.request(config.running["initialfilename"], "10.0.0.1"))
	elif arguments[:18] == "request merge-test" and len(sys.argv) >= 4:
		cfact.merge_test(sys.argv[3], "final")
	##### SERVICE #####
	elif arguments == "service":
		print " - service (start|stop|restart|status)            |  Start, Stop, or Restart the installed ZTP service"
	elif arguments == "service start":
		os.system('systemctl start ztp')
		os.system('systemctl status ztp')
	elif arguments == "service stop":
		os.system('systemctl stop ztp')
		os.system('systemctl status ztp')
	elif arguments == "service restart":
		os.system('systemctl restart ztp')
		os.system('systemctl status ztp')
	elif arguments == "service status":
		os.system('systemctl status ztp')
	##### VERSION #####
	elif arguments == "version":
		print("FreeZTP %s" % version)
	else:
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print "                     ARGUMENTS                    |                                  DESCRIPTIONS"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - run                                            |  Run the ZTP main program in shell mode begin listening for TFTP requests"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - install                                        |  Run the ZTP installer"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - show (config|run)                              |  Show the current ZTP configuration"
		print " - show status                                    |  Show the status of the ZTP background service"
		print " - show version                                   |  Show the current version of ZTP"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - set suffix <value>                             |  Set the file name suffix used by target when requesting the final config"
		print " - set initialfilename <value>                    |  Set the file name used by the target during the initial config request"
		print " - set community <value>                          |  Set the SNMP community you want to use for target ID identification"
		print " - set snmpoid <value>                            |  Set the SNMP OID to use to pull the target ID during identification"
		print "------------------------------------------------"
		print " - set initial-template <end_char>                |  Set the initial configuration j2 template used to prep target for identification"
		print " - set final-template <end_char>                  |  Set the final configuration j2 template pushed to host after discovery/identification"
		print "------------------------------------------------"
		print " - set keystore <id/arrayname> <keyword> <value>  |  Create a keystore entry to be used when merging final configurations"
		print " - set idarray <arrayname> <id_#1> <id_#2> ...    |  Create an ID array to allow multiple real ids to match one keystore id"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration"
		print " - clear idarray <arrayname>                      |  Delete an ID array from the configuration"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID"
		print " - request initial-merge                          |  See the result of an auto-merge of the initial-template"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - service (start|stop|restart|status)            |  Start, Stop, or Restart the installed ZTP service"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - version                                        |  Show the current version of ZTP"
		print "-------------------------------------------------------------------------------------------------------------------------------"


if __name__ == "__main__":
	interpreter()