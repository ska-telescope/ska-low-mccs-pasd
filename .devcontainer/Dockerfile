FROM artefact.skao.int/ska-tango-images-pytango-builder:9.5.0 AS buildenv
RUN apt-get update && apt-get install gnupg2 openssh-client -y
RUN poetry self update -n 1.8.4