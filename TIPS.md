[< Main README](/README.md)


# FreeZTP ![FreeZTP][logo]

Some usage tips and tricks from real world FreeZTP deployments.


-----------------------------------------
## TABLE OF CONTENTS
1. [Use-case: Provisioning Without Vlan1](#use-case-provisioning-without-vlan1)
2. [Use-case: Upgrade IOS-XE 3.7.x to 16.3.6](#use-case-upgrade-ios-xe-37x-to-1636)
3. [Use-case: IOS-XE Stack Numbering](#use-case-ios-xe-stack-numbering)


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
## Use-case: IOS-XE Stack Numbering

###### Author: [derek-shnosh](https://github.com/derek-shnosh), Rev: 1, Date: 2018.1012, FreeZTP dev1.1.0m

### Preamble

When the [required config (stack)](#required-config-stack) is added to a Jinja2 template for FreeZTP it will automatically build out an EEM applet that will set switch priorities and renumber all switches in the stack according to how they were allocated in the FreeZTP keystore.

In this use-case, FreeZTP's `idarray` variables are being used to define stack member serial numbers (see the CSV section below). When the template is merged with the keystore, an action sequence is generated for each serial number (`idarray_#`) associated with the hostname (`keystore_id`).

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

* The template gets a count of how many serial numbers are found in `idarray`.
* The template generates an EEM applet and a group of action sequences for each switch found in `idarray`.
* The configuration is pushed to the switch during the ZTP process.
* The EEM applet (*when ran\**) will do the following;
   * Execute the command `show module | inc ^.[1-9]` (*example output for two switches\*\**);
      ```cisco
      1       62     WS-C3850-12X48U-S     FOC22222222  abcd.ef01.1111  V02           16.3.6        
      2       62     WS-C3850-12X48U-S     FOC11111111  abcd.ef02.2222  V02           16.3.6        
      ASW-TR01-01#
      ```
   * For each switch, search the entire output for its serial number.
      * If found, the applet searches the output line-by-line until it finds the serial number.
         * If the line number does not match the allocated switch number (`idarray_#`), a syslog message will be generated, the priority will be set and the switch will be renumbered appropriately.
         * If the line number matches the allocated switch number, as syslog message will be generated and only the priority will be set.
      * If not found, a syslog message will be generated, no changes will take place, and the applet will move onto the next switch.

*See the Validation section to view the syslog message output for this example.*

*\* An event trigger can be defined to fully automate the process, or it can be left as is and triggered manually by typing `event manager run sw-stack` in an elevated command prompt.*

*\*\* This output is what EEM stores for parsing. Note the last line is the switch hostname, this line is ignored when searching for the switch serial number(s). All other line numbers correlate with the stack's current switch allocation numbers.*

### Merge-test
Merged configuration that is pushed to the switch from FreeZTP (J2 templating functions do not print).

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
event manager applet sw-stack
  event none
  action 00.00 cli command "enable"
  action 00.01 cli command "show mod | i ^.[1-9]"
  action 00.02 set stack "$_cli_result"
  !
  !
  action 01.00 set idarray_1 "FOC11111111"
  action 01.01 set sw "1"
  action 01.02 set pri "16"
  action 01.03 decrement pri 1
  action 01.04 set i "0"
  action 01.05 regexp "FOC11111111" "$stack"
  action 01.06 if $_regexp_result eq "1"
  action 01.07  foreach line "$stack" "\n"
  action 01.08   increment i
  action 01.09   if $i le "2"
  action 01.10    string trim "$line"
  action 01.11    set line "$_string_result"
  action 01.12    regexp "FOC11111111" "$line"
  action 01.13    if $_regexp_result eq "1"
  action 01.14     if $i ne $sw
  action 01.15      syslog msg "\n     ## $idarray_1 is currently switch number $i, it should be switch number $sw.\n     ## Setting priority to $pri and renumbering to $sw."
  action 01.16      cli command "switch $i priority $pri" pattern "continue|#"
  action 01.17      cli command ""
  action 01.18      cli command "switch $i renumber $sw" pattern "continue|#"
  action 01.19      cli command ""
  action 01.20     else
  action 01.21      syslog msg "\n     ## $idarray_1 is correctly numbered ($i).\n     ## Setting priority to $pri (renumbering not needed)."
  action 01.22      cli command "switch $i priority $pri" pattern "continue|#"
  action 01.23      cli command ""
  action 01.24     end
  action 01.25    end
  action 01.26   end
  action 01.27  end
  action 01.28 else
  action 01.29  syslog msg " ## FOC11111111 (sw-1 serial number) not found in the stack, check 'show mod' output."
  action 01.30 end
  !
  !
  action 02.00 set idarray_2 "FOC22222222"
  action 02.01 set sw "2"
  action 02.02 set pri "16"
  action 02.03 decrement pri 2
  action 02.04 set i "0"
  action 02.05 regexp "FOC22222222" "$stack"
  action 02.06 if $_regexp_result eq "1"
  action 02.07  foreach line "$stack" "\n"
  action 02.08   increment i
  action 02.09   if $i le "2"
  action 02.10    string trim "$line"
  action 02.11    set line "$_string_result"
  action 02.12    regexp "FOC22222222" "$line"
  action 02.13    if $_regexp_result eq "1"
  action 02.14     if $i ne $sw
  action 02.15      syslog msg "\n     ## $idarray_2 is currently switch number $i, it should be switch number $sw.\n     ## Setting priority to $pri and renumbering to $sw."
  action 02.16      cli command "switch $i priority $pri" pattern "continue|#"
  action 02.17      cli command ""
  action 02.18      cli command "switch $i renumber $sw" pattern "continue|#"
  action 02.19      cli command ""
  action 02.20     else
  action 02.21      syslog msg "\n     ## $idarray_2 is correctly numbered ($i).\n     ## Setting priority to $pri (renumbering not needed)."
  action 02.22      cli command "switch $i priority $pri" pattern "continue|#"
  action 02.23      cli command ""
  action 02.24     end
  action 02.25    end
  action 02.26   end
  action 02.27  end
  action 02.28 else
  action 02.29  syslog msg " ## FOC22222222 (sw-2 serial number) not found in the stack, check 'show mod' output."
  action 02.30 end
  !
```

### Resultant Config
Configuration as it appears once applied to the switch.

```cisco
event manager applet sw-stack
 event none
 action 00.00 cli command "enable"
 action 00.01 cli command "show mod | i ^.[1-9]"
 action 00.02 set stack "$_cli_result"
 action 01.00 set idarray_1 "FOC11111111"
 action 01.01 set sw "1"
 action 01.02 set pri "16"
 action 01.03 decrement pri 1
 action 01.04 set i "0"
 action 01.05 regexp "FOC11111111" "$stack"
 action 01.06 if $_regexp_result eq "1"
 action 01.07  foreach line "$stack" "\n"
 action 01.08   increment i
 action 01.09   if $i le "2"
 action 01.10    string trim "$line"
 action 01.11    set line "$_string_result"
 action 01.12    regexp "FOC11111111" "$line"
 action 01.13    if $_regexp_result eq "1"
 action 01.14     if $i ne "$sw"
 action 01.15      syslog msg "\n     ## $idarray_1 is currently switch number $i, it should be switch number $sw.\n     ## Setting priority to $pri and renumbering to $sw."
 action 01.16      cli command "switch $i priority $pri" pattern "continue|#"
 action 01.17      cli command ""
 action 01.18      cli command "switch $i renumber $sw" pattern "continue|#"
 action 01.19      cli command ""
 action 01.20     else
 action 01.21      syslog msg "\n     ## $idarray_1 is correctly numbered ($i).\n     ## Setting priority to $pri (renumbering not needed)."
 action 01.22      cli command "switch $i priority $pri" pattern "continue|#"
 action 01.23      cli command ""
 action 01.24     end
 action 01.25    end
 action 01.26   end
 action 01.27  end
 action 01.28 else
 action 01.29  syslog msg " ## FOC11111111 (sw-1 serial number) not found in the stack, check 'show mod' output."
 action 01.30 end
 action 02.00 set idarray_2 "FOC22222222"
 action 02.01 set sw "2"
 action 02.02 set pri "16"
 action 02.03 decrement pri 2
 action 02.04 set i "0"
 action 02.05 regexp "FOC22222222" "$stack"
 action 02.06 if $_regexp_result eq "1"
 action 02.07  foreach line "$stack" "\n"
 action 02.08   increment i
 action 02.09   if $i le "2"
 action 02.10    string trim "$line"
 action 02.11    set line "$_string_result"
 action 02.12    regexp "FOC22222222" "$line"
 action 02.13    if $_regexp_result eq "1"
 action 02.14     if $i ne "$sw"
 action 02.15      syslog msg "\n     ## $idarray_2 is currently switch number $i, it should be switch number $sw.\n     ## Setting priority to $pri and renumbering to $sw."
 action 02.16      cli command "switch $i priority $pri" pattern "continue|#"
 action 02.17      cli command ""
 action 02.18      cli command "switch $i renumber $sw" pattern "continue|#"
 action 02.19      cli command ""
 action 02.20     else
 action 02.21      syslog msg "\n     ## $idarray_2 is correctly numbered ($i).\n     ## Setting priority to $pri (renumbering not needed)."
 action 02.22      cli command "switch $i priority $pri" pattern "continue|#"
 action 02.23      cli command ""
 action 02.24     end
 action 02.25    end
 action 02.26   end
 action 02.27  end
 action 02.28 else
 action 02.29  syslog msg " ## FOC22222222 (sw-2 serial number) not found in the stack, check 'show mod' output."
 action 02.30 end
```

### Validation

* This template/applet has been confirmed functional on stacked C3850-12X48U-S switches running the following IOS-XE versions;
  * IOS-XE 3.7.4E
  * IOS-XE 16.3.6

* For testing, I changed the `renumber` and `priority` action sequences to `syslog msg` (instead of `cli command`) and ran the applet manually to test output...
  * ... when switches are not numbered correctly;
  ```cisco
  ASW-TR01-01#ev man run sw-stack
  ASW-TR01-01#
  *Oct 11 2018 17:02:22.999 PDT: %HA_EM-6-LOG: sw-stack: 
       ## FOC11111111 is currently switch number 2, it should be switch number 1.
       ## Setting priority to 15 and renumbering to 1.
  *Oct 11 2018 17:02:22.999 PDT: %HA_EM-6-LOG: sw-stack: switch 2 priority 15
  *Oct 11 2018 17:02:22.999 PDT: %HA_EM-6-LOG: sw-stack: 
  *Oct 11 2018 17:02:22.999 PDT: %HA_EM-6-LOG: sw-stack: switch 2 renumber 1
  *Oct 11 2018 17:02:23.000 PDT: %HA_EM-6-LOG: sw-stack: 
       ## FOC22222222 is currently switch number 1, it should be switch number 2.
       ## Setting priority to 14 and renumbering to 2.
  *Oct 11 2018 17:02:23.001 PDT: %HA_EM-6-LOG: sw-stack: switch 1 priority 14
  *Oct 11 2018 17:02:23.001 PDT: %HA_EM-6-LOG: sw-stack: 
  *Oct 11 2018 17:02:23.001 PDT: %HA_EM-6-LOG: sw-stack: switch 1 renumber 2
  *Oct 11 2018 17:02:23.001 PDT: %HA_EM-6-LOG: sw-stack: 
  ```

  * ...when switches are numbered correctly (manually renumbered and reloaded).
  ```cisco
  ASW-TR01-01(config)#do ev man run sw-stack
  ASW-TR01-01(config)#
  *Oct 11 2018 16:31:58.039 PDT: %HA_EM-6-LOG: sw-stack: 
       ## FOC11111111 is correctly numbered (1).
       ## Setting priority to 15 (renumbering not needed).
  *Oct 11 2018 16:31:58.040 PDT: %HA_EM-6-LOG: sw-stack: switch 1 priority 15
  *Oct 11 2018 16:31:58.041 PDT: %HA_EM-6-LOG: sw-stack: 
       ## FOC22222222 is correctly numbered (2).
       ## Setting priority to 14 (renumbering not needed).
  *Oct 11 2018 16:31:58.041 PDT: %HA_EM-6-LOG: sw-stack: switch 2 priority 14
  *Oct 11 2018 16:31:58.042 PDT: %HA_EM-6-LOG: sw-stack: 
  ```

### Required Config (Stack)

* Template Config Snippet.

    ```jinja2
    !-- Variables (keys) parsed from CSV keystore.
    !---- IDARRAY_1 (switch 1 serial number): {{idarray_1}}
    !---- IDARRAY_2 (switch 2 serial number): {{idarray_2}}
    !---- IDARRAY_3 (switch 3 serial number): {{idarray_3}}
    !---- IDARRAY_4 (switch 4 serial number): {{idarray_4}}
    !---- IDARRAY_4 (switch 5 serial number): {{idarray_5}}
    !---- IDARRAY_4 (switch 6 serial number): {{idarray_6}}
    !---- IDARRAY_4 (switch 7 serial number): {{idarray_7}}
    !---- IDARRAY_4 (switch 8 serial number): {{idarray_8}}
    !---- IDARRAY_4 (switch 9 serial number): {{idarray_9}}
    !---- IDARRAY (all serials): {{idarray}}
    !
    !-- Count number of serials parsed from CSV: {% set sw_count = idarray|count %}
    !---- SW_COUNT (count of serials found in IDARRAY): {{sw_count}}
    !
    !-- EEM applet to renumber switches accordingly.
    event manager applet sw-stack
      event none
      action 00.00 cli command "enable"
      action 00.01 cli command "show mod | i ^.[1-9]"
      action 00.02 set stack "$_cli_result"
      !{% for sw in idarray %}
      !{% set i = loop.index %}
      action 0{{i}}.00 set idarray_{{i}} "{{sw}}"
      action 0{{i}}.01 set sw "{{i}}"
      action 0{{i}}.02 set pri "16"
      action 0{{i}}.03 decrement pri {{i}}
      action 0{{i}}.04 set i "0"
      action 0{{i}}.05 regexp "{{sw}}" "$stack"
      action 0{{i}}.06 if $_regexp_result eq "1"
      action 0{{i}}.07  foreach line "$stack" "\n"
      action 0{{i}}.08   increment i
      action 0{{i}}.09   if $i le "{{sw_count}}"
      action 0{{i}}.10    string trim "$line"
      action 0{{i}}.11    set line "$_string_result"
      action 0{{i}}.12    regexp "{{sw}}" "$line"
      action 0{{i}}.13    if $_regexp_result eq "1"
      action 0{{i}}.14     if $i ne $sw
      action 0{{i}}.15      syslog msg "\n     ## $idarray_{{i}} is currently switch number $i, it should be switch number $sw.\n     ## Setting priority to $pri and renumbering to $sw."
      action 0{{i}}.16      cli command "switch $i priority $pri" pattern "continue|#"
      action 0{{i}}.17      cli command ""
      action 0{{i}}.18      cli command "switch $i renumber $sw" pattern "continue|#"
      action 0{{i}}.19      cli command ""
      action 0{{i}}.20     else
      action 0{{i}}.21      syslog msg "\n     ## $idarray_{{i}} is correctly numbered ($i).\n     ## Setting priority to $pri (renumbering not needed)."
      action 0{{i}}.22      cli command "switch $i priority $pri" pattern "continue|#"
      action 0{{i}}.23      cli command ""
      action 0{{i}}.24     end
      action 0{{i}}.25    end
      action 0{{i}}.26   end
      action 0{{i}}.27  end
      action 0{{i}}.28 else
      action 0{{i}}.29  syslog msg " ## {{sw}} (sw-{{i}} serial number) not found in the stack, check 'show mod' output."
      action 0{{i}}.30 end
      !{% endfor %}
    ```












[logo]: http://www.packetsar.com/wp-content/uploads/FreeZTP-100.png
[BugID]: https://i.imgur.com/s2avfF0.png