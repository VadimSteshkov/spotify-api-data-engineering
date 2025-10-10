# AVD shortcuts 
.PHONY: avd-env avd-up avd-producer avd-spark avd-app avd-logs avd-down avd-demo

avd-env: USR=avd
avd-up avd-producer avd-spark avd-app avd-logs avd-down avd-demo: USR=avd

# 0) Load user env + show key variables
avd-env:
	@$(MAKE) env-user USR=$(USR)
	@$(MAKE) show-env

# 1) Infra up + Kafka topics from .env
avd-up: avd-env
	@$(MAKE) up
	@$(MAKE) kafka-init-from-env

# 2) Build+run producer (ephemeral container)
avd-producer:
	@$(MAKE) producer-build
	@$(MAKE) producer-run

# 3) Start Spark streaming
avd-spark:
	@$(MAKE) spark-build
	@$(MAKE) spark-up

# 4) Start Streamlit app
avd-app:
	@$(MAKE) app-build
	@$(MAKE) app-up

# 5) Handy logs
avd-logs:
	@docker compose logs -f spark-app app || docker compose logs -f spark-app streamlit-app || true

# 6) Down (Spark first, then whole stack)
avd-down:
	@$(MAKE) spark-down || true
	@$(MAKE) down

# 7) Full chain in one go
avd-demo:
	@$(MAKE) avd-up
	@$(MAKE) avd-producer
	@$(MAKE) avd-spark
	@$(MAKE) avd-app

