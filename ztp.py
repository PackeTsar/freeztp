#!/usr/bin/python
# Globally disabled linting warnings
# pylint: disable=line-too-long
# pylint: disable=missing-docstring
# pylint: disable=invalid-name
# pylint: disable=global-statement
# pylint: disable=global-variable-undefined
# pylint: disable=too-many-lines
# pylint: disable=too-many-statements
# pylint: disable=too-many-instance-attributes
# pylint: disable=consider-using-join
# pylint: disable=consider-using-in
"""
#####             FreeZTP Server             #####
#####        Written by John W Kerns         #####
#####       http://blog.packetsar.com        #####
#####  https://github.com/packetsar/freeztp  #####
"""

##### Import native modules #####
import asyncio
import os
import re
import sys
import csv
import time
import json
import curses
import socket
import platform
import subprocess
import threading

version = "v1.6.0"

class os_detect:
    def __init__(self):
        self._dist = self._dist_detect()
        self._systemd = self._systemd_detect()
        self._pkgmgr = self._pkgmgr_detect()
        self._make_names()

    def _systemd_detect(self):
        params = {
            "capture_output": True,
            "text": True,
            "timeout": 10
        }
        try:
            _ = subprocess.run("systemctl", **params, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        return True

    def _pkgmgr_detect(self):
        checkpkgmgr = {}
        # checknames = ["yum", "apt", "apt-get"]
        checknames = ["apt"]
        params = {
            "capture_output": True,
            "text": True,
            "timeout": 10
        }
        for mgr in checknames:
            try:
                result = subprocess.run(mgr, **params, check=False)
            except FileNotFoundError:
                continue
            checkpkgmgr[len(result.stdout)] = mgr

        # PSC - Select item with longest output?? Obscure. Difficult to interpret.
        pkgmgr = checkpkgmgr[sorted(list(checkpkgmgr), key=int)[len(sorted(list(checkpkgmgr), key=int)) - 1]]
        return pkgmgr

    def _dist_detect(self):
        if platform.system() != "Linux":
            print("Unsupported OS Type! Please create an issue at https://github.com/PackeTsar/freeztp/issues and include below information.")
            sys.exit()
        return "debian"
        # PSC - platform.linux_distribution deprecated. New method needed.
        # PSC - hacking in debian as placeholder
        # distlist = platform.linux_distribution()
        # if "centos" in distlist[0].lower():
        #     return "centos"
        # elif "red hat" in distlist[0].lower() and float(distlist[1] > 8):
        #     return "rhel8"
        # elif "red hat" in distlist[0].lower():
        #     return "rhel"
        # elif "ubuntu" in distlist[0].lower():
        #     return "ubuntu"
        # elif "debian" in distlist[0].lower():
        #     return "debian"
        # else:
        #     print("Unsupported OS Type! Please create an issue at https://github.com/PackeTsar/freeztp/issues and include below information.")
        #     print(platform.linux_distribution())
        #     sys.exit()

    def _make_names(self):
        if self._dist == "debian":
            self.DHCPSVC = "isc-dhcp-server"
            self.DHCPPKG = "isc-dhcp-server"
            self.PIPPKG = "python3-pip"
            # self.PKGDIR = "/usr/local/lib/python2.7/dist-packages/"
            self.DHCPLEASES = "/var/lib/dhcp/dhcpd.leases"
        # elif self._dist == "centos":
        #     self.DHCPSVC = "dhcpd"
        #     self.DHCPPKG = "dhcp"
        #     self.PIPPKG = "python2-pip"
        #     self.PKGDIR = "/usr/lib/python2.7/site-packages/"
        #     self.DHCPLEASES = "/var/lib/dhcpd/dhcpd.leases"
        # elif self._dist == "rhel8":
        #     self.DHCPSVC = "dhcpd"
        #     self.DHCPPKG = "dhcp-server"
        #     self.PIPPKG = "python2-pip"
        #     self.PKGDIR = "/usr/lib/python2.7/site-packages/"
        #     self.DHCPLEASES = "/var/lib/dhcpd/dhcpd.leases"
        # elif self._dist == "rhel":
        #     self.DHCPSVC = "dhcpd"
        #     self.DHCPPKG = "dhcp"
        #     self.PIPPKG = "python2-pip"
        #     self.PKGDIR = "/usr/lib/python2.7/site-packages/"
        #     self.DHCPLEASES = "/var/lib/dhcpd/dhcpd.leases"
        # elif self._dist == "ubuntu":
        #     self.DHCPSVC = "isc-dhcp-server"
        #     self.DHCPPKG = "isc-dhcp-server"
        #     self.PIPPKG = "python-pip"
        #     self.PKGDIR = "/usr/local/lib/python2.7/dist-packages/"
        #     self.DHCPLEASES = "/var/lib/dhcp/dhcpd.leases"

    def service_control(self, cmd, service):
        if self._systemd:
            cli_cmd = ["sudo", "systemctl", cmd, service]
        else:
            # os.system("sudo service %s %s" % (service, cmd))
            cli_cmd = ["sudo", "service", service, cmd]

        subprocess.run(cli_cmd, capture_output=False, check=False)

    def install_pkg(self, pkg):
        cli_cmd = ["sudo", self._pkgmgr, "install", "-y", pkg]
        console("")
        subprocess.run(cli_cmd, capture_output=False, check=False)

def interceptor(afile, raddress, rport):
    log("interceptor: Called. Checking the cache")
    cached = cache.get(afile, raddress)                                        # pylint: disable=used-before-assignment
    if cached:
        return cached

    log("interceptor: Cache returned None. Running cfact.lookup procedure")
    lookup = cfact.lookup(afile, raddress)                                     # pylint: disable=used-before-assignment
    # log("interceptor: cfact.lookup returned (%s)" % lookup)
    log(f"interceptor: cfact.lookup returned ({lookup})")
    if lookup:
        log("interceptor: Returning ztp_dyn_file instantiated object")
        zfile = ztp_dyn_file(afile, raddress, rport)
        cache.store(afile, raddress, zfile)
        return zfile

    log("interceptor: Returning None")
    return None


class file_cache:
    """
    Class to cache generated file objects to prevent multiple rapid
    hits to the ZTP process: reducing logging
    """
    def __init__(self):
        self.timeout = config.running["file-cache-timeout"]
        self._cache_list = []
        self._cache = {}
        self.mthread = threading.Thread(target=self._maintenance)
        self.mthread.daemon = True
        self.mthread.start()

    def store(self, filename, ipaddr, fileobj):
        if self.timeout == 0:
            log("file_cache.store: Caching set to 0. Declining caching.")
        else:
            data = {time.time(): {"filename": filename, "ipaddr": ipaddr, "file": fileobj}}
            # log("file_cache.store: Storing %s" % str(data))
            log(f"file_cache.store: Storing {str(data)}")
            self._cache.update(data)

    def get(self, filename, ipaddr):
        currenttime = time.time()
        for entry in self._cache:                                              # pylint: disable=consider-using-dict-items
            if filename == self._cache[entry]["filename"] and ipaddr == self._cache[entry]["ipaddr"]:
                # log("file_cache.get: File (%s) requested by (%s) found in cache. Checking timeout." % (filename, ipaddr))
                log(f"file_cache.get: File ({filename}) requested by ({ipaddr}) found in cache. Checking timeout.")
                if currenttime - entry < self.timeout:
                    log("file_cache.get: Cached file is still within timeout period. Resetting to 0 and returning")
                    self._cache[entry]["file"].position = 0
                    return self._cache[entry]["file"]
                log("file_cache.get: Cached file is outside of timeout period. Deleting from cache. Returning None")
                del self._cache[entry]
                return None
        # log("file_cache.get: File (%s) requested by (%s) not in cache" % (filename, ipaddr))
        log(f"file_cache.get: File ({filename}) requested by ({ipaddr}) not in cache")
        return None

    def _maintenance(self):
        self.sthread = threading.Thread(target=self._maintain_cache)           # pylint: disable=attribute-defined-outside-init
        self.sthread.daemon = True
        self.sthread.start()
        while True:
            time.sleep(1)
            if not self.sthread.is_alive():
                self.sthread = threading.Thread(target=self._maintain_cache)   # pylint: disable=attribute-defined-outside-init
                self.sthread.daemon = True
                self.sthread.start()

    def _maintain_cache(self):
        while True:
            time.sleep(1)
            currenttime = time.time()
            for entry in list(self._cache):
                if currenttime - entry > self.timeout:
                    # log("file_cache._maintain_cache: Timing out and deleting %s:%s" % (entry, self._cache[entry]))
                    log(f"file_cache._maintain_cache: Timing out and deleting {entry}:{self._cache[entry]}")
                    del self._cache[entry]


class ztp_dyn_file:
    """
    Dynamic file object: instantiated by the tftpy server to generate TFTP
    files
    """
    closed = True
    position = 0
    def __init__(self, afile, raddress, rport, data=None, track=True):
        self.filename = afile
        self.name = afile
        self.ipaddr = raddress
        self.port = rport
        self.track = track
        if self.track:
            tracking.files.append(self)                                        # pylint: disable=used-before-assignment
        # log("ztp_dyn_file: Instantiated as (%s)" % str(self))
        log(f"ztp_dyn_file: Instantiated as ({str(self)})")
        if not data:
            self.data = cfact.request(afile, raddress)
        else:
            self.data = data
        self.__len__ = self.len
        # log("ztp_dyn_file: File size is %s bytes" % len(self.data))
        log(f"ztp_dyn_file: File size is {len(self.data)} bytes")

    def tell(self):
        #log("ztp_dyn_file.tell: Called. Returning (%s)" % str(self.position))
        return self.position

    def len(self):
        if len(self.data)-self.position < 1:
            return 0
        return len(self.data)-self.position

    def read(self, size):
        start = self.position                                                  # pylint: disable=redefined-outer-name
        end = self.position + size                                             # pylint: disable=redefined-outer-name
        result = str(self.data[start:end])
        self.position = end
        if self.track:
            tracking.report({
                "ipaddr": self.ipaddr,
                "filename": self.filename,
                "port": self.port,
                "position": self.position,
                "source": "ztp_dyn_file",
                "file": self})
        return result

    def seek(self, arg1, arg2):
        # log("ztp_dyn_file.seek: Called with args (%s) and (%s)" % (str(arg1), str(arg1)))
        log(f"ztp_dyn_file.seek: Called with args ({str(arg1)}) and ({str(arg2)})")

    def close(self):
        if not self.closed:
            log("ztp_dyn_file.close: Called. File closing.")
        else:
            log("ztp_dyn_file.close: Called again from cache.")
        self.closed = True


class config_factory:
    """
    Configuration factory: The main program which creates TFTP files based on
    the ZTP configuration
    """
    def __init__(self):
        global j2
        global meta
        import jinja2 as j2                                                    # pylint: disable=import-outside-toplevel
        from jinja2 import meta                                                # pylint: disable=import-outside-toplevel
        self.state = {}
        self.snmprequests = {}
        try:
            self.basefilename = config.running["initialfilename"]
            self.imagediscoveryfile = config.running["imagediscoveryfile"]
            self.basesnmpcom = config.running["community"]
            self.snmpoid = config.running["snmpoid"]
            self.baseconfig = config.running["starttemplate"]["value"]
            self.uniquesuffix = config.running["suffix"]
            self.templates = config.running["templates"]
            self.keyvalstore = config.running["keyvalstore"]
            self.associations = config.running["associations"]
        except:                                                                # pylint: disable=bare-except
            console("cfact.__init__: Error pulling settings from config file")

    def _check_supression(self, ipaddr):
        # log("cfact._check_supression: Called. Checking for image download supression for IP (%s)" % ipaddr)
        log(f"cfact._check_supression: Called. Checking for image download supression for IP ({ipaddr})")
        timeout = config.running["image-supression"]
        for session in tracking.status:
            timestamp = session
            filename = tracking.status[session]["filename"]
            sesip = tracking.status[session]["ipaddr"]
            if filename == config.running["imagediscoveryfile"]:
                if sesip == ipaddr:
                    if time.time()-float(timestamp) < timeout:
                        # log("cfact._check_supression: Previous session detected %s seconds ago (within %s seconds). Supressing upgrade." % (time.time()-float(timestamp), timeout))
                        log(f"cfact._check_supression: Previous session detected {time.time()-float(timestamp)} seconds ago (within {timeout} seconds). Supressing upgrade.")
                        return True
        # log("cfact._check_supression: Previous session not detected within %s seconds." % timeout)
        log(f"cfact._check_supression: Previous session not detected within {timeout} seconds.")
        return False

    def lookup(self, filename, ipaddr):
        # log("cfact.lookup: Called. Checking filename (%s) and IP (%s)" % (filename, ipaddr))
        log(f"cfact.lookup: Called. Checking filename ({filename}) and IP ({ipaddr})")
        tempid = filename.replace(self.uniquesuffix, "")
        if (self.uniquesuffix in filename) and (filename != self.basefilename):
            # log("cfact.lookup: TempID is (%s)" % tempid)
            log(f"cfact.lookup: TempID is ({tempid})")
            # log("cfact.lookup: Current SNMP Requests: %s" % list(self.snmprequests))
            log(f"cfact.lookup: Current SNMP Requests: {list(self.snmprequests)}")

        if filename == self.basefilename:
            log("cfact.lookup: Requested filename matches the initialfilename. Returning True")
            return True

        if filename == self.imagediscoveryfile:
            log("cfact.lookup: Requested filename matches the imagediscoveryfile")
            log("cfact.lookup: #############IOS UPGRADE ABOUT TO BEGIN!!!#############")
            return True

        if self.uniquesuffix in filename and tempid in list(self.snmprequests):  # If the filname contains the suffix and it has an entry in the snmp request list
            log("cfact.lookup: Seeing the suffix in the filename and the TempID in the SNMPRequests")
            if self.snmprequests[tempid].complete:  # If the snmprequest has completed
                log("cfact.lookup: The SNMP request is showing as completed")
                for response in self.snmprequests[tempid].responses:
                    if self.id_configured(self.snmprequests[tempid].responses[response]):  # If the snmp id response is a configured IDArray or keystore
                        log("cfact.lookup: The target ID is in the Keystore or in an IDArray")
                        return True
                if self._default_lookup():  # If there is a default keystore configured
                    log("cfact.lookup: The target ID is NOT in the Keystore or in an IDArray, but a default is configured")
                    return True
            elif self._default_lookup():  # If there is a default keystore configured
                log("cfact.lookup: The target ID is NOT in the Keystore or in an IDArray, but a default is configured")
                return True

        if "ztp-" in tempid.lower():
            # log("cfact.lookup: Creating new SNMP request for %s: %s" % (str(tempid), str(ipaddr)))
            log(f"cfact.lookup: Creating new SNMP request for {str(tempid)}: {str(ipaddr)}")
            self.create_snmp_request(tempid, ipaddr)

        return False

    def _default_lookup(self):
        log("cfact._default_lookup: Checking if a default-keystore is configured and ready...")
        if config.running["default-keystore"]:  # If a default keystore ID is set
            kid = config.running["default-keystore"]
            # log("cfact._default_lookup: A default keystore ID (%s) is configured" % kid)
            log(f"cfact._default_lookup: A default keystore ID ({kid}) is configured")
            if self.get_keystore_id({"default-keystore-test": kid}, silent=True):
                return kid
            # log("cfact._default_lookup: Keystore (%s) does not exist. Nothing to return" % kid)
            log(f"cfact._default_lookup: Keystore ({kid}) does not exist. Nothing to return")
        else:
            log("cfact._default_lookup: Default-keystore set to none. Returning none")
        return False

    def id_configured(self, serial):
        if serial in list(config.running["keyvalstore"]):
            return True

        arraykeys = []
        for array in config.running["idarrays"]:
            for iden in config.running["idarrays"][array]:
                arraykeys.append(iden)
        if serial in arraykeys:
            return True

        if serial in list(external_keystores.data["keyvalstore"]):
            return True

        arraykeys = []
        for array in external_keystores.data["idarrays"]:
            for iden in external_keystores.data["idarrays"][array]:
                arraykeys.append(iden)
        if serial in arraykeys:
            return True

        return False

    def request(self, filename, ipaddr, test=False):                           # pylint: disable=too-many-branches, too-many-return-statements
        # log("cfact.request: Called with filename (%s) and IP (%s)" % (filename, ipaddr))
        log(f"cfact.request: Called with filename ({filename}) and IP ({ipaddr})")
        if filename == self.basefilename:
            # log("cfact.request: Filename (%s) matches the configured initialfilename" % self.basefilename)
            log(f"cfact.request: Filename ({self.basefilename}) matches the configured initialfilename")
            tempid = self._generate_name()
            # log("cfact.request: Generated a TempID with cfact._generate_name: (%s)" % tempid)
            log(f"cfact.request: Generated a TempID with cfact._generate_name: ({tempid})")
            if not test:
                self.create_snmp_request(tempid, ipaddr)
                tracking.provision({
                    "Temp ID": tempid,
                    "IP Address": ipaddr,
                    "Matched Keystore": None,
                    "Status": "Incomplete",
                    "Real IDs": None,
                    "MAC Address": None,
                    "Timestamp": time.time()
                    })
            # log("cfact.request: Generated a SNMP Request with TempID (%s) and IP (%s)" % (tempid, ipaddr))
            log(f"cfact.request: Generated a SNMP Request with TempID ({tempid}) and IP ({ipaddr})")
            result = self.merge_base_config(tempid)
            # log("cfact.request: Returning the below initial config to TFTPy:\n%s\n%s\n%s" % ("#"*25, result, "#"*25))
            log(f"cfact.request: Returning the below initial config to TFTPy:\n{'#'*25}\n{result}\n{'#'*25}")
            self.send_tracking_update(ipaddr, filename, len(result))
            return result

        if filename == self.imagediscoveryfile:
            # log("cfact.request: Filename (%s) matches the configured imagediscoveryfile" % filename)
            log(f"cfact.request: Filename ({filename}) matches the configured imagediscoveryfile")
            if self._check_supression(ipaddr):
                result = "Image_Download_Supressed"
                self.send_tracking_update(ipaddr, filename, len(result))
                return result

            result = config.running["imagefile"]
            # log("cfact.request: Returning the value of the imagefile setting (%s)" % result)
            log(f"cfact.request: Returning the value of the imagefile setting ({result})")
            self.send_tracking_update(ipaddr, filename, len(result))
            return result

        # log("cfact.request: Filename (%s) does NOT match the configured initial filename" % filename)
        log(f"cfact.request: Filename ({filename}) does NOT match the configured initial filename")
        tempid = filename.replace(self.uniquesuffix, "")
        # log("cfact.request: Stripped filename to TempID (%s)" % tempid)
        log(f"cfact.request: Stripped filename to TempID ({tempid})")
        if config.running["delay-keystore"]:
            delay = float(config.running["delay-keystore"])
            # log("cfact.request: Delaying keystore loopup for (%s) milliseconds" % config.running["delay-keystore"])
            log(f"cfact.request: Delaying keystore loopup for ({config.running["delay-keystore"]}) milliseconds")
            time.sleep(delay/1000)

        if self.uniquesuffix in filename and tempid in list(self.snmprequests):
            log("cfact.request: Seeing the suffix in the filename and the TempID in the SNMP Requests")
            if self.snmprequests[tempid].complete:
                log("cfact.request: SNMP Request says it has completed")
                identifiers = self.snmprequests[tempid].responses
                # log("cfact.request: SNMP request returned target ID (%s)" % identifiers)
                log(f"cfact.request: SNMP request returned target ID ({identifiers})")
                if not test:
                    tracking.provision({
                        "Temp ID": tempid,
                        "IP Address": ipaddr,
                        "Matched Keystore": None,
                        "Status": "Processing",
                        "Real IDs": identifiers,
                        "MAC Address": None,
                        "Timestamp": time.time()
                        })
                keystoretup = self.get_keystore_id(identifiers)
                if keystoretup:
                    keystoreid, iden = keystoretup
                else:
                    keystoreid = None
                    iden = None
                # log("cfact.request: Keystore ID Lookup returned (%s)" % keystoreid)
                log(f"cfact.request: Keystore ID Lookup returned ({keystoreid})")
                snmpinfo = dict(identifiers)
                snmpinfo.update({"matched": iden})
                if keystoreid:
                    result, kvals = self.merge_final_config(keystoreid, snmpinfo)
                    if config.running["logging"]["merged-config-to-mainlog"] == "enable":
                        # log("cfact.request: Returning the below config to TFTPy:\n%s\n%s\n%s" % ("#"*25, result, "#"*25))
                        log(f"cfact.request: Returning the below config to TFTPy:\n{'#'*25}\n{result}\n{'#'*25}")
                    else:
                        log("cfact.request: Returning merged config to TFTPy")
                    self.log_merged_config_file(result, kvals, {
                        "keystore_id": keystoreid,
                        "ipaddr": ipaddr,
                        "epoch_timestamp": time.time(),
                        "local_timestamp": time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime(time.time())),
                        "local_year": time.strftime('%Y', time.localtime(time.time())),
                        "local_month": time.strftime('%m', time.localtime(time.time())),
                        "local_day": time.strftime('%d', time.localtime(time.time())),
                        "local_hour": time.strftime('%H', time.localtime(time.time())),
                        "local_minute": time.strftime('%M', time.localtime(time.time())),
                        "local_second": time.strftime('%S', time.localtime(time.time())),
                        "temp_id": tempid
                    })
                    self.send_tracking_update(ipaddr, filename, len(result))
                    if not test:
                        tracking.provision({
                            "Temp ID": tempid,
                            "IP Address": ipaddr,
                            "Matched Keystore": keystoreid,
                            "Status": "Complete",
                            "Real IDs": None,
                            "MAC Address": None,
                            "Timestamp": time.time()
                            })
                    return result

                # log("cfact.request: SNMP request for (%s) returned an unknown ID, checking for default-keystore" % self.snmprequests[tempid].host)
                log(f"cfact.request: SNMP request for ({self.snmprequests[tempid].host}) returned an unknown ID, checking for default-keystore")
                default = self._default_lookup()
                if default:
                    log("cfact.request: default-keystore is configured. Returning default")
                    result, kvals = self.merge_final_config(default, snmpinfo)
                    if config.running["logging"]["merged-config-to-mainlog"] == "enable":
                        # log("cfact.request: Returning the below config to TFTPy:\n%s\n%s\n%s" % ("#"*25, result, "#"*25))
                        log(f"cfact.request: Returning the below config to TFTPy:\n{'#'*25}\n{result}\n{'#'*25}")
                    else:
                        log("cfact.request: Returning merged config to TFTPy")
                    self.log_merged_config_file(result, kvals, {
                        "keystore_id": default,
                        "ipaddr": ipaddr,
                        "epoch_timestamp": time.time(),
                        "local_timestamp": time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime(time.time())),
                        "local_year": time.strftime('%Y', time.localtime(time.time())),
                        "local_month": time.strftime('%m', time.localtime(time.time())),
                        "local_day": time.strftime('%d', time.localtime(time.time())),
                        "local_hour": time.strftime('%H', time.localtime(time.time())),
                        "local_minute": time.strftime('%M', time.localtime(time.time())),
                        "local_second": time.strftime('%S', time.localtime(time.time())),
                        "temp_id": tempid
                    })
                    self.send_tracking_update(ipaddr, filename, len(result))
                    if not test:
                        tracking.provision({
                            "Temp ID": tempid,
                            "IP Address": ipaddr,
                            "Matched Keystore": default,
                            "Status": "Complete",
                            "Real IDs": None,
                            "MAC Address": None,
                            "Timestamp": time.time()
                            })
                    return result
            else:
                # log("cfact.request: SNMP request is not complete on host (%s), checking for default-keystore" % self.snmprequests[tempid].host)
                log(f"cfact.request: SNMP request is not complete on host ({self.snmprequests[tempid].host}), checking for default-keystore")
                default = self._default_lookup()
                if default:
                    log("cfact.request: default-keystore is configured. Returning default")
                    result, kvals = self.merge_final_config(default)
                    if config.running["logging"]["merged-config-to-mainlog"] == "enable":
                        # log("cfact.request: Returning the below config to TFTPy:\n%s\n%s\n%s" % ("#"*25, result, "#"*25))
                        log(f"cfact.request: Returning the below config to TFTPy:\n{'#'*25}\n{result}\n{'#'*25}")
                    else:
                        log("cfact.request: Returning merged config to TFTPy")
                    self.log_merged_config_file(result, kvals, {
                        "keystore_id": default,
                        "ipaddr": ipaddr,
                        "epoch_timestamp": time.time(),
                        "local_timestamp": time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime(time.time())),
                        "local_year": time.strftime('%Y', time.localtime(time.time())),
                        "local_month": time.strftime('%m', time.localtime(time.time())),
                        "local_day": time.strftime('%d', time.localtime(time.time())),
                        "local_hour": time.strftime('%H', time.localtime(time.time())),
                        "local_minute": time.strftime('%M', time.localtime(time.time())),
                        "local_second": time.strftime('%S', time.localtime(time.time())),
                        "temp_id": tempid
                    })
                    self.send_tracking_update(ipaddr, filename, len(result))
                    if not test:
                        tracking.provision({
                            "Temp ID": tempid,
                            "IP Address": ipaddr,
                            "Matched Keystore": default,
                            "Status": "Complete",
                            "Real IDs": None,
                            "MAC Address": None,
                            "Timestamp": time.time()
                            })
                    return result
        log("cfact.request: Nothing else caught. Returning None")
        return None

    def log_merged_config_file(self, filedata, keystore_data, other_args):
        if config.running["logging"]["merged-config-to-custom-file"] != "disable":
            newdict = dict(keystore_data)
            newdict.update(other_args)
            # log("cfact.log_merged_config_file: Creating custom log file name from variables:\n{}".format(json.dumps(newdict, indent=4)))
            log(f"cfact.log_merged_config_file: Creating custom log file name from variables:\n{json.dumps(newdict, indent=4)}")
            env = j2.Environment(loader=j2.FileSystemLoader('/'))
            template = env.from_string(config.running["logging"]["merged-config-to-custom-file"])
            newfile = template.render(newdict)
            # log("cfact.log_merged_config_file: Final merge log file is ({})".format(newfile))
            log(f"cfact.log_merged_config_file: Final merge log file is ({newfile})")
            directory, filename = os.path.split(newfile)
            if not directory or not filename:
                # log("cfact.log_merged_config_file: ERROR: Directory or Filename not present (dir={}), (filename={})".format(directory, filename))
                log(f"cfact.log_merged_config_file: ERROR: Directory or Filename not present (dir={directory}), (filename={filename})")
            elif os.path.isfile(newfile):
                # log("cfact.log_merged_config_file: File ({}) already exists. Appending".format(newfile))
                log(f"cfact.log_merged_config_file: File ({newfile}) already exists. Appending")
                with open(newfile, "w", encoding="utf8") as f:
                    f.write(f"\n\n{filedata}\n\n")
            elif not os.path.isdir(directory):
                # log("cfact.log_merged_config_file: Creating new directory ({})".format(directory))
                log(f"cfact.log_merged_config_file: Creating new directory ({directory})")
                os.makedirs(directory)
                # log("cfact.log_merged_config_file: Writing to file ({})".format(newfile))
                log(f"cfact.log_merged_config_file: Writing to file ({newfile})")
                with open(newfile, "w", encoding="utf8") as f:
                    f.write(f"\n\n{filedata}\n\n")
            else:
                # log("cfact.log_merged_config_file: Directory ({}) already exists".format(directory))
                log(f"cfact.log_merged_config_file: Directory ({directory}) already exists")
                # log("cfact.log_merged_config_file: Writing to file ({})".format(newfile))
                log(f"cfact.log_merged_config_file: Writing to file ({newfile})")
                with open(newfile, "w", encoding="utf8") as f:
                    f.write(f"\n\n{filedata}\n\n")

    def send_tracking_update(self, ipaddr, filename, filesize):
        tracking.report({
            "ipaddr": ipaddr,
            "filename": filename,
            "filesize": filesize,
            "port": None,
            "position": None,
            "source": "config_factory"})

    def create_snmp_request(self, tempid, ipaddr):
        newquery = snmp_query(ipaddr, self.basesnmpcom, self.snmpoid)
        self.snmprequests.update({tempid: newquery})

    def _generate_name(self):
        timeint = int(str(time.time()).replace(".", ""))
        timehex = hex(timeint)
        hname = timehex[2:12].upper()
        return f"ZTP-{hname}"

    def merge_base_config(self, tempid):
        env = j2.Environment(loader=j2.FileSystemLoader('/'))
        template = env.from_string(self.baseconfig)
        return template.render(autohostname=tempid, community=self.basesnmpcom)

    def merge_final_config(self, keystoreid, snmpinfo=None):
        if keystoreid in config.running["keyvalstore"]:
            path = config.running
        else:
            path = external_keystores.data
        templatedata = self.get_template(keystoreid)
        env = j2.Environment(loader=j2.FileSystemLoader('/'))
        template = env.from_string(templatedata)
        vals = self.pull_keystore_values(path, keystoreid)
        if snmpinfo:
            vals.update({"snmpinfo": snmpinfo})
        vals = self._global_keystore_merge(vals)
        # log("cfact.merge_final_config: Merging with values:\n{}".format(json.dumps(vals, indent=4)))
        log(f"cfact.merge_final_config: Merging with values:\n{json.dumps(vals, indent=4)}")
        return (template.render(vals), vals)

    def get_keystore_id(self, idens, silent=False):                            # pylint: disable=too-many-branches
        for identifier in idens:
            identifier = idens[identifier]
            if not silent:
                # log("cfact.get_keystore_id: Checking Keystores and IDArrays for (%s)" % identifier)
                log(f"cfact.get_keystore_id: Checking Keystores and IDArrays for ({identifier})")
                # log("cfact.get_keystore_id: Checking Keystore names for (%s)" % identifier)
                log(f"cfact.get_keystore_id: Checking Keystore names for ({identifier})")

            if identifier in list(config.running["keyvalstore"]):
                if not silent:
                    # log("cfact.get_keystore_id: ID (%s) resolved directly to a keystore" % identifier)
                    log(f"cfact.get_keystore_id: ID ({identifier}) resolved directly to a keystore")
                return (identifier, identifier)

            if not silent:
                # log("cfact.get_keystore_id: ID (%s) not found in keystore names, checking local IDArrays" % identifier)
                log(f"cfact.get_keystore_id: ID ({identifier}) not found in keystore names, checking local IDArrays")
            for arrayname in list(config.running["idarrays"]):
                if identifier in config.running["idarrays"][arrayname]:
                    if not silent:
                        # log("cfact.get_keystore_id: ID '%s' resolved to arrayname '%s'" % (identifier, arrayname))
                        log(f"cfact.get_keystore_id: ID '{identifier}' resolved to arrayname '{arrayname}'")
                    if arrayname in list(config.running["keyvalstore"]):
                        # log("cfact.get_keystore_id: Keystore with name '%s' has been found" % arrayname)
                        log(f"cfact.get_keystore_id: Keystore with name '{arrayname}' has been found")
                        return (arrayname, identifier)

                    if arrayname in list(external_keystores.data["keyvalstore"]):
                        # log("cfact.get_keystore_id: Keystore with name '%s' has been found in an external-keystore" % arrayname)
                        log(f"cfact.get_keystore_id: Keystore with name '{arrayname}' has been found in an external-keystore")
                        return (arrayname, identifier)
                    # log("cfact.get_keystore_id: A keystore matching arrayname '%s' cannot be found. Discarding IDArray match" % arrayname)
                    log(f"cfact.get_keystore_id: A keystore matching arrayname '{arrayname}' cannot be found. Discarding IDArray match")

            if not silent:
                # log("cfact.get_keystore_id: ID (%s) not found in local IDArrays, checking external Keystore names" % identifier)
                log(f"cfact.get_keystore_id: ID ({identifier}) not found in local IDArrays, checking external Keystore names")
            if identifier in list(external_keystores.data["keyvalstore"]):
                if not silent:
                    # log("cfact.get_keystore_id: ID (%s) resolved directly to an external-keystore" % identifier)
                    log(f"cfact.get_keystore_id: ID ({identifier}) resolved directly to an external-keystore")
                return (identifier, identifier)

            if not silent:
                # log("cfact.get_keystore_id: ID (%s) not found in external Keystore names, checking external IDArrays" % identifier)
                log(f"cfact.get_keystore_id: ID ({identifier}) not found in external Keystore names, checking external IDArrays")
            for arrayname in list(external_keystores.data["idarrays"]):
                if identifier in external_keystores.data["idarrays"][arrayname]:
                    if not silent:
                        # log("cfact.get_keystore_id: ID '%s' resolved to arrayname '%s' in an external-keystore" % (identifier, arrayname))
                        log(f"cfact.get_keystore_id: ID '{identifier}' resolved to arrayname '{arrayname}' in an external-keystore")
                    return (arrayname, identifier)

            if not silent:
                # log("cfact.get_keystore_id: ID (%s) not found in external IDArrays. ID Lookup failed!" % identifier)
                log(f"cfact.get_keystore_id: ID ({identifier}) not found in external IDArrays. ID Lookup failed!")
        return None

    def get_template(self, identity):                                          # pylint: disable=too-many-branches
        # log("cfact.get_template: Looking up association for identity (%s)" % identity)
        log(f"cfact.get_template: Looking up association for identity ({identity})")
        response = False
        for association in self.associations:
            if identity == association:
                templatename = self.associations[association]
                # log("cfact.get_template: Found associated template (%s)" % templatename)
                log(f"cfact.get_template: Found associated template ({templatename})")
                if templatename in self.templates:
                    # log("cfact.get_template: Template (%s) exists in local config. Returning" % templatename)
                    log(f"cfact.get_template: Template ({templatename}) exists in local config. Returning")
                    response = self.templates[templatename]["value"]
                elif templatename in external_templates.templates:
                    # log("cfact.get_template: Template (%s) exists as an external-template. Returning" % templatename)
                    log("cfact.get_template: Template (%s) exists as an external-template. Returning")
                    response = external_templates.templates[templatename]
                else:
                    # log("cfact.get_template: Template (%s) does not exist. Checking for default-template" % templatename)
                    log(f"cfact.get_template: Template ({templatename}) does not exist. Checking for default-template")
        if not response:
            for association in external_keystores.data["associations"]:
                if identity == association:
                    templatename = external_keystores.data["associations"][association]
                    # log("cfact.get_template: Found associated template (%s) in an external keystore" % templatename)
                    log(f"cfact.get_template: Found associated template ({templatename}) in an external keystore")
                    if templatename in self.templates:
                        # log("cfact.get_template: Template (%s) exists in local config. Returning" % templatename)
                        log(f"cfact.get_template: Template ({templatename}) exists in local config. Returning")
                        response = self.templates[templatename]["value"]
                    elif templatename in external_templates.templates:
                        # log("cfact.get_template: Template (%s) exists as an external-template. Returning" % templatename)
                        log(f"cfact.get_template: Template ({templatename}) exists as an external-template. Returning")
                        response = external_templates.templates[templatename]
                    else:
                        # log("cfact.get_template: Template (%s) does not exist. Checking for default-template" % templatename)
                        log(f"cfact.get_template: Template ({templatename}) does not exist. Checking for default-template")
        if not response:
            if config.running["default-template"]:
                # log("cfact.get_template: Default-template is pointing to (%s)" % config.running["default-template"])
                log(f"cfact.get_template: Default-template is pointing to ({config.running["default-template"]})")
                templatename = config.running["default-template"]
                if templatename in self.templates:
                    # log("cfact.get_template: Template (%s) exists in local config. Returning" % templatename)
                    log(f"cfact.get_template: Template ({templatename}) exists in local config. Returning")
                    response = self.templates[templatename]["value"]
                elif templatename in external_templates.templates:
                    # log("cfact.get_template: Template (%s) exists as an external-template. Returning" % templatename)
                    log(f"cfact.get_template: Template ({templatename}) exists as an external-template. Returning")
                    response = external_templates.templates[templatename]
                else:
                    # log("cfact.get_template: Template (%s) does not exist. Checking for default-template" % templatename)
                    log(f"cfact.get_template: Template ({templatename}) does not exist. Checking for default-template")
            else:
                log("cfact.get_template: Default-template is set to None")
        return response

    def merge_test(self, iden, template):                                      # pylint: disable=too-many-branches, too-many-locals
        idtup = self.get_keystore_id({"Merge Test":iden})
        if not idtup:
            # log("ID '%s' cannot be found!" % iden)
            log(f"ID '{iden}' cannot be found!")
            log("To check for usage of a default keystore use: ztp request default-keystore-test")
            return
        identity, identifier = idtup                                           # pylint: disable=unused-variable

        if identity in config.running["keyvalstore"]:
            path = config.running
        else:
            path = external_keystores.data

        if not identity:
            # log("ID '%s' does not exist in keystore!" % iden)
            log(f"ID '{iden}' does not exist in keystore!")
        else:
            if template == "final":
                templatedata = self.get_template(identity)
                if not templatedata:
                    # log("No tempate associated with identity %s" % iden)
                    log(f"No tempate associated with identity {iden}")
                    sys.exit()
                else:
                    env = j2.Environment(loader=j2.FileSystemLoader('/'))
                    j2template = env.from_string(templatedata)
                    ast = env.parse(templatedata)
            elif template == "initial":
                env = j2.Environment(loader=j2.FileSystemLoader('/'))
                j2template = env.from_string(self.baseconfig)
                ast = env.parse(self.baseconfig)
            templatevarlist = list(meta.find_undeclared_variables(ast))        # pylint: disable=possibly-used-before-assignment
            varsmissing = False
            missingvarlist = []
            for var in templatevarlist:
                if var not in path["keyvalstore"][identity]:
                    varsmissing = True
                    missingvarlist.append(var)
            if varsmissing:
                console("\nSome variables in jinja template do not exist in keystore:")
                for var in missingvarlist:
                    console(f"\t-{var}")
                console("\n")
            kvalues = self.pull_keystore_values(path, identity)
            snmpinfo = {"matched": "FAKEMATCHEDSERIAL"}
            for oid in config.running["snmpoid"]:
                snmpinfo.update({oid: f"{oid}_FAKESERIAL"})
            kvalues.update({"snmpinfo": snmpinfo})
            # log("cfact.merge_test: Merging with values:\n{}".format(json.dumps(kvalues, indent=4)))
            log(f"cfact.merge_test: Merging with values:\n{json.dumps(kvalues, indent=4)}")
            console("##############################")
            console(j2template.render(kvalues))                                # pylint: disable=possibly-used-before-assignment
            console("##############################")

    def pull_keystore_values(self, path, keystore_id):
        if (keystore_id not in path["idarrays"]) and (keystore_id not in list(config.running["idarrays"])):
            return self._global_keystore_merge(path["keyvalstore"][keystore_id])

        log("cfact.pull_keystore_values: Inserting IDArray keys")
        base_vals = dict(path["keyvalstore"][keystore_id])
        # Grab values from selected path first
        if keystore_id in path["idarrays"]:
            ida_vals = path["idarrays"][keystore_id]
        else:  # Otherwise grab from local config
            ida_vals = config.running["idarrays"][keystore_id]
        # If it doesn't exist at all, inject it
        if "idarray" not in base_vals:
            base_vals.update({"idarray": ida_vals})
        # It it exists but is empty
        elif not base_vals["idarray"]:
            # Replace empty data with the local data
            base_vals.update({"idarray": ida_vals})
        index = 1
        for value in ida_vals:
            key = f"idarray_{index}"
            if key not in base_vals:
                base_vals.update({key: value})
            index += 1
        return self._global_keystore_merge(base_vals)

    def _global_keystore_merge(self, ksdata):
        keystoredata = dict(ksdata)
        log("cfact._global_lookup: Checking if a global-keystore is configured and ready...")
        if config.running["global-keystore"]:  # If a global keystore ID is set
            kid = config.running["global-keystore"]
            # log("cfact._global_lookup: A global-keystore is configured ({}), checking if it exists in local config".format(kid))
            log(f"cfact._global_lookup: A global-keystore is configured ({kid}), checking if it exists in local config")
            if kid in config.running["keyvalstore"]:
                log("cfact._global_lookup: Global keystore exists in local config. Adding and returning")
                keystoredata[kid] = config.running["keyvalstore"][kid]
                return keystoredata

            if kid in external_keystores.data["keyvalstore"]:
                log("cfact._global_lookup: Global keystore exists in external keystore. Returning")
                keystoredata[kid] = external_keystores.data["keyvalstore"][kid]
                return keystoredata

            log("cfact._global_lookup: Global keystore doesn't exist. Returning keystore data unchanged")
            return keystoredata

        log("cfact._global_lookup: Global-keystore configured as none. Discarding")
        return keystoredata


class snmp_query:                                                              # pylint: disable=too-few-public-methods
    """
    SNMP Querying object: It is instantiated by the config_factory when the
    initial template is pulled down. A thread is spawned which continuously
    tries to query the ID of the switch. Once successfully queried, the
    querying object retains the real ID of the switch which is mapped to a
    keystore ID when the final template is requested
    """
    def __init__(self, host, community, oids, timeout=30):
        global psa
        import pysnmp.hlapi.v3arch.asyncio as psa                              # pylint: disable=import-outside-toplevel
        self.complete = False
        self.status = "starting"
        self.responses = {}
        self.host = host
        self.community = community
        self.oids = oids
        self.timeout = timeout
        self.threads = []
        #self._start()
        self.thread = threading.Thread(target=self._start)
        self.thread.daemon = True
        self.thread.start()

    def _start(self):
        for oid in self.oids:
            thread = threading.Thread(target=self._query_worker, args=(oid, self.oids[oid]))
            thread.daemon = True
            thread.start()
            self.threads.append(thread)

    def _watch_threads(self):
        loop = True
        while loop:
            alldead = True
            for thread in self.threads:
                if thread.isAlive():
                    alldead = False
            if alldead:
                loop = False

    def _query_worker(self, oidname, oid):
        starttime = time.time()
        self.status = "running"
        while not self.complete:
            response = str(asyncio.run(self._get_oid(oid)))
            # response will be oid data or None
            if response:
                self.responses.update({oidname: response})
                self.status = "success"
                self.complete = True
                log(f"snmp_query._query_worker: SNMP Query Successful (OID: {oidname}). Host ({self.host}) responded with ({response})")
            else:
                self.status = "retrying"
                log("snmp_query._query_worker: SNMP Query Timed Out")

            if (time.time() - starttime) > self.timeout:
                self.status = "failed"
                log("snmp_query._query_worker: Timeout Expired, Query Thread Terminating")
                break

            time.sleep(0.1)

    async def _get_oid(self, oid):
        iterator = psa.get_cmd(
            psa.SnmpEngine(),
            psa.CommunityData(self.community, mpModel=1),
            await psa.UdpTransportTarget.create((self.host, 161)),
            psa.ContextData(),
            psa.ObjectType(psa.ObjectIdentity(oid)),
        )
        _, _, _, varBinds = await iterator

        psa.SnmpEngine().close_dispatcher()
        return varBinds[0][1] if varBinds else None


class config_manager:                                                          # pylint: disable=too-many-public-methods
    """
    Configuration Manager: handles publishing of and changes to the ZTP
    configuration input by the administrator
    """
    def __init__(self):
        self.sections = [
        {"name": "dhcpd", "function": self.show_config_dhcpd},
        {"name": "template", "function": self.show_config_template},
        {"name": "keystore", "function": self.show_config_keystore},
        {"name": "idarray", "function": self.show_config_idarray},
        {"name": "association", "function": self.show_config_association},
        {"name": "integration", "function": self.show_config_integration}
        ]
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
            with open(self.configfile, "r", encoding="utf8") as f:
                self.rawconfig = f.read()
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
            console("No Config File Found! Please install app!")

    def load_external(self):
        if self.configfile:
            if "external-keystores" in self.running:
                external_keystores.load()
            if "external-templates" in self.running:
                external_templates.load()

    def save(self):
        rawconfig = json.dumps(self.running, indent=4, sort_keys=True)
        with open(self.configfile, "w", encoding="utf8") as f:
            f.write(rawconfig)

    def set(self, args):                                                       # pylint: disable=too-many-branches
        setting = args[2]
        value = args[3]
        exceptions = ["keyvalstore", "starttemplate"]
        # PSC - probably better using 'match...case' available in python 3.10
        if setting in exceptions:
            console("Cannot configure this way")

        elif setting == "snmpoid":
            self.running[setting].update({value: args[4]})
            self.save()

        elif setting == "integration":
            self.set_integration(args[3], args[4], args[5])

        elif setting == "external-keystore":
            self.set_external_keystore(args[3], args[4], args[5])

        elif setting == "template" or setting == "initial-template":           # pylint: disable=consider-using-in
            if setting == "initial-template":
                # console("Enter each line of the template ending with '%s' on a line by itself" % args[3])
                console(f"Enter each line of the template ending with '{args[3]}' on a line by itself")
                newtemplate = self.multilineinput(args[3])
                self.running["starttemplate"] = {"delineator":args[3], "value": newtemplate}

            elif setting == "template":
                # console("Enter each line of the template ending with '%s' on a line by itself" % args[4])
                console(f"Enter each line of the template ending with '{args[4]}' on a line by itself")
                newtemplate = self.multilineinput(args[4])
                if "templates" not in list(self.running):
                    self.running.update({"templates": {}})
                self.running["templates"].update({value:{}})
                self.running["templates"][value]["value"] = newtemplate
                self.running["templates"][value]["delineator"] = args[4]
            self.save()

        elif setting == "external-template":
            self.set_external_template(args[3], args[4], args[5])

        elif setting == "keystore":
            self.set_keystore(args[3], args[4], args[5] )

        elif setting == "idarray":
            self.set_idarray(value, args[4:])

        elif setting == "association":
            iden = args[4]
            template = args[6]
            self.set_association(iden, template)

        elif setting == "default-keystore" or setting == "default-template" or setting == "global-keystore":    # pylint: disable=consider-using-in
            if value.lower() == "none":
                value = None
            self.running[setting] = value
            self.save()

        elif setting == "image-supression" or setting == "file-cache-timeout" or setting == "delay-keystore":   # pylint: disable=consider-using-in
            try:
                self.running[setting] = int(value)
                self.save()
            except ValueError:
                console("Must be an integer!")

        elif setting == "dhcpd-option":
            self.set_dhcpd_options(args)

        elif setting == "dhcpd":
            self.set_dhcpd(args)

        elif setting == "logging":
            self.set_logging(args[3], args[4])

        else:
            if setting in list(self.running):
                self.running[setting] = value
                self.save()
            else:
                console("Unknown Setting!")

    def clear(self, args):                                                     # pylint: disable=too-many-branches
        setting = args[2]
        iden = args[3]
        if setting == "keystore":
            key = args[4]
            if iden not in list(self.running["keyvalstore"]):
                # console("ID does not exist in keystore: %s" % iden)
                console(f"ID does not exist in keystore: {iden}")
            else:
                if key == "all":
                    del self.running["keyvalstore"][iden]
                else:
                    if key not in list(self.running["keyvalstore"][iden]):
                        # console("Key does not exist under ID %s: %s" % (iden, key))
                        console(f"Key does not exist under ID {iden}: {key}")
                    else:
                        del self.running["keyvalstore"][iden][key]
                        if self.running["keyvalstore"][iden] == {}: # No keys left
                            del self.running["keyvalstore"][iden]

        elif setting == "integration":
            key = args[4]
            if iden not in list(self.running["integrations"]):
                # console("Integration (%s) does not exist!" % iden)
                console(f"Integration ({iden}) does not exist!")
            else:
                if key == "all":
                    del self.running["integrations"][iden]
                else:
                    if key not in list(self.running["integrations"][iden]):
                        # console("Key (%s) does not exist under integration (%s)" % (iden, key))
                        console(f"Key ({iden}) does not exist under integration ({key})")
                    else:
                        del self.running["integrations"][iden][key]
                        if self.running["integrations"][iden] == {}: # No keys left
                            del self.running["integrations"][iden]

        elif setting == "external-keystore":
            key = args[4]
            if iden not in list(self.running["external-keystores"]):
                # console("External-keystore (%s) does not exist!" % iden)
                console(f"External-keystore ({iden}) does not exist!")
            else:
                if key == "all":
                    del self.running["external-keystores"][iden]
                else:
                    if key not in list(self.running["external-keystores"][iden]):
                        # console("Key (%s) does not exist under external-keystore (%s)" % (iden, key))
                        console(f"Key ({iden}) does not exist under external-keystore ({key})")
                    else:
                        del self.running["external-keystores"][iden][key]
                        if self.running["external-keystores"][iden] == {}: # No keys left
                            del self.running["external-keystores"][iden]

        elif setting == "idarray":
            if iden not in list(self.running["idarrays"]):
                # console("ID does not exist in the idarrays: %s" % iden)
                console(f"ID does not exist in the idarrays: {iden}")
            else:
                del self.running["idarrays"][iden]

        elif setting == "snmpoid":
            if self.running["snmpoid"] == {}:
                console("No SNMP OID's are currently configured")
            elif iden not in list(self.running["snmpoid"]):
                # console("snmpoid '%s' is not currently configured" % iden)
                console(f"snmpoid '{iden}' is not currently configured")
            else:
                del self.running["snmpoid"][iden]

        elif setting == "template":
            if "templates" not in list(self.running):
                console("No templates are currently configured")
            elif iden not in list(self.running["templates"]):
                # console("Template '%s' is not currently configured" % iden)
                console(f"Template '{iden}' is not currently configured")
            else:
                del self.running["templates"][iden]

        elif setting == "external-template":
            if iden not in self.running["external-templates"]:
                # console("External-template '%s' is not currently configured" % iden)
                console(f"External-template '{iden}' is not currently configured")
            else:
                del self.running["external-templates"][iden]

        elif setting == "association":
            if "associations" not in list(self.running):
                console("No associations are currently configured")
            elif iden not in list(self.running["associations"]):
                # console("Association '%s' is not currently configured" % iden)
                console(f"Association '{iden}' is not currently configured")
            else:
                del self.running["associations"][iden]

        elif setting == "dhcpd":
            if "dhcpd" not in list(self.running):
                console("No DHCP scopes are currently configured")
            elif iden not in list(self.running["dhcpd"]):
                # console("DHCP Scope '%s' is not currently configured" % iden)
                console(f"DHCP Scope '{iden}' is not currently configured")
            else:
                del self.running["dhcpd"][iden]

        elif setting == "dhcpd-option":
            if "dhcpd-options" not in list(self.running):
                console("No DHCP options are currently configured")
            elif iden not in list(self.running["dhcpd-options"]):
                # console("DHCP Option '%s' is not currently configured" % iden)
                console(f"DHCP Option '{iden}' is not currently configured")
            else:
                del self.running["dhcpd-options"][iden]

        else:
            console("Unknown Setting!")
        self.save()

    def multilineinput(self, ending):
        result = ""
        for line in iter(input, ending):
            result += line+"\n"
        return result[0:len(result)-1]

    def set_integration(self, iden, key, value):
        if key == "type":
            if value not in integration_main.mods:
                # console("Integration type (%s) not recognized or allowed" % value)
                console(f"Integration type ({value}) not recognized or allowed")
                sys.exit()
        if iden in list(self.running["integrations"]):
            self.running["integrations"][iden].update({key: value})
        else:
            self.running["integrations"].update({iden: {key: value}})
        self.save()

    def set_external_keystore(self, iden, key, value):
        if key == "type":
            if value not in external_keystore_main.mods:
                # console("External-keystore type (%s) not recognized or allowed" % value)
                console(f"External-keystore type ({value}) not recognized or allowed")
                sys.exit()
        if iden in list(self.running["external-keystores"]):
            self.running["external-keystores"][iden].update({key: value})
        else:
            self.running["external-keystores"].update({iden: {key: value}})
        self.save()

    def set_external_template(self, iden, setting, value):
        if setting == "file":
            if iden in list(self.running["external-templates"]):
                self.running["external-templates"][iden].update({"file": value})
            else:
                self.running["external-templates"].update({iden: {"file": value}})
        self.save()

    def set_keystore(self, iden, keyword, value):
        try:
            value = json.loads(value)
        except ValueError:
            pass
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
    dhcp_option_types = [
        "string",
        "ip-address",
        "int32",
        "domain-list",
        "domain-name"
    ]

    def set_dhcpd_options(self, args):
        try:
            code = int(args[5])
            if code > 254 or code < 1:
                console("ERROR: Code must be integer between 1-254")
                sys.exit()
        except ValueError:
            console("ERROR: Code must be integer between 1-254")
        if args[7] not in self.dhcp_option_types:
            # console("ERROR: Option type not valid. Accepted options are ({})".format(self.dhcp_option_types))
            console(f"ERROR: Option type not valid. Accepted options are ({self.dhcp_option_types})")
            sys.exit()
        self.running["dhcpd-options"].update({args[3]: {"type": args[7], "code": int(args[5])}})
        self.save()

    def set_dhcpd(self, args):
        global netaddr
        import netaddr                                                         # pylint: disable=import-outside-toplevel
        if len(args) < 6:
            console("ERROR: Incomplete Command!")
            sys.exit()
        scope = args[3]
        setting = args[4]
        value = args[5]
        checks = {
            "subnet": self.is_net,
            "first-address": self.is_ip,
            "last-address": self.is_ip,
            "gateway": self.is_ip,
            "domain-name": self.make_true,
            "lease-time": self.is_num,
            "imagediscoveryfile-option": self.make_true
        }
        #### Build Path
        if "dhcpd" not in list(self.running):
            self.running.update({"dhcpd": {}})
        if scope not in self.running["dhcpd"]:
            console("INFO: New scope creation detected. Adding a few commands automatically")
            scopedict = {}
            cmds = []
            ips = self.filter_ips(self.get_addresses())  # Get current interface addresses
            if len(ips) == 1:
                myip = ips[0][1]
                # console("INFO: Detected ZTP server IP: {}".format(myip))
                console(f"INFO: Detected ZTP server IP: {myip}")
                cmds.append(f"ztp set dhcpd {scope} ztp-tftp-address {myip}")
                scopedict.update({"ztp-tftp-address": myip})
            else:
                # console("INFO: Could not detect ZTP server IP. To set IP for this scope, use: ztp set dhcpd {} ztp-tftp-address <ip-address>".format(scope))
                console(f"INFO: Could not detect ZTP server IP. To set IP for this scope, use: ztp set dhcpd {scope} ztp-tftp-address <ip-address>")
            cmds.append(f"ztp set dhcpd {scope} lease-time 3600")
            cmds.append(f"ztp set dhcpd {scope} imagediscoveryfile-option enable")
            scopedict.update({"imagediscoveryfile-option": "enable", "lease-time": 3600})
            self.running["dhcpd"].update({scope: scopedict})
            for cmd in cmds:
                # console("    Injecting Command: {}".format(cmd))
                console(f"    Injecting Command: {cmd}")

        if setting in checks:
            check = checks[setting](value)
            # if check == True:
            if check is True:
                self.running["dhcpd"][scope].update({setting: value})
            else:
                console(check)
        elif setting == "dns-servers":
            value = ", ".join(args[5:])
            self.running["dhcpd"][scope].update({setting: value})
        elif setting in self.running["dhcpd-options"]:
            self.running["dhcpd"][scope].update({setting: value})
        else:
            console("BAD COMMAND!")
        self.save()

    def is_ip(self, data):
        try:
            netaddr.IPAddress(data)
            return True
        except Exception as err:                                               # pylint: disable=broad-exception-caught
            return err

    def is_net(self, data):
        try:
            ipobj = netaddr.IPNetwork(data)
            if str(ipobj.cidr) == data:
                return True
            return "Please provide a CIDR address (ie: 10.0.0.0/24)"

        except ValueError as err:
            return err

    def is_num(self, data):
        try:
            int(data)
            return True
        except Exception:                                                      # pylint: disable=broad-exception-caught
            return "Must be a number!"

    def make_true(self):
        return True

    def set_logging(self, setting, value):
        endis = ["enable", "disable"]
        if setting == "merged-config-to-mainlog":
            if value not in endis:
                console("ERROR: Only (enable|disable) are allowed")
            else:
                self.running["logging"][setting] = value
                self.save()
        elif setting == "merged-config-to-custom-file":
            self.running["logging"][setting] = value
            self.save()

    def show_config(self):                                                     # pylint: disable=too-many-branches, too-many-locals
        cmdlist = []
        simplevals = ["suffix", "initialfilename", "community", "tftproot", "imagediscoveryfile", "file-cache-timeout"]
        for each in simplevals:
            cmdlist.append(f"ztp set {each} {self.running[each]}")

        for oid in self.running["snmpoid"]:
            cmdlist.append(f"ztp set snmpoid {oid} {self.running["snmpoid"][oid]}")

        info = self.running["logging"]["merged-config-to-mainlog"]
        log_merged_mainlog = f"ztp set logging merged-config-to-mainlog {info}"
        if self.running["logging"]["merged-config-to-custom-file"] == "disable":
            log_merged_customfile = "ztp set logging merged-config-to-custom-file disable"
        else:
            info = self.running["logging"]["merged-config-to-custom-file"]
            log_merged_customfile = f"ztp set logging merged-config-to-custom-file '{info}'"

        itempval = self.running["starttemplate"]["value"]
        itempdel = self.running["starttemplate"]["delineator"]
        itemp = f"ztp set initial-template {itempdel}\n{itempval}\n{itempdel}"

        templatetext = ""
        for template in self.running["templates"]:
            tempval = self.running["templates"][template]["value"]
            tempdel = self.running["templates"][template]["delineator"]
            templatetext += "#\n#\n#\n"
            templatetext += f"ztp set template {template} {tempdel}\n{tempval}\n{tempdel}"
            templatetext += "\n#\n#\n#\n#######################################################\n"

        idarraylist = []
        for arrayname in self.running["idarrays"]:
            command = f"ztp set idarray {arrayname}"
            for iden in self.running["idarrays"][arrayname]:
                command += f" {iden}"
            idarraylist.append(command)

        keylist = []
        for iden in self.running["keyvalstore"]:
            for key in self.running["keyvalstore"][iden]:
                value = self.running["keyvalstore"][iden][key]
                if type(value) != type("") and type(value) != type(u""):       # pylint: disable=unidiomatic-typecheck, redundant-u-string-prefix
                    value = f"'{json.dumps(value)}'"
                else:
                    if " " in value:
                        value = f"'{value}'"
                keylist.append(f"ztp set keystore {iden} {key} {value}")
            keylist.append("#")

        intglist = []
        for iden in self.running["integrations"]:
            for key in self.running["integrations"][iden]:
                value = self.running["integrations"][iden][key]
                if type(value) != type("") and type(value) != type(u""):       # pylint: disable=unidiomatic-typecheck, redundant-u-string-prefix
                    value = f"'{json.dumps(value)}'"
                else:
                    if " " in value:
                        value = f"'{value}'"
                intglist.append(f"ztp set integration {iden} {key} {value}")
            intglist.append("#")

        exkeystlist = []
        for iden in self.running["external-keystores"]:
            for key in self.running["external-keystores"][iden]:
                value = self.running["external-keystores"][iden][key]
                if key == "file":
                    value = f"'{value}'"
                exkeystlist.append(f"ztp set external-keystore {iden} {key} {value}")
            exkeystlist.append("#")

        extemplist = []
        for iden in self.running["external-templates"]:
            for key in self.running["external-templates"][iden]:
                value = self.running["external-templates"][iden][key]
                if key == "file":
                    value = f"'{value}'"
                extemplist.append(f"ztp set external-template {iden} {key} {value}")
            extemplist.append("#")

        associationlist = []
        for association in self.running["associations"]:
            template = self.running["associations"][association]
            associationlist.append(f"ztp set association id {association} template {template}")

        dkeystore = f"ztp set default-keystore {str(self.running["default-keystore"])}"
        gkeystore = f"ztp set global-keystore {str(self.running["global-keystore"])}"
        dtemplate = f"ztp set default-template {str(self.running["default-template"])}"
        imagefile = f"ztp set imagefile {str(self.running["imagefile"])}"
        imagesup = f"ztp set image-supression {str(self.running["image-supression"])}"
        delaykey = f"ztp set delay-keystore {str(self.running["delay-keystore"])}"

        dhcpoptlist = []
        for option in self.running["dhcpd-options"]:
            code = self.running["dhcpd-options"][option]["code"]
            typ = self.running["dhcpd-options"][option]["type"]
            dhcpoptlist.append(f"ztp set dhcpd-option {option} code {code} type {typ}")

        scopelist = []
        for scope in self.running["dhcpd"]:
            for option in self.running["dhcpd"][scope]:
                value = self.running["dhcpd"][scope][option]
                command = f"ztp set dhcpd {scope} {option} {value}"
                command = command.replace(",", "")
                scopelist.append(command)
            scopelist.append("#")
        scopelist = scopelist[:len(scopelist)-1] # Remove last '#'

        configtext = "#######################################################\n#\n#\n#\n"
        for cmd in cmdlist:
            configtext += f"{cmd}\n"
        configtext += f"{log_merged_mainlog}\n"
        configtext += f"{log_merged_customfile}\n"
        configtext += "#\n#\n"
        configtext += itemp

        configtext += "\n#\n#\n#\n#######################################################\n"
        configtext += "#\n#\n#\n"
        for cmd in dhcpoptlist:
            configtext += f"{cmd}\n"
        configtext += "#\n#\n#\n"
        for cmd in scopelist:
            configtext += f"{cmd}\n"

        configtext += "#\n#\n#\n#######################################################\n"
        configtext += templatetext

        configtext += "#\n#\n#\n"
        for cmd in keylist:
            configtext += f"{cmd}\n"
        configtext += "#\n#\n"
        for cmd in idarraylist:
            configtext += f"{cmd}\n"
        configtext += "#\n#\n#\n"
        for cmd in associationlist:
            configtext += f"{cmd}\n"
        configtext += "#\n#\n#\n"
        configtext += dkeystore
        configtext += "\n"
        configtext += gkeystore
        configtext += "\n"
        configtext += dtemplate
        configtext += "\n"
        configtext += imagefile
        configtext += "\n"
        configtext += imagesup
        configtext += "\n"
        configtext += delaykey
        configtext += "\n#\n#\n#\n"
        for cmd in intglist:
            configtext += f"{cmd}\n"
        for cmd in exkeystlist:
            configtext += f"{cmd}\n"
        configtext += "#\n#\n"
        for cmd in extemplist:
            configtext += f"{cmd}\n"
        configtext += "#\n#\n#\n#######################################################"

        console(configtext)

    def show_config_dhcpd(self):
        pass

    def show_config_template(self):
        pass

    def show_config_keystore(self):
        pass

    def show_config_idarray(self):
        pass

    def show_config_association(self):
        pass

    def show_config_integration(self):
        intglist = []
        for iden in self.running["integrations"]:
            for key in self.running["integrations"][iden]:
                value = self.running["integrations"][iden][key]
                if type(value) != type("") and type(value) != type(u""):       # pylint: disable=unidiomatic-typecheck, redundant-u-string-prefix
                    value = f"'{json.dumps(value)}'"
                else:
                    if " " in value:
                        value = f"'{value}'"
                intglist.append("ztp set integration {iden} {key} {value}")
            intglist.append("#")
        return intglist

    def show_config_section(self, secinput):
        for section in self.sections:
            if section["name"] == secinput:
                return section["function"]()
        # console("Section (%s) not found!" % secinput)
        console(f"Section ({secinput}) not found!")
        return ""

    def calcopt125hex(self):
        # Basedata meaning as follows:
        ### 00 00 00 09 = Cisco vendor specific code
        basedata = "000000090a05"
        filenamedata = self.running["imagediscoveryfile"].encode("utf-8").hex()
        lenval = f"{int(len(filenamedata)/2):x}"
        if len(lenval) < 2:
            lenval = "0"+lenval
        return basedata+lenval+filenamedata

    def ciscohex(self, hexdata):
        last = 0
        current = 1
        templist = []
        for char in hexdata:                                                   # pylint: disable=unused-variable
            if (len(hexdata) - last) < 4:
                templist.append(hexdata[last:len(hexdata)])
                break
            if current%4 == 0:
                templist.append(hexdata[last:current])
                last = current
            current += 1
        result = ""
        for quad in templist:
            result += quad + "."
        return result[:len(result)-1]

    def isc_hex(self, hexdata):
        return ":".join(map(''.join, zip(*[iter(hexdata)]*2))).upper()

    def opt125(self, mode):                                                    # pylint: disable=inconsistent-return-statements
        if mode == "windows":
            console("    Follow the below Instructions:")
            console("        - Open the Windows DHCP Server admin window")
            console("        - Right click on the 'IPv4' object under the DHCP server name")
            console("            - Select 'Set Predefined Options'")
            console("        - Click the 'Add' button")
            console("            - Set the following values")
            console("                - Name        = Cisco Image Discovery File")
            console("                - Data Type   = Encapsulated")
            console("                - Code        = 125")
            console("                - Description = Used by FreeZTP for IOS upgrade")
            console("            - Click OK")
            console("        - Click OK again")
            console("")
            console("        - Find the DHCP scope serving ZTP devices")
            console("        - Expand the scope and right click 'Scope Options'")
            console("            - Click 'Configure Options'")
            console("        - Scroll down and check the box for option '125 Cisco Image Discovery File'")
            console("        - Place the typing cursor into the data field under 'Binary'")
            console("        - Copy and paste the below hex code into the firewalld")
            console(f"            - Hex code between quotes - '{self.calcopt125hex()}'")
            console("        - You should see the ZTP configured imagediscoveryfile name under the 'ASCII' field")
            console("        - Click OK")
            console("        - Close the Windows DHCP Server admin window")
        elif mode == "cisco":
            optiondata = self.running["imagediscoveryfile"].encode("hex")      # pylint: disable=unused-variable
            console("\n\nAdd the below line to your 'ip dhcp pool XXXX' config:\n")
            # console("option 125 hex %s\n\n" % self.ciscohex(self.calcopt125hex()))
            info = self.ciscohex(self.calcopt125hex())
            console(f"option 125 hex {info}\n\n")
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

    def hidden_list_array_members(self):
        for arrayname in list(self.running["idarrays"]):
            for member in self.running["idarrays"][arrayname]:
                console(member)

    def hidden_list_array_name_options(self):
        done = []
        for arrayname in list(self.running["idarrays"]):
            done.append(arrayname)
            console(arrayname)
        for keystorename in list(self.running["keyvalstore"]):
            if keystorename not in done:
                console(keystorename)

    def hidden_list_snmpoid(self):
        for oid in self.running["snmpoid"]:
            console(oid)

    def hidden_list_templates(self):
        for template in self.running["templates"]:
            console(template)
        for template in self.running["external-templates"]:
            console(template)

    def hidden_list_external_templates(self):
        for template in self.running["external-templates"]:
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
            console(each)

    def hidden_list_dhcpd_options(self):
        for option in self.running["dhcpd-options"]:
            console(option)

    def hidden_list_dhcpd_option_types(self):
        for typ in self.dhcp_option_types:
            console(typ)

    def hidden_show_dhcpd_option(self, opt_name):
        console(self.running["dhcpd-options"][opt_name]["type"])

    def hidden_list_dhcpd_scopes(self):
        for scope in self.running["dhcpd"]:
            console(scope)

    def hidden_list_integrations(self):
        for scope in self.running["integrations"]:
            console(scope)

    def hidden_list_external_keystores(self):
        for scope in self.running["external-keystores"]:
            console(scope)

    def hidden_list_integration_types(self):
        for typ in integration_main.mods:
            console(typ)

    def hidden_list_external_keystore_types(self):
        for typ in external_keystore_main.mods:
            console(typ)

    def hidden_show_integration_keys(self, iden):
        try:
            for key in list(self.running["integrations"][iden]):
                console(key)
        except KeyError:
            pass

    def hidden_show_external_keystore_keys(self, iden):
        try:
            for key in list(self.running["external-keystores"][iden]):
                console(key)
        except KeyError:
            pass

    def hidden_show_integration_opts(self, iden):
        try:
            typ = self.running["integrations"][iden]["type"]
            options = integration_main.mods[typ].options
            for option in options:
                console(option)
        except KeyError:
            pass

    def hidden_show_external_keystore_opts(self, iden):
        try:
            typ = self.running["external-keystores"][iden]["type"]
            options = external_keystore_main.mods[typ].options
            for option in options:
                console(option)
        except KeyError:
            pass

    def dhcpd_compile(self):                                                   # pylint: disable=too-many-locals
        result = "########### FREEZTP DHCP SCOPES ###########\n"
        result += "############## DO NOT MODIFY ##############\n"
        result += "option imagediscoveryfile-option code 125 = string;\n"
        for option in self.running["dhcpd-options"]:
            typ = self.running["dhcpd-options"][option]["type"]
            code = self.running["dhcpd-options"][option]["code"]
            # result += "option {} code {} = {};\n".format(option, code, typ)
            result += f"option {option} code {code} = {typ};\n"
        result += "#\n"
        result += "#"
        mappings = {
        "gateway": " option routers <value>;",
        "dns-servers": " option domain-name-servers <value>;",
        "domain-name": ' option domain-name "<value>";',
        "lease-time": " max-lease-time <value>;"
        }
        for scope in self.running["dhcpd"]:
            ### Run Basic Checks
            if "subnet" not in self.running["dhcpd"][scope]:
                # console("ERROR: DHCP Scope %s has no subnet defined. A subnet is required!. Compiling stopped." % scope)
                console(f"ERROR: DHCP Scope {scope} has no subnet defined. A subnet is required!. Compiling stopped.")
                sys.exit()

            elif "first-address" in self.running["dhcpd"][scope] and "last-address" not in self.running["dhcpd"][scope]:
                # console("ERROR: Need to define a 'last-address' in scope %s. Compiling stopped." % scope)
                console(f"ERROR: Need to define a 'last-address' in scope {scope}. Compiling stopped.")
                sys.exit()

            elif "last-address" in self.running["dhcpd"][scope] and "first-address" not in self.running["dhcpd"][scope]:
                # console("ERROR: Need to define a 'first-address' in scope %s. Compiling stopped." % scope)
                console(f"ERROR: Need to define a 'first-address' in scope {scope}. Compiling stopped.")
                sys.exit()

            else:
                ### Start Compiling
                scopetext = f"#### Scope: {scope} ####"
                ending = f" }}\n{'#'*len(scopetext)}"
                scopetext = f"\n#\n{scopetext}\n"

                subnet = netaddr.IPNetwork(self.running["dhcpd"][scope]["subnet"])
                net = str(subnet.network)
                mask = str(subnet.netmask)

                scopetext += f"subnet {net} netmask {mask} {{\n"

                for option in self.running["dhcpd"][scope]:
                    if option in mappings:
                        value = str(self.running["dhcpd"][scope][option])
                        txt = mappings[option].replace("<value>", value)
                        scopetext += f"{txt}\n"
                    elif option == "first-address":
                        first = self.running["dhcpd"][scope]["first-address"]
                        last = self.running["dhcpd"][scope]["last-address"]
                        txt = f" range {first} {last};"
                        scopetext += f"{txt}\n"
                    elif option in self.running["dhcpd-options"]:
                        txt = f' option {option} {self.running["dhcpd"][scope][option]};'
                        scopetext += f"{txt}\n"
                if self.running["dhcpd"][scope]["imagediscoveryfile-option"] == "enable":
                    opt125val = self.opt125("isc")
                    txt = f" send imagediscoveryfile-option {opt125val};"
                    scopetext += f"{txt}\n"

                scopetext += ending
                result += scopetext
        return result

    def dhcpd_commit(self):
        global netaddr
        import netaddr                                                         # pylint: disable=import-outside-toplevel
        dhcpdata = self.dhcpd_compile()
        with open("/etc/dhcp/dhcpd.conf", "r", encoding="utf8") as f:
            filedatalist = f.readlines()
        index = 1
        for line in filedatalist:
            if line == '########### FREEZTP DHCP SCOPES ###########\n':
                break

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
        with open("/etc/dhcp/dhcpd.conf", "w", encoding="utf8") as f:
            f.write(strippeddata)
        console("\nWrite Complete. Restarting DHCP Service...\n")
        osd.service_control("restart", osd.DHCPSVC)
        osd.service_control("status", osd.DHCPSVC)

    def get_addresses(self):
        import netifaces                                                       # pylint: disable=import-outside-toplevel, redefined-outer-name
        result = []
        for iface in netifaces.interfaces():                                   # pylint: disable=c-extension-no-member
            addressdict = netifaces.ifaddresses(iface)                         # pylint: disable=c-extension-no-member
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
                na_mask = netaddr.IPAddress(adtup[2].split("/")[0])
                bits = netaddr.IPAddress(na_mask).netmask_bits()
                ip_composed = f"{adtup[1].split("%")[0]}/{str(bits)}"
                na_net = netaddr.IPNetwork(ip_composed)
                uni = na_net.is_unicast()
                loc = na_net.is_link_local()
                loop = na_net.is_loopback()
                multi = na_net.is_multicast()
                res = na_net.is_reserved()
                host = na_mask.is_hostmask()

                if (uni, loc, loop, multi, res, host) == (True, False, False, False, False, False):
                    # Unicast address without /32 or /128 host mask
                    if ":" not in ip_composed:
                        # IPv4 unicast address
                        result.append((adtup[0], adtup[1], adtup[2], str(na_net.cidr)))
                    else:
                        # IPv6 unicast address (non-link local)
                        pass
            except netaddr.AddrFormatError:
                # HW address (MAC), loopback IPs, IPs with host mask, IPv6 link local
                pass

        return result

    def _write_interfaces(self, iflist):
        if os.path.isfile("/etc/default/isc-dhcp-server"):
            ifstr = " ".join(iflist)
            newfilelines = []
            with open("/etc/default/isc-dhcp-server", "r", encoding="utf8") as f:
                filedatalist = f.readlines()
            for line in filedatalist:
                if "INTERFACESv4=" in line:
                    newfilelines.append(f'INTERFACESv4="{ifstr}"\n')
                elif "INTERFACES=" in line:
                    newfilelines.append(f'INTERFACES="{ifstr}"\n')
                else:
                    newfilelines.append(line)
            newfile = ""
            for line in newfilelines:
                newfile += line                                                # pylint: disable=consider-using-join
            with open("/etc/default/isc-dhcp-server", "w", encoding="utf8") as f:
                f.write(newfile)

    def auto_dhcpd(self):
        global netaddr
        import netaddr                                                         # pylint: disable=import-outside-toplevel
        console("INFO: Autodetection can often detect an incorrect subnet mask. You may need to correct the subnet on auto built scopes")
        console("INFO: You will need to set the 'first-address' and 'last-address' settings on any auto-built scope for it to actually serve IP addresses")
        console("Detecting interfaces and determining usable IP addresses...")
        ips = self.filter_ips(self.get_addresses())
        iflist = []
        # console("  Found: %s\nCreating Scopes..." % ips)
        console(f"  Found: {ips}\nCreating Scopes...")
        for net in ips:
            scopename = f"INTERFACE-{net[0].upper()}"
            console(f"  Building Scope {scopename}")
            if net[2] == "255.255.255.255":
                console(f"    WARNING: Scope {scopename} has a /32 subnet size. You may need to adjust it if you want to serve IP addresses on that subnet")
            subnet = net[3]
            myip = net[1]
            cmd1 = f"ztp set dhcpd {scopename} subnet {subnet}"
            api1 = ['ztp', 'set', 'dhcpd', scopename, 'subnet', subnet]
            cmd2 = f"ztp set dhcpd {scopename} ztp-tftp-address {myip}"
            api2 = ['ztp', 'set', 'dhcpd', scopename, 'ztp-tftp-address', myip]
            # console("    Injecting Command: %s" % cmd1)
            console(f"    Injecting Command: {cmd1}")
            self.set_dhcpd(api1)
            # console("    Injecting Command: %s" % cmd2)
            console(f"    Injecting Command: {cmd2}")
            self.set_dhcpd(api2)
            iflist.append(net[0])
        self._write_interfaces(iflist)
        console("\n\nComplete!\n\nRemember to commit the new DHCP config using the command 'ztp request dhcpd-commit'\n")


class log_management:
    """
    Log Management Class: Handles all prnting to console and logging to the
    logfile
    """
    def __init__(self):
        self.logfile = "/etc/ztp/ztp.log"
        self._publish_methods()
        self.can_log = True

    def _logger(self, data):
        # logdata = time.strftime("%Y-%m-%d %H:%M:%S") + ":   " + data + "\n"
        logdata = f"{time.strftime("%Y-%m-%d %H:%M:%S")}:  {data}\n"
        if self.can_log:
            try:
                with open(self.logfile, "a", encoding="utf8") as f:
                    f.write(logdata)
            except IOError:
                # self._console("Unable to log to logfile %s. Make sure FreeZTP is installed. Disabling logging to logfile" % self.logfile)
                self._console(f"Unable to log to logfile {self.logfile}. Make sure FreeZTP is installed. Disabling logging to logfile")
                self.can_log = False
        self._console(logdata)

    def _console(self, data, timestamp=False):
        if timestamp:
            logdata = f"{time.strftime("%Y-%m-%d %H:%M:%S")}:  {data}\n"
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
            subprocess.run(["more", self.logfile], capture_output=False, check=True)
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
                        # self._console("Invalid input '%s'. Must be an integer" % args[4])
                        self._console(f"Invalid input '{args[4]}'. Must be an integer")
            else:
                # self._console("Invalid input '%s'" % args[3])
                self._console(f"Invalid input '{args[3]}'")

    def tail(self, length="25"):
        subprocess.run(["tail", "-fn", length, self.logfile], capture_output=False, check=True)

    def clear(self):
        with open(self.logfile,"w", encoding="utf8") as f:
            f.write("")


class installer:
    """
    Installer class: A simple holder class which contains all of the
    installation scripts used to install/upgrade the ZTP server
    """
    defaultconfig = '''{
    "associations": {
        "SERIAL100": "SHORT_TEMPLATE",
        "STACK1": "LONG_TEMPLATE"
    },
    "community": "secretcommunity",
    "default-keystore": "DEFAULT_VALUES",
    "default-template": "LONG_TEMPLATE",
    "delay-keystore": 1000,
    "dhcpd": {
    },
    "dhcpd-options": {
        "ztp-tftp-address": {
            "code": 150,
            "type": "ip-address"
        }
    },
    "external-keystores": {
    },
    "external-templates": {
    },
    "file-cache-timeout": 10,
    "global-keystore": null,
    "idarrays": {
        "STACK1": [
            "SERIAL1",
            "SERIAL2",
            "SERIAL3"
        ]
    },
    "image-supression": 3600,
    "imagediscoveryfile": "freeztp_ios_upgrade",
    "imagefile": "cat3k_caa-universalk9.SPA.03.06.06.E.152-2.E6.bin",
    "initialfilename": "network-confg",
    "integrations": {
    },
    "keyvalstore": {
        "DEFAULT_VALUES": {
            "hostname": "UNKNOWN_HOST",
            "vl1_ip_address": "dhcp"
        },
        "SERIAL100": {
            "hostname": "SOMEDEVICE",
            "vl1_ip_address": "10.0.0.201"
        },
        "STACK1": {
            "hostname": "CORESWITCH",
            "vl1_ip_address": "10.0.0.200",
            "vl1_netmask": "255.255.255.0"
        }
    },
    "logging": {
        "merged-config-to-custom-file": "disable",
        "merged-config-to-mainlog": "enable"
    },
    "snmpoid": {
        "C9K_CHASSIS_SERIAL": "1.3.6.1.2.1.47.1.1.1.1.11.1",
        "C9K_MOD1_SERIAL": "1.3.6.1.2.1.47.1.1.1.1.11.1000",
        "C9800_SERIAL": "1.3.6.1.2.1.47.1.1.1.1.11.2"
    },
    "starttemplate": {
        "delineator": "^",
        "value": "hostname {{ autohostname }}\\n!\\nsnmp-server community {{ community }} RO\\n!\\nend"
    },
    "suffix": "-confg",
    "templates": {
        "LONG_TEMPLATE": {
            "delineator": "^",
            "value": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} {{ vl1_netmask }}\\n no shut\\n!\\n!{% for interface in range(1,49) %}\\ninterface GigabitEthernet1/0/{{interface}}\\n description User Port (VLAN 1)\\n switchport access vlan 1\\n switchport mode access\\n no shutdown\\n!{% endfor %}\\n!\\nip domain-name test.com\\n!\\nusername admin privilege 15 secret password123\\n!\\naaa new-model\\n!\\n!\\naaa authentication login CONSOLE local\\naaa authorization console\\naaa authorization exec default local if-authenticated\\n!\\ncrypto key generate rsa modulus 2048\\n!\\nip ssh version 2\\n!\\nline vty 0 15\\nlogin authentication default\\ntransport input ssh\\nline console 0\\nlogin authentication CONSOLE\\nend"
        },
        "SHORT_TEMPLATE": {
            "delineator": "^",
            "value": "hostname {{ hostname }}\\n!\\ninterface Vlan1\\n ip address {{ vl1_ip_address }} 255.255.255.0\\n no shut\\n!\\nend"
        }
    },
    "tftproot": "/etc/ztp/tftproot/"
}'''

    def minor_update_script(self):
        newconfigkeys = {
        "integrations": {},
        "external-keystores": {},
        "external-templates": {},
        "global-keystore": None,
        "logging": {
            "merged-config-to-mainlog": "enable",
            "merged-config-to-custom-file": "disable"
            },
        "dhcpd-options": {
            "ztp-tftp-address": {
                "code": 150,
                "type": "ip-address"
                }
            }
        }
        for key in newconfigkeys:                                              # pylint: disable=consider-using-dict-items
            if key not in list(config.running):
                # console("Adding (%s) to config schema" % key)
                console(f"Adding ({key}) to config schema")
                config.running.update({key: newconfigkeys[key]})
        config.save()
        try:
            import requests                                                    # pylint: disable=import-outside-toplevel, unused-import, redefined-outer-name
        except ImportError:
            console("\n\nInstalling some new dependencies...\n")
            subprocess.run(["pip", "install", "requests"], capture_output=False, check=True)
            subprocess.run(["pip", "install", "requests_toolbelt"], capture_output=False, check=True)

    def snmp_name_fix(self):
        # PSC - not sure what problem this fixes. only called by installer.
        console("\n\nChecking for incompatible SNMP OID names")
        changes = False
        for objname in dict(config.running["snmpoid"]):
            newobjname = objname.replace("-", "_")
            if newobjname != objname:
                changes = True
                # console("    Replacing SNMPOID name {} with {}".format(objname, newobjname))
                console(f"    Replacing SNMPOID name {objname} with {newobjname}")
                config.running["snmpoid"].update({newobjname: config.running["snmpoid"][objname]})
                del config.running["snmpoid"][objname]
        if changes:
            config.save()
        else:
            console("    Nothing to update")

    def copy_binary(self):
        binpath = "/bin/"
        binname = "ztp"
        subprocess.run(["cp", "ztp.py", f"{binpath}{binname}"], capture_output=False, check=True)
        subprocess.run(["chmod", "777", f"{binpath}{binname}"], capture_output=False, check=True)
        # console("Binary file installed at " + binpath + binname)
        console(f"Binary file installed at {binpath}{binname}")

    def create_configfile(self):
        config = json.loads(self.defaultconfig)                                # pylint: disable=redefined-outer-name
        rawconfig = json.dumps(config, indent=4, sort_keys=True)
        configfilepath = "/etc/ztp/"
        configfilename = "ztp.cfg"
        subprocess.run(["mkdir", "-p", configfilepath], capture_output=False, check=True)
        subprocess.run(["mkdir", "-p", f"{configfilepath}tftproot/"], capture_output=False, check=True)
        with open(f"{configfilepath}{configfilename}", "w", encoding="utf8") as f:
            f.write(rawconfig)
        # console("Config File Created at " + configfilepath + configfilename)
        console(f"Config File Created at {configfilepath}{configfilename}")

    def install_tftpy(self):
        console("\n\nInstalling tftpy via PIP...\n")
        subprocess.run(["pip", "install", "--break-system-packages", "--root-user-action=ignore", "tftpy"], capture_output=False, check=True)

    def disable_firewall(self):
        try:
            subprocess.run(["systemctl", "stop", "firewalld"], capture_output=False, check=True)
        except subprocess.CalledProcessError:
            console("Firewalld not running on system")
            return
        subprocess.run(["systemctl", "disable", "firewalld"], capture_output=False, check=True)
        console("Firewalld stopped and disabled")

    def install_dependencies(self):
        if osd._pkgmgr == "apt-get":  # If using apt-get, update the repos     # pylint: disable=protected-access
            subprocess.run(["sudo", "apt-get", "update", "-y"], capture_output=False, check=True)
        osd.install_pkg(osd.PIPPKG)
        osd.install_pkg("telnet")
        # apt installed python modules for modern "externally managed environments"
        osd.install_pkg("python3-pysnmp")
        osd.install_pkg("python3-requests")
        osd.install_pkg("python3-requests-toolbelt")
        osd.install_pkg("python3-jinja2")
        osd.install_pkg("python3-netaddr")
        osd.install_pkg("python3-netifaces")
        osd.install_pkg("python3-isc-dhcp-leases")

    def dhcp_setup(self):
        console("\n\nInstalling DHCPD...\n")
        osd.install_pkg(osd.DHCPPKG)
        osd.service_control("enable", osd.DHCPSVC)
        console("\n\nSucking in config file...\n")
        global config
        config = config_manager()
        console("\n\nRetrying Module Imports...")
        try:
            global netaddr
            global netifaces
            import netaddr                                                     # pylint: disable=import-outside-toplevel
            import netifaces                                                   # pylint: disable=import-outside-toplevel
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
        with open(installpath, "w", encoding="utf8") as f:                     # pylint: disable=possibly-used-before-assignment
            f.write(installfile)                                               # pylint: disable=possibly-used-before-assignment
        if systemd:
            osd.service_control("enable", "ztp")
            osd.service_control("start", "ztp")
        elif not systemd:
            subprocess.run(["chmod", "777", "/etc/init.d/radiuid"], capture_output=False, check=True)
            subprocess.run(["chkconfig", "radiuid", "on"], capture_output=False, check=True)
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
        COMPREPLY=( $(compgen -W "config run status version log downloads dhcpd provisioning" -- $cur) )
        ;;
      hidden)
        COMPREPLY=( $(compgen -W "reset-config show" -- $cur) )
        ;;
      "set")
        COMPREPLY=( $(compgen -W "suffix initialfilename community snmpoid initial-template tftproot imagediscoveryfile file-cache-timeout integration external-keystore template external-template keystore idarray association default-keystore global-keystore default-template imagefile image-supression delay-keystore dhcpd-option dhcpd logging" -- $cur) )
        ;;
      "clear")
        COMPREPLY=( $(compgen -W "keystore idarray snmpoid integration external-keystore template external-template association dhcpd-option dhcpd log downloads provisioning" -- $cur) )
        ;;
      "request")
        COMPREPLY=( $(compgen -W "merge-test initial-merge default-keystore-test snmp-test dhcp-option-125 dhcpd-commit auto-dhcpd ipc-console integration-setup integration-test external-keystore-test keystore-csv-export" -- $cur) )
        ;;
      "service")
        COMPREPLY=( $(compgen -W "start stop restart status freeztp dhcpd all" -- $cur) )
        ;;
      *)
        ;;
    esac
  elif [ $COMP_CWORD -eq 3 ]; then
    case "$prev" in
      show)
        if [ "$prev2" == "hidden" ]; then
          COMPREPLY=( $(compgen -W "keystores keys idarrays idarray idarray-nameoptions snmpoids templates external-templates associations all_ids imagefiles dhcpd-options dhcpd-option-types dhcpd-option dhcpd-scopes integrations integration-types integration-opts integration-keys external-keystores external-keystore-types external-keystore-opts external-keystore-keys" -- $cur) )
        fi
        ;;
      freeztp)
        if [ "$prev2" == "service" ]; then
          COMPREPLY=( $(compgen -W "start stop restart" -- $cur) )
        fi
        ;;
      all)
        if [ "$prev2" == "service" ]; then
          COMPREPLY=( $(compgen -W "start stop restart" -- $cur) )
        fi
        ;;
      config)
        if [ "$prev2" == "show" ]; then
          COMPREPLY=( $(compgen -W "raw -" -- $cur) )
        fi
        ;;
      run)
        if [ "$prev2" == "show" ]; then
          COMPREPLY=( $(compgen -W "raw -" -- $cur) )
        fi
        ;;
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
      file-cache-timeout)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "<timeout_in_seconds> -" -- $cur) )
        fi
        ;;
      snmpoid)
        local oids=$(for k in `ztp hidden show snmpoids`; do echo $k ; done)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "${oids} <name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          COMPREPLY=( $(compgen -W "${oids}" -- $cur) )
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
      integration)
        local integrations=$(for k in `ztp hidden show integrations`; do echo $k ; done)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "${integrations} <svc_name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          COMPREPLY=( $(compgen -W "${integrations}" -- $cur) )
        fi
        ;;
      external-keystore)
        local exkeystores=$(for k in `ztp hidden show external-keystores`; do echo $k ; done)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "${exkeystores} <store_name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          COMPREPLY=( $(compgen -W "${exkeystores}" -- $cur) )
        fi
        ;;
      template)
        local templates=$(for k in `ztp hidden show templates`; do echo $k ; done)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "${templates} <template_name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          COMPREPLY=( $(compgen -W "${templates}" -- $cur) )
        fi
        ;;
      external-template)
        local templates=$(for k in `ztp hidden show external-templates`; do echo $k ; done)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "${templates} <template_name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          COMPREPLY=( $(compgen -W "${templates}" -- $cur) )
        fi
        ;;
      keystore)
        local ids=$(for id in `ztp hidden show keystores`; do echo $id ; done)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "${ids} <new_id_or_arrayname> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
        fi
        ;;
      idarray)
        if [ "$prev2" == "set" ]; then
          local options=$(for id in `ztp hidden show idarray-nameoptions`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${options} <new_array_name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          local arrays=$(for id in `ztp hidden show idarrays`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${arrays}" -- $cur) )
        fi
        ;;
      association)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "id" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          local asso=$(for id in `ztp hidden show associations`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${asso}" -- $cur) )
        fi
        ;;
      default-keystore)
        if [ "$prev2" == "set" ]; then
          local ids=$(for id in `ztp hidden show keystores`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${ids} <keystore-id> None" -- $cur) )
        fi
        ;;
      global-keystore)
        if [ "$prev2" == "set" ]; then
          local ids=$(for id in `ztp hidden show keystores`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${ids} <keystore-id> None" -- $cur) )
        fi
        ;;
      default-template)
        if [ "$prev2" == "set" ]; then
          local templates=$(for k in `ztp hidden show templates`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "${templates} <template_name> None" -- $cur) )
        fi
        ;;
      imagefile)
        if [ "$prev2" == "set" ]; then
          local ids=$(for id in `ztp hidden show imagefiles`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${ids} <binary_image_file_name> -" -- $cur) )
        fi
        ;;
      image-supression)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "<seconds-to-supress> -" -- $cur) )
        fi
        ;;
      delay-keystore)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "<msec-to-delay> -" -- $cur) )
        fi
        ;;
      dhcpd-option)
        if [ "$prev2" == "set" ]; then
          local ids=$(for id in `ztp hidden show dhcpd-options`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${ids} <opt-name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          local ids=$(for id in `ztp hidden show dhcpd-options`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
        fi
        ;;
      dhcpd)
        if [ "$prev2" == "show" ]; then
          COMPREPLY=( $(compgen -W "leases" -- $cur) )
        fi
        if [ "$prev2" == "service" ]; then
          COMPREPLY=( $(compgen -W "start stop restart" -- $cur) )
        fi
        if [ "$prev2" == "set" ]; then
          local ids=$(for id in `ztp hidden show dhcpd-scopes`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${ids} <new_dhcp_scope_name> -" -- $cur) )
        fi
        if [ "$prev2" == "clear" ]; then
          local ids=$(for id in `ztp hidden show dhcpd-scopes`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${ids}" -- $cur) )
        fi
        ;;
      logging)
        if [ "$prev2" == "set" ]; then
          COMPREPLY=( $(compgen -W "merged-config-to-mainlog merged-config-to-custom-file" -- $cur) )
        fi
        ;;
      merge-test)
        local ids=$(for id in `ztp hidden show keystores`; do echo $id ; done)
        local mems=$(for id in `ztp hidden show idarray members`; do echo $id ; done)
        if [ "$prev2" == "request" ]; then
          COMPREPLY=( $(compgen -W "${ids} ${mems}" -- $cur) )
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
      integration-setup)
        if [ "$prev2" == "request" ]; then
          local objs=$(for id in `ztp hidden show integrations`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${objs} <svc_name> -" -- $cur) )
        fi
        ;;
      integration-test)
        if [ "$prev2" == "request" ]; then
          local objs=$(for id in `ztp hidden show integrations`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${objs} <svc_name> -" -- $cur) )
        fi
        ;;
      external-keystore-test)
        if [ "$prev2" == "request" ]; then
          local objs=$(for id in `ztp hidden show external-keystores`; do echo $id ; done)
          COMPREPLY=( $(compgen -W "${objs} <store_name> -" -- $cur) )
        fi
        ;;
      keystore-csv-export)
        if [ "$prev2" == "request" ]; then
          COMPREPLY=( $(compgen -W "<file_name> -" -- $cur) )
        fi
        ;;
      *)
        ;;
    esac
  elif [ $COMP_CWORD -eq 4 ]; then
    prev3=${COMP_WORDS[COMP_CWORD-3]}
    if [ "$prev2" == "keystore" ]; then
      local idkeys=$(for k in `ztp hidden show keys $prev`; do echo $k ; done)
      if [ "$prev3" == "set" ]; then
        COMPREPLY=( $(compgen -W "${idkeys} <new_key> -" -- $cur) )
      fi
      if [ "$prev3" == "clear" ]; then
        COMPREPLY=( $(compgen -W "${idkeys} all" -- $cur) )
      fi
    fi
    if [ "$prev2" == "show" ]; then
      if [ "$prev3" == "hidden" ]; then
        if [ "$prev" == "idarray" ]; then
          COMPREPLY=( $(compgen -W "members" -- $cur) )
        fi
        if [ "$prev" == "keys" ]; then
          local keystores=$(for k in `ztp hidden show keystores`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "${keystores} <keystore> -" -- $cur) )
        fi
        if [ "$prev" == "integration-opts" ]; then
          local integrations=$(for k in `ztp hidden show integrations`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "${integrations} <svc_name> -" -- $cur) )
        fi
        if [ "$prev" == "integration-keys" ]; then
          local integrations=$(for k in `ztp hidden show integrations`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "${integrations} <svc_name> -" -- $cur) )
        fi
        if [ "$prev" == "dhcpd-option" ]; then
          local options=$(for k in `ztp hidden show dhcpd-options`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "${options} -" -- $cur) )
        fi
      fi
    fi
    if [ "$prev2" == "integration" ]; then
      local keys=$(for k in `ztp hidden show integration-keys $prev`; do echo $k ; done)
      if [ "$prev3" == "set" ]; then
        local opts=$(for k in `ztp hidden show integration-opts $prev`; do echo $k ; done)
        COMPREPLY=( $(compgen -W "${opts} ${keys} type" -- $cur) )
      fi
      if [ "$prev3" == "clear" ]; then
        COMPREPLY=( $(compgen -W "${keys} all -" -- $cur) )
      fi
    fi
    if [ "$prev2" == "external-keystore" ]; then
      local keys=$(for k in `ztp hidden show external-keystore-keys $prev`; do echo $k ; done)
      if [ "$prev3" == "set" ]; then
        local opts=$(for k in `ztp hidden show external-keystore-opts $prev`; do echo $k ; done)
        COMPREPLY=( $(compgen -W "${opts} ${keys} type" -- $cur) )
      fi
      if [ "$prev3" == "clear" ]; then
        COMPREPLY=( $(compgen -W "${keys} all -" -- $cur) )
      fi
    fi
    if [ "$prev2" == "idarray" ]; then
      if [ "$prev3" == "set" ]; then
        COMPREPLY=( $(compgen -W "<real_id> -" -- $cur) )
      fi
    fi
    if [ "$prev2" == "log" ]; then
      if [ "$prev3" == "show" ]; then
        COMPREPLY=( $(compgen -W "<num_of_lines> -" -- $cur) )
      fi
    fi
    if [ "$prev2" == "snmpoid" ]; then
      if [ "$prev3" == "set" ]; then
        COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
      fi
    fi
    if [ "$prev2" == "template" ]; then
      if [ "$prev3" == "set" ]; then
        COMPREPLY=( $(compgen -W "<end_char> -" -- $cur) )
      fi
    fi
    if [ "$prev2" == "external-template" ]; then
      if [ "$prev3" == "set" ]; then
        COMPREPLY=( $(compgen -W "file" -- $cur) )
      fi
    fi
    if [ "$prev2" == "association" ]; then
      if [ "$prev3" == "set" ]; then
        local allids=$(for k in `ztp hidden show all_ids`; do echo $k ; done)
        COMPREPLY=( $(compgen -W "<id/arrayname> ${allids} -" -- $cur) )
      fi
    fi
    if [ "$prev2" == "dhcpd-option" ]; then
      if [ "$prev3" == "set" ]; then
        COMPREPLY=( $(compgen -W "code" -- $cur) )
      fi
    fi
    if [ "$prev2" == "dhcpd" ]; then
      if [ "$prev3" == "set" ]; then
        local options=$(for k in `ztp hidden show dhcpd-options`; do echo $k ; done)
        COMPREPLY=( $(compgen -W "${options} subnet first-address last-address gateway dns-servers domain-name lease-time imagediscoveryfile-option" -- $cur) )
      fi
      if [ "$prev3" == "show" ]; then
        COMPREPLY=( $(compgen -W "current all raw" -- $cur) )
      fi
    fi
    if [ "$prev2" == "logging" ]; then
      if [ "$prev3" == "set" ]; then
        if [ "$prev" == "merged-config-to-mainlog" ]; then
          COMPREPLY=( $(compgen -W "enable disable" -- $cur) )
        fi
        if [ "$prev" == "merged-config-to-custom-file" ]; then
          COMPREPLY=( $(compgen -W "<filepath> disable" -- $cur) )
        fi
      fi
    fi
  elif [ $COMP_CWORD -eq 5 ]; then
    prev3=${COMP_WORDS[COMP_CWORD-3]}
    prev4=${COMP_WORDS[COMP_CWORD-4]}
    if [ "$prev4" == "set" ]; then
      if [ "$prev3" == "keystore" ]; then
        COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
      fi
      if [ "$prev3" == "dhcpd-option" ]; then
        COMPREPLY=( $(compgen -W "<1-254> -" -- $cur) )
      fi
    fi
    if [ "$prev4" == "set" ]; then
      if [ "$prev3" == "integration" ]; then
        if [ "$prev" == "type" ]; then
          local types=$(for k in `ztp hidden show integration-types`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "${types}" -- $cur) )
        else
          COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
        fi
      fi
    fi
    if [ "$prev4" == "set" ]; then
      if [ "$prev3" == "external-keystore" ]; then
        if [ "$prev" == "type" ]; then
          local types=$(for k in `ztp hidden show external-keystore-types`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "${types}" -- $cur) )
        else
          COMPREPLY=( $(compgen -W "<value> -" -- $cur) )
        fi
      fi
    fi
    if [ "$prev4" == "set" ]; then
      if [ "$prev3" == "association" ]; then
        COMPREPLY=( $(compgen -W "template" -- $cur) )
      fi
    fi
    if [ "$prev4" == "set" ]; then
      if [ "$prev3" == "external-template" ]; then
        COMPREPLY=( $(compgen -W "<filepath> -" -- $cur) )
      fi
    fi
    if [ "$prev4" == "set" ]; then
      if [ "$prev3" == "dhcpd" ]; then
        if [ "$prev" == "subnet" ]; then
          COMPREPLY=( $(compgen -W "<ipv4_subnet_value> -" -- $cur) )
        elif [ "$prev" == "first-address" ]; then
          COMPREPLY=( $(compgen -W "<first_address_to_lease> -" -- $cur) )
        elif [ "$prev" == "last-address" ]; then
          COMPREPLY=( $(compgen -W "<last_address_to_lease> -" -- $cur) )
        elif [ "$prev" == "gateway" ]; then
          COMPREPLY=( $(compgen -W "<gateway_ipv4_address> -" -- $cur) )
        elif [ "$prev" == "dns-servers" ]; then
          COMPREPLY=( $(compgen -W "<first_dns_ipv4_address> 8.8.8.8" -- $cur) )
        elif [ "$prev" == "domain-name" ]; then
          COMPREPLY=( $(compgen -W "<dns_search_domain> -" -- $cur) )
        elif [ "$prev" == "lease-time" ]; then
          COMPREPLY=( $(compgen -W "<lease_time_in_seconds> -" -- $cur) )
        elif [ "$prev" == "imagediscoveryfile-option" ]; then
          COMPREPLY=( $(compgen -W "enable disable" -- $cur) )
        else
          local typ=$(for k in `ztp hidden show dhcpd-option $prev`; do echo $k ; done)
          COMPREPLY=( $(compgen -W "<${typ}> -" -- $cur) )
        fi
      fi
    fi
  elif [ $COMP_CWORD -eq 6 ]; then
    prev4=${COMP_WORDS[COMP_CWORD-4]}
    prev5=${COMP_WORDS[COMP_CWORD-5]}
    if [ "$prev5" == "set" ]; then
      if [ "$prev4" == "association" ]; then
        local templates=$(for k in `ztp hidden show templates`; do echo $k ; done)
        COMPREPLY=( $(compgen -W "<template_name> ${templates} -" -- $cur) )
      fi
      if [ "$prev4" == "dhcpd-option" ]; then
        COMPREPLY=( $(compgen -W "type" -- $cur) )
      fi
    fi
  elif [ $COMP_CWORD -eq 7 ]; then
    prev5=${COMP_WORDS[COMP_CWORD-5]}
    prev6=${COMP_WORDS[COMP_CWORD-6]}
    if [ "$prev6" == "set" ]; then
      if [ "$prev5" == "dhcpd-option" ]; then
        local typs=$(for k in `ztp hidden show dhcpd-option-types`; do echo $k ; done)
        COMPREPLY=( $(compgen -W "${typs}" -- $cur) )
      fi
    fi
  fi
  return 0
} &&
complete -F _ztp_complete ztp &&
bind 'set show-all-if-ambiguous on'"""
        ##### BASH SCRIPT DATA STOP #####

        ##### Remove legacy script file #####
        if os.path.isfile('/etc/profile.d/ztp-complete.sh'):
            console("Legacy completion file detected at /etc/profile.d/ztp-complete.sh... Removing...")
            os.remove('/etc/profile.d/ztp-complete.sh')
            console("    Removed!")

        ##### Place script file #####
        installpath = '/etc/bash_completion.d/ztp_completion'
        with open(installpath, "w", encoding="utf8") as f:
            f.write(bash_complete_script)
        subprocess.run(["chmod", "777", "/etc/bash_completion.d/ztp_completion"], capture_output=False, check=True)
        console("Auto-complete script installed to /etc/bash_completion.d/ztp_completion")

        ##### Run script file from profile #####
        rcfilepath = os.path.join(os.path.expanduser("~") , ".bashrc")
        with open(rcfilepath, "r", encoding="utf8") as f:
            rcfile = f.read()
        if "source /etc/bash_completion.d/ztp_completion" not in rcfile:
            # console("Adding completion file to user profile in {}".format(rcfilepath))
            console(f"Adding completion file to user profile in {rcfilepath}")
            with open(rcfilepath, "a", encoding="utf8") as f:
                f.write("\n\n\n# FreeZTP BASH Completion\nsource /etc/bash_completion.d/ztp_completion")

def make_table(columnorder, tabledata):                                        # pylint: disable=too-many-locals
    ##### Check and fix input type #####
    if type(tabledata) != type([]): # If tabledata is not a list               # pylint: disable=unidiomatic-typecheck
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
    for columnwidth in datalengthdict: # For each of the longest column values # pylint: disable=consider-using-dict-items
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


class tracking_class:
    def __init__(self, client=False):
        self._master = {}
        self.store = persistent_store("tracking")
        self.provdb = persistent_store("provisioning")
        self.files = []
        if not client:
            self.status = self.store.recall()
            self.mthread = threading.Thread(target=self._maintenance)
            self.mthread.daemon = True
            self.mthread.start()
            self.ipc_server()

    def find_session(self, args):
        for session in self._master:                                           # pylint: disable=consider-using-dict-items
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
                filename = args["filename"]
                ip = args["ipaddr"]
                # log("tracking_class.report: New transfer of (%s) from (%s) detected" % (filename, ip))
                log(f"tracking_class.report: New transfer of ({filename}) from ({ip}) detected")
                self._master.update({time.time(): self.request_class(args, self)})

    def _maintenance(self):
        self.sthread = threading.Thread(target=self._maintain_store)           # pylint: disable=attribute-defined-outside-init
        self.sthread.daemon = True
        self.sthread.start()
        while True:
            time.sleep(1)
            if not self.sthread.is_alive():
                log("tracking_class._maintenance: Maintenance thread died. Restarting")
                self.sthread = threading.Thread(target=self._maintain_store)   # pylint: disable=attribute-defined-outside-init
                self.sthread.daemon = True
                self.sthread.start()

    def _maintain_store(self):
        while True:
            time.sleep(10)
            ### Update all downloads in memory (self._master)
            for session in self._master:                                       # pylint: disable=consider-using-dict-items
                self._master[session].update_percent()
                self._master[session].update_rate()
                data = {
                    "time": self._master[session].friendlytime,
                    "ipaddr": self._master[session].ipaddr,
                    "ports": self._master[session].ports,
                    "filename": self._master[session].filename,
                    "position": self._master[session].position,
                    "bytessent": self._master[session].position,
                    "active": self._master[session].active,
                    "filesize": self._master[session].filesize,
                    "percent": self._master[session].percent,
                    "rate": self._master[session].rate
                }
                self.status.update({session: data})
            ### Mark any old downloads in store (and not in mem) as dead
            for session in self.status:
                if session not in self._master:
                    self.status[session]["active"] = False
            self.store(self.status)

    class request_class:
        def __init__(self, args, parent):
            self.ipaddr = None
            self.ports = {}
            self.filename = None
            self.position = 0
            self.last_position = 0
            self.parent = parent
            self.active = True
            self.threads = []
            self.filesize = None
            self.file = None
            self.percent = None
            self.rate = 0
            self.creation = time.time()
            self.friendlytime = time.strftime("%Y-%m-%d %H:%M:%S")
            self.lastupdate = self.creation
            self._inactivity_timeout(30)
            self.update(args)

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
                        if not self.filesize:
                            self.filename = args[arg]
                            self.check_file()
                    elif arg == "position":
                        self.position = args[arg]
                    elif arg == "filesize":
                        self.filesize = args[arg]
                    elif arg == "file":
                        self.file = args[arg]

        def _inactivity_timeout(self, seconds, thread=False):
            if not thread:  #If not started in a thread, restart in a thread
                thread = threading.Thread(target=self._inactivity_timeout,
                    args=(seconds, True))
                thread.daemon = True
                thread.start()
                self.threads.append(thread)  # Add to list of session threads
                return None

            while True:
                if not self.active:  # If this session is no longer inactive
                    return None  # Return and stop the thread

                if time.time() - self.lastupdate > seconds:
                    # If there has been no activity
                    # in the timeout period
                    self.active = False  # Mark session as inactive
                time.sleep(0.1)  # Sleep for .1 seconds

        def check_file(self):
            path = config.running["tftproot"]+self.filename
            if os.path.isfile(path):
                self.filesize = os.path.getsize(path)

        def update_percent(self):
            if self.filesize:
                percent = round(100.0*self.position/self.filesize, 4)
                if percent > 100:
                    self.percent = 100.00
                else:
                    self.percent = percent

        def update_rate(self):
            diff = self.position - self.last_position
            rate = diff * 8
            if rate > 1000000:
                self.rate = str(rate/1000000.0) + " Mbps"
            elif rate > 1000:
                self.rate = str(rate/1000.0) + " Kbps"
            else:
                self.rate = str(rate) + " bps"
            self.last_position = self.position

    class dhcplease_class:
        def __init__(self):
            global isc
            global datetime
            import isc_dhcp_leases as isc                                      # pylint: disable=import-outside-toplevel
            import datetime                                                    # pylint: disable=import-outside-toplevel
            self.leasesobj = isc.IscDhcpLeases(osd.DHCPLEASES)

        def utc_to_local(self, dt):
            if time.localtime().tm_isdst:
                return dt - datetime.timedelta(seconds = time.altzone)

            return dt - datetime.timedelta(seconds = time.timezone)

        def get(self, mode="current"):
            index = 0
            result = {}
            if mode == "current":
                leases = self.leasesobj.get_current()
                for lease in leases:                                           # pylint: disable=consider-using-dict-items
                    result.update({index: self._format_lease(leases[lease])})
                    index += 1
                return result

            leases = self.leasesobj.get()
            for lease in leases:
                result.update({index: self._format_lease(lease)})
                index += 1
            return result

        def _format_lease(self, lease):
            try:
                uid = lease.data["uid"]
            except KeyError:
                uid = None
            result = {
                "ip": lease.ip,
                "ethernet": lease.ethernet,
                "hostname": lease.hostname,
                "state": lease.binding_state,
                "start": self.utc_to_local(lease.start).strftime("%Y-%m-%d %H:%M:%S"),
                "end": self.utc_to_local(lease.end).strftime("%Y-%m-%d %H:%M:%S"),
                "uid": uid
            }
            return result

    def show_downloads(self, args):                                            # pylint: disable=unused-argument
        data = []
        d = self.store.recall()
        dlist = list(d)
        dlist.sort(reverse=True)
        for dload in dlist:
            data.append(d[dload])

        return make_table(['time', 'ipaddr', 'filename', 'filesize', 'bytessent', 'percent', 'rate', 'active'], data)

    class screen:                                                              # pylint: disable=too-few-public-methods
        def __init__(self):
            self.win = curses.initscr()
            curses.noecho()
            curses.cbreak()

        def write(self, data):
            linelist = data.split("\n")
            index = 0
            #self.win.clear()
            for line in linelist:
                self.win.addstr(index, 0, line)
                index += 1
            self.win.refresh()

    def clear_downloads(self, nested=False):
        self._master = {}
        self.status = {}
        if not nested:
            try:
                client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                console("Service Running. Clearing downloads with IPC")
                client.connect(('localhost', 10000))
                time.sleep(0.1)
                client.send("clear downloads\n".encode("utf-8"))
                time.sleep(0.1)
                client.send("exit\n".encode("utf-8"))
                time.sleep(0.1)
                client.close()
            except socket.error:
                console("Service not running. Clearing store.")
        self.store({})

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
            client, addr = sock.accept()                                       # pylint: disable=unused-variable
            thread = threading.Thread(target=self._status_ipc_talker, args=(client,))
            thread.start() # Start talker thread to listen to port

    def _status_ipc_talker(self, client):
        while True:
            recv = client.recv(1024)
            recieve = recv.decode("utf-8")
            if len(recieve) > 0:
                if "?" in recieve:
                    table = """
- threads
- clear downloads
- clear provisioning
- get downloads
- exit
"""
                    client.send(table.encode("utf-8"))
                elif "exit" in recieve:
                    client.close()
                    return
                elif "threads" in recieve:
                    client.send(str(threading.active_count()).encode("utf-8"))  # Send the query response
                    client.send(str(threading.enumerate()).encode("utf-8"))
                elif "clear downloads" in recieve:
                    self.clear_downloads(nested=True)
                    msg = json.dumps(self.status, indent=4, sort_keys=True)+"\n"
                    client.send(msg.encode("utf-8"))  # Send the query response
                elif "get downloads" in recieve:
                    msg = json.dumps(self.status, indent=4, sort_keys=True)+"\n"
                    client.send(msg.encode("utf-8"))  # Send the query response
                elif "clear provisioning" in recieve:
                    self.clear_provisioning(nested=True)
                    msg = json.dumps(self.provdb.recall(), indent=4, sort_keys=True)+"\n"
                    client.send(msg.encode("utf-8"))  # Send the query response
                else:
                    client.send("ZTP#".encode("utf-8"))  # Send the query response

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
        client.send("get downloads\n")
        time.sleep(0.1)
        d = client.recv(100000)
        d = json.loads(d)
        dlist = list(d)
        dlist.sort(reverse=True)
        for dload in dlist[:20]:
            data.append(d[dload])
        return make_table(['time', 'ipaddr', 'filename', 'filesize', 'bytessent', 'percent', 'rate', 'active'], data)

    def show_downloads_live(self, args):                                       # pylint: disable=unused-argument
        s = self.screen()
        ani = self._gen_animation()
        client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        client.connect(('localhost', 10000))
        try:
            index = 0                                                          # pylint: disable=unused-variable
            while True:
                table = self.get_live_status(client)
                s.write(table+next(ani))
        except:                                                                # pylint: disable=bare-except
            curses.echo()
            curses.nocbreak()
            curses.endwin()
            # quit()
            sys.exit()

    def show_dhcp_leases(self, mode="current"):
        dleases = self.dhcplease_class()
        leases = dleases.get(mode)
        data = []
        for lease in leases:                                                   # pylint: disable=consider-using-dict-items
            data.append(leases[lease])
        return make_table(['ethernet', 'ip', 'start', 'end', 'state', 'uid'], data)

    def check_integrations(self, provdata):
        if provdata["Status"] == "Complete":
            message = integration_message({
                "ip": provdata["IP Address"],
                "tempid": provdata["Temp ID"],
                "mac": provdata["MAC Address"],
                "realid": provdata["Real IDs"],
                "keystore": provdata["Matched Keystore"],
                "status": "Complete",
                "file": None
                })
            integrations.send(message)                                         # pylint: disable=used-before-assignment

    def provision(self, data):
        current = self.provdb.recall()
        for tstamp in current:  # For each ID in provdb
            if data["Temp ID"] == current[tstamp]["Temp ID"]:  # If the temp IDs match
                for attrib in data:  # For each reported attribute
                    if data[attrib]:  # If the attribute has a value
                        current[tstamp][attrib] = data[attrib]  # Update the provdb
                self.provdb(current)
                self.check_integrations(current[tstamp])

                return  # Return to prevent further execution

        # To prevent multiple provdb entries when multiple requests
        for tstamp in current:                                                 # pylint: disable=too-many-nested-blocks
            if "IP Address" in data:
                if data["IP Address"] == current[tstamp]["IP Address"]:
                    if data["Timestamp"] - current[tstamp]["Timestamp"] < 60:
                        for attrib in data:  # For each reported attribute
                            if data[attrib]:  # If the attribute has a value
                                current[tstamp][attrib] = data[attrib]  # Update the provdb
                        self.provdb(current)
                        self.check_integrations(current[tstamp])

                        return  # Return to prevent further execution

        # If the tempid was not in provdb
        dhcpinfo = self.prov_get_mac(data["IP Address"])
        if dhcpinfo:
            data["MAC Address"] = dhcpinfo[0]
        current.update({data["Timestamp"]: data})  # Add the entry with data
        self.provdb(current)

    def clear_provisioning(self, nested=False):
        self.provdb({})
        if not nested:
            try:
                console("Service Running. Clearing provisioning with IPC")
                client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                client.connect(('localhost', 10000))
                client.send("clear provisioning\n".encode("utf-8"))
                client.send("exit\n".encode("utf-8"))
                client.close()
            except socket.error:
                console("Service not running. Clearing provisioning.")
        self.store({})

    def show_provisioning(self):
        data = self.provdb.recall()
        tabledata = []

        tlist = []
        for timestamp in data:
            tlist.append(timestamp)
        tlist.sort(reverse=True)

        for each in tlist:
            if type(data[each]["Real IDs"]) == type({}):                       # pylint: disable=unidiomatic-typecheck
                real = ""
                for id in data[each]["Real IDs"]:                              # pylint: disable=redefined-builtin
                    if data[each]["Real IDs"][id]:
                        if real == "":
                            real += data[each]["Real IDs"][id]
                        else:
                            real += "," + data[each]["Real IDs"][id]
                data[each]["Real IDs"] = real
            data[each]["Timestamp"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data[each]["Timestamp"]))
            tabledata.append(data[each])
        return make_table(["Timestamp", "IP Address", "Temp ID", "MAC Address", "Real IDs", "Matched Keystore", "Status"], tabledata)

    def prov_get_mac(self, ip):
        dleases = self.dhcplease_class()
        leases = dleases.get("current")
        for lease in leases:                                                   # pylint: disable=consider-using-dict-items
            if leases[lease]["ip"] == ip:
                mac = leases[lease]["ethernet"]
                uid = leases[lease]["uid"]
                return [mac, uid]
        return None

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
        rawout = json.dumps(fulldb, indent=4, sort_keys=False)
        with open(self._file, "w", encoding="utf8") as f:
            f.write(rawout)

    def _create_blank(self):
        with open(self._file, "w", encoding="utf8") as f:
            f.write("{}")

    def _read(self):
        try:
            data = self._pull_full_db()
            try:
                self._running = data[self._dbid]
            except KeyError:
                self._write()
        except Exception as e:                                                 # pylint: disable=broad-exception-caught
            log("persistent_store: ERROR: Error in reading from store file")
            log("persistent_store: ERROR: " + str(e))

    def _pull_full_db(self):
        try:
            with open(self._file, "r", encoding="utf8") as f:
                rawdata = f.read()

        except IOError:
            self._create_blank()
            with open(self._file, "r", encoding="utf8") as f:
                rawdata = f.read()

        result = json.loads(rawdata)
        return result

class integration_spark:
    name = "spark"
    options = ["api-key", "roomId", "toPersonEmail", "toPersonId"]
    def __init__(self, cfg, setup=False):
        global requests
        global MultipartEncoder
        import requests                                                        # pylint: disable=import-outside-toplevel
        from requests_toolbelt import MultipartEncoder                         # pylint: disable=import-outside-toplevel
        self.config = cfg
        if not setup:
            self.me = self._get("https://api.ciscospark.com/v1/people/me")

    def _get(self, url, payload=None):
        headers = {'Authorization': "Bearer "+self.config["api-key"], 'Content-Type': 'application/json'}
        response = requests.get(url=url, headers=headers, params=payload, timeout=30)
        return self._decode(response)

    def _post(self, url, payload):
        payload = MultipartEncoder(fields=payload)
        headers = {'Authorization': "Bearer "+self.config["api-key"], 'Content-Type': payload.content_type}
        response = requests.post(url=url, headers=headers, data=payload, timeout=30)
        return self._decode(response)

    def _decode(self, response):
        if response.status_code == 200:
            try:
                return json.loads(response.text)
            except Exception as e:                                             # pylint: disable=broad-exception-caught
                console(e)
                return None
        else:
            raise ValueError(f"Invalid Server Response Status Code: ({str(response.status_code)})\n({response.text})")

    def _rooms(self):
        return self._get("https://api.ciscospark.com/v1/rooms")

    def _get_destination(self):
        for option in self.options[1:]:
            if option in self.config:
                return {option: self.config[option]}
        return None

    def send(self, message):
        import io                                                              # pylint: disable=import-outside-toplevel
        # log("integration_spark.send: Processing message for object (%s)" % self.config["objname"])
        log(f"integration_spark.send: Processing message for object ({self.config["objname"]})")
        data = self._get_destination()
        if not data:
            raise ValueError("Invalid or Unknown Integration Destination")
        if message.file is not None:
            sendfile = io.StringIO(message.file.data)
            # data.update({'files': ("{}.txt".format(message.file.filename), sendfile, "text/plain")})
            data.update({'files': (f"{message.file.filename}.txt", sendfile, "text/plain")})
        txtmsg = f"""------------------------------
## **FreeZTP Provisioning ({self.config["objname"]})**
- Timestamp: **{message.timestamp}**
- IP: **{message.ip}**
- Temp ID: **{message.tempid}**
- MAC Address: **{message.mac}**
- Real ID: **{message.realid}**
- Matched Keystore: **{message.keystore}**
------------------------------"""
        data.update({"markdown": txtmsg})
        _ = self._post("https://api.ciscospark.com/v1/messages", data)
        # log("integration_spark.send: Message delivery for (%s) complete" % self.config["objname"])
        log(f"integration_spark.send: Message delivery for ({self.config["objname"]}) complete")

    def setup(self):
        console("""
        Spark Integration Wizard Overview:
        -----------------------------------------------------------------------
            You must provide an API key (api-key). Once that is provided, you can select
            one of the below destinations for your update messages:
                - roomId
                - toPersonEmail
                - toPersonId""")
        akey = input("Enter your Cisco Spark API Key > ")
        self.config.update({"api-key": akey})  # Update API key entry
        console("Testing API Key:")
        console(make_table(["displayName", "emails"], [self._get("https://api.ciscospark.com/v1/people/me")])+"\n\n")
        opts = [{"destination type": entry} for entry in self.options[1:]]
        dtype = integrations.table_select(["destination type"], opts, "Select a Destination Type")
        if dtype["destination type"] == "roomId":
            rooms = self._rooms()["items"]
            selection = integrations.table_select(["title"], rooms, "Select a Room")
            value = selection["id"]
        elif dtype["destination type"] == "toPersonEmail":
            value = input(f"Enter the {dtype["destination type"]} value > ")
        elif dtype["destination type"] == "toPersonId":
            value = input(f"Enter the {dtype["destination type"]} value > ")
        self.config.update({dtype["destination type"]: value})                 # pylint: disable=possibly-used-before-assignment
        return self.config

class integration_power_automate:
    name = 'powerautomate'
    options = ['url']
    def __init__(self, cfg, setup=False):                                      # pylint: disable=unused-argument
        global requests
        global MultipartEncoder
        import requests                                                        # pylint: disable=import-outside-toplevel
        from requests_toolbelt import MultipartEncoder                         # pylint: disable=import-outside-toplevel
        self.config = cfg
        self.appfilename = (os.path.basename(__file__).lower())
        self.hostfqdn = (socket.getfqdn().lower())
        self.src_id = self.appfilename + '.' + self.hostfqdn
        self.msgtype = 'status'

    def _post(self, url, payload):
        headers = {'Content-Type': 'application/json'}
        data = json.dumps(payload)
        response = requests.post(url=url, headers=headers, data=data, timeout=30)
        return self._decode(response)

    def _decode(self, response):
        if response.status_code in range (200,299):
            try:
                return json.loads(response.text)
            except Exception as e:                                             # pylint: disable=broad-exception-caught
                console(e)
                return None
        else:
            raise ValueError(f"Invalid Server Response Status Code: ({str(response.status_code)})\n({response.text})")

    def send(self, message):
        # log("integration_power_automate.send: Processing message for object (%s)" % self.config["objname"])
        log(f"integration_power_automate.send: Processing message for object ({self.config["objname"]})")
        msgdict = {}
        if not self.config['url']:
            log("integration_power_automate.send: ERROR: Invalid or Unknown Integration Destination")
            raise ValueError("Invalid or Unknown Integration Destination")
        if message.file is not None:
            msgdict.update({'file-data': message.file.data})
            msgdict.update({'file-name': f'{message.keystore}.txt'})
        htmlmsg = (
            '<p><strong>freeZTP Provisioning</strong></p>'
            '<ul><li>Matched Keystore: ' + message.keystore + '</li>'
            '<li>Real ID: ' + str(message.realid) + '</li>'
            '<li>IP: ' + message.ip + '</li>'
            '<li>Temp ID: ' + message.tempid + '</li></ul>'
            '<span style="display: none">'
        )
        msgdict.update({'message': htmlmsg})
        msgdict.update({'src-id': self.src_id})
        msgdict.update({'type': self.msgtype})
        _ = self._post(self.config['url'], msgdict)
        # log("integration_power_automate.send: Message delivery for (%s) complete" % self.config["objname"])
        log(f"integration_power_automate.send: Message delivery for ({self.config["objname"]}) complete")

    def setup(self):
        console(
            'Microsoft Power Automate Integration Wizard Overview:\r\n'
            '-----------------------------------------------------------------\r\n'
            'The flow trigger "When a HTTP request is received" will create\r\n'
            'an Azure Webhook URL. Please provide the URL. This integration\r\n'
            'sends a JSON string to the target URL in this format:\r\n'
            '{\r\n'
            '    "src-id": "<scriptname>.<hostfqdn>",\r\n'
            '    "type": "status",\r\n'
            '    "message": "[HTML Formatted Message]",\r\n'
            '    "file-name": "<keystore_id>.txt",\r\n'
            '    "file-data": "[Full Config Text]"\r\n'
            '}\r\n'
            '\r\n'
        )
        url = input("Enter your Power Automate Webhook URL.> ")
        self.config.update({"url": url})  # Update API key entry
        return self.config

class integration_message:                                                     # pylint: disable=too-few-public-methods
    def __init__(self, data={}):                                               # pylint: disable=dangerous-default-value
        self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.ip = None  # String
        self.tempid = None  # String
        self.mac = None  # String
        self.realid = None  # String
        self.keystore = None  # String
        self.status = None  # String
        self.file = None  # File-like object
        self.update(data)

    def update(self, data):
        for key in data:
            if key in self.__dict__:
                self.__dict__[key] = data[key]

class integration_main:
    mods = {
        integration_spark.name: integration_spark,
        integration_power_automate.name: integration_power_automate
    }
    def __init__(self):
        self.loaded = False
        self.targets = {}
        self._load()

    def _load(self):
        log("integration_main._load: Beginning load of integration objects. Make sure your internet connection is working properly.")
        for target in config.running["integrations"]:
            try:
                if "type" in config.running["integrations"][target]:
                    typ = config.running["integrations"][target]["type"]
                    if typ in self.mods:
                        cfg = {"objname":target}
                        cfg.update(config.running["integrations"][target])
                        self.targets.update({target: self.mods[typ](cfg)})
                        # log("integration_main._load: Integration object (%s) loaded to targets successfully" % target)
                        log(f"integration_main._load: Integration object ({target}) loaded to targets successfully")
                    else:
                        # log("integration_main._load: Integration object (%s) has unrecognized type (%s)! Cannot load object" % (target, typ))
                        log(f"integration_main._load: Integration object ({target}) has unrecognized type ({typ})! Cannot load object")
                else:
                    # log("integration_main._load: Integration object (%s) has no type! Cannot load object" % target)
                    log(f"integration_main._load: Integration object ({target}) has no type! Cannot load object")
            except Exception as e:                                             # pylint: disable=broad-exception-caught
                # log("integration_main._load: Error loading object (%s): %s" % (target, e))
                log(f"integration_main._load: Error loading object ({target}): {e}")

    def send(self, message, thread=False):
        if not thread:
            log("integration_main.send: Starting initialization thread to wait for files")
            t = threading.Thread(target=self.send, args=(message,True))
            t.daemon = True
            t.start()
        else:
            found = False
            while not found:
                for file in tracking.files:
                    if message.tempid in file.filename:
                        message.file = file
                        found = True
                time.sleep(1)
            for target in self.targets:                                        # pylint: disable=consider-using-dict-items
                # log("integration_main.send: Kicking off thread for integration (%s)" % target)
                log(f"integration_main.send: Kicking off thread for integration ({target})")
                thread = threading.Thread(target=self.targets[target].send, args=(message,))
                thread.daemon = True
                thread.start()

    def table_select(self, columnorder, tabdata, message):
        index = 1
        lookup = {}
        for option in tabdata:
            option.update({"#": str(index)})
            lookup.update({str(index): option})
            index += 1
        columnorder = ["#"] + columnorder
        console(make_table(columnorder, tabdata))
        selection = input(message+" [1] ")
        if not selection:
            selection = "1"
        elif selection not in lookup:
            # console("Invalid selection (%s)" % selection)
            console(f"Invalid selection ({selection})")
            sys.exit()
        del lookup[selection]["#"]
        return lookup[selection]

    def setup(self, objname):
        try:
            typ = config.running["integrations"][objname]["type"]
        except KeyError:
            modtab = [{"name": mod} for mod in self.mods]
            typ = self.table_select(["name"], modtab, "Select an integration type")["name"]
        cfg = {"type": typ}
        new_integration = self.mods[typ](cfg, setup=True)
        newintcfg = new_integration.setup()
        config.running["integrations"].update({objname: newintcfg})
        config.save()
        console("New Integration Config Saved!")

    def test(self, objname):
        if objname not in config.running["integrations"]:
            # console("Integration object (%s) does not exist!" % objname)
            console(f"Integration object ({objname}) does not exist!")
        else:
            typ = config.running["integrations"][objname]["type"]
            cfg = {"objname": objname}
            cfg.update(config.running["integrations"][objname])
            intgobj = self.mods[typ](cfg)
            testfile = ztp_dyn_file("testconfig", "127.0.0.1", "65000",data="This is a\ntest configuration", track=False)
            message = integration_message({
                "ip": "127.0.0.1",
                "tempid": "ZTP-TESTING123",
                "mac": "aa:bb:cc:dd:ee",
                "realid": {'OIDNAME': 'SERIAL12345'},
                "keystore": "NO_KEYSTORE",
                "status": "testing",
                "file": testfile
                })
            intgobj.send(message)

class external_keystore_csv:                                                   # pylint: disable=too-few-public-methods
    name = "csv"
    options = ["file"]

class external_keystore_main:
    mods = {
        external_keystore_csv.name: external_keystore_csv
    }
    def __init__(self):
        self.data = {
            "keyvalstore": {},
            "idarrays": {},
            "associations": {}
        }

    def export(self, filename):
        headers = [
            "keystore_id",
            "association"
        ]
        idarray_count = 1
        for idarray in config.running["idarrays"]:
            if len(config.running["idarrays"][idarray]) > idarray_count:       # pylint: disable=consider-using-max-builtin
                idarray_count = len(config.running["idarrays"][idarray])
        for each in range(1, idarray_count+1):
            headers.append("idarray_"+str(each))
        for keystore_id in config.running["keyvalstore"]:
            for key in config.running["keyvalstore"][keystore_id]:
                if key not in headers:
                    headers.append(key)
        tabledata = []
        for keystore_id in config.running["keyvalstore"]:
            rowdata = {"keystore_id": keystore_id}
            if keystore_id in config.running["associations"]:
                rowdata.update({"association": config.running["associations"][keystore_id]})
            if keystore_id in config.running["idarrays"]:
                array_num = 1
                for value in config.running["idarrays"][keystore_id]:
                    rowdata.update({"idarray_"+str(array_num): value})
                    array_num += 1
            for key in config.running["keyvalstore"][keystore_id]:
                rowdata.update({key: config.running["keyvalstore"][keystore_id][key]})
            tabledata.append(rowdata)

        with open(filename, "w", encoding="utf8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for row in tabledata:
                writer.writerow(row)

    def test(self, objname):                                                   # pylint: disable=too-many-branches
        if objname not in config.running["external-keystores"]:
            # console("External-keystore object (%s) does not exist!" % objname)
            console(f"External-keystore object ({objname}) does not exist!")
            sys.exit()

        if "file" not in config.running["external-keystores"][objname]:
            # console("External-keystore object (%s) has no file defined!" % objname)
            console(f"External-keystore object ({objname}) has no file defined!")
            sys.exit()

        filename = config.running["external-keystores"][objname]["file"]
        if not os.path.isfile(filename):
            # console("Cannot find file (%s)" % filename)
            console(f"Cannot find file ({filename})")
            sys.exit()

        with open(filename, "r", encoding="utf8") as csvfile:
            reader = csv.DictReader(csvfile)
            keystore_commands = []
            idarray_commands = []
            association_commands = []
            for row in reader:
                if "keystore_id" not in row:
                    console("ERROR: Cannot find required header (keystore_id)")
                    sys.exit()
                id = row["keystore_id"]                                        # pylint: disable=redefined-builtin
                array_keys = []
                for key in reader.fieldnames:
                    if row[key]:
                        if key == "association":
                            association_commands.append(f"ztp set association id {id} template {row[key]}")
                        elif key[:7] == "idarray":
                            array_keys.append(row[key])
                        else:
                            # PSC - WTF?? intent unclear
                            if " " in key:
                                key = '%s' % key                               # pylint: disable=consider-using-f-string
                            if " " in row[key]:
                                row[key] = '%s' % row[key]                     # pylint: disable=consider-using-f-string
                            keystore_commands.append(f"ztp set keystore {id} {key} {row[key]}")
                if array_keys:
                    key_set = " ".join(array_keys)
                    idarray_commands.append(f"ztp set idarray {id} {key_set}")
                keystore_commands.append("#")

        console("#\n#\n#")
        for cmd in keystore_commands:
            console(cmd)
        console("#\n#")
        for cmd in idarray_commands:
            console(cmd)
        console("#\n#\n#")
        for cmd in association_commands:
            console(cmd)
        console("#\n#\n#")
        self.load()

    def load(self):                                                            # pylint: disable=too-many-locals, too-many-branches
        keyvalstore = {}
        idarrays = {}
        associations = {}
        # log("external_keystore_main.load: Starting load of external-keystores")
        for objname in config.running["external-keystores"]:                   # pylint: disable=too-many-nested-blocks
            # log("external_keystore_main.load: Loading external-keystore (%s)" % objname)
            # log(f"external_keystore_main.load: Loading external-keystore ({objname})")
            if "file" not in config.running["external-keystores"][objname]:
                # log("external_keystore_main.load: ERROR: External-keystore (%s) has no file defined!" % objname)
                # log(f"external_keystore_main.load: ERROR: External-keystore ({objname}) has no file defined!")
                pass
            elif not os.path.isfile(config.running["external-keystores"][objname]["file"]):
                # log("external_keystore_main.load: ERROR: Cannot fine file (%s)" % config.running["external-keystores"][objname]["file"])
                # log(f"external_keystore_main.load: ERROR: Cannot fine file ({config.running["external-keystores"][objname]["file"]})")
                pass
            else:
                with open(config.running["external-keystores"][objname]["file"], "r", encoding="utf8") as csvfile:
                    reader = csv.DictReader(csvfile)
                    counter = 1
                    for row in reader:                                         # pylint: disable=too-many-nested-blocks
                        try:
                            if "keystore_id" not in row:
                                # log("ERROR: External-keystore ({}): Cannot find required header (keystore_id). Discarding keystore.".format(objname))
                                log(f"ERROR: External-keystore ({objname}): Cannot find required header (keystore_id). Discarding keystore.")
                                break
                            id = row["keystore_id"]                            # pylint: disable=redefined-builtin
                            array_values = []
                            unordered_arrays = {}
                            ordered_keys = []
                            for key in row:
                                if row[key]:
                                    if key == "association":
                                        associations.update({id: row[key]})
                                    if key[:7] == "idarray":
                                        array_values.append(row[key])
                                        if id not in keyvalstore:
                                            keyvalstore.update({id:{}})
                                        keyvalstore[id].update({key: row[key]})
                                        unordered_arrays.update({key: row[key]})
                                    else:
                                        if id not in keyvalstore:
                                            keyvalstore.update({id:{}})
                                        keyvalstore[id].update({key: row[key]})
                            if array_values:
                                idarrays.update({id:array_values})
                            if unordered_arrays:
                                ordered_array_keys = list(unordered_arrays)
                                ordered_array_keys.sort()
                                for key in ordered_array_keys:
                                    ordered_keys.append(unordered_arrays[key])
                            keyvalstore[id].update({"idarray": ordered_keys})
                            counter += 1
                        except Exception:                                      # pylint: disable=broad-exception-caught
                            # log("ERROR: External-keystore ({}) error encountered in row {}, row excluded".format(objname, counter))
                            log(f"ERROR: External-keystore ({objname}) error encountered in row {counter}, row excluded")
                            # log("    Row Info: {}".format(row))
                            log(f"    Row Info: {row}")
        self.data = {
            "keyvalstore": keyvalstore,
            "idarrays": idarrays,
            "associations": associations,
        }


class external_templates_main:                                                 # pylint: disable=too-few-public-methods
    def __init__(self):
        self.templates = {}
    def load(self):
        for template_name in config.running["external-templates"]:
            filepath = config.running["external-templates"][template_name]["file"]
            if os.path.isfile(filepath):
                # log("Loading template ({}) from file ({})".format(template_name, filepath))
                # log(f"Loading template ({template_name}) from file ({filepath})")
                with open(filepath, "r", encoding="utf8") as f:
                    data = f.read()
                self.templates.update({template_name: data})
            else:
                # log("ERROR: Cannot find template file ({})".format(filepath))
                # log(f"ERROR: Cannot find template file ({filepath})")
                pass




def start_tftp():
    """
    TFTP Server main entry. Starts the TFTP server listener and is the main
    program loop. It is started with the ztp_dyn_file class passed in as the
    dynamic file function.
    """
    global tftpy
    import tftpy                                                               # pylint: disable=import-outside-toplevel

    log("start_tftp: Starting Up TFTPy")

    try:
        server = tftpy.TftpServer(config.running["tftproot"], dyn_file_func=interceptor)

    except tftpy.TftpShared.TftpException:
        log("start_tftp: ERROR: TFTP Root path doesn't exist. Creating...")
        subprocess.run(["mkdir", "-p", config.running["tftproot"]], capture_output=False, check=True)
        server = tftpy.TftpServer(config.running["tftproot"], dyn_file_func=interceptor)

    server.listen(listenip="0.0.0.0", listenport=69)
    log("start_tftp: Started up successfully")


def cat_list(listname):
    """
    Concatenate a list of words into a space-seperated string
    """
    result = ""
    counter = 0
    for word in listname:                                                      # pylint: disable=unused-variable
        result = result + listname[counter].lower() + " "
        counter = counter + 1
    result = result[:len(result) - 1:]
    return result


def interpreter():                                                             # pylint: disable=too-many-branches
    """
    Main CLI interpreter and helper function. Entry point for the app.
    """
    arguments = cat_list(sys.argv[1:])
    global config
    global logger
    global osd
    global integrations
    global external_keystores
    global external_templates
    osd = os_detect()
    logger = log_management()
    external_keystores = external_keystore_main()
    external_templates = external_templates_main()
    config = config_manager()
    config.load_external()

    ##### TEST #####
    if arguments == "test":
        pass

    ##### RUN #####
    elif arguments == "run":
        global cfact
        global cache
        cfact = config_factory()
        cache = file_cache()
        integrations = integration_main()
        log("interpreter: Command to run received. Calling start_tftp")
        global tracking
        tracking = tracking_class()
        start_tftp()

    ##### INSTALL #####
    elif arguments == "install":
        # console("***** Are you sure you want to install FreeZTP using version %s?*****" % version)
        console(f"***** Are you sure you want to install FreeZTP using version {version}?*****")
        answer = input(">>>>> If you are sure you want to do this, type in 'CONFIRM' and hit ENTER >>>>")
        if answer.lower() == "confirm":
            inst = installer()
            inst.copy_binary()
            inst.create_configfile()
            inst.install_completion()
            inst.install_dependencies()
            inst.install_tftpy()
            inst.disable_firewall()
            inst.create_service()
            inst.dhcp_setup()
            console("\nInstall complete! Logout and log back into SSH to activate auto-complete")
        else:
            console("Install/upgrade cancelled")

    elif arguments == "upgrade":
        # console("***** Are you sure you want to upgrade FreeZTP using version %s?*****" % version)
        console(f"***** Are you sure you want to upgrade FreeZTP using version {version}?*****")
        answer = input(">>>>> If you are sure you want to do this, type in 'CONFIRM' and hit ENTER >>>>")
        if answer.lower() == "confirm":
            inst = installer()
            inst.copy_binary()
            inst.install_completion()
            inst.create_service()
            inst.minor_update_script()
            inst.snmp_name_fix()
            console("\n")
            osd.service_control("status", "ztp")
            console("\n")
            console("\nInstall complete! Logout and log back into SSH to activate auto-complete\n")
        else:
            console("Install/upgrade cancelled")

    elif arguments == "hidden" or arguments == "hidden show":
        console("NOTE: These hidden commands are mostly meant to display information for use in TAB autocomplete")
        console(" - hidden reset-config                            |  Replace the ZTP config with the default configuration")
        console(" - hidden show keystores                          |  Show a list of configured keystores")
        console(" - hidden show keys <keystore>                    |  Show a list of configured keys under a keystore")
        console(" - hidden show idarrays                           |  Show a list of configured IDArrays")
        console(" - hidden show idarray members                    |  Show a list of members in an IDArray")
        console(" - hidden show idarray-nameoptions                |  Show a list of options for new or existing IDArrays")
        console(" - hidden show snmpoids                           |  Show a list of configured SNMP OIDs")
        console(" - hidden show templates                          |  Show a list of configured templates")
        console(" - hidden show external-templates                 |  Show a list of configured external-templates")
        console(" - hidden show associations                       |  Show a list of configured template associations")
        console(" - hidden show all_ids                            |  Show a list of all configured IDs (Keystores and IDArrays)")
        console(" - hidden show imagefiles                         |  Show a list of candidate imagefiles in the TFTP root directory")
        console(" - hidden show dhcpd-options                      |  Show a list of configured DHCPD options")
        console(" - hidden show dhcpd-option-types                 |  Show a list of allowed DHCP option types")
        console(" - hidden show dhcpd-option <opt_name>            |  Show the type for this option")
        console(" - hidden show dhcpd-scopes                       |  Show a list of configured DHCPD scopes")
        console(" - hidden show integrations                       |  Show a list of external integrations")
        console(" - hidden show integration-types                  |  Show a list of available integration types")
        console(" - hidden show integration-opts <svc_name>        |  Show a external integration key options")
        console(" - hidden show integration-keys <svc_name>        |  Show a list of keys configured on an integration")
        console(" - hidden show external-keystores                 |  Show a list of keys configured for external-keystores")
        console(" - hidden show external-keystore-types            |  Show a list of available external-keystore types")

    elif arguments == "hidden reset-config":
        inst = installer()
        inst.create_configfile()
    elif arguments == "hidden show keystores":
        config.hidden_list_ids()
    elif arguments[:16] == "hidden show keys" and len(sys.argv) >= 4:
        config.hidden_list_keys(sys.argv[4])
    elif arguments == "hidden show idarrays":
        config.hidden_list_arrays()
    elif arguments == "hidden show idarray members":
        config.hidden_list_array_members()
    elif arguments == "hidden show idarray-nameoptions":
        config.hidden_list_array_name_options()
    elif arguments == "hidden show snmpoids":
        config.hidden_list_snmpoid()
    elif arguments == "hidden show templates":
        config.hidden_list_templates()
    elif arguments == "hidden show external-templates":
        config.hidden_list_external_templates()
    elif arguments == "hidden show associations":
        config.hidden_list_associations()
    elif arguments == "hidden show all_ids":
        config.hidden_list_all_ids()
    elif arguments == "hidden show imagefiles":
        config.hidden_list_image_files()
    elif arguments == "hidden show dhcpd-options":
        config.hidden_list_dhcpd_options()
    elif arguments == "hidden show dhcpd-option-types":
        config.hidden_list_dhcpd_option_types()
    elif arguments[:24] == "hidden show dhcpd-option" and len(sys.argv) >= 4:
        config.hidden_show_dhcpd_option(sys.argv[4])
    elif arguments == "hidden show dhcpd-scopes":
        config.hidden_list_dhcpd_scopes()
    elif arguments == "hidden show integrations":
        config.hidden_list_integrations()
    elif arguments == "hidden show external-keystores":
        config.hidden_list_external_keystores()
    elif arguments == "hidden show integration-types":
        config.hidden_list_integration_types()
    elif arguments == "hidden show external-keystore-types":
        config.hidden_list_external_keystore_types()
    elif arguments[:28] == "hidden show integration-keys" and len(sys.argv) >= 4:
        config.hidden_show_integration_keys(sys.argv[4])
    elif arguments[:34] == "hidden show external-keystore-keys" and len(sys.argv) >= 4:
        config.hidden_show_external_keystore_keys(sys.argv[4])
    elif arguments[:28] == "hidden show integration-opts" and len(sys.argv) >= 4:
        config.hidden_show_integration_opts(sys.argv[4])
    elif arguments[:34] == "hidden show external-keystore-opts" and len(sys.argv) >= 4:
        config.hidden_show_external_keystore_opts(sys.argv[4])

    ##### SHOW #####
    elif arguments == "show":
        console(" - show (config|run) (raw)                        |  Show the current ZTP configuration")
        console(" - show status                                    |  Show the status of the ZTP background service")
        console(" - show version                                   |  Show the current version of ZTP")
        console(" - show log (tail) (<num_of_lines>)               |  Show or tail the log file")
        console(" - show downloads (live)                          |  Show list of TFTP downloads")
        console(" - show dhcpd leases (current|all|raw)            |  Show DHCPD leases")
        console(" - show provisioning                              |  Show list of provisioned devices")

    elif arguments == "show config raw" or arguments == "show run raw":
        subprocess.run(["more", "/etc/ztp/ztp.cfg"], capture_output=False, check=True)
    elif arguments == "show config" or arguments == "show run":
        config.show_config()
    elif arguments[:11] == "show config" and len(sys.argv) > 3:
        cfglist = config.show_config_section(sys.argv[3])
        console("#######################################################\n#\n#\n#")
        for line in cfglist:
            console(line)
        console("#\n#\n#\n#######################################################")
    elif arguments == "show status":
        console("\n")
        osd.service_control("status", "ztp")
        console("\n\n")
        osd.service_control("status", osd.DHCPSVC)
        console("\n")
    elif arguments == "show version":
        console(f"FreeZTP {version}")
    elif arguments[:8] == "show log":
        logger.show(sys.argv)
    elif arguments[:19] == "show downloads live":
        tracking = tracking_class(client=True)
        tracking.show_downloads_live(sys.argv)
    elif arguments[:14] == "show downloads":
        tracking = tracking_class(client=True)
        console(tracking.show_downloads(sys.argv))
    elif arguments == "show dhcpd":
        console(" - show dhcpd leases (current|all|raw)            |  Show DHCPD leases")
    elif arguments == "show dhcpd leases":
        tracking = tracking_class(client=True)
        console(tracking.show_dhcp_leases())
    elif arguments == "show dhcpd leases raw":
        subprocess.run(["more", osd.DHCPLEASES], capture_output=False, check=True)
    elif arguments == "show dhcpd leases current":
        tracking = tracking_class(client=True)
        console(tracking.show_dhcp_leases())
    elif arguments == "show dhcpd leases all":
        tracking = tracking_class(client=True)
        console(tracking.show_dhcp_leases("all"))
    elif arguments == "show provisioning":
        tracking = tracking_class(client=True)
        console(tracking.show_provisioning())

    ##### SET #####
    elif arguments == "set":
        console("--------------------------------------------------- SETTINGS YOU PROBABLY SHOULDN'T CHANGE ---------------------------------------------------")
        console(" - set suffix <value>                                          |  Set the file name suffix used by target when requesting the final config")
        console(" - set initialfilename <value>                                 |  Set the file name used by the target during the initial config request")
        console(" - set community <value>                                       |  Set the SNMP community you want to use for target ID identification")
        console(" - set snmpoid <name> <value>                                  |  Set named SNMP OIDs to use to pull the target ID during identification")
        console(" - set initial-template <end_char>                             |  Set the initial configuration j2 template used for target identification")
        console(" - set tftproot <tftp_root_directory>                          |  Set the root directory for TFTP files")
        console(" - set imagediscoveryfile <filename>                           |  Set the name of the IOS image discovery file used for IOS upgrades")
        console(" - set file-cache-timeout <timeout>                            |  Set the timeout for cacheing of files. '0' disables caching.")
        console("--------------------------------------------------------- SETTINGS YOU SHOULD CHANGE ---------------------------------------------------------")
        console(" - set integration <svc_name> [parameters]                     |  Configure external integrations")
        console(" - set external-keystore <store_name> [parameters]             |  Configure an external keystore")
        console(" - set template <template_name> <end_char>                     |  Create/Modify a named J2 tempate which is used for the final config push")
        console(" - set external-template <template_name> [parameters]          |  Configure an external template")
        console(" - set keystore <id/arrayname> <keyword> <value>               |  Create a keystore entry to be used when merging final configurations")
        console(" - set idarray <arrayname> <id's>                              |  Create an ID array to allow multiple real ids to match one keystore id")
        console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
        console(" - set default-keystore (none|keystore-id)                     |  Set a last-resort keystore and template for when target identification fails")
        console(" - set global-keystore (none|keystore-id)                      |  Set a keystore to be injected into all merges")
        console(" - set default-template (none|template_name)                   |  Set a last-resort template for when no keystore/template association is found")
        console(" - set imagefile <binary_image_file_name>                      |  Set the image file name to be used for upgrades (must be in tftp root dir)")
        console(" - set image-supression <seconds-to-supress>                   |  Set the seconds to supress a second image download preventing double-upgrades")
        console(" - set delay-keystore <msec-to-delay>                          |  Set the miliseconds to delay the processing of a keystore lookup")
        console(" - set dhcpd-option <opt-name> code <code> type <field-type>   |  Configure DHCP options to be available to the DHCP server")
        console(" - set dhcpd <scope-name> [parameters]                         |  Configure DHCP scope(s) to serve IP addresses to ZTP clients")
        console(" - set logging [parameters]                                    |  Set up custom logging settings")
    elif arguments == "set suffix":
        console(" - set suffix <value>                             |  Set the file name suffix used by target when requesting the final config")
    elif arguments == "set initialfilename":
        console(" - set initialfilename <value>                    |  Set the file name used by the target during the initial config request")
    elif arguments == "set community":
        console(" - set community <value>                          |  Set the SNMP community you want to use for target ID identification")
    elif (arguments[:11] == "set snmpoid" and len(sys.argv) < 5) or arguments == "set snmpoid":
        console(" - set snmpoid <name> <value>                     |  Set named SNMP OIDs to use to pull the target ID during identification")
    elif arguments == "set initial-template":
        console(" - set initial-template <end_char>                |  Set the initial configuration j2 template used for target identification")
    elif arguments == "set tftproot":
        console(" - set tftproot <tftp_root_directory>             |  Set the root directory for TFTP files")
    elif arguments == "set imagediscoveryfile":
        console(" - set imagediscoveryfile <filename>              |  Set the name of the IOS image discovery file used for IOS upgrades")
    elif arguments == "set file-cache-timeout":
        console(" - set file-cache-timeout <timeout>               |  Set the timeout for cacheing of files. '0' disables caching.")
    elif (arguments[:15] == "set integration" and len(sys.argv) < 6) or arguments == "set integration":
        console(" - set integration <svc_name> [parameters]                     |  Configure external integrations")
        console("                                                                    Examples:")
        console("                                                                         - set integration ADMINSROOM type spark")
        console("                                                                         - set integration ADMINSROOM api-key $ucH@ran60mk3y")
        console("                                                                         - set integration ADMINSROOM roomId SOMEROOMID")
        console("                                                                         ")
        console("                                                                         - set integration DIRECTMSG type spark")
        console("                                                                         - set integration DIRECTMSG api-key $ucH@ran60mk3y")
        console("                                                                         - set integration DIRECTMSG toPersonEmail admin@company.com")
    elif (arguments[:21] == "set external-keystore" and len(sys.argv) < 6) or arguments == "set external-keystore":
        console(" - set external-keystore <store_name> [parameters]             |  Configure an external keystore")
        console("                                                                    Examples:")
        console("                                                                         - set external-keystore MYCSV type csv")
        console("                                                                         - set external-keystore MYCSV file '/home/user/mycsv.csv'")
        console("                                                                         - set external-keystore MYCSV mode offline")
    elif (arguments[:12] == "set template" and len(sys.argv) < 5) or arguments == "set template":
        console(" - set template <template_name> <end_char>        |  Set the final configuration j2 template pushed to host after discovery/identification")
    elif (arguments[:21] == "set external-template" and len(sys.argv) < 6) or arguments == "set external-template":
        console(" - set external-template <template_name> file <filepath>       |  Configure an external template")
    elif (arguments[:12] == "set keystore" and len(sys.argv) < 6) or arguments == "set keystore":
        console(" - set keystore <id/arrayname> <keyword> <value>  |  Create a keystore entry to be used when merging final configurations")
    elif (arguments[:11] == "set idarray" and len(sys.argv) < 5) or arguments == "set idarray":
        console(" - set idarray <arrayname> <id_#1> <id_#2> ...    |  Create an ID array to allow multiple real ids to match one keystore id")
    elif (arguments[:15] == "set association" and len(sys.argv) < 7) or arguments == "set association":
        console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
    elif (arguments[:20] == "set default-keystore" and len(sys.argv) < 4) or arguments == "default-keystore":
        console(" - set default-keystore (none|keystore-id)        |  Set a last-resort keystore and template for when target identification fails")
    elif (arguments[:19] == "set global-keystore" and len(sys.argv) < 4) or arguments == "global-keystore":
        console(" - set global-keystore (none|keystore-id)         |  Set a keystore to be injected into all merges")
    elif (arguments[:20] == "set default-template" and len(sys.argv) < 4) or arguments == "default-template":
        console(" - set default-template (none|template_name)      |  Set a last-resort template for when no keystore/template association is found")
    elif arguments == "set imagefile":
        console(" - set imagefile <binary_image_file_name>         |  Set the image file name to be used for upgrades (must be in tftp root dir)")
    elif arguments == "set image-supression":
        console(" - set image-supression <seconds-to-supress>      |  Set the seconds to supress a second image download preventing double-upgrades")
    elif arguments == "set delay-keystore":
        console(" - set delay-keystore <msec-to-delay>             |  Set the miliseconds to delay the processing of a keystore lookup")
    elif (arguments[:16] == "set dhcpd-option" and len(sys.argv) < 8) or arguments == "default-template":
        console(" - set dhcpd-option <opt-name> code <code> type <field-type>       |  Configure DHCP options to be available to the DHCP server")
        console("                                                                    Examples:")
        console("                                                                         - set dhcpd-option ztp-tftp-address code 150 type ip-address")
    elif arguments == "set dhcpd":
        console(" - set dhcpd <scope-name> [parameters]            |  Configure DHCP scope(s) to serve IP addresses to ZTP clients")
    elif (arguments[:11] == "set logging" and len(sys.argv) < 5) or arguments == "set logging":
        console(" - set logging merged-config-to-mainlog (enable|disable)           |  Enable or disable logging of final configs to the main log file")
        console(" - set logging merged-config-to-custom-file (<filepath>|disable)   |  Log your merged configs to a Jinja2 rendered custom file")
        console("                                                                    Examples:")
        console("                                                                         - set logging merged-config-to-mainlog disable")
        console("                                                                         - set logging merged-config-to-custom-file '/etc/ztp/merged-logs/{{ hostname }}'")
    elif arguments[:3] == "set" and len(sys.argv) >= 4:
        config.set(sys.argv)

    ##### CLEAR #####
    elif arguments == "clear":
        console(" - clear snmpoid <name>                           |  Delete an SNMP OID from the configuration")
        console(" - clear integration <svc_name> (all|<key>)       |  Delete an individual integration key or the whole object")
        console(" - clear external-keystore <name> (all|<key>)     |  Delete an individual external-keystore key or the whole object")
        console(" - clear template <template_name>                 |  Delete a named configuration template")
        console(" - clear external-template <template_name>        |  Delete a named external-template")
        console(" - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration")
        console(" - clear idarray <arrayname>                      |  Delete an ID array from the configuration")
        console(" - clear association <id/arrayname>               |  Delete an association from the configuration")
        console(" - clear dhcpd-option <opt-name>                  |  Delete a configured DHCP option")
        console(" - clear dhcpd <scope-name>                       |  Delete a DHCP scope")
        console(" - clear log                                      |  Delete the logging info from the logfile")
        console(" - clear downloads                                |  Delete the list of TFTP downloads")
        console(" - clear provisioning                             |  Delete the list of provisioned devices")
    elif (arguments[:13] == "clear snmpoid" and len(sys.argv) < 4) or arguments == "clear snmpoid":
        console(" - clear snmpoid <name>                           |  Delete an SNMP OID from the configuration")
    elif (arguments[:17] == "clear integration" and len(sys.argv) < 5) or arguments == "clear integration":
        console(" - clear integration <svc_name> (all|<key>)       |  Delete an individual key or a whole keystore ID from the configuration")
    elif (arguments[:23] == "clear external-keystore" and len(sys.argv) < 5) or arguments == "clear external-keystore":
        console(" - clear external-keystore <name> (all|<key>)     |  Delete an individual external-keystore key or the whole object")
    elif (arguments[:14] == "clear template" and len(sys.argv) < 4) or arguments == "clear template":
        console(" - clear template <template_name>                 |  Delete a named configuration template")
    elif (arguments[:23] == "clear external-template" and len(sys.argv) < 4) or arguments == "clear external-template":
        console(" - clear external-template <template_name>        |  Delete a named external-template")
    elif (arguments[:14] == "clear keystore" and len(sys.argv) < 5) or arguments == "clear keystore":
        console(" - clear keystore <id> (all|<keyword>)            |  Delete an individual key or a whole keystore ID from the configuration")
    elif (arguments[:13] == "clear idarray" and len(sys.argv) < 4) or arguments == "clear idarray":
        console(" - clear idarray <arrayname>                      |  Delete an ID array from the configuration")
    elif (arguments[:17] == "clear association" and len(sys.argv) < 4) or arguments == "clear association":
        console(" - clear association <id/arrayname>               |  Delete an association from the configuration")
    elif (arguments[:18] == "clear dhcpd-option" and len(sys.argv) < 4) or arguments == "clear dhcpd-option":
        console(" - clear dhcpd-option <opt-name>                  |  Delete a configured DHCP option")
    elif (arguments[:11] == "clear dhcpd" and len(sys.argv) < 4) or arguments == "clear dhcpd":
        console(" - clear dhcpd <scope-name>                       |  Delete a DHCP scope")
    elif arguments[:13] == "clear snmpoid" and len(sys.argv) >= 4:
        config.clear(sys.argv)
    elif arguments[:17] == "clear integration" and len(sys.argv) >= 5:
        config.clear(sys.argv)
    elif arguments[:23] == "clear external-keystore" and len(sys.argv) >= 5:
        config.clear(sys.argv)
    elif arguments[:14] == "clear template" and len(sys.argv) >= 4:
        config.clear(sys.argv)
    elif arguments[:23] == "clear external-template" and len(sys.argv) >= 4:
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
    elif arguments == "clear provisioning":
        tracking = tracking_class(client=True)
        tracking.clear_provisioning()
        log("Provisioning history has been cleared")

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
        console(" - request integration-setup <svc_name>           |  Run the setup wizard for the module type configured on the object")
        console(" - request integration-test <svc_name>            |  Perform a test message push to a target integration object")
        console(" - request external-keystore-test <store_name>    |  Perform a test import of external-keystore data and print as set keystore config")
        console(" - request keystore-csv-export <file_name>        |  Export the current keystore, idarray, and association config as CSV")
    elif arguments == "request merge-test":
        console(" - request merge-test <id>                        |  Perform a test jinja2 merge of the final template with a keystore ID")
    elif arguments == "request dhcp-option-125":
        console(" - request dhcp-option-125 (windows|cisco)        |  Show the DHCP Option 125 Hex value to use on the DHCP server for OS upgrades")
    elif arguments == "request integration-setup":
        console(" - request integration-setup <svc_name>           |  Run the setup wizard for the module type configured on the object")
    elif arguments == "request integration-test":
        console(" - request integration-test <svc_name>            |  Perform a test message push to a target integration object")
    elif arguments == "request external-keystore-test":
        console(" - request external-keystore-test <store_name>    |  Perform a test import of external-keystore data and print as set keystore config")
    elif arguments == "request keystore-csv-export":
        console(" - request keystore-csv-export <file_name>        |  Export the current keystore, idarray, and association config as CSV")
    elif arguments == "request initial-merge":
        cfact = config_factory()
        tracking = tracking_class(client=True)
        cfact.request(config.running["initialfilename"], "10.0.0.1", test=True)
    elif arguments == "request default-keystore-test":
        cfact = config_factory()
        default = cfact._default_lookup()                                      # pylint: disable=protected-access
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
        console("\nHit CTRL+C to kill the SNMP query test")
        # console("\nQuerying %s using community (%s) and OID (%s)\n" % (sys.argv[3], community, oid))
        console(f"\nQuerying {sys.argv[3]} using community ({community}) and OID ({oid})\n")
        query = snmp_query(sys.argv[3], community, oid)
        while query.thread.is_alive():
            time.sleep(3)
    elif arguments[:23] == "request dhcp-option-125" and (sys.argv[3] == "cisco" or sys.argv[3] == "windows"):
        config.opt125(sys.argv[3])
    elif arguments == "request dhcpd-commit":
        config.dhcpd_commit()
    elif arguments == "request auto-dhcpd":
        config.auto_dhcpd()
    elif arguments == "request ipc-console":
        subprocess.run(["telnet", "localhost", "10000"], capture_output=False, check=True)
    elif arguments[:25] == "request integration-setup" and len(sys.argv) >= 4:
        integrations = integration_main()
        integrations.setup(sys.argv[3])
    elif arguments[:24] == "request integration-test" and len(sys.argv) >= 4:
        integrations = integration_main()
        integrations.test(sys.argv[3])
    elif arguments[:30] == "request external-keystore-test" and len(sys.argv) >= 4:
        external_keystores = external_keystore_main()
        external_keystores.test(sys.argv[3])
    elif arguments[:27] == "request keystore-csv-export" and len(sys.argv) >= 4:
        external_keystores = external_keystore_main()
        external_keystores.export(sys.argv[3])

    ##### SERVICE #####
    elif arguments == "service":
        console(" - service (start|stop|restart|status)            |  Start, Stop, or Restart the installed ZTP service")
    elif arguments == "service start" or arguments == "service freeztp start":
        log("#########################################################")
        log("Starting the ZTP Service")
        osd.service_control("start", "ztp")
        osd.service_control("status", "ztp")
        log("#########################################################")
    elif arguments == "service stop" or arguments == "service freeztp stop":
        log("#########################################################")
        log("Stopping the ZTP Service")
        osd.service_control("stop", "ztp")
        osd.service_control("status", "ztp")
        log("#########################################################")
    elif arguments == "service restart" or arguments == "service freeztp restart":
        log("#########################################################")
        log("Restarting the ZTP Service")
        osd.service_control("restart", "ztp")
        osd.service_control("status", "ztp")
        log("#########################################################")
    elif arguments == "service dhcpd start":
        log("#########################################################")
        log("Starting the ZTP Service")
        osd.service_control("start", osd.DHCPSVC)
        osd.service_control("status", osd.DHCPSVC)
        log("#########################################################")
    elif arguments == "service dhcpd stop":
        log("#########################################################")
        log("Stopping the ZTP Service")
        osd.service_control("stop", osd.DHCPSVC)
        osd.service_control("status", osd.DHCPSVC)
        log("#########################################################")
    elif arguments == "service dhcpd restart":
        log("#########################################################")
        log("Restarting the ZTP Service")
        osd.service_control("restart", osd.DHCPSVC)
        osd.service_control("status", osd.DHCPSVC)
        log("#########################################################")
    elif arguments == "service all start":
        log("#########################################################")
        log("Starting the ZTP Service")
        osd.service_control("start", "ztp")
        osd.service_control("start", osd.DHCPSVC)
        osd.service_control("status", "ztp")
        osd.service_control("status", osd.DHCPSVC)
        log("#########################################################")
    elif arguments == "service all stop":
        log("#########################################################")
        log("Stopping the ZTP Service")
        osd.service_control("stop", "ztp")
        osd.service_control("stop", osd.DHCPSVC)
        osd.service_control("status", "ztp")
        osd.service_control("status", osd.DHCPSVC)
        log("#########################################################")
    elif arguments == "service all restart":
        log("#########################################################")
        log("Restarting the ZTP Service")
        osd.service_control("restart", "ztp")
        osd.service_control("restart", osd.DHCPSVC)
        osd.service_control("status", "ztp")
        osd.service_control("status", osd.DHCPSVC)
        log("#########################################################")
    elif arguments == "service status":
        osd.service_control("status", "ztp")
        osd.service_control("status", osd.DHCPSVC)

    ##### VERSION #####
    elif arguments == "version":
        # console("FreeZTP %s" % version)
        console(f"FreeZTP {version}")

    else:
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console("                     ARGUMENTS                                 |                                  DESCRIPTIONS")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console(" - run                                                         |  Run the ZTP main program in shell mode begin listening for TFTP requests")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console(" - install                                                     |  Run the ZTP installer")
        console(" - upgrade                                                     |  Run the ZTP upgrade process to update the software")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console(" - show (config|run) (raw)                                     |  Show the current ZTP configuration")
        console(" - show status                                                 |  Show the status of the ZTP background service")
        console(" - show version                                                |  Show the current version of ZTP")
        console(" - show log (tail) (<num_of_lines>)                            |  Show or tail the log file")
        console(" - show downloads (live)                                       |  Show list of TFTP downloads")
        console(" - show dhcpd leases (current|all|raw)                         |  Show DHCPD leases")
        console(" - show provisioning                                           |  Show list of provisioned devices")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console("--------------------------------------------------- SETTINGS YOU PROBABLY SHOULDN'T CHANGE ---------------------------------------------------")
        console(" - set suffix <value>                                          |  Set the file name suffix used by target when requesting the final config")
        console(" - set initialfilename <value>                                 |  Set the file name used by the target during the initial config request")
        console(" - set community <value>                                       |  Set the SNMP community you want to use for target ID identification")
        console(" - set snmpoid <name> <value>                                  |  Set named SNMP OIDs to use to pull the target ID during identification")
        console(" - set initial-template <end_char>                             |  Set the initial configuration j2 template used for target identification")
        console(" - set tftproot <tftp_root_directory>                          |  Set the root directory for TFTP files")
        console(" - set imagediscoveryfile <filename>                           |  Set the name of the IOS image discovery file used for IOS upgrades")
        console(" - set file-cache-timeout <timeout>                            |  Set the timeout for cacheing of files. '0' disables caching.")
        console("--------------------------------------------------------- SETTINGS YOU SHOULD CHANGE ---------------------------------------------------------")
        console(" - set integration <svc_name> [parameters]                     |  Configure external integrations (experimental)")
        console(" - set external-keystore <store_name> [parameters]             |  Configure an external keystore")
        console(" - set template <template_name> <end_char>                     |  Create/Modify a named J2 tempate which is used for the final config push")
        console(" - set external-template <template_name> [parameters]          |  Configure an external template")
        console(" - set keystore <id/arrayname> <keyword> <value>               |  Create a keystore entry to be used when merging final configurations")
        console(" - set idarray <arrayname> <id_#1> <id_#2> ...                 |  Create an ID array to allow multiple real ids to match one keystore id")
        console(" - set association id <id/arrayname> template <template_name>  |  Associate a keystore id or an idarray to a specific named template")
        console(" - set default-keystore (none|keystore-id)                     |  Set a last-resort keystore and template for when target identification fails")
        console(" - set global-keystore (none|keystore-id)                      |  Set a keystore to be injected into all merges")
        console(" - set default-template (none|template_name)                   |  Set a last-resort template for when no keystore/template association is found")
        console(" - set imagefile <binary_image_file_name>                      |  Set the image file name to be used for upgrades (must be in tftp root dir)")
        console(" - set image-supression <seconds-to-supress>                   |  Set the seconds to supress a second image download preventing double-upgrades")
        console(" - set delay-keystore <msec-to-delay>                          |  Set the miliseconds to delay the processing of a keystore lookup")
        console(" - set dhcpd-option <opt-name> code <code> type <field-type>   |  Configure DHCP options to be available to the DHCP server")
        console(" - set dhcpd <scope-name> [parameters]                         |  Configure DHCP scope(s) to serve IP addresses to ZTP clients")
        console(" - set logging [parameters]                                    |  Set up custom logging settings")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console(" - clear snmpoid <name>                                        |  Delete an SNMP OID from the configuration")
        console(" - clear integration <svc_name> (all|<key>)                    |  Delete an individual integration key or the whole object")
        console(" - clear template <template_name>                              |  Delete a named configuration template")
        console(" - clear external-template <template_name>                     |  Delete a named external-template")
        console(" - clear keystore <id> (all|<keyword>)                         |  Delete an individual key or a whole keystore ID from the configuration")
        console(" - clear external-keystore <name> (all|<key>)                  |  Delete an individual external-keystore key or the whole object")
        console(" - clear idarray <arrayname>                                   |  Delete an ID array from the configuration")
        console(" - clear association <id/arrayname>                            |  Delete an association from the configuration")
        console(" - clear dhcpd-option <opt-name>                               |  Delete a configured DHCP option")
        console(" - clear dhcpd <scope-name>                                    |  Delete a DHCP scope")
        console(" - clear log                                                   |  Delete the logging info from the logfile")
        console(" - clear downloads                                             |  Delete the list of TFTP downloads")
        console(" - clear provisioning                                          |  Delete the list of provisioned devices")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console(" - request merge-test <id>                                     |  Perform a test jinja2 merge of the final template with a keystore ID")
        console(" - request initial-merge                                       |  See the result of an auto-merge of the initial-template")
        console(" - request default-keystore-test                               |  Check that the default-keystore is fully configured to return a template")
        console(" - request snmp-test <ip-address>                              |  Run a SNMP test using the configured community and OID against an IP")
        console(" - request dhcp-option-125 (windows|cisco)                     |  Show the DHCP Option 125 Hex value to use on the DHCP server for OS upgrades")
        console(" - request dhcpd-commit                                        |  Compile the DHCP config, write to config file, and restart the DHCP service")
        console(" - request auto-dhcpd                                          |  Automatically detect local interfaces and build DHCP scopes accordingly")
        console(" - request ipc-console                                         |  Connect to the IPC console to run commands (be careful)")
        console(" - request integration-setup <svc_name>                        |  Run the setup wizard for the module type configured on the object")
        console(" - request integration-test <svc_name>                         |  Perform a test message push to a target integration object")
        console(" - request external-keystore-test <store_name>                 |  Perform a test import of external-keystore data and print as set keystore config")
        console(" - request keystore-csv-export <file_name>                     |  Export the current keystore, idarray, and association config as CSV")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console(" - service (start|stop|restart|status|freeztp|dhcpd|all)       |  Start, Stop, or Restart the installed services")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")
        console(" - version                                                     |  Show the current version of ZTP")
        console("----------------------------------------------------------------------------------------------------------------------------------------------")


if __name__ == "__main__":
    interpreter()
