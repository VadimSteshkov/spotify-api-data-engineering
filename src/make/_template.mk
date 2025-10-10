# TEMPLATE shortcuts (copy this file to make/<user>.mk and replace 'usr')
.PHONY: usr-env usr-up usr-producer usr-spark usr-app usr-logs usr-down usr-demo

usr-env: USR=usr
usr-up usr-producer usr-spark usr-app usr-logs usr-down usr-demo: USR=usr

usr-env:
	@$(MAKE) env-user USR=$(USR)
	@$(MAKE) show-env

usr-up: usr-env
	@$(MAKE) up
	@$(MAKE) kafka-init-from-env

usr-producer:
	@$(MAKE) producer-build
	@$(MAKE) producer-run

usr-spark:
	@$(MAKE) spark-build
	@$(MAKE) spark-up

usr-app:
	@$(MAKE) app-build
	@$(MAKE) app-up

usr-logs:
	@docker compose logs -f spark-app app || docker compose logs -f spark-app streamlit-app || true

usr-down:
	@$(MAKE) spark-down || true
	@$(MAKE) down

usr-demo:
	@$(MAKE) usr-up
	@$(MAKE) usr-producer
	@$(MAKE) usr-spark
	@$(MAKE) usr-app

