DB_CONTAINER=db

.PHONY: db_up db_down db_logs db_backup refresh_leaderboard

db_up:
	docker compose up -d $(DB_CONTAINER)

db_down:
	docker compose down

db_logs:
	docker compose logs -f $(DB_CONTAINER)

# Creates backup.sql in current directory
db_backup:
	PGPASSWORD=football pg_dump -h localhost -U football -d football -f backup.sql

refresh_leaderboard:
	python tools/refresh_leaderboard.py
