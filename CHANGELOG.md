# Version History

## unreleased

## 0.11.0

* [MCCS-2141] Update ska-tango-base to 1.0.0
* [MCCS-2115] Update field station to use new antenna mappings

## 0.10.1

* [LOW-952]: Point at ska-low-tmdata for AA0.5 telmodel data
* [MCCS-2216]: Support nulls in values schemas
* [WOM-370]: Faster, more reliable tests

## 0.10.0

* [WOM-147]: Add metadata to the Tango attributes
* [SKB-455]: Automatically reset the connection when a poll fails
* [WOM-144]: Synchronize Tango alarm config with threshold values
* [WOM-361]: Change FEM current trip threshold attributes to an array
* [WOM-384]: Fix misleading messages
* [WOM-217]: Use YAML to define the mapping between Tango attributes and device registers
* [WOM-374]: Enforce init order of device servers
* [WOM-385]: Remove redundant archive events from pasdbus device

## 0.9.0

* [MCCS-2175]: Add HealthState to FieldStation
* [MCCS-2153]: Add MCCS schemas to TelModel
* [WOM-381]: Always push change events from pasdbus
* [MCCS-2029]: Pull TMData to pasd
* [MCCS-2107]: Remove deprecated environments
* [WOM-276]: Only poll deployed smartboxes
* [WOM-331]: Remove resetFndhPortBreakers cmd

## 0.8.0

* [WOM-244]: Support for reading the FNCC registers
* [WOM-249,WOM-317]: User documentation
* [WOM-112]: Mark attributes as invalid when a device doesn't respond
* [MCCS-1978]: infra-managed Low ITF credentials
* [MCCS-1963]: Change backoff to exponential
* [MCCS-1995]: Chart values schema
* [MCCS-2070]: String keys
* [MCCS-2083]: use HTTP for PaSD config server
* [MCCS-2091]: refactor configuration server
* [MCCS-2093]: one PaSD config server
* [MCCS-2090]: Remove placeholder code, causing incorrect health reporting
* [MCCS-2094]: remove unused access
* [WOM-326]: Delays in executing commands
* [WOM-329]: Change in attribute quality does not push change event
* [WOM-318]: Make threshold attributes writeable
* [MCCS-1968]: Fix manual config commands
* [MCCS-2081]: Fix empty port power change event bug
* [MCCS-2060]: Add eda_config.yaml with all pasd attributes

## 0.7.0

* [WOM-183] Update error log message for modbus exception responses
* [MCCS-1957] Support namespace override
* [WOM-240] Remove default logger and ensure correct object used
* [WOM-184] Refactor functional and smartbox integration tests
* [WOM-165] Add command to set sensors' low-pass filter cutoff frequency
* [WOM-149] Add support for setting multiple port powers in a single modbus command
* [WOM-246] Indicate modbus address in all error messages and refactor request exceptions
* [MCCS-1966] use infra-issued credentials for AAVS3
* [MCCS-1973] Update MccsPasdBUs to update SimulationConfig on device creation
* [MCCS-1963] Add backoff retry for connection to configuration server

## 0.6.0

* [MCCS-1751] FieldStation Dashboard
* [MCCS-1745] - Add FieldStation antenna mapping
* [WOM-119] Improve MODBUS API test coverage
* [WOM-159] Request to re-read the static info and thresholds
* [MCCS-1745] Smartbox Mapping
* [WOM-167] Fix simulator server and uptime conversion
* [MCCS-1861] Parameterise MccsSmartbox property FieldStationName
* [MCCS-1859] helm values
* [LOW-637] use correct dev image in dev chart builds
* [MCCS-1939] AAVS3 staging on Low ITF
* [MCCS-1944] Check in Chart.lock
* [MCCS-1957] Support namespace override
* [MCCS-1871] Allow configuarble PaSDBus Polling rates.
* [WOM-161] Update port register parsing
* [WOM-110] Update attributes immediately after writing
* [MCCS-1848] - Convert OutsideTemperature to attribute.
* [MCCS-1857] refactor helmfile templates
* [MCCS-1813] MccsSmartbox is pushing change events with malformed attribute names
* [MCCS-1864] Update FieldStation attribute to optional.
* [MCCS-1868] Update FieldStation to derive state from antenna states.
* [MCCS-1937] Update pasd-configuration-server to deploy when interfacing with hardware.
* [MCCS-1938] Prevent MccsSmartbox from turning on ports on other smartboxes.
* [MCCS-1870] Antenna power command bug
* [MCCS-1849] Fix incorrect exception handle type in fieldstation.
* [MCCS-1869] Fix FieldStation On command Bug.
* [MCCS-1939] more tweaks
* [MCCS-1837] Speed up python-test
* [MCCS-1855] Update CODEOWNERS
* [WOM-157] Partially revert merge and update simulator
* [MCCS-1947] Support platform spec without pasd


## 0.5.0

* [WOM-157] Update set led pattern commands
* [WOM-107] Implement FNDH port state registers PWRSENSE & POWER
* [MCCS-1846] Support disabling PaSD
* [WOM-111] Handle bad responses more robustly
* [WOM-162] Fix bug in SmartBoxComponentManager and its PasdBusProxy
* [MCCS-1745] : Add antenna powers attribute to FieldStation
* [MCCS-1753] Modify PaSD Bus Simulator to use Modbus API rather than JSON API
* [MCCS-1755] Fieldstation ON/OFF
* [WOM-156] Make timeout setting in values.yaml take effect
* [WOM-140] Smarboxes depend on attached FNDH ports in functional and integration tests
* [WOM-150] Add warning/alarm flags to FNDH and SMART box polling loop
* [MCCS-1814] Simplify smartbox
* [MCCS-1801] Poll management
* [MCCS-1807] Filter by device
* [WOM-108] - Alarm thresholds
* [MCCS-1800] set port powers
* [MCCS-1794] defer connecting
* [MCCS-1788] Refactor test harness
* [MCCS-1787] TurnAllPortsOn
* [WOM-113] Removed ports_connected attribute from FNDH/smartbox.
* [MCCS-1784] field station configure


## 0.4.0

* [MCCS-1769] Update to pytango 9.4.2
* [MCCS-1697] Support using platform-service tangodb instead of always deploying our own.
* [MCCS-1694] Fix bug in use of "enabled" key to control what gets deployed

## 0.3.0

* [MCCS-1685] remove ska-tango-base
* [MCCS-1680] platform dependent configuration
* [WOM-103] [WOM-104] Smartbox simulator instances depend on FNDH ports' power state.
  Uptime tracked from instantiation.
* [MCCS-1679] external PaSD configuration
* [WOM-59] [WOM-46] FNDH/smartbox attributes and simulator updates
* Implementation of PaSD commands
* [MCCS-1646] Remove xfail from fieldStation device.
* [MCCS-1636] Use ska-ser-sphinx-theme
* [MCCS-1633] Update /docs/src/_static/img/ in MCCS repos
* [MCCS-1482] Implement solution to "attribute requested before first Poll" error.
* [WOM-43] Implement read_attributes part of Modbus client API
* [MCCS-1619] MccsFNDH does not subscribe to state or adminMode changes on MccsPaSDBus
* [MCCS-1622] Transport logging
* [MCCS-1503] fndh functional test
* [MCCS-1618] Update proxy callbacks in MccsSmartbox
* [MCCS-1569] Add FieldStation device with forwarded attribute outsideTemperature
* [MCCS-1613] Add version logging to device init
* [MCCS-1356] Update state changed callback to use kwargs
* [WOM-30] skeleton Modbus API

## 0.2.1

* MCCS-1526 - Fix broken docs.
* MCCS-1500 - Fix broken umbrella chart.
* MCCS-764  - Fix some minor bugs in Smartbox/FNDH.
* MCCS-1528 - Fix charts to not publish umbrella.

## 0.2.0

* MCCS-1345 - Update ska-low-mccs-pasd to use ska-tango-testing
* MCCS-1445 - Modify configuration file path, update pasdbus entry point
* MCCS-1403 - Create standalone PaSD simulator
* MCCS-1404 - Helm chart update for PaSD simulator
* MCCS-1454 - Add log statements to the PASD simulator
* MCCS-1470 - Rewrite PaSD simulator and driver to address one PaSD device at a time.
* MCCS-1461 - Create Xray tickets and dummy implementation for PASD test set
* MCCS-1475 - Reimplement PaSD bus component manager as a poller.
* MCCS-768  - Implement Smartbox device
* MCCS-764  - Implement FNDH device

## 0.1.0

* MCCS-1209 - Use ska_tango_testing.mock
* MCCS-1196 - enable k8s-test
* MCCS-1111 - Update license with copyright
* MCCS-1156 - Fix linting & static type checking in ska-low-mccs-pasd

Initial release

* MCCS-1151 - initial creation
