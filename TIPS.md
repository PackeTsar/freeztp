[< Main README](/README.md)


# FreeZTP ![FreeZTP][logo]

Some usage tips and tricks from real world FreeZTP deployments.


-----------------------------------------
## TABLE OF CONTENTS
1. [Use-case: Provisioning Without Vlan1](#use-case-provisioning-without-vlan1)
2. [Use-case: Upgrade IOS-XE 3.7.x to 16.3.6](#use-case-upgrade-ios-xe-37x-to-1636)
3. [Use-case: Automated IOS-XE Stack Renumbering](#use-case-automated-ios-xe-stack-renumbering)
4. [Tip: Advanced Jinja Syntax](#tip-advanced-jinja-syntax)
5. [Use Case: Multi-Platform IOS / IOS-XE Upgrade](#use-case-multi-platform-ios--ios-xe-upgrade)
6. [Use Case: Automatic Stack Reordering - Alternate Method](#use-case-automatic-stack-renumbering---alternate-method)


-----------------------------------------
## Use-case: Provisioning Without Vlan1

###### Author: [derek-shnosh](https://github.com/derek-shnosh), Rev: 1, Date: 2018.1008, FreeZTP v1.1.0

The use of Vlan1 is not required for provisioning. The client switch running the smart-install process will still bring up all interfaces as *dynamic desirable* (or other default behavior) on Vlan1; however, disabling CDP and enabling BPDU filter will circumvent any undesirable spanning-tree behavior that would otherwise interfere with the link coming up between the master and client switches.

**NOTE: A client switch should only be connected to the *master* provisioning switch during provisioning**; i.e. a client switch should never be connected to the provisioning environment and production infrastructure during the provisioning process, spanning-tree loops can occur.

### Interface Configuration (Master Switch)

* Configure the *master* provisioning switch interfaces as follows; Replace `<n>` with interfaces that client switches will connect to.

    ```cisco-ios-cfg
    interface <n>
      desc PROVISION
      switchport access vlan 3967
      switchport mode access
      switchport nonegotiate
      no cdp enable
      spanning-tree portfast
      spanning-tree bpdufilter enable
    ```

* *Interface config assumes the following details for the provisioning environment, adjust accordingly.*

    | VLAN  | Subnet          | IP Allocation                                                                      |
    | :---: | :-------------: | :--------------------------------------------------------------------------------- |
    | 3967  | 172.31.255.0/24 | **.1** - Gateway (optional)<br>**.2** - FreeZTP server<br>**.5 - .254** DHCP range |


-----------------------------------------
## Use-case: Upgrade IOS-XE 3.7.x to 16.3.6

###### Author: [derek-shnosh](https://github.com/derek-shnosh), Rev: 2, Date: 2018.1224, FreeZTP v1.1.0

### Preamble

IOS-XE 3.7.4 cannot upgrade to 16.3.6 via smart-install because `new force` isn't appended. This workaround utilizes EEM applets in a Jinja2 switch template to download install the updated image. 

#### Switch log output from failure

```cisco-ios-log
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

#### TAC confirmation

> The behavior is expected due to the command syntax difference as you suspected. We documented the behavior in a bug below: [https://bst.cloudapps.cisco.com/bugsearch/bug/CSCvd49193](https://bst.cloudapps.cisco.com/bugsearch/bug/CSCvd49193). The running code 3.7.4E is affected and this issue is fixed on 3.6.8E.
> 
> Is it possible for you to try the following?
>
> 1- Upgrade from 3.7.4E to 3.6.8E via smart install
> 
> 2- Upgrade from 3.6.8E to 16.3.6 via smart install
> 
> ![BugID_Screenshot_from_TAC][BugID]

### Considerations/Notes

* Validated on Cisco 3850-12X48U-S switches with IOS-XE 3.7.4E installed out of the box; upgrading to IOS-XE 16.3.6.
* Default TFTP blocksize is *512* on IOS-XE 3.7.4E, and *8192* on IOS-XE 16.3.6; adding this to the template significantly reduces the image transfer time.
* The J2 template should not contain any configuration or syntax that is incompatible in IOS-XE version (3.7.4E). Any commands that are compatible with later IOS-XE versions only should be added to the `post_ztp_2` applet.

#### Applet: `post_ztp_1`

* Triggered by the switch receiving a DHCP address on Vlan1; notes regarding the `maxrun` and `wait`;
  * `action 01.00 ... maxrun 900` - 15 minutes to accommodate the 2 minute wait, the 4-5 minute TFTP download, and the 5-6 minute install.
  * `action 01.01 wait 120` - Vlan1 obtains a DHCP address approximately 1.5 minutes before the switch will allow configurations if stacked (see **IOS-XE 3.7.4E Log** below). *This wait can be omitted for stand-alone switches*.

##### IOS-XE 3.7.4E Log

```cisco-ios-log
*21:32:15.992: %DHCP-6-ADDRESS_ASSIGN: Interface Vlan1 assigned DHCP address 172.17.250.6, mask 255.255.254.0
...
*21:33:42.831: %HA_CONFIG_SYNC-6-BULK_CFGSYNC_SUCCEED: Bulk Sync succeeded
*21:33:43.824: %RF-5-RF_TERMINAL_STATE: 1 ha_mgr:  Terminal state reached for (SSO)
```


#### Applet: `post_ztp_2`

* Triggered by IOS-XE 16.x specific *redundancy* syslog message; notes regarding the `maxrun` and `wait`;
  * `action 01.00 ... maxrun 600` - 10 minutes to accommodate the 2 minute wait, any optional configuration changes and the software package clean process.
  * `action 01.01 wait 120` - *Redundancy* syslog message is logged approximately 1.75 minutes before the switch will allow configurations if stacked (see **IOS-XE 16.3.6 Log** below). *This wait can be omitted for stand_alone switches*.

##### IOS-XE 16.3.6 Log

```cisco-ios-log
21:54:16.002 PDT: %IOSXE_REDUNDANCY-6-PEER: Active detected switch 2 as standby.
...
21:56:00.711 PDT: %HA_CONFIG_SYNC-6-BULK_CFGSYNC_SUCCEED: Bulk Sync succeeded
21:56:01.735 PDT: %RF-5-RF_TERMINAL_STATE: Terminal state reached for (SSO)
```

### Process/Explanation

1. Switch is powered up connected to the provisioning network and initiates smart-install. Switch requests an upgrade first but no image is downloaded since image download is disabled in FreeZTP.
2. Switch requests config, FreeZTP gives a (merged) config containing the *required config*.
3. Switch applies configuration with Vlan1 configured for DHCP addressing.
   * **`post_ztp_1` is triggered by Vlan1 obtaining a DHCP address**.
4. *[EEM Applet `post_ztp_1` loaded to memory.]*
    1. Applet deletes itself from running config, downloads the bin file, cleans up temp configs and writes the startup-config.
    2. Switch then runs the `software install` command, answers **y** to reload prompt from install command.
5. Switch reloads.
   * **`post_ztp_2` is triggered by a syslog command specific to IOS-XE 16.x *(%IOSXE_REDUNDANCY-6-PEER)***.
      > **This trigger may need to be changed!** *I'm unsure if this syslog message is present when provisioning a stand-alone switch as I never tested this scenario. I will update if I get an opportunity to test this on a stand-alone switch.*
6. *[EEM applet `post_ztp_2` loaded into memory.]*
    1. Applet deletes itself from running configuration and writes the startup-config.
    2. *(Optional)* Add action sequences for any IOS-XE 16.x specific commands.
    3. Applet runs the package clean process to delete the old .pkg and packages.conf file(s).

### Required Config

* Disable FreeZTP image downloads, replace `<SCOPE>` with the name of your configured DHCP scope.

   ```bash
   ztp set dhcpd <SCOPE> imagediscoveryfile-option disable && \
   ztp request dhcpd-commit && \
   ztp service restart
   ```

* Allocate a *provisioning interface* as `prov_int`; i.e. the interface connected to the provisioning network.

* Modify the variables in the template config snippet below to suit network/needs, then add the whole snippet to the J2 switch template.
   > These four variables can be defined in the keystore or left in the template.

   |    Variable     | Description                                                                                                     |
   | :-------------: | :-------------------------------------------------------------------------------------------------------------- |
   |   `tftp_addr`   | Address of TFTP server, typically FreeZTP.                                                                      |
   |  `access_vlan`  | Vlan to configure on the provisioning interface (Gi1/0/48) after upgrade/reload is complete.                    |
   |   `prov_int`    | Interface to be used for provisioning; e.g. Te1/0/48 *(3850-12X48U-S interfaces 37-48 are TenGigabitEthernet.)* |
   | `image.bin/ver` | Name of the image file to download, and the image version short-hand.                                                                             |

#### Template Config Snippet

```jinja2
!-- EEM applet to upgrade switches accordingly (ALL SUBSEQUENT LINES ARE REQUIRED).
!---- {%set sw_count=idarray|count%}
!---- {%set tftp_addr="172.17.251.251"%}
!---- {%set access_vlan="501"%}
!---- {%set prov_int="Te1/0/48"%}
!---- {%set image={"bin":"cat3k_caa-universalk9.16.03.06.SPA.bin",
                   "ver":"16.3.6"}%}
!
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
!
event manager environment q "
!
event manager applet sw_upgrade
!-- Check all switches in stack to see if an upgrade is needed.
 event syslog occurs 1 pattern "Configured from tftp://{{tftp_addr}}" maxrun 960
 action 00.00 syslog msg "\n     ## Configuration received via TFTP, run 'sw_upgrade' EEM applet in 120s."
 action 00.01 wait 120
 action 00.02 syslog msg "\n     ## Checking all switches' version."
 action 00.03 cli command "enable"
 action 00.04 cli command "show mod | i ^.[1-9]"
 action 00.05 set stack "$_cli_result"
 action 00.06 syslog msg "\n     ## Current list of switches in stack;\n$stack"
 action 00.07 set error_list ""
 action 00.08 set upgrade_list ""
 !{% for sw in idarray %}
 !{% set i = loop.index %}
 action 0{{i}}.00 set sw_num "{{i}}"
 action 0{{i}}.01 set pri "16"
 action 0{{i}}.02 decrement pri {{i}}
 action 0{{i}}.03 regexp "{{sw}}" "$stack"
 action 0{{i}}.04 if $_regexp_result ne "1"
 action 0{{i}}.05  append error_list "\n     ##  {{sw}} is allocated (idarray_{{i}}) but was not found in the stack."
 action 0{{i}}.06 else
 action 0{{i}}.07  set i "0"
 action 0{{i}}.08  foreach line "$stack" "\n"
 action 0{{i}}.09   increment i
 action 0{{i}}.10   if $i le "{{sw_count}}"
 action 0{{i}}.11    string trim "$line"
 action 0{{i}}.12    set line "$_string_result"
 action 0{{i}}.13    regexp "{{sw}}" "$line"
 action 0{{i}}.14    if $_regexp_result eq "1"
 action 0{{i}}.15     regexp "([0-9\.A-Z]+$)" "$line" curr_ver
 action 0{{i}}.16     if $curr_ver ne "{{image.ver}}"
 action 0{{i}}.17      append upgrade_list "{{i}}"
 action 0{{i}}.18     end
 action 0{{i}}.19     break
 action 0{{i}}.20    end
 action 0{{i}}.21   end
 action 0{{i}}.22  end
 action 0{{i}}.23 end
 !{% endfor %}
 action 10.00 wait 5
 action 10.01 if $error_list ne ""
 action 10.02  syslog msg "\n     ## The following errors occurred; $error_list"
 action 10.03 end
 action 11.00 cli command "conf t"
 action 11.01 cli command "no event man app sw_upgrade"
 action 12.00 if $upgrade_list eq ""
 action 12.01  syslog msg "\n     ## All switches are running version {{target_ver}}, skipping download->upgrade/reload.\n     ## Finalizing config in 20s."
 action 12.02  cli command "no event man env q"
 action 12.03  cli command "event man env ztp_upgraded no"
 action 12.04  cli command " event man app post_upgrade"
 action 12.05  cli command " event timer countdown time 20 maxrun 480"
 action 12.06  cli command " no action 00.00"
 action 12.07  cli command " no action 00.01"
 action 12.08  cli command " end"
 action 12.09  cli command "write mem" pattern "confirm|#"
 action 12.10  cli command ""
 action 12.11 else
 action 12.12  syslog msg "\n     ## One or more switches require an upgrade to version {{target_ver}} ($upgrade_list).\n     ## Proceeding with download->upgrade/reload."
 action 12.13  cli command "event man env ztp_upgraded yes"
 action 12.14  cli command "event man app post_upgrade"
 action 12.15  cli command " event syslog occurs 1 pattern $q%IOSXE_REDUNDANCY-6-PEER$q maxrun 630"
 action 12.16  cli command " no event man env q"
 action 12.17  cli command "end"
 action 12.18  cli command "write mem" pattern "confirm|#"
 action 12.19  cli command ""
 action 12.20  syslog msg "\n     ## (Standby) Downloading image..."
 action 12.21  cli command "copy tftp://{{tftp_addr}}/{{image.bin}} flash:"
 action 12.22  syslog msg "\n     ## (Standby) Image downloaded, upgrading..."
 action 12.23  cli command "software install file flash:{{image.bin}} new force" pattern "proceed|#"
 action 12.24  syslog msg "\n     ## Upgrade complete, rebooting."
 action 12.25  cli command "y"
 action 12.26 end
 !
 event manager applet post_upgrade
!-- Clean up VL-1 and `prov_int` configs, write mem, and then perform package clean.
!-- (Optional) Add any desired configs between actions 03.00 and 04.00.
 event none
 action 00.00 syslog msg "\n     ## Switch reloaded on new image, running 'post_upgrade' EEM applet in 150s."
 action 00.01 wait 150
 action 00.02 syslog msg "\n     ## Applying global configs ignored by smart-install and generating crypto key."
 action 00.03 cli command "enable"
 action 00.04 set upgr "$ztp_upgraded"
 action 01.00 cli command "conf t"
 action 01.01 cli command "no event man env ztp_upgraded"
 action 01.02 cli command "no event man app post_upgrade"
 !-- action 02.00 cli command "" {# Use actions 02.00 - 02.99 for desired configs or configs specific to later IOS-XE version(s). #}
 action 03.00 syslog msg "\n     ## Disabling VL-1 SVI, updating Te#/0/48 configs, and writing startup config."
 action 03.01 cli command "int vl 1"
 action 03.02 cli command " no desc"
 action 03.03 cli command " no ip addr"
 action 03.04 cli command " shut"
 action 03.05 cli command "default range {{prov_int}}"
 action 03.06 cli command "int {{prov_int}}"
 !-- action 03.07 cli command "" {# Use actions 3.07 - 3.99 to configure `prov_int` as desired. #}
 action 04.00 cli command "end"
 action 04.01 cli command "write mem" pattern "confirm|#"
 action 04.02 cli command ""
 action 05.00 if $upgr eq "yes"
 action 05.01  syslog msg "\n     ## (Standby) ZTP upgrade detected, performing software package clean..."
 action 05.02  cli command "req plat soft pack clean sw all" pattern "proceed|#"
 action 05.03  cli command "y"
 action 05.04  syslog msg "\n     ## Unused .bin or .pkg files from previous version(s) have been deleted."
 action 05.05 else
 action 05.06  syslog msg "\n     ## ZTP upgrade not detected, skipping software package clean."
 action 05.07 end
 action 05.08 syslog msg "\n     ## Start-up config written, ({{hostname}}) is ready for deployment, OK to power off."
```

-----------------------------------------
## Use-case: Automated IOS-XE Stack Renumbering

###### Author: [derek-shnosh](https://github.com/derek-shnosh), Rev: 5b, Date: 2019.0823, FreeZTP v1.1.0

### Preamble

Include this snippet in a FreeZTP Jinja2 template to create an EEM applet that will renumber and prioritize all switches in a stack according to how they were allocated in the FreeZTP keystore.

It's almost guaranteed that stacked switches will not be numbered in the desired order if powered on simultaneously for the first time. The first switch in the stack might be assigned switch number 3, and the second switch might be assigned switch number 1, etc.

This can be circumvented by waiting [*2 minutes*](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst3850/hardware/installation/guide/b_c3850_hig/b_c3850_hig_chapter_010.html#ariaid-title13) between powering up switches. However this becomes a bit cumbersome and inefficient when provisioning a large amount of switch stacks.

With this snippet all switches in the stack can be powered on simultaneously. After the election processes are complete the stack will continue booting and then perform the smart-install procedure where it will receive the EEM applet as part of the templated configuration.

In this use-case, FreeZTP's `idarray` variables are being used to define stack member serial numbers. When the template is merged with the keystore, an action sequence is generated for each serial number (`idarray_#`) associated with the hostname (`keystore_id`). Switch serial numbers should be assigned to `idarray_#`'s as they're meant to be numbered in the stack (see the CSV example below).

#### Snippet

* Configuration snippet to be added to the Jinja2 template.
  * The first section serves to have the `IDARRAY` variables (passed from FreeZTP) appear in the merged config; these lines are *ignored by the switch* due to the leading `!` notations (commented out).
  * **Everything below `!-- EEM applet to renumber switches accordingly` is required**.

```jinja2
!-- Variables (keys) parsed from CSV keystore.
!---- IDARRAY_1 (switch 1 serial number): {{idarray_1}}
!---- IDARRAY_2 (switch 2 serial number): {{idarray_2}}
!---- IDARRAY_3 (switch 3 serial number): {{idarray_3}}
!---- IDARRAY_4 (switch 4 serial number): {{idarray_4}}
!---- IDARRAY_5 (switch 5 serial number): {{idarray_5}}
!---- IDARRAY_6 (switch 6 serial number): {{idarray_6}}
!---- IDARRAY_7 (switch 7 serial number): {{idarray_7}}
!---- IDARRAY_8 (switch 8 serial number): {{idarray_8}}
!---- IDARRAY_9 (switch 9 serial number): {{idarray_9}}
!---- IDARRAY (all serials): {{idarray}}
!
!-- EEM applet to renumber switches accordingly (ALL SUBSEQUENT LINES ARE REQUIRED).
!---- SW_COUNT (count of serials found in IDARRAY): {%set sw_count=idarray|count%}{{sw_count}}
event manager applet sw_stack
  event syslog occurs 1 pattern "%SYS-5-CONFIG_I: Configured from tftp" maxrun 75
  action 00.00 syslog msg "\n     ## FreeZTP configuration received via TFTP, run 'sw_stack' EEM applet in 15s."
  action 00.01 wait 15
  action 00.02 cli command "enable"
  action 00.03 cli command "show mod | i ^.[1-9]"
  action 00.04 set stack "$_cli_result"
  action 00.05 syslog msg "\n     ## Checking all switches' version and stack membership, adjusting where necessary.\n     ## Current order;\n$stack"
  action 00.06 set error_list ""
  action 00.07 set change_list ""
  action 00.08 set upgrade_list ""
  {%for sw in idarray%}
  {%-  set i=loop.index%}
  action 0{{i}}.00 set sw_num "{{i}}"
  action 0{{i}}.01 set pri "16"
  action 0{{i}}.02 decrement pri {{i}}
  action 0{{i}}.03 regexp "{{sw}}" "$stack"
  action 0{{i}}.04 if $_regexp_result ne "1"
  action 0{{i}}.05  syslog msg "\n     ## {{sw}} (Sw-{{i}} serial) not found in the stack, check 'show mod' output."
  action 0{{i}}.06  append error_list "\n     ##  {{sw}} is allocated (idarray_{{i}}) but was not found in the stack."
  action 0{{i}}.07 else
  action 0{{i}}.08  set i "0"
  action 0{{i}}.09  foreach line "$stack" "\n"
  action 0{{i}}.10   increment i
  action 0{{i}}.11   if $i le "{{sw_count}}"
  action 0{{i}}.12    string trim "$line"
  action 0{{i}}.13    set line "$_string_result"
  action 0{{i}}.14    regexp "{{sw}}" "$line"
  action 0{{i}}.15    if $_regexp_result eq "1"
  action 0{{i}}.16     regexp "([0-9\.A-Z]+$)" "$line" curr_ver
  action 0{{i}}.17     cli command "switch $i priority $pri" pattern "continue|#"
  action 0{{i}}.18     cli command "y"
  action 0{{i}}.19     if $i eq $sw_num
  action 0{{i}}.20      append change_list "\n     ##  {{sw}} (Priority: $pri // Numbered:       $sw_num  // Version: $curr_ver)"
  action 0{{i}}.21     else
  action 0{{i}}.22      cli command "switch $i renumber $sw_num" pattern "continue|#"
  action 0{{i}}.23      cli command "y"
  action 0{{i}}.24      append change_list "\n     ##  {{sw}} (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver)"
  action 0{{i}}.25     end
  action 0{{i}}.26     break
  action 0{{i}}.27    end
  action 0{{i}}.28   end
  action 0{{i}}.29  end
  action 0{{i}}.30 end
  {%endfor%}
  action 10.00 wait 5
  action 10.01 if $error_list ne ""
  action 10.02  syslog msg "\n     ## The following errors occurred; $error_list"
  action 10.03 end
  action 10.04 syslog msg "\n     ## Switches below have been assigned a priority and renumbered* as needed; $change_list"
  action 10.05 cli command "conf t"
  action 10.06 cli command "no event man app sw_stack"
  action 10.07 cli command "end"
  action 10.08 cli command "write mem" pattern "confirm|#"
  action 10.09 cli command ""
  action 10.10 syslog msg "\n     ## EEM applet (sw_stack) deleted and config written, reload for changes to take effect."
  !
```

### Example

In this example, there are four switches allocated to the stack **ASW-TR01-01**;

| Order/Array # | Serial # | MAC Address |  Notes |
| :-: | :-: | :-: | :- |
| `idarray_1` | **FOC11111111** | **abcd.ef11.1111** | Should be switch 1 in the stack, with a priority of 15. |
| `idarray_2` | **FOC22222222** | **abcd.ef22.2222** | Should be switch 2 in the stack, with a priority of 14. |
| `idarray_3` | **FOC33333333** | **abcd.ef33.3333** | Should be switch 3 in the stack, with a priority of 13. |
| `idarray_4` | **FOC44444444** | **abcd.ef44.4444** | Should be switch 4 in the stack, with a priority of 12. |

#### CSV

Variables defined in the keystore (FreeZTP);

* `keystore_id` = Hostname of the switch.
* `association` = J2 template configured in FreeZTP.
* `idarray_#` = Switch serial number(s).

> `idarray_#` fields are populated with serial numbers in accordance with how they are to be numbered in the stack.

```csv
keystore_id,association,idarray_1,idarray_2,idarray_3,idarray_4,idarray_5,idarray_6,idarray_7,idarray_8,idarray_9
ASW-TR01-01,TEST,FOC11111111,FOC22222222,FOC33333333,FOC44444444,,,,,
```

#### Switch Priorities

The default *priority* for all switches (out of the box) is **1**; these priorities do not change during the election process.

Notice that all switches have a priority of **1** in the output below. The priority range is **1-15**; the (online) switch with highest priority will be chosen as the *active* 'supervisor' switch during any election processes/failure events.

```cisco-ios-show
ASW-TR01-01#show switch
Switch/Stack Mac Address : abcd.ef22.2222 - Local Mac Address
Mac persistency wait time: Indefinite
                                             H/W   Current
Switch#   Role    Mac Address     Priority Version  State 
------------------------------------------------------------
*1       Active   abcd.ef22.2222     1      V02     Ready               
 2       Standby  abcd.ef44.4444     1      V02     Ready               
 3       Member   abcd.ef11.1111     1      V02     Ready               
 4       Member   abcd.ef33.3333     1      V02     Ready               
```

#### Switch Numbers

The default *number* for all switches (out of the box) is also **1**; as the switches boot they detect stack neighbors and perform an election process which renumbers the switches automatically.

The election process for this example resulted in the switches being numbered as follows;

```cisco-ios-show
ASW-TR01-01#show module
Switch  Ports    Model                Serial No.   MAC address     Hw Ver.       Sw Ver. 
------  -----   ---------             -----------  --------------  -------       --------
 1       62     WS-C3850-12X48U-S     FOC22222222  abcd.ef22.2222  V02           03.07.04E   
 2       62     WS-C3850-12X48U-S     FOC44444444  abcd.ef44.4444  V02           03.07.04E   
 3       62     WS-C3850-12X48U-S     FOC11111111  abcd.ef11.1111  V02           03.07.04E   
 4       62     WS-C3850-12X48U-S     FOC33333333  abcd.ef33.3333  V02           03.07.04E   
```

### Process/Explanation

1. Switches are connected via stack cables and powered up simultaneously.
    > An interface on only one of the switches needs to be connected to the provisioning network.
2. Switches complete the election process and stack initiates smart-install.
3. Stack requests config, FreeZTP gives a (merged) config containing the code.
    * J2 variable `sw_count` is *set*  during the merge process by counting serial numbers found in `idarray`.
4. Stack applies configuration and a syslog message is generated; **`sw_stack` applet is triggered**.
5. *[EEM Applet `sw_stack` loaded to memory.]*
    1. Waits 120 seconds for the stack redundancy operations to complete.
    2. Executes command `show module | inc ^.[1-9]` *(output as read by EEM for current example)*;
        > This output is what EEM stores as `$stack` for parsing. All line numbers correlate with the stack's current switch allocation numbers; i.e. first line contains information for switch 1, second line contains information for switch 2, etc... 
       ```cisco-ios-log
        1       62     WS-C3850-12X48U-S     FOC22222222  abcd.ef22.2222  V02           03.07.04E   
        2       62     WS-C3850-12X48U-S     FOC44444444  abcd.ef44.4444  V02           03.07.04E   
        3       62     WS-C3850-12X48U-S     FOC11111111  abcd.ef11.1111  V02           03.07.04E   
        4       62     WS-C3850-12X48U-S     FOC33333333  abcd.ef33.3333  V02           03.07.04E   
       ASW-TR01-01#
       ```
    3. [J2 Loop] For each switch, searches the entire output for its serial number;
        * If not found, a syslog message will be generated and the applet will move onto the next switch.
        * [EEM Loop] If found, the applet searches the output line-by-line until it finds the serial number;
            > The last line of the output is the switch hostname (elevated prompt), which is ignored when searching for switch serial number(s); i.e. the number of lines that the applet will search is limited by the Jinja2 `sw_count` variable set in the template.
            * If the line number where the serial number was found matches the allocated switch number (`idarray_#`), only the priority will be set.
            * If the line number where the serial number was found does not match the allocated switch number, the priority will be set and the switch will be renumbered.
    4. Syslog messages are generated outlining any errors and all changes made to priorities and numbers.
    5. Applet deletes itself from running configuration, writes the startup-config, and generates a syslog message stating that the process is complete.
6. The stack can now be reloaded to finish the renumbering process.

### Merged Config

* Merged configuration that is pushed to the switch from FreeZTP for this example;
  * J2 templating functions do not *print*; i.e. anything enclosed with `{% %}` will not appear in the merged config.
  * Any line starting with a `!` will be ignored by the switch.

```cisco-ios-cfg
!-- Variables (keys) parsed from CSV keystore.
!---- IDARRAY_1 (switch 1 serial number): FOC11111111
!---- IDARRAY_2 (switch 2 serial number): FOC22222222
!---- IDARRAY_3 (switch 3 serial number): FOC33333333
!---- IDARRAY_4 (switch 4 serial number): FOC44444444
!---- IDARRAY_5 (switch 5 serial number): 
!---- IDARRAY_6 (switch 6 serial number): 
!---- IDARRAY_7 (switch 7 serial number): 
!---- IDARRAY_8 (switch 8 serial number): 
!---- IDARRAY_9 (switch 9 serial number): 
!---- IDARRAY (all serials): ['FOC11111111', 'FOC22222222', 'FOC33333333', 'FOC44444444']
!
!-- EEM applet to renumber switches accordingly (ALL SUBSEQUENT LINES ARE REQUIRED).
!---- SW_COUNT (count of serials found in IDARRAY): 4
event manager applet sw_stack
  event syslog occurs 1 pattern "%SYS-5-CONFIG_I: Configured from tftp" maxrun 75
  action 00.00 syslog msg "\n     ## FreeZTP configuration received via TFTP, run 'sw_stack' EEM applet in 15s."
  action 00.01 wait 15
  action 00.02 cli command "enable"
  action 00.03 cli command "show mod | i ^.[1-9]"
  action 00.04 set stack "$_cli_result"
  action 00.05 syslog msg "\n     ## Checking all switches' version and stack membership, adjusting where necessary.\n     ## Current order;\n$stack"
  action 00.06 set error_list ""
  action 00.07 set change_list ""
  action 00.08 set upgrade_list ""
  
  action 01.00 set sw_num "1"
  action 01.01 set pri "16"
  action 01.02 decrement pri 1
  action 01.03 regexp "FOC11111111" "$stack"
  action 01.04 if $_regexp_result ne "1"
  action 01.05  syslog msg "\n     ## FOC11111111 (Sw-1 serial) not found in the stack, check 'show mod' output."
  action 01.06  append error_list "\n     ##  FOC11111111 is allocated (idarray_1) but was not found in the stack."
  action 01.07 else
  action 01.08  set i "0"
  action 01.09  foreach line "$stack" "\n"
  action 01.10   increment i
  action 01.11   if $i le "4"
  action 01.12    string trim "$line"
  action 01.13    set line "$_string_result"
  action 01.14    regexp "FOC11111111" "$line"
  action 01.15    if $_regexp_result eq "1"
  action 01.16     regexp "([0-9\.A-Z]+$)" "$line" curr_ver
  action 01.17     cli command "switch $i priority $pri" pattern "continue|#"
  action 01.18     cli command "y"
  action 01.19     if $i eq $sw_num
  action 01.20      append change_list "\n     ##  FOC11111111 (Priority: $pri // Numbered:       $sw_num  // Version: $curr_ver)"
  action 01.21     else
  action 01.22      cli command "switch $i renumber $sw_num" pattern "continue|#"
  action 01.23      cli command "y"
  action 01.24      append change_list "\n     ##  FOC11111111 (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver)"
  action 01.25     end
  action 01.26     break
  action 01.27    end
  action 01.28   end
  action 01.29  end
  action 01.30 end
  
  action 02.00 set sw_num "2"
  action 02.01 set pri "16"
  action 02.02 decrement pri 2
  action 02.03 regexp "FOC22222222" "$stack"
  action 02.04 if $_regexp_result ne "1"
  action 02.05  syslog msg "\n     ## FOC22222222 (Sw-2 serial) not found in the stack, check 'show mod' output."
  action 02.06  append error_list "\n     ##  FOC22222222 is allocated (idarray_2) but was not found in the stack."
  action 02.07 else
  action 02.08  set i "0"
  action 02.09  foreach line "$stack" "\n"
  action 02.10   increment i
  action 02.11   if $i le "4"
  action 02.12    string trim "$line"
  action 02.13    set line "$_string_result"
  action 02.14    regexp "FOC22222222" "$line"
  action 02.15    if $_regexp_result eq "1"
  action 02.16     regexp "([0-9\.A-Z]+$)" "$line" curr_ver
  action 02.17     cli command "switch $i priority $pri" pattern "continue|#"
  action 02.18     cli command "y"
  action 02.19     if $i eq $sw_num
  action 02.20      append change_list "\n     ##  FOC22222222 (Priority: $pri // Numbered:       $sw_num  // Version: $curr_ver)"
  action 02.21     else
  action 02.22      cli command "switch $i renumber $sw_num" pattern "continue|#"
  action 02.23      cli command "y"
  action 02.24      append change_list "\n     ##  FOC22222222 (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver)"
  action 02.25     end
  action 02.26     break
  action 02.27    end
  action 02.28   end
  action 02.29  end
  action 02.30 end
  
  action 03.00 set sw_num "3"
  action 03.01 set pri "16"
  action 03.02 decrement pri 3
  action 03.03 regexp "FOC33333333" "$stack"
  action 03.04 if $_regexp_result ne "1"
  action 03.05  syslog msg "\n     ## FOC33333333 (Sw-3 serial) not found in the stack, check 'show mod' output."
  action 03.06  append error_list "\n     ##  FOC33333333 is allocated (idarray_3) but was not found in the stack."
  action 03.07 else
  action 03.08  set i "0"
  action 03.09  foreach line "$stack" "\n"
  action 03.10   increment i
  action 03.11   if $i le "4"
  action 03.12    string trim "$line"
  action 03.13    set line "$_string_result"
  action 03.14    regexp "FOC33333333" "$line"
  action 03.15    if $_regexp_result eq "1"
  action 03.16     regexp "([0-9\.A-Z]+$)" "$line" curr_ver
  action 03.17     cli command "switch $i priority $pri" pattern "continue|#"
  action 03.18     cli command "y"
  action 03.19     if $i eq $sw_num
  action 03.20      append change_list "\n     ##  FOC33333333 (Priority: $pri // Numbered:       $sw_num  // Version: $curr_ver)"
  action 03.21     else
  action 03.22      cli command "switch $i renumber $sw_num" pattern "continue|#"
  action 03.23      cli command "y"
  action 03.24      append change_list "\n     ##  FOC33333333 (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver)"
  action 03.25     end
  action 03.26     break
  action 03.27    end
  action 03.28   end
  action 03.29  end
  action 03.30 end
  
  action 04.00 set sw_num "4"
  action 04.01 set pri "16"
  action 04.02 decrement pri 4
  action 04.03 regexp "FOC44444444" "$stack"
  action 04.04 if $_regexp_result ne "1"
  action 04.05  syslog msg "\n     ## FOC44444444 (Sw-4 serial) not found in the stack, check 'show mod' output."
  action 04.06  append error_list "\n     ##  FOC44444444 is allocated (idarray_4) but was not found in the stack."
  action 04.07 else
  action 04.08  set i "0"
  action 04.09  foreach line "$stack" "\n"
  action 04.10   increment i
  action 04.11   if $i le "4"
  action 04.12    string trim "$line"
  action 04.13    set line "$_string_result"
  action 04.14    regexp "FOC44444444" "$line"
  action 04.15    if $_regexp_result eq "1"
  action 04.16     regexp "([0-9\.A-Z]+$)" "$line" curr_ver
  action 04.17     cli command "switch $i priority $pri" pattern "continue|#"
  action 04.18     cli command "y"
  action 04.19     if $i eq $sw_num
  action 04.20      append change_list "\n     ##  FOC44444444 (Priority: $pri // Numbered:       $sw_num  // Version: $curr_ver)"
  action 04.21     else
  action 04.22      cli command "switch $i renumber $sw_num" pattern "continue|#"
  action 04.23      cli command "y"
  action 04.24      append change_list "\n     ##  FOC44444444 (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver)"
  action 04.25     end
  action 04.26     break
  action 04.27    end
  action 04.28   end
  action 04.29  end
  action 04.30 end
  
  action 10.00 wait 5
  action 10.01 if $error_list ne ""
  action 10.02  syslog msg "\n     ## The following errors occurred; $error_list"
  action 10.03 end
  action 10.04 syslog msg "\n     ## Switches below have been assigned a priority and renumbered* as needed; $change_list"
  action 10.05 cli command "conf t"
  action 10.06 cli command "no event man app sw_stack"
  action 10.07 cli command "end"
  action 10.08 cli command "write mem" pattern "confirm|#"
  action 10.09 cli command ""
  action 10.10 syslog msg "\n     ## EEM applet (sw_stack) deleted and config written, reload for changes to take effect."
  !
```

### Validation

* This has been confirmed functional on stacked C3850-12X48U-S switches running the following IOS-XE versions;
  * IOS-XE 3.7.4E
  * IOS-XE 16.3.6

#### Logs

Below is an abbreviated and sanitized log output from 4 stacked switches, real serial numbers have been replaced by those in this example.

```cisco-ios-log
Would you like to enter the initial configuration dialog? [yes/no]: 
Loading network-confg from 172.17.251.251 (via Vlan1): !
[OK - 94 bytes]

Loading ZTP-23D9F46EC4-confg from 172.17.251.251 (via Vlan1): !
[OK - 154241 bytes]

...
*Oct 17 2018 12:45:34.347 PDT: %SYS-5-CONFIG_I: Configured from tftp://172.17.251.251/ZTP-23D9F46EC4-confg by console
*Oct 17 2018 12:45:34.365 PDT: %HA_EM-6-LOG: sw_stack: 
     ## FreeZTP configuration received via TFTP, run 'sw_stack' EEM applet in 15s.
...
*Oct 17 2018 12:47:34.376 PDT: %HA_EM-6-LOG: sw_stack: 
     ## Checking all switches' version and stack membership, adjusting where necessary.
*Oct 17 2018 12:47:44.755 PDT: %HA_EM-6-LOG: sw_stack: 
     ## Switches below have been assigned a priority and renumbered* as needed; 
     ##  FOC11111111 (Priority: 15 // Renumbered: 3 > 1* // Version: 03.07.04E )
     ##  FOC22222222 (Priority: 14 // Renumbered: 1 > 2* // Version: 03.07.04E )
     ##  FOC33333333 (Priority: 13 // Renumbered: 4 > 3* // Version: 03.07.04E )
     ##  FOC44444444 (Priority: 12 // Renumbered: 2 > 4* // Version: 03.07.04E )
*Oct 17 2018 12:47:52.732 PDT: %SYS-5-CONFIG_I: Configured from console by eem_svc on vty0 (EEM:sw_stack)
*Oct 17 2018 12:47:52.756 PDT: %HA_EM-6-LOG: sw_stack: 
     ## EEM applet `sw_stack` deleted and config written, reload for changes to take effect.
...
```


## Tip: Advanced Jinja Syntax

###### Author: [Paul S. Chapman](https://github.com/pschapman), Rev: 1, Date: 2020.0704, FreeZTP v1.3.1 and later

For pratical purposes, having fewer baseline templates in a deployment means less maintenance for common settings.  These advanced Jinja 2 templating tricks can make this possible.  The examples presented below will show a combination of Jinja 2 and Cisco configuration and the expected post-merge output.

### In-line Jinja Variables

Sometimes it may be desirable to use custom variable for Jinja to use during its processing of the template.  This example shows how to take a variable from ZTP and place it in another variable used by Jinja.

**ZTP Configuration**

```
ztp set keystore myswitch model1 c9300-48uxm
```

**Jinja 2 Example**

```
{%set switch=model1%}
banner login You've connected to a {{switch}}
```

**Post-merge Result**

```
banner login You've connected to a c9300-48uxm
```

### Dictionaries

Dictionaries follow a combination of Python and Jinja syntax.

**Jinja 2 Example**

```
{%set hostdata={"name":"myswitch1","ip":"192.0.2.14"%}
banner login You've connected to {{hostdata.name}} at {{hostdata.ip}}
```

**Post-merge Result**

```
banner login You've connected to myswitch1 at 192.0.2.14
```

### Substrings (Indexes)

Substrings follow common python style in the form `var[x:x]`.

**Jinja 2 Example**

```
!{%set model1="c9300-48uxm"%}
!{%set prefix=model1[:5]%}
banner login You've connected to a {{prefix}}
```

**Post-merge Result**

```
banner login You've connected to a c9300
```

### Text Formatting

In many cases, python style formatting can be applied as a method in the form of `var.method()`.

**Jinja 2 Example**

```
{%set model1="c9300-48uxm"%}
banner login You've connected to a {{model1.upper()}}
```

**Post-merge Result**

```
banner login You've connected to a C9300-48UXM
```

### Conditional Lists

Lists can be created in the usual python style, `var=["item1","item2",...]`.  Lists can also be manipulated with standard python methods like `var.append("item3")`

This example shows how to extend a list based on whether or not a variable exists.

```
{% set o = listvar.append( var ) if var %}
```

Where
- '`if var`' is a Jinja 2 style condition.  In this case, if the variable contains data, then proceed with the `set` portion of the statement
- '`listvar.append( var )`' extends the list
- '`o = `' sets the operation result code to a discardable variable so that it does not show up in the merged config

**ZTP Configuration**

```
ztp set keystore myswitch model1 c9300-48uxm
ztp set keystore myswitch model2 c9300-48u
```

**Jinja 2 Example**

```
!{% set models = [] %}
!{% set o = models.append( model1 ) if model1 %}
!{% set o = models.append( model2 ) if model2 %}
!{% set o = models.append( model3 ) if model3 %}
!{% set o = models.append( model4 ) if model4 %}
```

**Post-merge Result** (Contents of variable)

Note that no blank items exist from model3 and model4

`models=["c9300-48uxm","c9300-48u"]`

### Conditional Logic

Conditional logic can be used to include or exclude portions of the template.

**ZTP Configuration**

`ztp set keystore myswitch model1 c9300`

**Jinja 2 Example**

```
!{% if model1[:5] == "c9300" %}
system mtu 9198
!{% else %}
system mtu jumbo 9198
!{% endif %}
```

**Post-merge Result** (Assuming all other criteria are met for myswitch keystore to be used)

```
!
system mtu 9198
!
```

### Looping Logic (with conditional logic and conditional list)

For practical purposes, looping logic is particularly useful to bring variable configurations together (e.g. switch stacks with mixed models, multi model support, etc.)

**ZTP Configuration**

```
ztp set keystore myswitch1 model1 c9300-48uxm
ztp set keystore myswitch1 model2 c9300-48u
#
ztp set keystore myswitch2 model1 ws-c3560cx-12pc-s
```

**Jinja 2 Example**

```
!{% set models = [] %}
!{% set o = models.append( model1 ) if model1 %}
!{% set o = models.append( model2 ) if model2 %}
!{% set o = models.append( model3 ) if model3 %}
!
!{% for model in models %}{% if model[:5] == "c9300" %}
switch {{ loop.index }} provision {{ model }}
!{% endif %}{% endfor %}
```

**Post-merge Result - myswitch1**

```
!
!
!
!
!
!
switch 1 provision c9300-48uxm
!
switch 2 provision c9300-48u
```

**Post-merge Result - myswitch2**

```
!
!
!
!
!
!
!
```


## Use Case: Multi-Platform IOS / IOS-XE Upgrade

###### Author: [Paul S. Chapman](https://github.com/pschapman), Rev: 1.2, Date: 2021.0417, FreeZTP v1.4.1

### Purpose

This is an expansion on the switch upgrade EEM presented by Derek Schnosh.  The goal is to provide an autmation set that can upgrade a wide list of Cisco Catalyst platforms including 3560CX, 3850, 9300, 94xx, 9500, and Industrial Ethernet platforms.  To support these platforms, the automation must be able to account for variations in file system names (flash vs bootflash), installation methods (request platform, install add, archive, and bootvar), and boot cadences.

### Field Usage

1000+ switch deployment.  Switches would be taken to the field new-in-box and configured by ZTP.  Inventory for project contained a mix of 5 different Cisco Catalyst models, each having unique port names (e.g. TeX/0/X, TwX/0/X, GiX/0/X, Gi0/X, etc.), file system names, and upgrade methodologies.  Actual serial numbers, stack/standalone arrangement, hostname, and IP would be unknown until time of deployment.  Additional non-ZTP automation was used to dynamically aquire data from field techs and update related ZTP Keystores and ID Arrays (not documented here).  

### Methodology

The script suite presented contains 4 basic sections: discovery, upgrade, finalize, and cleanup.
- Discovery
  - Acquires
    - Current OS Version - ZTP must pass new version to config in Jinja merge for comparison and upgrade decision.
    - HW model of the switch (or stack master) to determine upgrade method
    - File system name (flash or bootflash) for variations between chassis and fixed config switches
    - Module count to set necessary pauses in script.  (Single supervisor chassis automatically 1.)
  - Start upgrade if needed, otherwise start finalize
- Upgrade determines install method, then executes install
  - Method 1: `request platform software package upgrade...`
  - Method 2: `install add file...`
  - Method 3: `archive download-sw...`
    - Integrated removal of old OS
  - Method 4: Change boot statement in configuration
    - Pre-remove old OS before installing new
- Finalize
  - Remove legacy OS if installed via `request` or `install` commands
  - Add supplementary configuration (items which may be initially undesireable in main config, like AAA)
- Cleanup
  - Presented as a cron job that runs at midnight, but could be triggered another way
    - In this case, it allowed for other cron-based scripts to be cleaned off the switch a few hours after deployment.

### Tested Platforms and Versions

- ZTP version 1.4.1 (examples use new global keystore feature)
- Cisco Catalyst 9300 (24U / 24UX / 48U / 48UXM) in stacked and standalone configurations
  - Versions: 16.6.6, 16.9.3, 16.9.3s, 16.11.1, 16.12.1s
- Cisco Catalyst 94xx in single- and dual-supervisor configurations
  - Version: 16.9.3, 16.12.1s
- Cisco Catalyst 3560CX (8PC / 8PD / 12PC)
  - Versions: 15.2(6)E1, 15.2(7)E, 15.2(7)E0s

### Notes

- Based on testing it is expected that scripts will work on Catalyst 3850, IE-3200, IE-3400, and IE-4010
- Comments in the form `action ### comment <note>` added throughout suite to help provide clarity
- All EEM applets configured with `event none` to allow manual execution during testing / troubleshooting
  - Where needed compound triggers are used to allow `event none` to be present
- Simplified action tags were adopted to reduce line length
  - All tags end in 0 to allow insertion of additional commands (typically in troubleshooting)
- While all efforts have been made to reduce time from initial boot to ready, testing shows time is consistently 18-25 minutes for Catalyst 9K and 25-35 minutes for Catalyst 3560cx
  - Variation typically due to slow speed writing to flash, particularly on the 3560
  - Both jumbo and standard frame configurations were tested
  - Apache was installed on ZTP server to provide HTTP download

### Changes (2021-04-17)
- Order of operations change in system_check to fix stack detection issues.
- Migrated embedded Jinja2 substitutions to event manager environment variables (global). This improves readability and simplifies manual configuration when ZTP variables are not available.
- Added Catalyst 9200 to system_upgrade (uses `install` method)
- Changed example ZTP configuration to use "c9k" and "c9klite".  `c9k_image` covers all Catalyst 9K except ones that use the "lite" image (e.g. Catalyst 9200).

### Implementation

The sample leverages ZTP keystores to provide variables that are consumed in the configuration merge.
- OS File Name
- OS Version
- ZTP server IP (optional) - allow baseline portability between environments (prod / test)
- Environment (Optional) - allow dynamic add/remove of command groups based on prod / test concept

#### ZTP Configuration

This is a minimal configuration which shows variables provided by ZTP and consumed by Jinja 2 templating.  Actual usage could be altered to used External Keystores or other features.

```
ztp set keystore GLOBAL ztp_env test
ztp set keystore GLOBAL ztp_ip_addr 10.254.64.20
ztp set keystore GLOBAL c9k_ver 16.9.3s
ztp set keystore GLOBAL c9k_image cat9k_iosxe.16.09.03s.SPA.bin
ztp set keystore GLOBAL c9klite_image cat9k_iosxe.16.09.03s.SPA.bin
ztp set keystore GLOBAL c3560cx_ver 15.2(7)e0s
ztp set keystore GLOBAL c3560cx_image c3560cx-universalk9-tar.152-7.E0s.tar
ztp set global-keystore GLOBAL
#
ztp set keystore myswitch1 model1 c9300-48uxm
#
ztp set keystore myswitch2 model1 ws-c3560cx-12pc-s
#
ztp set association myswitch1 template SWITCH_BASELINE
ztp set association myswitch2 template SWITCH_BASELINE
```

#### Baseline Jinja Components

Place these commands anywhere above the EEM scripts.
- Uses Jinja 2 if-else-endif logic
  - `model1[:5]` takes first 5 characters from string passed from ZTP
- `GLOBAL.c9k_ver` or `GLOBAL.c3560cx_ver` --> `image.ver`
- `GLOBAL.c9k_image` or `GLOBAL.c9klite_image` or `GLOBAL.c3560cx_image` --> `image.bin`
- `image.ver` and `image.bin` are standard variables used through EEM scripts

```
!{% if model1[:5] == "c9200" %}
! {%set image={"bin":GLOBAL.c9klite_image,"ver":GLOBAL.c9k_ver}%}
!{% elif model1[:2] == "c9" %}
! {%set image={"bin":GLOBAL.c9k_image,"ver":GLOBAL.c9k_ver}%}
!{% else %}
!---- {%set image={"bin":GLOBAL.c3560cx_image,"ver":GLOBAL.c3560cx_ver}%}
!{% endif %}
```

### EEM Scripts

#### Initial Global Commands

```
event manager environment q "
event manager environment ver {{image.ver}}
event manager environment lver {{image.ver.lower()}}
event manager environment image {{image.bin}}
event manager environment ztp_ip {{GLOBAL.ztp_ip_addr}}
event manager history size events 50
```

#### Discovery

```
event manager applet system_check authorization bypass
 event tag 1 syslog occurs 1 pattern "Configured from tftp://$ztp_ip" maxrun 300
 event tag 2 none
 trigger
  correlate event 1 or event 2
 action 0010 wait 30
 action 0020 cli command "enable"
 action 0030 syslog priority informational msg "## Configuration received via TFTP."
 action 0040 comment Init variables
 action 0050 set upgrade_required "false"
 action 0060 set module_ctr 0
 action 0070 set sup_count 0
 action 0080 set loop_ctr 0
 action 0090 syslog priority informational msg "## Gathering information."
 action 0100 comment ##### Get Module Count #####
 action 0110 comment Get module for alt script timings. Single sup chassis gets count of 1.
 action 0120 comment Stacks & dual-sup modular chassis log RF-5-RF_TERMINAL_STATE when ready.
 action 0130 comment Standalone & single sup chassis are ready at SYS-5-RESTART.
 action 0140 cli command "show module | include ^\ *[0-9]+\ "
 action 0150 comment Look for ^ from command failure (non-stackable switches)
 action 0160 string match "*^*" "$_cli_result"
 action 0170 if $_string_result eq "1"
 action 0180  comment Non-stackable, standalone chassis found. Statically set module count to 1.
 action 0190  syslog priority informational msg "## Pausing 30s for post-boot processes."
 action 0200  wait 30
 action 0210  set module_ctr 1
 action 0220 else
 action 0230  comment Stack, stackable, or modular chassis found
 action 0240  set modules $_cli_result
 action 0250  foreach line $modules "\n"
 action 0260   string match nocase "*supervisor*" "$line"
 action 0270   if $_string_result eq "1"
 action 0280    increment sup_count 1
 action 0290   end
 action 0300   comment Check current line for MAC address (ignore if not present (e.g. switch prompt))
 action 0310   regexp "[0-9a-fA-F]+\.[0-9a-fA-F]+\.[0-9a-fA-F]+\ " $line
 action 0320   if $_regexp_result eq "1"
 action 0330    increment module_ctr 1
 action 0340   end
 action 0350  end
 action 0360  if $sup_count eq 1
 action 0370   comment Single sup chassis found. Statically set module count to 1.
 action 0380   set module_ctr 1
 action 0390  end
 action 0400  syslog priority informational msg "## Modules in switch: \n$modules"
 action 0410  comment Pause script as needed to allow SSO to complete
 action 0420  if $module_ctr gt "1"
 action 0430   syslog priority informational msg "## Pausing up to 210s for SSO."
 action 0440   while $loop_ctr lt 42
 action 0450    cli command "show logging | in RF-5-RF_TERMINAL_STATE"
 action 0460    regexp "RF-5-RF_TERMINAL_STATE" $_cli_result
 action 0470    if $_regexp_result eq "1"
 action 0480     break
 action 0490    else
 action 0500     increment loop_ctr 1
 action 0510     wait 5
 action 0520    end
 action 0530   end
 action 0540  end
 action 0550 end
 action 0560 comment Store module count for future applets
 action 0570 cli command "configure terminal"
 action 0580 cli command "event manager environment module_count $module_ctr"
 action 0590 cli command "end"
 action 0600 syslog priority informational msg "## Module Count: $module_count"
 action 0610 comment ##### Disable Autorun of Current Applet #####
 action 0620 cli command "configure terminal"
 action 0630 cli command "event manager applet system_check authorization bypass"
 action 0640 cli command " event tag 1 none maxrun 960"
 action 0650 cli command "end"
 action 0660 comment ##### Get Model #####
 action 0670 comment Get system model from show version (for stacks, gets master)
 action 0680 cli command "show version | in \)\ processor"
 action 0690 comment Regex matches cisco + model name
 action 0700 regexp "[cC]isco\ [a-zA-Z0-9\-]+" "$_cli_result" regexp_match
 action 0710 comment Remove cisco from string to isolate model, then put in all lower case
 action 0720 string replace $regexp_match 0 5 ""
 action 0730 string tolower "$_string_result"
 action 0740 set result "$_string_result"
 action 0750 comment Store model name for future applets
 action 0760 cli command "configure terminal"
 action 0770 cli command "event manager environment system_model $result"
 action 0780 cli command "end"
 action 0790 syslog priority informational msg "## System Model: $system_model"
 action 0800 comment ##### Get Version #####
 action 0810 comment Get system version from SNMP
 action 0820 info type snmp oid 1.3.6.1.2.1.1.1.0 get-type exact
 action 0830 comment Regex matches version + version name
 action 0840 regexp "[vV]ersion\ [a-zA-Z0-9\.\(\)]+" "$_info_snmp_value" regexp_match
 action 0850 comment Remove word version from string to isolate value, then put in lower case
 action 0860 string replace $regexp_match 0 7 ""
 action 0870 string tolower "$_string_result"
 action 0880 set system_version "$_string_result"
 action 0890 if $system_version ne "$lver"
 action 0900  set upgrade_required "true"
 action 0910 end
 action 0920 syslog priority informational msg "## System Version: $system_version"
 action 0930 syslog priority informational msg "## ZTP Version: $ver"
 action 0940 comment ##### Get File System #####
 action 0950 cli command "show file systems | in \*"
 action 0960 regexp "boot" $_cli_result
 action 0970 cli command "configure terminal"
 action 0980 comment Set fs env var based on presence or absence of word boot
 action 0990 if $_regexp_result eq 1
 action 1000  cli command "event manager environment fs bootflash"
 action 1010 else
 action 1020  cli command "event manager environment fs flash"
 action 1030 end
 action 1040 cli command "end"
 action 1050 syslog priority informational msg "## File System: $fs"
 action 1060 comment ##### Prepare for Next Applet #####
 action 1070 if $upgrade_required eq "false"
 action 1080  cli command "configure terminal"
 action 1090  cli command "event manager environment os_upgraded no"
 action 1100  cli command "end"
 action 1110  syslog priority informational msg "## Job Complete. Starting Finalize applet."
 action 1120  cli command "event manager run system_finalize"
 action 1130 else
 action 1140  syslog priority informational msg "## Switches require an upgrade to version $ver."
 action 1150  cli command "configure terminal"
 action 1160  cli command "event manager environment os_upgraded yes"
 action 1170  cli command "event manager applet system_finalize authorization bypass"
 action 1180  if $module_ctr gt 1
 action 1190   syslog priority informational msg "## Configuring multi-module trigger for Finalize applet"
 action 1200   cli command " event tag 1 syslog occurs 1 pattern $q%RF-5-RF_TERMINAL_STATE$q maxrun 630"
 action 1210  else
 action 1220   syslog priority informational msg "## Configuring single-module trigger for Finalize applet"
 action 1230   cli command " event tag 1 syslog occurs 1 pattern $q%SYS-5-RESTART$q maxrun 630"
 action 1240  end
 action 1250  cli command "end"
 action 1260  cli command "write mem" pattern "confirm|#"
 action 1270  cli command ""
 action 1280  syslog priority informational msg "## Job Complete. Starting upgrade."
 action 1290  cli command "event manager run system_upgrade"
 action 1300 end
```

#### Upgrade

```
event manager applet system_upgrade authorization bypass
 event none maxrun 1800
 action 010 set download_first 0
 action 020 set short_model 0
 action 030 cli command "enable"
 action 040 regexp "(c9200|c9300|c9404r|c9407r|c9410r|c9500|c3850|ie-3200|ie-3400)" $system_model short_model
 action 050 comment #### Get Install & Cleanup Method #####
 action 060 cli command "configure terminal"
 action 070 regexp "(c9300|c3850)" $short_model
 action 080 if $_regexp_result eq "1"
 action 090  comment IOS-XE Fixed configuration switch upgrade method
 action 100  cli command "event manager environment install_method request"
 action 110  set download_first 1
 action 120 end
 action 130 regexp "(c9200|c9404r|c9407r|c9410r|c9500)" $short_model
 action 140 if $_regexp_result eq "1"
 action 150  comment IOS-XE Chassis / vStackwise install method
 action 160  cli command "event manager environment install_method install"
 action 170  set download_first 1
 action 180 end
 action 190 regexp "(ie-3200|ie-3400)" $short_model
 action 200 if $_regexp_result eq "1"
 action 210  comment IOS Direct replacement of boot variable
 action 220  cli command "event manager environment install_method bootvar"
 action 230  set download_first 1
 action 240 end
 action 250 comment Check if install_method env var exists
 action 260 handle-error type ignore
 action 270 set test $install_method
 action 280 if $_error eq FH_EMEMORY
 action 290  comment Var absent.  All other switches use archive method
 action 300  handle-error type exit
 action 310  comment IOS Tarball install method.  Auto removes old image from switch
 action 320  cli command "event manager environment install_method archive"
 action 330 end
 action 340 cli command "end"
 action 350 handle-error type exit
 action 360 syslog priority informational msg "## Installation Method: $install_method"
 action 370 comment ##### Load OS #####
 action 380 if $download_first eq "1"
 action 390  syslog priority informational msg "## Downloading image..."
 action 400  comment HTTP may offer better download performance for large images.
 action 410  comment Server address and image from jinja merge.
 action 420  comment Delete previous download, if present, to prevent script hang
 action 430  cli command "delete /force $fs:$image"
 action 440  cli command "copy http://$ztp_ip/$image $fs:" pattern "Destination|#"
 action 450  cli command ""
 action 460 end
 action 470 comment Save before install to prevent unwanted save prompts
 action 480 cli command "write mem" pattern "confirm|#"
 action 490 cli command ""
 action 500 if $install_method eq "request"
 action 510  syslog priority informational msg "## Upgrading..."
 action 520  cli command "request platform software package install switch all file $fs:$image force new auto-copy verbose" pattern "proceed|#"
 action 530  cli command "y"
 action 540  reload
 action 550 elseif $install_method eq "install"
 action 560  syslog priority informational msg "## Upgrading..."
 action 570  comment WARNING - Do not use ISSU method.  Allow entire chassis to reboot.
 action 580  cli command "install add file $fs:$image activate commit" pattern "proceed|#"
 action 590  cli command "y"
 action 600 elseif $install_method eq "bootvar"
 action 610  syslog priority informational msg "## Upgrading..."
 action 620  comment Get booted image from SNMP, then delete to clear space
 action 630  info type snmp oid 1.3.6.1.2.1.16.19.6.0 get-type exact
 action 640  cli command "delete /force $_info_snmp_value"
 action 650  cli command "configure terminal"
 action 660  cli command "no boot manual"
 action 670  cli command "no boot system"
 action 680  cli command "boot system $fs:$image"
 action 690  cli command "end"
 action 700  cli command "write mem" pattern "confirm|#"
 action 710  cli command ""
 action 720  reload
 action 730 elseif $install_method eq "archive"
 action 740  syslog priority informational msg "## Downloading and Upgrading..."
 action 750  cli command "archive download-sw /imageonly /overwrite /allow-feature-upgrade http://$ztp_ip/$image"
 action 760  reload
 action 770 end
```

#### Finalize

```
event manager applet system_finalize authorization bypass
 event tag 1 none maxrun 120
 event tag 2 none
 trigger
  correlate event 1 or event 2
 action 010 syslog priority informational msg "## Starting Finalize..."
 action 020 cli command "enable"
 action 030 syslog priority informational msg "## Applying supplemental configuration."
 action 040 cli command "configure terminal"
{% if GLOBAL.ztp_env == "prod" %}
 action 050 cli command "errdisable recovery interval 900"
 action 060 cli command "no logging console"
 action 070 cli command "aaa authentication login default group TACACS-SERVERS local"
 action 080 cli command "aaa authorization exec default group TACACS-SERVERS local if-authenticated"
 action 090 cli command "aaa authorization commands 15 default group TACACS-SERVERS local if-authenticated"
 action 100 cli command "aaa accounting exec default start-stop group TACACS-SERVERS"
 action 110 cli command "aaa accounting commands 15 default start-stop group TACACS-SERVERS"
 action 120 cli command "line vty 0 15"
 action 130 cli command " access-class 30 in"
{% endif %}
 action 140 cli command "no snmp-server community secretcommunity RO"
 action 150 cli command "interface Vlan1"
 action 160 cli command " description UNUSED. SHUTDOWN."
 action 170 cli command " no ip address"
 action 180 cli command " shutdown"
 action 190 cli command "end"
 action 200 cli command "write mem" pattern "confirm|#"
 action 210 cli command ""
 action 220 syslog priority informational msg "## Job complete."
```

#### Cleanup

```
event manager applet system_clean authorization bypass
 event tag 1 timer cron name system_clean_cron cron-entry "0 0 * * *" maxrun 630
 event tag 2 none
 trigger
  correlate event 1 or event 2
 action 010 syslog priority informational msg "## Starting Cleanup applet."
 action 020 cli command "enable"
 action 030 if $os_upgraded eq "yes"
 action 040  if $module_count gt 1
 action 050   comment Stack or dual-sup. Applet triggered at Bulk Sync. Start immediately.
 action 060   syslog priority informational msg "## Stack rebooted to new image. SSO Terminal State reached."
 action 070  else
 action 080   comment Standalone switch. Applet triggered at boot.  Pause for boot processes to complete.
 action 090   syslog priority informational msg "## Switch rebooted to new image. Waiting 60s."
 action 100   wait 60
 action 110  end
 action 120  syslog priority informational msg "## Removing unused packages..."
 action 130  if $install_method eq "request"
 action 140   cli command "request platform software package clean switch all" pattern "proceed|#"
 action 150   cli command "y"
 action 160  elseif $install_method eq "install"
 action 170   cli command "install remove inactive" pattern "\[y\/n\]|#"
 action 180   cli command "y"
 action 190  end
 action 200  syslog priority informational msg "## Unused packages have been removed."
 action 210 end
 action 220 syslog priority informational msg "## Removing EEM applets and environment variables."
 action 230 cli command "configure terminal"
 action 240 cli command "no event manager environment q"
 action 250 cli command "event manager environment ver"
 action 260 cli command "event manager environment lver"
 action 270 cli command "event manager environment image"
 action 280 cli command "event manager environment ztp_ip"
 action 290 cli command "no event manager environment system_model"
 action 300 cli command "no event manager environment module_count"
 action 310 cli command "no event manager environment fs"
 action 320 cli command "no event manager environment install_method"
 action 330 cli command "no event manager environment os_upgraded"
 action 340 cli command "no event manager applet system_check"
 action 350 cli command "no event manager applet system_upgrade"
 action 360 cli command "no event manager applet system_finalize"
 action 370 cli command "no event manager applet system_clean"
 action 380 cli command "end"
 action 390 cli command "write mem" pattern "confirm|#"
 action 400 cli command ""
 action 410 cli command "exit"
 action 420 syslog priority informational msg "## Cleanup applet complete."
 ```

## Use Case: Automatic Stack Renumbering - Alternate Method

###### Author: [Paul S. Chapman](https://github.com/pschapman), Rev: 1, Date: 2021.0417, FreeZTP v1.4.1

### Purpose

This is an alternate to the Stack Renumbering presented by Derek Schnosh.  The goal was to provide the same result with minimal requirements from the ZTP Jinja2 merge and a finite EEM script length.

### Methodology

ZTP automatically passes an ordered list of serials to Jinja2 as `idarray`.  Leveraging this, we include or exclude the EEM from the merge based on whether ZTP passes more than 1 serial.

```
{% if idarray|length > 1 %}
...
{% endif %}
```

To build our "stack order" list we join the `idarray` into a string using space as the delimiter. The ID array is an ordered list (e.g. `idarray_1` is always the first position in the `idarray` list).  We then set it as an EEM environment variable for use by the script.

```
{% set stack_order=idarray|join(' ') %}
event manager environment stack_order {{ stack_order }}
```

The proposed EEM pulls the list of live switches using the `show module` command and builds an ordered list of serials (e.g. module 1 is item 1 in the list).  Since both serial number lists are ordered, then we can assume that a mismatch for a given position in the order means that switch needs to be renumbered.  The script implements loop counters as `designated_pos` and `current_pos` to keep track of the positions being compared.

### Implementation
Below is the complete script. It is bounded by `if` / `endif` to dynamically exclude the EEM from standalone switches.

The primary trigger `event tag 1 none` is a place holder. Depending on your needs, substitute the event with one appropriate for your deployment.

```
!{% if idarray|length > 1 %}{% set stack_order=idarray|join(' ') %}
event manager environment stack_order {{ stack_order }}
!
event manager applet stack_reorder authorization bypass
 event tag 1 none
 event tag 2 none
  trigger
  correlate event 1 or event 2
 action 010 syslog priority informational msg "## Checking stack order against known order from ZTP."
 action 020 set designated_pos "0"
 action 030 set current_pos "0"
 action 040 set renum "0"
 action 050 cli command "enable"
 action 060 comment Get list of modules
 action 070 cli command "show module | include ^\ *[0-9]+\ "
 action 080 set modules $_cli_result
 action 090 foreach line $modules "\n"
 action 100  comment Extract 4th field (serial number) from line as sub1
 action 110  regexp "^\ [1-8]\ +[0-9]+\ +[A-Z0-9-]+\ +([A-Z0-9]+)" $line match sub1
 action 120  if $_regexp_result eq "1"
 action 130   append member " $sub1"
 action 140  end
 action 150 end
 action 160 comment Remove leading space from list
 action 170 string trim $member
 action 180 comment Loop through ordered serial list from ZTP
 action 190 foreach designated_sn $stack_order
 action 200  increment designated_pos 1
 action 210  comment Find matching serial for online switch
 action 220  foreach current_sn $_string_result
 action 230   increment current_pos 1
 action 240   if $designated_sn eq $current_sn
 action 250    comment When serials match, counters should match. Renumber on mismatch.
 action 260    if $designated_pos ne $current_pos
 action 270     cli command "switch $current_pos renumber $designated_pos" pattern "continue|#"
 action 280     cli command "y"
 action 290     set renum "1"
 action 300     syslog priority informational msg "## Renumbering switch $current_pos to $designated_pos."
 action 310    end
 action 320   end
 action 330  end
 action 340  set current_pos "0"
 action 350 end
 action 360 if $renum eq "1"
 action 370  cli command "copy running-config startup-config"
 action 380  syslog priority informational msg "## Switch order reset. Rebooting in 10s."
 action 390  wait 10
 action 400  reload
 action 410 end
!{% endif %}

```

[logo]: http://www.packetsar.com/wp-content/uploads/FreeZTP-100.png
[BugID]: https://i.imgur.com/s2avfF0.png
