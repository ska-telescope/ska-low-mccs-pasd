# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides an entry point for a Mccs Configurator."""
from __future__ import annotations

import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler
import yaml
import json
import tango
from typing import List

class MccsConfigurator:
    """
    # TODO: This is a proof of concept
    # Code is in no way ready or designed.
    # Should this be a TANGO device?
    """

    def __init__(self, file_to_watch="/config/pasd_configuration.yaml"):
        self.observer = Observer()

        # TODO: there could be 2 config files to watch, One updated by TelModel one updated by PaSDSimulators.
        # When the PaSDBus goes into simulation mode it can simulate a configuration, this allows us to test
        # how high up devices will respond. i.e does the fieldstation change its mapping in response? 

        self.directory_to_watch, self.config_file = os.path.split(os.path.normpath(file_to_watch))
        self.file_to_watch = file_to_watch
        self.change_handler = FileChangeHandle(self.file_to_watch)


    def run(self):
        on_change_event = self.change_handler
        self.observer.schedule(on_change_event, self.directory_to_watch, recursive=False)
        self.observer.start()
        try:
            while True:
                time.sleep(5)

        except:
            self.observer.stop()

        self.observer.join()


class FileChangeHandle(LoggingEventHandler):
    """
    # TODO: This is a proof of concept
    # Code is in no way ready or designed.
    """

    def __init__(self, file_to_watch: str):

        self.file_to_watch = file_to_watch

        super().__init__()

    def on_any_event(self, event):
        if event.is_directory:
            return None

        elif event.event_type == 'created':

            # TODO: This can be called before the FieldStation devices are 
            # initialised. Deal with it!
            logging.error("Received created event - %s." % event.src_path)

        elif event.event_type == 'modified':
            # Issue: This gets called 2 times https://github.com/gorakhargosh/watchdog/issues/93
            # Hmmm... this issue was opened for a long time, do we want to use this library?

            logging.error("Received modified event - %s." % event.src_path)

            # TODO: This can be called before the FieldStation devices are 
            # initialised. Deal with it!


            # check changed file is the one under interest
            if event.src_path == self.file_to_watch:
                with open(event.src_path, 'r') as file:
                    configuration = yaml.safe_load(file)

                # TODO: Assumptions about parsing need to be removed! Versioned configuration validators?
                for cluster_name in configuration["station_clusters"]:
                    for station_name in configuration["station_clusters"][cluster_name]["stations"]: # TODO: Yuck!! 
                        try:
                            # TODO: if station not in TANGO database, WHY?, What should we do?
                            # "low-mccs/fieldstation/" should be parameterised, may change.

                            logging.error(f"name forming proxy : low-mccs/fieldstation/{cluster_name}-{station_name}")
                            _fieldStationProxy = tango.DeviceProxy(f"low-mccs/fieldstation/{cluster_name}-{station_name}")

                            # TODO: We don't want to be updating every station with everything
                            _fieldStationProxy.UpdateConfiguration(json.dumps(configuration))

                        except Exception as e:
                            logging.error(f"Did not manage to update device: {e}")


def main(*path_to_configuration_file):
    w = MccsConfigurator(*path_to_configuration_file)
    w.run()

if __name__ == '__main__':
    main()