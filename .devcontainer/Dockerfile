FROM artefact.skao.int/ska-tango-images-pytango-builder:9.4.3 AS buildenv
RUN apt-get update && apt-get install gnupg2 openssh-client -y
RUN poetry self update -n 1.8.3