"""Raw-SQL repository functions, one module per table family.

Migrations are hand-written SQL (infra/migrations/env.py); so is every query
here, via `sqlalchemy.text`, matching `core/db.py`. There is no ORM layer --
adding one is a bigger decision than any single Week 3/4 task and isn't
needed yet.
"""
