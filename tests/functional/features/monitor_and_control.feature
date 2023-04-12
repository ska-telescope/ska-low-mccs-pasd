@SP-1931
Feature: Monitoring and control of PaSD
    Test that MCCS subsystem can monitor and control a PaSD system.

    @XTP-20301
    Scenario: Monitor PaSD
        Given the PaSD is available
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
        And MCCS-for-PaSD reports its FNDH 48v PSU temperature
        And MCCS-for-PaSD reports its FNDH 5v PSU voltage 
        And MCCS-for-PaSD reports its FNDH 5v PSU temperature 
        And MCCS-for-PaSD reports its FNDH PCB temperature
        And MCCS-for-PaSD reports its FNDH outside temperature
        And MCCS-for-PaSD reports its smartbox uptime
        And MCCS-for-PaSD reports its smartbox status
        And MCCS-for-PaSD reports its smartbox LED pattern
        And MCCS-for-PaSD reports its smartbox input voltage
        And MCCS-for-PaSD reports its smartbox power supply output voltage
        And MCCS-for-PaSD reports its smartbox power supply temperature
        And MCCS-for-PaSD reports its smartbox outside temperature
        And MCCS-for-PaSD reports its smartbox PCB temperature
        And MCCS-for-PaSD health becomes OK

    @XTP-21514
    Scenario: Turn on FNDH port
        Given the PaSD is available
        And MCCS-for-PaSD is in ON state
        And a connected FNDH port
        And the FNDH port is off
        When I tell MCCS-for-PaSD to turn the FNDH port on
        Then the FNDH port turns on

    @XTP-21515
    Scenario: Turn off FNDH port
        Given the PaSD is available
        And MCCS-for-PaSD is in ON state
        And a connected FNDH port
        And the FNDH port is on
        When I tell MCCS-for-PaSD to turn the FNDH port off
        Then the FNDH port turns off

    @XTP-21516
    Scenario: Turn on smartbox port
        Given the PaSD is available
        And MCCS-for-PaSD is in ON state
        And a smartbox
        And a connected smartbox port
        And the smartbox port is off
        When I tell MCCS-for-PaSD to turn the smartbox port on
        Then the smartbox port turns on

    @XTP-21517
    Scenario: Turn off smartbox port
        Given the PaSD is available
        And MCCS-for-PaSD is in ON state
        And a smartbox
        And a connected smartbox port
        And the smartbox port is on
        When I tell MCCS-for-PaSD to turn the smartbox port off
        Then the smartbox port turns off
