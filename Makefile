#
# Project makefile for a SKA low MCCS PASD project. 
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE.txt for more info.

PROJECT = ska-low-mccs-pasd

PYTHON_SWITCHES_FOR_ISORT = --skip-glob=*/__init__.py
PYTHON_SWITCHES_FOR_BLACK = --line-length 88
PYTHON_TEST_FILE = tests
PYTHON_VARS_AFTER_PYTEST = --forked

## Paths containing python to be formatted and linted
PYTHON_LINT_TARGET = src/ tests/

DOCS_SOURCEDIR=./docs/src
DOCS_SPHINXOPTS= -n -W --keep-going

# include makefile to pick up the standard Make targets, e.g., 'make build'
include .make/oci.mk
include .make/k8s.mk
include .make/python.mk
include .make/raw.mk
include .make/base.mk
include .make/docs.mk
include .make/helm.mk

# include your own private variables for custom deployment configuration
-include PrivateRules.mak

# Add this for typehints & static type checking
python-post-format:
	$(PYTHON_RUNNER) docformatter -r -i --wrap-summaries 88 --wrap-descriptions 72 --pre-summary-newline $(PYTHON_LINT_TARGET)

python-post-lint:
	$(PYTHON_RUNNER) mypy --config-file mypy.ini src/ tests/

docs-pre-build:
	python3 -m pip install -r docs/requirements.txt


# THIS IS SPECIFIC TO THIS REPO
ifdef CI_REGISTRY_IMAGE
K8S_CHART_PARAMS = \
	--set low_mccs_pasd.image.registry=$(CI_REGISTRY_IMAGE) \
	--set low_mccs_pasd.image.tag=$(VERSION)-dev.c$(CI_COMMIT_SHORT_SHA)
endif

K8S_TEST_RUNNER_PYTEST_OPTIONS = -v --testbed local --junitxml=build/reports/functional-tests.xml
K8S_TEST_RUNNER_PYTEST_TARGET = tests/functional
K8S_TEST_RUNNER_PIP_INSTALL_ARGS = -r tests/functional/requirements.txt

# ALL THIS SHOULD BE UPSTREAMED
K8S_TEST_RUNNER_CHART_REGISTRY ?= https://artefact.skao.int/repository/helm-internal
K8S_TEST_RUNNER_CHART_NAME ?= ska-low-mccs-k8s-test-runner
K8S_TEST_RUNNER_CHART_TAG ?= 0.2.0

K8S_TEST_RUNNER_CHART_OVERRIDES =
ifdef K8S_TEST_RUNNER_IMAGE_REGISTRY
K8S_TEST_RUNNER_CHART_OVERRIDES += --set image.registry=$(K8S_TEST_RUNNER_IMAGE_REGISTRY)
endif

ifdef K8S_TEST_RUNNER_IMAGE_NAME
K8S_TEST_RUNNER_CHART_OVERRIDES += --set image.image=$(K8S_TEST_RUNNER_IMAGE_NAME)
endif

ifdef K8S_TEST_RUNNER_IMAGE_TAG
K8S_TEST_RUNNER_CHART_OVERRIDES += --set image.tag=$(K8S_TEST_RUNNER_IMAGE_TAG)
endif

ifdef CI_COMMIT_SHORT_SHA
K8S_TEST_RUNNER_CHART_RELEASE = k8s-test-runner-$(CI_COMMIT_SHORT_SHA)
else
K8S_TEST_RUNNER_CHART_RELEASE = k8s-test-runner
endif

K8S_TEST_RUNNER_PIP_INSTALL_COMMAND =
ifdef K8S_TEST_RUNNER_PIP_INSTALL_ARGS
K8S_TEST_RUNNER_PIP_INSTALL_COMMAND = pip install ${K8S_TEST_RUNNER_PIP_INSTALL_ARGS}
endif

K8S_TEST_RUNNER_WORKING_DIRECTORY ?= /home/tango

k8s-do-test:
	helm -n $(KUBE_NAMESPACE) install --repo $(K8S_TEST_RUNNER_CHART_REGISTRY) \
		$(K8S_TEST_RUNNER_CHART_RELEASE) $(K8S_TEST_RUNNER_CHART_NAME) \
		--version $(K8S_TEST_RUNNER_CHART_TAG) $(K8S_TEST_RUNNER_CHART_OVERRIDES) 
	kubectl -n $(KUBE_NAMESPACE) wait pod ska-low-mccs-k8s-test-runner \
		--for=condition=ready --timeout=$(K8S_TIMEOUT)
	kubectl -n $(KUBE_NAMESPACE) cp tests/ ska-low-mccs-k8s-test-runner:$(K8S_TEST_RUNNER_WORKING_DIRECTORY)/tests
	@kubectl -n $(KUBE_NAMESPACE) exec ska-low-mccs-k8s-test-runner -- bash -c \
		"cd $(K8S_TEST_RUNNER_WORKING_DIRECTORY) && \
		mkdir -p build/reports && \
		$(K8S_TEST_RUNNER_PIP_INSTALL_COMMAND) && \
		pytest $(K8S_TEST_RUNNER_PYTEST_OPTIONS) $(K8S_TEST_RUNNER_PYTEST_TARGET)" ; \
    EXIT_CODE=$$? ; \
	kubectl -n $(KUBE_NAMESPACE) cp ska-low-mccs-k8s-test-runner:$(K8S_TEST_RUNNER_WORKING_DIRECTORY)/build/ ./build/ ; \
	helm  -n $(KUBE_NAMESPACE) uninstall $(K8S_TEST_RUNNER_CHART_RELEASE) ; \
    exit $$EXIT_CODE

.PHONY: python-post-format python-post-lint docs-pre-build
