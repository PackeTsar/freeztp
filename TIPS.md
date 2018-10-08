[< Main README](/README.md)


# FreeZTP ![FreeZTP][logo]

Some usage tips and tricks from real world FreeZTP deployments.


-----------------------------------------
## TABLE OF CONTENTS
1. [Use-case: Provisioning without using Vlan1](#use-case:-provisioning-without-using-vlan1)
2. [Use-case: Upgrade IOS-XE 3.7.x to 16.3.6](#use-case:-upgrade-ios-xe-3.7.x-to-16.3.6)


-----------------------------------------
## Use-case: Provisioning without using Vlan1

###### Author: [derek_shnosh](https://github.com/derek-shnosh), Rev: 1, Date: 2018.1008, FreeZTP dev1.1.0m

To avoid using Vlan1 for provisioning, configure the *master* provisioning switch interfaces as follows; *e.g. assumes the following details for the provisioning environment.* The client switch running the smart-install process will still bring up all interfaces as *dynamic desireable* (or other default behavior) on Vlan1, but disabling CDP and enabling BPDU filter will circumvent any undesirable spanning-tree behavior that would otherwise interfere with the link coming up between the master and client switches.

**NOTE: A client switch should only be connected to the *master* provisioning switch during provisioning**; i.e. a client switch should never be connected to the provisioning environment and production infrastructure during the provisioning process, spanning-tree loops can occur.

### Provisioning Network Information

| VLAN  | Subnet          | IP Allocation                                                                      |
| :---: | :-------------: | :--------------------------------------------------------------------------------- |
| 3967  | 172.31.255.0/24 | **.1** - Gateway (optional)<br>**.2** - FreeZTP server<br>**.5 - .254** DHCP range |

### Interface Configuration (Master Switch)

* Replace `<n>` with interfaces that client switches will connect to.

    ```
    interface <n>
    desc PROVISION
    switchport access vlan 3967
    switchport mode access
    switchport nonegotiate
    no cdp enable
    spanning-tree portfast
    spanning-tree bpdufilter enable
    ```


-----------------------------------------
## Use-case: Upgrade IOS-XE 3.7.x to 16.3.6

###### Author: [derek_shnosh](https://github.com/derek-shnosh), Rev: 1, Date: 2018.1008, FreeZTP dev1.1.0m

### Problem

IOS-XE 3.7.4 cannot upgrade to 16.3.6 via smart-install because `new force` isn't appended.

* Switch log output from failure;

    ```
    Would you like to enter the initial configuration dialog? [yes/no]:
    Loading ztp_ios_upgrade from 172.17.251.251 (via Vlan1): !
    [OK - 38 bytes]
    Preparing install operation ...
    [1]: Downloading file tftp://172.17.251.251/cat3k_caauniversalk9.16.03.06.
    SPA.bin to active switch 1
    [1]: Finished downloading file tftp://172.17.251.251/cat3k_caauniversalk9.16.03.06.
    SPA.bin to active switch 1
    [1]: Copying software from active switch 1 to switch 2
    [1]: Finished copying software to switch 2
    [1 2]: Starting install operation
    [1 2]: Expanding bundle cat3k_caa-universalk9.16.03.06.SPA.bin
    [1 2]: Copying package files
    [1 2]: Package files copied
    [1 2]: Finished expanding bundle cat3k_caa-universalk9.16.03.06.SPA.bin
    [1 2]: Verifying and copying expanded package files to flash:
    [1 2]: Verified and copied expanded package files to flash:
    [1 2]: Starting compatibility checks
    [1]: % Candidate package compatibility checks failed because the following
    package dependencies were not satisfied. Operation aborted.


    [2]: % Candidate package compatibility checks failed because the following
    package dependencies were not satisfied. Operation aborted.


    [1]: % An internal error was encountered. Operation aborted.
    [2]: % An internal error was encountered. Operation aborted.

    ERROR: Software Installation Failed: 35 2

    Loading network-confg from 172.17.251.251 (via Vlan1): !
    [OK - 69 bytes]
    Loading ZTP-23CFBA478F-confg from 172.17.251.251 (via Vlan1): !
    [OK - 77012 bytes] 
    ```

* TAC confirmation;

    >The behavior is expected due to the command syntax difference as you suspected.
    We documented the behavior in a bug below: https://bst.cloudapps.cisco.com/bugsearch/bug/CSCvd49193
    The running code 3.7.4E is affected and this issue is fixed on 3.6.8E.
    Is it possible for you to try the following?
    1- Upgrade from 3.7.4E to 3.6.8E via smart install
    2- Upgrade from 3.6.8E to 16.3.6 via smart install

    ![BugID_Screenshot_from_TAC][BugID]

### Workaround

This workaround uses EEM applets in the J2 switch template to download install the updated image.

#### Process Order

1. Switch is powered up connected to provisioning network and initiates smart-install, FreeZTP does not give an image.
2. Switch requests config, FreeZTP gives a (merged) config, containing the [required config](#required-config).
    * *Merged template should not contain any incompatible configuration commands for current software version (3.7.4E).*
3. Switch applies configuration with Vlan1 configured for DHCP addressing; **`post_ztp_1` is triggered by Vlan1 obtaining a DHCP address**.
4. [EEM Applet `post_ztp_1` loaded to memory.]
    1. Applet deletes itself from running configuration, downloads the bin file, cleans up temp configs and then writes the startup-config.
    2. Switch then runs the `software install` command, answers **y** to reload prompt from install command.
5. Switch reloads; **`post_ztp_2` is triggered by a syslog command specific to IOS-XE 16.x *(%IOSXE_REDUNDANCY-6-PEER)***.
    * **This trigger may need to be changed!**<br>*I'm unsure if this syslog message is present when provisioning a single switch (i.e. not stacked) as I never tested this scenario. I will update if I get an opportunity to test this on a single switch.*
6. [EEM applet `post_ztp_2` loaded into memory.]
    1. Applet deletes itself from running configuration and writes the startup-config.
    2. (Optional) Add action sequences for any IOS-XE 16.x specific commands.
    3. Applet runs the package clean process to delete the old .pkg and packages.conf file(s).

#### Considerations

* Tested and validated on Cisco 3850-12X48U-S switches with IOS-XE 3.7.4E installed out of the box (upgrading to IOS-XE 16.3.6).
* Default TFTP blocksize is *512* on IOS-XE 3.7.4E (default is *8192* on IOS-XE 16.3.6); this speeds up the image transfer substantially.
* `post_ztp_1` applet, triggered by Vlan1 receiving a DHCP address;
  * `action 01.00 ... maxrun 900` - 15 minutes to accommodate the 2 minute wait, the 4-5 minute TFTP download, and the 5-6 minute install.
  * `action 01.01 wait 120` - Vlan1 obtains a DHCP address approximately 1.5 minutes before the switch will allow configurations if stacked (see **IOS-XE 3.7.4E Log** below).
* `post_ztp_2` applet, triggered by IOS-XE 16.x specific *redundancy* syslog message;
  * `action 01.00 ... maxrun 600` - 10 minutes to accommodate the 2 minute wait, any optional configuration changes and the software package clean process.
  * `action 01.01 wait 120` - *Redundancy* syslog message is logged approximately 1.75 minutes before the switch will allow configurations if stacked (see **IOS 16.3.6 Log** below).

#### Log files

* IOS-XE 3.7.4E
    ```
    *21:32:15.992: %DHCP-6-ADDRESS_ASSIGN: Interface Vlan1 assigned DHCP address 172.17.250.6, mask 255.255.254.0
    ...
    *21:33:42.831: %HA_CONFIG_SYNC-6-BULK_CFGSYNC_SUCCEED: Bulk Sync succeeded
    *21:33:43.824: %RF-5-RF_TERMINAL_STATE: 1 ha_mgr:  Terminal state reached for (SSO)
    ```

* IOS-XE 16.3.6
    ```
    21:54:16.002 PDT: %IOSXE_REDUNDANCY-6-PEER: Active detected switch 2 as standby.
    ...
    21:56:00.711 PDT: %HA_CONFIG_SYNC-6-BULK_CFGSYNC_SUCCEED: Bulk Sync succeeded
    21:56:01.735 PDT: %RF-5-RF_TERMINAL_STATE: Terminal state reached for (SSO)
    ```

#### Required Config

* Disable FreeZTP image downloads

    ```
    ztp set dhcpd <SCOPE> imagediscoveryfile-option disable
    ztp request dhcpd-commit
    ztp service restart
    ```

* Allocate a *provisioning interface*; i.e. the interface connected to the provisioning network.

* Modify the variables in the template config snippet below to suit network/needs, then add the whole snippet to the J2 switch template.

    * *The four variables can be defined in the keystore or left in the template.*

        | Variable      | Description                                                                                                        |
        | :-----------: | :----------------------------------------------------------------------------------------------------------------- |
        | `tftp_addr`   | Address of TFTP server, typically FreeZTP.                                                                         |
        | `image_bin`   | Name of the image file to download.                                                                                |
        | `prov_int`    | Interface to be used for provisioning; e.g. Te1/0/48<br>> *3850-12X48U-S interfaces 37-48 are TenGigabitEthernet.* |
        | `access_vlan` | Vlan to configure on the provisioning interface (Gi1/0/48) after upgrade/reload is complete.                       |

* Template Config Snippet

    ```jinja2
    !-- Variables (keys) statically defined within the template.
    !{% set tftp_addr = "172.17.251.251" %}
    !{% set image_bin = "cat3k_caa-universalk9.16.03.06.SPA.bin"%}
    !{% set access_vlan = "501" %}
    !{% set prov_int = "Te1/0/48" %}

    !-- Required for EEM applet to function as intended.
    logging buffered 20480 debugging
    file prompt quiet
    ip tftp blocksize 8192

    !-- Required for TFTP transfers from FreeZTP (or other reachable TFTP server; i.e. `tftp_addr`).
    interface Vlan1
    ip address dhcp
    no shutdown

    !-- Interface that is connected to the provisioning network, must remain on Vlan1 for TFTP download.
    interface GigabitEthernet1/0/48
    description TMP//PROVISION:Omit config; updated with post_ztp_2 EEM applet.
    switchport
    switchport mode access
    switchport nonegotiate
    switchport access vlan 1
    spanning-tree portfast
    no shutdown

    !-- POST_ZTP_1 EEM applet to download and install the image, clean up config, then reload.
    event manager applet post_ztp_1
    event syslog occurs 1 pattern "%DHCP-6-ADDRESS_ASSIGN: Interface Vlan1 assigned DHCP address" maxrun 900
    action 01.00 syslog msg "\n     ##Switch/stack is ready, downloading and installing image in 120s."
    action 01.01 wait 120
    action 01.02 cli command "enable"
    action 01.03 cli command "debug event man act cli"
    action 02.00 cli command "conf t"
    action 03.00 cli command "no event man app post_ztp_1"
    action 04.00 cli command "do copy tftp://{{ tftp_addr }}/{{ image_bin }} flash:"
    action 05.00 cli command "int vlan 1"
    action 05.01 cli command   "no ip addr"
    action 05.02 cli command   "shut"
    action 06.00 cli command "int {{ prov_int }}"
    action 06.01 cli command   "no desc"
    action 06.02 cli command   "switchp acc vl {{ access_vlan }}
    action 07.00 cli command "end"
    action 08.00 cli command "write mem" pattern "confirm|#"
    action 08.01 cli command ""
    action 09.00 cli command "software install file flash:{{ image_bin }} new force" pattern "proceed|#"
    action 09.01 cli command "y"
    action 10.00 syslog msg "\n     ## Installation complete, reloading for upgrade."
    action 10.01 cli command "undebug all"

    !-- (Optional) POST_ZTP_2 applet to run package clean and add any config commands that were previously incompatible.
    !-- (Optional) Add any desired configs between actions 03.00 and 04.00.
    event manager applet post_ztp_2
    event syslog occurs 1 pattern "%IOSXE_REDUNDANCY-6-PEER" maxrun 600
    action 01.00 syslog msg "\n     ## Switch/stack reloaded on new image, running 'post_ztp_2' EEM applet in 120s."
    action 01.01 wait 120
    action 01.02 cli command "enable"
    action 01.03 cli command "debug event man act cli"
    action 02.00 cli command "conf t"
    action 03.00 cli command "no event man app post_ztp_2"
    action 04.00 cli command "end"
    action 05.00 cli command "write mem" pattern "confirm|#"
    action 05.01 cli command ""
    action 06.00 cli command "req plat soft pack clean sw all" pattern "proceed|#"
    action 06.01 cli command "y"
    action 07.00 syslog msg "\n     ## Any unused .bin or .pkg files have been deleted.\n     ## Switch is ready for deployment, OK to power off."
    action 07.01 cli command "undebug all"
    ```










[logo]: http://www.packetsar.com/wp-content/uploads/FreeZTP-100.png
[BugID]: https://i.imgur.com/s2avfF0.png