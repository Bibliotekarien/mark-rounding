"""Command line entry point: serve, init-db, hash-password.

Note: markrounding.config resolves env vars at import time, so --db is
exported to MARKROUNDING_DB_PATH *before* any application import happens.
"""

import argparse
import getpass
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="markrounding")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the API + frontend server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--db", default=None)
    serve.add_argument("--reload", action="store_true")

    initdb = sub.add_parser("init-db", help="Create the database schema")
    initdb.add_argument("--db", default=None)

    sub.add_parser(
        "hash-password",
        help="Hash an admin password for MARKROUNDING_ADMIN_PASSWORD_HASH",
    )

    args = parser.parse_args()

    if getattr(args, "db", None):
        os.environ["MARKROUNDING_DB_PATH"] = args.db

    if args.command == "init-db":
        from . import db
        from .config import DEFAULT_DB_PATH

        conn = db.connect(DEFAULT_DB_PATH)
        db.init_db(conn)
        conn.close()
        print(f"Databas initierad: {DEFAULT_DB_PATH}")
    elif args.command == "hash-password":
        from .auth import hash_password

        password = getpass.getpass("Lösenord: ")
        again = getpass.getpass("Upprepa: ")
        if password != again:
            raise SystemExit("Lösenorden matchar inte.")
        print(f"MARKROUNDING_ADMIN_PASSWORD_HASH={hash_password(password)}")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run(
            "markrounding.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )


if __name__ == "__main__":
    main()
