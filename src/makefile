.PHONY: kafka-init kafka-list kafka-events kafka-snapshot

# Creează topicurile necesare
kafka-init:
	docker exec -it kafka kafka-topics --create --topic spotify_recent_events --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1 || true
	docker exec -it kafka kafka-topics --create --topic spotify_recent_snapshot --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1 || true

# Listează toate topicurile existente
kafka-list:
	docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092

# Consumă ultimele mesaje din topicul "spotify_recent_events"
kafka-events:
	kcat -b localhost:9092 -t spotify_recent_events -C -o beginning -q

# Consumă ultimul snapshot
kafka-snapshot:
	kcat -b localhost:9092 -t spotify_recent_snapshot -C -o beginning -q
run:
	.venv/bin/python3 DE-Spotify.py
	
demo:
	@echo ">>> Ctrl+C ca să oprești fiecare consumator"
	$(MAKE) -s kafka-events & \
	$(MAKE) -s kafka-snapshot



