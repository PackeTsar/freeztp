#!/usr/bin/python

'''
To Do:
	- Build installer (run as service)
	- Build service control
	- Build autocomplete
	- Build logging system

Bugs:
	- If an ID is created in the keystore, then all keys cleared from it, the ID remains in the JSON config but nothing will show in the "show config"

NEXT: Get app to find config file in /etc/ztp or local
'''


try:
	import jinja2 as j2
	import pysnmp.hlapi
	import tftpy
except ImportError:
	print("Had some import errors, may not have dependencies installed yet")




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

#################################################################
#################################################################
#################################################################

import time


class config_factory:
	def __init__(self):
		self.state = {}
		self.snmprequests = {}
		self.basefilename = config.running["startfilename"]
		self.basesnmpcom = config.running["startsnmpcommunity"]
		self.snmpoid = config.running["startsnmpoid"]
		self.baseconfig = config.running["starttemplate"]
		self.uniquesuffix = config.running["finalsuffix"]
		self.finaltemplate = config.running["finaltemplate"]
		self.keyvalstore = config.running["keyvalstore"]
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
		print(self.snmprequests)
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

import time
import threading

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
		self.thread.daemon = False
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


import os
import json
import commands

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
			self.finalsuffix = self.running["finalsuffix"]
			self.finaltemplate = self.running["finaltemplate"]
			self.keyvalstore = self.running["keyvalstore"]
			self.startfilename = self.running["startfilename"]
			self.startsnmpcommunity = self.running["startsnmpcommunity"]
			self.startsnmpoid = self.running["startsnmpoid"]
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
	def hidden_list_ids(self):
		for iden in list(self.running["keyvalstore"]):
			print(iden)
	def hidden_list_keys(self, iden):
		try:
			for key in list(self.running["keyvalstore"][iden]):
				print(key)
		except KeyError:
			pass
			


import os
import json
class installer:
	defaultconfig = '''{\n    "finalsuffix": "-confg", \n    "finaltemplate": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} 255.255.255.0\\n no shut\\n!\\nip domain-name test.com\\n!\\nusername admin privilege 15 secret password123\\n!\\naaa new-model\\n!\\n!\\naaa authentication login CONSOLE local\\naaa authorization console\\naaa authorization exec default local if-authenticated\\n!\\ncrypto key generate rsa modulus 2048\\n!\\nip ssh version 2\\n!\\nline vty 0 15\\nlogin authentication default\\ntransport input ssh\\nline console 0\\nlogin authentication CONSOLE\\nend", \n    "keyvalstore": {\n        "FCW2039D0P7": {\n            "hostname": "3850CORE", \n            "vl1_ip_address": "10.0.0.200"\n        }, \n        "NEWID": {}\n    }, \n    "startfilename": "network-confg", \n    "startsnmpcommunity": "secretcommunity", \n    "startsnmpoid": "1.3.6.1.2.1.47.1.1.1.1.11.1000", \n    "starttemplate": "hostname {{ hostname }}\\n!\\nsnmp-server community {{ basesnmpcom }} RO\\n!\\nend"\n}'''
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
    COMPREPLY=( $(compgen -W "run install show set clear service version" -- $cur) )
  elif [ $COMP_CWORD -eq 2 ]; then
    case "$prev" in
      show)
        COMPREPLY=( $(compgen -W "config" -- $cur) )
        ;;
      "set")
        COMPREPLY=( $(compgen -W "finalsuffix startfilename startsnmpcommunity startsnmpoid initial-template final-template keystore" -- $cur) )
        ;;
      "clear")
        COMPREPLY=( $(compgen -W "keystore" -- $cur) )
        ;;
      "service")
        COMPREPLY=( $(compgen -W "start stop restart status" -- $cur) )
        ;;
      *)
        ;;
    esac
  elif [ $COMP_CWORD -eq 3 ]; then
    case "$prev" in
      finalsuffix)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
        fi
        ;;
      startfilename)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
        fi
        ;;
      startsnmpcommunity)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
        fi
        ;;
      startsnmpoid)
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
          COMPREPLY=( $(compgen -W "${ids} <new_device_id> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
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
        COMPREPLY=( $(compgen -W "${idkeys} <new_key>" -- $cur) )
      fi
      if [ "$prev3" == "clear" ]; then
        COMPREPLY=( $(compgen -W "${idkeys} all" -- $cur) )
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













































import sys

def cat_list(listname):
	result = ""
	counter = 0
	for word in listname:
		result = result + listname[counter].lower() + " "
		counter = counter + 1
	result = result[:len(result) - 1:]
	return result


"""
Fire up the TFTP server referencing the dyn_file_func class
for dynamic file creations
"""

import logging

def start_tftp():
	tftpy.setLogLevel(logging.DEBUG)
	server = tftpy.TftpServer("/", dyn_file_func=ztp_dyn_file)
	server.listen(listenip="", listenport=69)


def interpreter():
	arguments = cat_list(sys.argv[1:])
	global config
	global cfact
	config = config_manager()
	cfact = config_factory()
	##### RUN #####
	if arguments == "run":
		start_tftp()
		config = config_factory()
	##### TEST #####
	if arguments == "test":
		ztp = ztp_dyn_file("network-confg", "10.0.0.101", 65000)
		print(ztp.read(10000))
	##### INSTALL #####
	elif arguments == "install":
		inst = installer()
		inst.copy_binary()
		inst.create_configfile()
		inst.install_completion()
		inst.install_tftpy()
		inst.disable_firewall()
		inst.install_dependencies()
		inst.create_service()
		print("Install complete! Logout and log back into SSH to activate auto-complete")
	##### SHOW #####
	elif arguments == "show ids":
		config.hidden_list_ids()
	elif arguments[:9] == "show keys" and len(sys.argv) >= 4:
		config.hidden_list_keys(sys.argv[3])
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
	##### SERVICE #####
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
		print " - service (start|stop|restart|status)            |  Start, Stop, or Restart the installed ZTP service"
		print "-------------------------------------------------------------------------------------------------------------------------------"
		print " - version                                        |  Show the current version of ZTP"
		print "-------------------------------------------------------------------------------------------------------------------------------"










if __name__ == "__main__":
	interpreter()


