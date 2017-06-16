


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
			tempid = generate_name()
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



config = config_factory()
# config.request("network-confg", "10.0.0.101")



#################################################################
#################################################################
#################################################################







"""
Create a unique temporary name for the device while the 
	device-specific info is discovered.
"""
import time

def generate_name():
	timeint = int(str(time.time()).replace(".", ""))
	timehex = hex(timeint)
	hname = timehex[2:12].upper()
	return("ZTP-"+hname)











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





"""
Query a device with SNMP for a OID using a community
"""
import pysnmp.hlapi

def get_oid(host, community, oid):
	errorIndication, errorStatus, errorIndex, varBinds = next(
		pysnmp.hlapi.getCmd(pysnmp.hlapi.SnmpEngine(),
			   pysnmp.hlapi.CommunityData(community, mpModel=0),
			   pysnmp.hlapi.UdpTransportTarget((host, 161)),
			   pysnmp.hlapi.ContextData(),
			   pysnmp.hlapi.ObjectType(pysnmp.hlapi.ObjectIdentity(oid)))
	)
	return varBinds
	#return str(varBinds[0][1])



if __name__ == "__main__":
	start_tftp()
	config = config_factory()
	

