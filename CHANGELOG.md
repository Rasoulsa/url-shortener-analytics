# Changelog

All notable changes to this project will be documented in this file.

The project follows a practical changelog style inspired by [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- Initial FastAPI project structure
- Core configuration with Pydantic settings
- SQLAlchemy models for users, links, and click analytics
- Redis client configuration
- Short-code generation service using random Base62 codes
- Redis `SETNX`-based short-code reservation
- Base62 encode/decode helper functions
- Tests for short-code generation and Base62 behavior
- Dockerfile for containerized application runtime
- Docker Compose stack with API, PostgreSQL, Redis, Celery worker, and Alembic migration service
- Project documentation files

### Changed
- Environment configuration standardized around `.env.example` as the committed template

### Notes
- `.env` and `.env.dev` are local/private files and should not be committed
- Docker service hostnames use Compose service names: `db` and `redis`

---

## [1.0.0] - 2026-06-28

### Added
- Day 1 foundation for URL Shortener & Analytics project
