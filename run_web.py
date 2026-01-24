#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AutoGLM Web Server - Entry Point

Starts the FastAPI-based web server as an alternative to the GUI.
Supports headless systems and multi-user web access.

Usage:
    python run_web.py [--host HOST] [--port PORT] [--reload]
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def setup_logging():
    """Setup logging system."""
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"autoglm_web_{datetime.now().strftime('%Y%m%d')}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return log_file


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AutoGLM Web Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_web.py                    # Start with default settings
    python run_web.py --port 8000        # Use custom port
    python run_web.py --host 0.0.0.0     # Listen on all interfaces
    python run_web.py --reload           # Enable auto-reload (dev mode)
        """
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to (default: 8080)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)"
    )

    args = parser.parse_args()

    # Setup logging
    log_file = setup_logging()
    logger = logging.getLogger("AutoGLM-Web")

    logger.info("=" * 60)
    logger.info("AutoGLM Web Server Starting")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("=" * 60)

    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Please run: pip install uvicorn[standard]")
        sys.exit(1)

    try:
        logger.info(f"Starting server at http://{args.host}:{args.port}")
        logger.info(f"API docs available at http://localhost:{args.port}/docs")
        logger.info(f"Web interface at http://localhost:{args.port}")

        uvicorn.run(
            "web_app.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers if not args.reload else 1,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.exception(f"Server error: {e}")
        sys.exit(1)
    finally:
        logger.info("AutoGLM Web Server stopped")


if __name__ == "__main__":
    main()
