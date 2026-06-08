#
# Project makefile for a SKA-Low MCCS PaSD project.
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE.txt for more info.

PROJECT = ska-low-mccs-pasd

SKART_DEPS_FILE ?= skart.toml
SKART_WAIT ?= 300
SKART_REQUERY ?= 5
SKART_UPDATE_MODE ?= devel
SKART_UPDATE_DEPS ?= all
SKART_ALLOW_ALL ?= false

include .make/raw.mk
include .make/base.mk

-include PrivateRules.mak


#######################################
# PYTHON
#######################################
include .make-uv/make/python-uv.mk

# TODO: Not supported by ska-python-uv yet
# PYTHON_VARS_BEFORE_PYTEST = timeout -k 120 -s INT 3000	# 50min t/o with 2min grace
# PYTHON_VARS_BEFORE_K8S_PYTEST = timeout -k 120 -s INT 3000

python-lint: mypy


#######################################
# OCI
#######################################
include .make/oci.mk


#######################################
# K8S
#######################################
K8S_USE_HELMFILE = true
K8S_HELMFILE = helmfile.d/helmfile.yaml.gotmpl

ifdef CI_COMMIT_SHORT_SHA
K8S_HELMFILE_ENV ?= stfc-ci
else
K8S_HELMFILE_ENV ?= minikube-ci
endif


include .make/k8s.mk
include .make/xray.mk

# THIS IS SPECIFIC TO THIS REPO
ifdef CI_REGISTRY_IMAGE
K8S_CHART_PARAMS = \
	--selector chart=ska-low-mccs-pasd \
	--selector chart=ska-tango-base \
	--set image.registry=$(CI_REGISTRY_IMAGE) \
	--set image.tag=$(VERSION)-dev.c$(CI_COMMIT_SHORT_SHA) \
	--set ska-tango-devices.deviceServerTypes.pasd.image.registry=$(CI_REGISTRY_IMAGE) \
	--set ska-tango-devices.deviceServerTypes.pasd.image.tag=$(VERSION)-dev.c$(CI_COMMIT_SHORT_SHA) \	--set global.exposeAllDS=false
endif

JUNITXML_REPORT_PATH ?= build/reports/functional-tests.xml
CUCUMBER_JSON_PATH ?= build/reports/cucumber.json
JSON_REPORT_PATH ?= build/reports/report.json

K8S_TEST_RUNNER_PYTEST_OPTIONS = -v --true-context \
    --junitxml=$(JUNITXML_REPORT_PATH) \
    --cucumberjson=$(CUCUMBER_JSON_PATH) \
	--json-report --json-report-file=$(JSON_REPORT_PATH)

ifdef K8S_PYTEST_EXTRA_ARGUMENTS
K8S_TEST_RUNNER_PYTEST_OPTIONS += $(K8S_PYTEST_EXTRA_ARGUMENTS)
endif

K8S_TEST_RUNNER_PYTEST_TARGET = tests/functional
K8S_TEST_RUNNER_PIP_INSTALL_ARGS = -r tests/functional/requirements.txt

# ALL THIS SHOULD BE UPSTREAMED
K8S_TEST_RUNNER_CHART_REGISTRY ?= https://artefact.skao.int/repository/helm-internal
K8S_TEST_RUNNER_CHART_NAME ?= ska-low-mccs-k8s-test-runner
K8S_TEST_RUNNER_CHART_TAG ?= 0.9.0

K8S_TEST_RUNNER_CHART_OVERRIDES = --set global.tango_host=databaseds-tango-base:10000  # TODO: This should be the default in the k8s-test-runner
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
PYTHON_VARS_BEFORE_K8S_PYTEST += STATION_LABEL=$(STATION_LABEL)

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
		$(PYTHON_VARS_BEFORE_K8S_PYTEST) pytest $(K8S_TEST_RUNNER_PYTEST_OPTIONS) $(K8S_TEST_RUNNER_PYTEST_TARGET)" ; \
	EXIT_CODE=$$? ; \
		kubectl -n $(KUBE_NAMESPACE) cp ska-low-mccs-k8s-test-runner:$(K8S_TEST_RUNNER_WORKING_DIRECTORY)/build/ ./build/; \
		source $(K8S_SUPPORT); \
		k8sSaveLogs $(KUBE_NAMESPACE); \
		helm -n $(KUBE_NAMESPACE) uninstall $(K8S_TEST_RUNNER_CHART_RELEASE); \
		echo $$EXIT_CODE > build/status; \
		exit $$EXIT_CODE; \


telmodel-deps:
	pip install --extra-index-url https://artefact.skao.int/repository/pypi-internal/simple ska-telmodel jsonschema jsonschema-specifications fqdn

k8s-pre-install-chart: telmodel-deps
k8s-pre-uninstall-chart: telmodel-deps

python-pre-format:
	python docs/scripts/document_schemas.py

python-pre-lint:
	python docs/scripts/document_schemas.py -c

.PHONY: docs-pre-build python-post-format python-post-lint k8s-do-test k8s-pre-install-chart k8s-pre-uninstall-chart


#######################################
# HELM
#######################################
include .make/helm.mk

HELM_CHARTS_TO_PUBLISH = ska-low-mccs-pasd

helm-pre-build:
	helm repo add skao https://artefact.skao.int/repository/helm-internal

#######################################
# DOCS
#######################################
include .make-uv/make/docs-uv.mk

DOCS_SPHINXOPTS= -W --keep-going

.PHONY: python-post-lint k8s-do-test docs-pre-build

########################################################################
# HELMFILE
########################################################################
helmfile-lint:
	SKIPDEPS=""
	for environment in minikube-ci stfc-ci aa0.5 low-itf low-itf-minikube; do \
        echo "Linting helmfile against environment '$$environment'" ; \
		helmfile -e $$environment lint $$SKIPDEPS; \
		EXIT_CODE=$$? ; \
		if [ $$EXIT_CODE -gt 0 ]; then \
		echo "Linting of helmfile against environment '$$environment' FAILED." ; \
		break ; \
		fi ; \
		SKIPDEPS="--skip-deps" ; \
	done
	exit $$EXIT_CODE

deps-update-uv:
	@update_mode="$(SKART_UPDATE_MODE)"; \
	update_deps="$(strip $(SKART_UPDATE_DEPS))"; \
	update_deps_origin="$(origin SKART_UPDATE_DEPS)"; \
	deps_file="$(SKART_DEPS_FILE)"; \
	if [ "$$update_mode" != "devel" ] && [ "$$update_mode" != "release" ]; then \
		echo "deps-update-uv: SKART_UPDATE_MODE must be 'devel' or 'release' (got '$$update_mode')"; \
		exit 2; \
	fi; \
	if [ -z "$$update_deps" ]; then \
		echo "deps-update-uv: SKART_UPDATE_DEPS must not be empty"; \
		exit 2; \
	fi; \
	if [ "$$update_deps" = "all" ] && [ "$$update_deps_origin" = "command line" ] && [ "$(SKART_ALLOW_ALL)" != "true" ]; then \
		echo "deps-update-uv: refusing full update; set SKART_ALLOW_ALL=true to proceed"; \
		exit 2; \
	fi; \
	if [ ! -e "$$deps_file" ]; then \
		echo "deps-update-uv: $$deps_file not found; nothing to update (no-op)"; \
		exit 0; \
	fi; \
	if ! grep -Eq '^\[dep\.[^]]+\]' "$$deps_file"; then \
		echo "deps-update-uv: no [dep.*] entries found in $$deps_file; nothing to update (no-op)"; \
		exit 0; \
	fi; \
	if command -v uv >/dev/null 2>&1; then \
		run_skart_update() { uv run skart update "$$@"; }; \
	elif command -v skart >/dev/null 2>&1; then \
		run_skart_update() { skart update "$$@"; }; \
	else \
		echo "deps-update-uv: neither uv nor skart is available in PATH"; \
		exit 3; \
	fi; \
	mode_args=""; \
	if [ "$$update_mode" = "release" ]; then \
		mode_args="--mode release"; \
	fi; \
	if [ "$$update_deps" = "all" ]; then \
		run_skart_update $$mode_args --dep-file "$$deps_file" --wait="$(SKART_WAIT)" --requery="$(SKART_REQUERY)"; \
	else \
		for dep in $$update_deps; do \
			run_skart_update $$mode_args --dep-file "$$deps_file" --wait="$(SKART_WAIT)" --requery="$(SKART_REQUERY)" "$$dep" || exit $$?; \
		done; \
	fi

.PHONY: helmfile-lint deps-update-uv
