Feature: field station antenna mapping
    Scenario: field station initialises with valid mapping
        Given A MCCS-for-PaSD which is ready
        And PasdBus is initialised
        And A MccsFndh which is ready
        And the smartboxes are ready
        And A MccsFieldStation which is ready
        When we check the fieldstations maps
        Then we get valid mappings