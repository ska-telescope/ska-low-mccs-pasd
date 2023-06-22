
Feature: Forwarded attributes.

    # This is marked as xfail since forwarded attributes are not supported
    # by Multidevicetestcontext
    @xfail
    Scenario: FNDH-FieldStation forwarded attributes change event
        Given we have a fndh device
        When we have a fieldstation device
        Then they agree on the outsideTemperature