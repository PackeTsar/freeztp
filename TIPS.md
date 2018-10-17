[< Main README](/README.md)


# FreeZTP ![FreeZTP][logo]

Some usage tips and tricks from real world FreeZTP deployments.


-----------------------------------------
## TABLE OF CONTENTS
1. [Use-case: Provisioning Without Vlan1](#use-case-provisioning-without-vlan1)
2. [Use-case: Upgrade IOS-XE 3.7.x to 16.3.6](#use-case-upgrade-ios-xe-37x-to-1636)
3. [Use-case: Automated IOS-XE Stack Renumbering](#use-case-automated-ios-xe-stack-renumbering)


-----------------------------------------
## Use-case: Provisioning Without Vlan1

###### Author: [derek-shnosh](https://github.com/derek-shnosh), Rev: 1, Date: 2018.1008, FreeZTP dev1.1.0m

The use of Vlan1 is not required for provisioning. The client switch running the smart-install process will still bring up all interfaces as *dynamic desirable* (or other default behavior) on Vlan1; however, disabling CDP and enabling BPDU filter will circumvent any undesirable spanning-tree behavior that would otherwise interfere with the link coming up between the master and client switches.

**NOTE: A client switch should only be connected to the *master* provisioning switch during provisioning**; i.e. a client switch should never be connected to the provisioning environment and production infrastructure during the provisioning process, spanning-tree loops can occur.

### Interface Configuration (Master Switch)

* Configure the *master* provisioning switch interfaces as follows; Replace `<n>` with interfaces that client switches will connect to.

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

* *Interface config assumes the following details for the provisioning environment, adjust accordingly.*

    | VLAN  | Subnet          | IP Allocation                                                                      |
    | :---: | :-------------: | :--------------------------------------------------------------------------------- |
    | 3967  | 172.31.255.0/24 | **.1** - Gateway (optional)<br>**.2** - FreeZTP server<br>**.5 - .254** DHCP range |


-----------------------------------------
## Use-case: Upgrade IOS-XE 3.7.x to 16.3.6

###### Author: [derek-shnosh](https://github.com/derek-shnosh), Rev: 1, Date: 2018.1008, FreeZTP dev1.1.0m

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
2. Switch requests config, FreeZTP gives a (merged) config, containing the [required config (upgrade)](#required-config-upgrade).
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

#### Required Config (Upgrade)

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
      | `access_vlan` | Vlan to configure on the provisioning interface (Gi1/0/48) after upgrade/reload is complete.                       |
      | `prov_int`    | Interface to be used for provisioning; e.g. Te1/0/48<br>> *3850-12X48U-S interfaces 37-48 are TenGigabitEthernet.* |

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

-----------------------------------------
## Use-case: Automated IOS-XE Stack Renumbering

###### Author: [derek-shnosh](https://github.com/derek-shnosh), Rev: 3, Date: 2018.1017, FreeZTP dev1.1.0m

### Preamble

When the [required config (stack)](#required-config-stack) is added to a Jinja2 template for FreeZTP it will automatically build out an EEM applet that will set switch priorities and renumber all switches in the stack according to how they were allocated in the FreeZTP keystore.

All switches in the stack can be powered on simultaneously. After the election processes are complete, the stack will continue booting and then perform the smart-install procedure where it will receive this applet as part of the templated configuration.

The applet will need to be assigned a syslog trigger to automatically execute after all members in the stack are online. To find an appropriate syslog message, power up a couple switches in a stack and observe their console logs during the boot process. The following `syslog` trigger worked on IOS-XE 3.7.4E.

```cisco
event manager applet sw_stack
 event syslog occurs 1 pattern "%HA_CONFIG_SYNC-6-BULK_CFGSYNC_SUCCEED: Bulk Sync succeeded" maxrun 60
```

In this use-case, FreeZTP's `idarray` variables are being used to define stack member serial numbers (see the CSV section below). When the template is merged with the keystore, an action sequence is generated for each serial number (`idarray_#`) associated with the hostname (`keystore_id`). Switch serial numbers should be assigned to `idarray_#`'s as they're meant to be numbered in the stack.

#### CSV

Variables defined in the keystore (FreeZTP);

* `keystore_id` = hostname
* `association` = template
* `idarray_<n>` = serial number(s)

The switch serial numbers should be added to the `idarray_#` fields in accordance with how they are to be positioned in the stack.

```csv
keystore_id,association,idarray_1,idarray_2,idarray_3,idarray_4,idarray_5,idarray_6,idarray_7,idarray_8,idarray_9
ASW-TR01-01,TEST,FOC11111111,FOC22222222,,,,,,,
```

In this example, there are two serial numbers allocated to the stack **ASW-TR01-01**;
* **FOC11111111** (`idarray_1`) should be switch 1 in the stack, with a priority of 15.
* **FOC22222222** (`idarray_2`) should be switch 2 in the stack, with a priority of 14.

#### Explanation

* J2 template gets a count of how many serial numbers are found in `idarray`.
* J2 template generates an EEM applet containing a group of action sequences for each switch found in `idarray`.
* The onfiguration is pushed to the switch during the ZTP process.
* EEM applet (when ran, needs trigger) will do the following;
   * Execute the command `show module | inc ^.[1-9]` (*example output for two switches\*\**);
      ```cisco
       1       62     WS-C3850-12X48U-S     FOC22222222  abcd.ef01.1111  V02           16.3.6        
       2       62     WS-C3850-12X48U-S     FOC11111111  abcd.ef02.2222  V02           16.3.6        
      ASW-TR01-01#
      ```
   * For each switch, search the entire output for its serial number.
      * If not found, a syslog message will be generated, no changes will take place, and the applet will move onto the next switch.
      * If found, the applet searches the output line-by-line until it finds the serial number.
       * If the line number where the serial number was found matches the allocated switch number, as syslog message will be generated and only the priority will be set.
       * If the line number where the serial number was found does not match the allocated switch number (`idarray_#`), a syslog message will be generated, the priority will be set and the switch will be renumbered appropriately.

*\*\* This output is what EEM stores for parsing. Note the last line is the switch hostname, this line is ignored when searching for the switch serial number(s). All other line numbers correlate with the stack's current switch allocation numbers.*

*See the Validation section to view the syslog message output for this example.*

### Merge-test
Merged configuration that is pushed to the switch from FreeZTP (J2 templating functions do not print). Any line starting with a `!` will be ignored by the switch.

```cisco
!-- Variables (keys) parsed from CSV keystore.
!---- IDARRAY_1 (switch 1 serial number): FOC11111111
!---- IDARRAY_2 (switch 2 serial number): FOC22222222
!---- IDARRAY_3 (switch 3 serial number): 
!---- IDARRAY_4 (switch 4 serial number): 
!---- IDARRAY_5 (switch 5 serial number): 
!---- IDARRAY_6 (switch 6 serial number): 
!---- IDARRAY_7 (switch 7 serial number): 
!---- IDARRAY_8 (switch 8 serial number): 
!---- IDARRAY_9 (switch 9 serial number): 
!---- IDARRAY (all serials): ['FOC11111111', 'FOC22222222']
!
!-- Count number of serials parsed from CSV: 
!---- SW_COUNT (count of serials found in IDARRAY): 2
!
!-- EEM applet to renumber switches accordingly.
event manager applet sw_stack
  event none maxrun 60
  action 00.00 cli command "enable"
  action 00.01 cli command "show mod | i ^.[1-9]"
  action 00.02 set stack "$_cli_result"
  action 00.03 set error_list ""
  action 00.04 set change_list ""
  action 00.05 set upgrade_list ""
  !
  !
  action 01.00 set sw_num "1"
  action 01.01 set pri "16"
  action 01.02 decrement pri 1
  action 01.03 regexp "FOC11111111" "$stack"
  action 01.04 if $_regexp_result ne "1"
  action 01.05  syslog msg "\n     ## FOC11111111 (Sw-1 serial) not found in the stack, check 'show mod' output."
  action 01.06  append error_list "\n     ## FOC11111111 is allocated (idarray_1) but was not found in the stack."
  action 01.07 else
  action 01.08  set i "0"
  action 01.09  foreach line "$stack" "\n"
  action 01.10   increment i
  action 01.11   if $i le "2"
  action 01.12    string trim "$line"
  action 01.13    set line "$_string_result"
  action 01.14    regexp "FOC11111111" "$line"
  action 01.15    if $_regexp_result eq "1"
  action 01.16     regexp "([0-9]+.)+$" "$line" curr_ver
  action 01.17     if $curr_ver ne ""
  action 01.18      append upgrade_list "1"
  action 01.19     end
  action 01.20     if $i eq $sw_num 
  action 01.21      cli command "switch $i priority $pri" pattern "continue|#"
  action 01.22      cli command "y"
  action 01.23      append change_list "\n     ## FOC11111111 (Priority: $pri // Numbered:       $sw_num // Version: $curr_ver )"
  action 01.24     else 
  action 01.25      cli command "switch $i priority $pri" pattern "continue|#"
  action 01.26      cli command "y"
  action 01.27      cli command "switch $i renumber $sw_num" pattern "continue|#"
  action 01.28      cli command "y"
  action 01.29      append change_list "\n     ## FOC11111111 (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver )"
  action 01.30     end
  action 01.31    end
  action 01.32   end
  action 01.33  end
  action 01.34 end
  !
  !
  action 02.00 set sw_num "2"
  action 02.01 set pri "16"
  action 02.02 decrement pri 2
  action 02.03 regexp "FOC22222222" "$stack"
  action 02.04 if $_regexp_result ne "1"
  action 02.05  syslog msg "\n     ## FOC22222222 (Sw-2 serial) not found in the stack, check 'show mod' output."
  action 02.06  append error_list "\n     ## FOC22222222 is allocated (idarray_2) but was not found in the stack."
  action 02.07 else
  action 02.08  set i "0"
  action 02.09  foreach line "$stack" "\n"
  action 02.10   increment i
  action 02.11   if $i le "2"
  action 02.12    string trim "$line"
  action 02.13    set line "$_string_result"
  action 02.14    regexp "FOC22222222" "$line"
  action 02.15    if $_regexp_result eq "1"
  action 02.16     regexp "([0-9]+.)+$" "$line" curr_ver
  action 02.17     if $curr_ver ne ""
  action 02.18      append upgrade_list "2"
  action 02.19     end
  action 02.20     if $i eq $sw_num 
  action 02.21      cli command "switch $i priority $pri" pattern "continue|#"
  action 02.22      cli command "y"
  action 02.23      append change_list "\n     ## FOC22222222 (Priority: $pri // Numbered:       $sw_num // Version: $curr_ver )"
  action 02.24     else 
  action 02.25      cli command "switch $i priority $pri" pattern "continue|#"
  action 02.26      cli command "y"
  action 02.27      cli command "switch $i renumber $sw_num" pattern "continue|#"
  action 02.28      cli command "y"
  action 02.29      append change_list "\n     ## FOC22222222 (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver )"
  action 02.30     end
  action 02.31    end
  action 02.32   end
  action 02.33  end
  action 02.34 end
  !
  action 09.90 wait 3
  action 09.91 if $error_list ne ""
  action 09.92  syslog msg "\n     ## The following errors occurred; $error_list"
  action 09.93 end
  action 09.94 syslog msg "\n     ## Switches below have been assigned a priority and renumbered* as needed; $change_list"
  !
```

### Validation

* This template/applet has been confirmed functional on stacked C3850-12X48U-S switches running the following IOS-XE versions;
  * IOS-XE 3.7.4E
  * IOS-XE 16.3.6

### Required Config (Stack)

* Template Config Snippet.

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
    !-- Count number of serials parsed from CSV: {% set sw_count = idarray|count %}
    !---- SW_COUNT (count of serials found in IDARRAY): {{sw_count}}
    !
    !-- EEM applet to renumber switches accordingly.
    event manager applet sw_stack
    event none maxrun 60
      action 00.00 cli command "enable"
      action 00.01 cli command "show mod | i ^.[1-9]"
      action 00.02 set stack "$_cli_result"
      action 00.03 set error_list ""
      action 00.04 set change_list ""
      action 00.05 set upgrade_list ""
      !{% for sw in idarray %}
      !{% set i = loop.index %}
      action 0{{i}}.00 set sw_num "{{i}}"
      action 0{{i}}.01 set pri "16"
      action 0{{i}}.02 decrement pri {{i}}
      action 0{{i}}.03 regexp "{{sw}}" "$stack"
      action 0{{i}}.04 if $_regexp_result ne "1"
      action 0{{i}}.05  syslog msg "\n     ## {{sw}} (Sw-{{i}} serial) not found in the stack, check 'show mod' output."
      action 0{{i}}.06  append error_list "\n     ## {{sw}} is allocated (idarray_{{i}}) but was not found in the stack."
      action 0{{i}}.07 else
      action 0{{i}}.08  set i "0"
      action 0{{i}}.09  foreach line "$stack" "\n"
      action 0{{i}}.10   increment i
      action 0{{i}}.11   if $i le "{{sw_count}}"
      action 0{{i}}.12    string trim "$line"
      action 0{{i}}.13    set line "$_string_result"
      action 0{{i}}.14    regexp "{{sw}}" "$line"
      action 0{{i}}.15    if $_regexp_result eq "1"
      action 0{{i}}.16     regexp "([0-9]+.)+$" "$line" curr_ver
      action 0{{i}}.17     if $curr_ver ne "{{target_ver}}"
      action 0{{i}}.18      append upgrade_list "{{i}}"
      action 0{{i}}.19     end
      action 0{{i}}.20     if $i eq $sw_num 
      action 0{{i}}.21      cli command "switch $i priority $pri" pattern "continue|#"
      action 0{{i}}.22      cli command "y"
      action 0{{i}}.23      append change_list "\n     ## {{sw}} (Priority: $pri // Numbered:       $sw_num // Version: $curr_ver )"
      action 0{{i}}.24     else 
      action 0{{i}}.25      cli command "switch $i priority $pri" pattern "continue|#"
      action 0{{i}}.26      cli command "y"
      action 0{{i}}.27      cli command "switch $i renumber $sw_num" pattern "continue|#"
      action 0{{i}}.28      cli command "y"
      action 0{{i}}.29      append change_list "\n     ## {{sw}} (Priority: $pri // Renumbered: $i > $sw_num* // Version: $curr_ver )"
      action 0{{i}}.30     end
      action 0{{i}}.31    end
      action 0{{i}}.32   end
      action 0{{i}}.33  end
      action 0{{i}}.34 end
      !{% endfor %}
      action 09.90 wait 3
      action 09.91 if $error_list ne ""
      action 09.92  syslog msg "\n     ## The following errors occurred; $error_list"
      action 09.93 end
      action 09.94 syslog msg "\n     ## Switches below have been assigned a priority and renumbered* as needed; $change_list"
    ```












[logo]: http://www.packetsar.com/wp-content/uploads/FreeZTP-100.png
[BugID]: https://i.imgur.com/s2avfF0.png