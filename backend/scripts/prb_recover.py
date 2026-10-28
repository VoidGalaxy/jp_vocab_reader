"""P-RB recovery operator tool (P_RB_TOOL_CONTRACT.md): preview, prepare (step A), recover
(step B), verify, release (the completed release of a verified recovery, contract 14), status.

    python scripts/prb_recover.py preview --user-id N [--recovery-key K]
    python scripts/prb_recover.py prepare --user-id N --recovery-key K --plan <64 hex>
    python scripts/prb_recover.py recover --user-id N --recovery-key K --plan <64 hex>
    python scripts/prb_recover.py verify  --user-id N --recovery-key K
    python scripts/prb_recover.py release --user-id N --recovery-key K --plan <64 hex>
    python scripts/prb_recover.py status  --user-id N --recovery-key K

- `preview` is the default use: read only, counts / reason codes / plan fingerprint only.
- `prepare`, `recover`, `verify` and `release` ask the account id again and the grant token by HIDDEN
  input (getpass). The token is never an argument, an environment value or a file, and is
  never printed.
- The target database is the app's DATABASE_URL under the app's own safety checks; nothing
  here relaxes them. Production use needs its own approval.
Exit: 0 done, 2 refused / not verified / input mismatch."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

_WITH_TOKEN = ("prepare", "recover", "verify", "release")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P-RB recovery tool (preview / prepare / recover / verify / release / status)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "prepare", "recover", "verify", "release", "status"):
        command = sub.add_parser(name)
        command.add_argument("--user-id", type=int, required=True)
        command.add_argument("--recovery-key", required=name != "preview")
        if name in ("prepare", "recover", "release"):
            command.add_argument("--plan", required=True)
    return parser


def main(argv: list[str] | None = None, *, ask=input, secret=getpass.getpass, out=print) -> int:
    args = _parser().parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import account_blocks, recovery
    from app.account_write import AccountWriteError

    try:
        if args.command == "preview":
            result = recovery.preview(args.user_id, args.recovery_key)
        elif args.command == "status":
            result = recovery.resume_status(args.user_id, args.recovery_key)
        else:
            again = ask("Account id again: ").strip()
            if again != str(args.user_id):
                out(json.dumps({"status": "refused", "code": "account_confirmation_mismatch"}))
                return 2
            token = secret("Grant token (hidden): ")
            if args.command == "prepare":
                result = recovery.prepare(args.user_id, args.recovery_key, token, args.plan)
            elif args.command == "recover":
                result = recovery.recover(args.user_id, args.recovery_key, token, args.plan)
            elif args.command == "release":
                result = account_blocks.release_block(args.user_id, args.recovery_key, token, "completed",
                                                      plan=args.plan)
            else:
                result = recovery.verify(args.user_id, args.recovery_key, token)
            del token
    except recovery.RecoveryRefused as error:
        out(json.dumps({"status": "refused", "code": error.code, "reasons": error.reasons}))
        return 2
    except AccountWriteError as error:
        out(json.dumps({"status": "refused", "code": error.code}))
        return 2
    out(json.dumps(result, sort_keys=True))
    return 2 if result.get("status") == "not_verified" else 0


if __name__ == "__main__":
    raise SystemExit(main())
