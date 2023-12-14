Feature: field station antenna mapping
    Scenario: field station initialises with valid mapping
        Given A MCCS-for-PaSD which is ready
        And PasdBus is initialised
        And A MccsFndh which is ready
        And the smartboxes are ready
        And A MccsFieldStation which is ready
        When we check the fieldstations maps
        Then we get valid mappings
    
    Scenario Outline: we can turn on any antenna given a station
        Given A MCCS-for-PaSD which is ready
        And PasdBus is initialised
        And A MccsFndh which is ready
        And the smartboxes are ready
        And A MccsFieldStation which is ready
        And smartbox <smartbox_id> is <setup_state>
        And the smartbox port <smartbox_port> is <setup_state>
        And antenna <antenna_number> is <setup_state>
        When we turn <desired_state> antenna <antenna_number>
        Then the correct smartbox becomes <desired_state>
        And antenna <antenna_number> turns <desired_state>
        And smartbox port <smartbox_port> turns <desired_state>

        Examples:
        |  station_name  |  antenna_number  | smartbox_id  | smartbox_port  |  setup_state |  desired_state  |
        |     "ci-1"     |        113       |      1       |       7        |      OFF     |       ON        |
#        |     "ci-1"     |        113       |      1       |       7        |      ON      |       OFF       | # bug in MCCS-1870
    