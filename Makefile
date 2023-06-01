#
# Project makefile for a SKA-Low MCCS PaSD project. 
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE.txt for more info.

PROJECT = ska-low-mccs-pasd

include .make/raw.mk
include .make/base.mk
-include PrivateRules.mak


#######################################
# PYTHON
#######################################
include .make/python.mk

PYTHON_LINE_LENGTH = 88
PYTHON_VARS_AFTER_PYTEST = --forked
PYTHON_LINT_TARGET = src/ tests/

python-post-lint:
	$(PYTHON_RUNNER) mypy --config-file mypy.ini src/ tests/


#######################################
# OCI
#######################################
include .make/oci.mk


#######################################
# K8S
#######################################
include .make/k8s.mk
include .make/xray.mk

# THIS IS SPECIFIC TO THIS REPO
ifdef CI_REGISTRY_IMAGE
K8S_CHART_PARAMS = \
	--set low_mccs_pasd.image.registry=$(CI_REGISTRY_IMAGE) \
	--set low_mccs_pasd.image.tag=$(VERSION)-dev.c$(CI_COMMIT_SHORT_SHA)
endif


JUNITXML_REPORT_PATH ?= build/reports/functional-tests.xml
CUCUMBER_JSON_PATH ?= build/reports/cucumber.json
JSON_REPORT_PATH ?= build/reports/report.json

K8S_TEST_RUNNER_PYTEST_OPTIONS = -v --true-context \
    --junitxml=$(JUNITXML_REPORT_PATH) \
    --cucumberjson=$(CUCUMBER_JSON_PATH) \
	--json-report --json-report-file=$(JSON_REPORT_PATH)

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


#######################################
# HELM
#######################################
include .make/helm.mk

HELM_CHARTS_TO_PUBLISH = ska-low-mccs-pasd


#######################################
# DOCS
#######################################
include .make/docs.mk

DOCS_SOURCEDIR=./docs/src
DOCS_SPHINXOPTS= -n -W --keep-going

docs-pre-build:
	poetry config virtualenvs.create false
	poetry install --no-root --only docs


.PHONY: python-post-lint k8s-do-test docs-pre-build
