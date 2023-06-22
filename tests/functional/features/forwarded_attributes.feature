Feature: Forwarded attributes.

    # This is marked as xfail since forwarded attributes are not supported
    # by Multidevicetestcontext
    @xfail
    Scenario: FieldStation forwarded attributes.
        Given we have a fndh device
        When we have a fieldstation device
        Then they agree on the outsideTemperature