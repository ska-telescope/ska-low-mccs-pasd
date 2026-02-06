Feature: Pasd On Off tests against hardware
    Test that MCCS subsystem attached to real hardware can be turned on and off safetly

    Scenario: Initialise PaSD devices
        Given A pasd setup that is connected to hardware
        And pasd is in DISABLE state
        And pasd has UNKNOWN health
        When pasd adminMode is set to ONLINE
        Then pasd reports ON state

    Scenario: Turn off PaSD devices
        Given A pasd setup that is connected to hardware
        And pasd is in ON state
        And pasd has OK health
        When field station is turned off
        Then pasd reports OFF state

    Scenario: Turn on PaSD devices
        Given A pasd setup that is connected to hardware
        And pasd is in OFF state
        And pasd has OK health
        When field station is turned on
        Then pasd reports ON state



# @stations(ci-1)
# Scenario: Turn on MCCS-for-PaSD
#     Given A MCCS-for-PaSD which is not ready
#     And MCCS-for-PaSD is in DISABLE state
#     And MCCS-for-PaSD has UNKNOWN health
#     When MCCS-for-PaSD adminMode is set to ONLINE
#     Then MCCS-for-PaSD reports ON state
