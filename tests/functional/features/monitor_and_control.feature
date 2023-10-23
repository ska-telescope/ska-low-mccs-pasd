@SP-1931
Feature: Monitoring and control of PaSD
    Test that MCCS subsystem can monitor and control a PaSD system.

    @XTP-20301 @XTP-21594
    Scenario: Monitor PaSD FNDH
        Given A MCCS-for-PaSD which is not ready
        And a smartbox
        And MCCS-for-PaSD is in DISABLE state
        And MCCS-for-PaSD has UNKNOWN health
        When MCCS-for-PaSD adminMode is set to ONLINE
        Then MCCS-for-PaSD reports ON state
        And MCCS-for-PaSD reports its FNDH uptime
        And MCCS-for-PaSD reports its FNDH status
        And MCCS-for-PaSD reports its FNDH LED pattern
        And MCCS-for-PaSD reports its FNDH 48v PSU voltages
        And MCCS-for-PaSD reports its FNDH 48v PSU current
        And MCCS-for-PaSD reports its FNDH 48v PSU temperatures
        And MCCS-for-PaSD reports its FNDH panel temperature
        And MCCS-for-PaSD reports its FNDH FNCB ambient temperature
        And MCCS-for-PaSD reports its FNDH FNCB ambient humidity
        And MCCS-for-PaSD reports its FNDH communications gateway enclosure temperature
        And MCCS-for-PaSD reports its FNDH power module enclosure temperature
        And MCCS-for-PaSD reports its FNDH ouside ambient reference temperature
        And MCCS-for-PaSD reports its FNDH internal ambient reference temperature
        And MCCS-for-PaSD health becomes OK
    
    @XTP-20301
    Scenario: Monitor PaSD Smartbox
        Given A MCCS-for-PaSD which is ready
        And MCCS-for-PaSD is in ON state
        And the FNDH is initialized
        And a smartbox
        And a FNDH port
        And the FNDH port is on
        When MCCS-for-PaSD adminMode is set to ONLINE
        Then MCCS-for-PaSD reports its smartbox uptime
        And MCCS-for-PaSD reports its smartbox status
        And MCCS-for-PaSD reports its smartbox LED pattern
        And MCCS-for-PaSD reports its smartbox input voltage
        And MCCS-for-PaSD reports its smartbox power supply output voltage
        And MCCS-for-PaSD reports its smartbox power supply temperature
        And MCCS-for-PaSD reports its smartbox PCB temperature
        And MCCS-for-PaSD reports its smartbox FEM package ambient temperature
        And MCCS-for-PaSD reports its smartbox FEM 6 & 12 case temperatures
        And MCCS-for-PaSD reports its smartbox FEM heatsink temperatures
        And MCCS-for-PaSD health becomes OK

    @XTP-21514 @XTP-21594
    Scenario: Turn on FNDH port
        Given A MCCS-for-PaSD which is ready
        And MCCS-for-PaSD is in ON state
        And the FNDH is initialized
        And a FNDH port
        And the FNDH port is off
        When I tell MCCS-for-PaSD to turn the FNDH port on
        Then the FNDH port turns on

    @XTP-21515 @XTP-21594
    Scenario: Turn off FNDH port
        Given A MCCS-for-PaSD which is ready
        And MCCS-for-PaSD is in ON state
        And the FNDH is initialized
        And a FNDH port
        And the FNDH port is on
        When I tell MCCS-for-PaSD to turn the FNDH port off
        Then the FNDH port turns off

    @XTP-21516 @XTP-21594
    Scenario: Turn on smartbox port
        Given A MCCS-for-PaSD which is ready
        And MCCS-for-PaSD is in ON state
        And a smartbox
        And the smartbox is initialized
        And a smartbox port
        And the smartbox port is off
        When I tell MCCS-for-PaSD to turn the smartbox port on
        Then the smartbox port turns on

    @XTP-21517 @XTP-21594
    Scenario: Turn off smartbox port
        Given A MCCS-for-PaSD which is ready
        And MCCS-for-PaSD is in ON state
        And a smartbox
        And the smartbox is initialized
        And a smartbox port
        And the smartbox port is on
        When I tell MCCS-for-PaSD to turn the smartbox port off
        Then the smartbox port turns off
