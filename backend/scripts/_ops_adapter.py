"""Operations tool safety contract, connection provider unit 6-1d: the connection adapter that ties
the 6-1a provider, the 6-1b verified certificate copy and the 6-1c observer together
(OPS_CONNECTION_PROVIDER_CONTRACT.md 11절).

There is no real driver here: the entry point needs a driver function passed in, and only tests
pass a fake. Nothing in this module calls `psycopg.connect`; the provider's default entry point
and production mode keep refusing. A pass is not a connection permission and does not prove
that TLS, authentication or server `options` were applied: only that these arguments were passed.

Order inside `open`: build and check the driver arguments -> make the verified copy -> call the
driver with `sslrootcert` = the copy -> after the call returns, remove the copy. The provider
then observes, judges, rolls back, checks IDLE and hands over.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import psycopg
from psycopg.conninfo import conninfo_to_dict

import _ops_observer as ob
import _ops_preflight as op
import _ops_provider as pv
import _ops_target as ot
import _ops_tlsroot as tr

USER_KEYS = ("user", "password", "host", "port", "dbname")
DSN_KEYS = frozenset(USER_KEYS + ("sslmode", "sslrootcert"))
FIXED_KEYS = frozenset({"application_name", "connect_timeout", "gssencmode", "options", "sslcertmode"})
_PRIORITY = ("connection_close_unconfirmed", "tls_copy_cleanup_unconfirmed", "observation_rollback_failed")


def _ranked(codes: list[str]) -> pv.OpsProviderRefused:
    """Contract 11절: close unconfirmed > copy cleanup unconfirmed > rollback failed > original."""
    unique = list(dict.fromkeys(codes))
    unique.sort(key=lambda c: _PRIORITY.index(c) if c in _PRIORITY else len(_PRIORITY))
    return pv.OpsProviderRefused(unique[0], tuple(unique[1:]))


def _copy_codes(error: tr.OpsTlsRootRefused) -> list[str]:
    return [error.code, *error.also]


class CopyingFactory:
    """6-1a `ConnectionFactory`: one use. Holds the manifest bytes and deployment root fixed at
    start; the driver is whatever the caller passed (tests: a fake)."""

    def __init__(self, manifest: bytes, deploy_root: str, driver: Callable[..., Any]):
        self._manifest = manifest
        self._root = deploy_root
        self._driver = driver
        self._used = False

    def __repr__(self) -> str:
        return "CopyingFactory()"

    def _arguments(self, request: pv.ConnectRequest) -> dict[str, str]:
        """Structured keyword arguments; no string-built DSN and no extra keys."""
        if not isinstance(request, pv.ConnectRequest) or type(request.secret_dsn) is not str:
            raise pv.OpsProviderRefused("connect_arguments_invalid")
        try:
            parsed = conninfo_to_dict(request.secret_dsn)                  # libpq parse only, no connection
        except (psycopg.Error, UnicodeError, ValueError):
            raise pv.OpsProviderRefused("connect_arguments_invalid") from None
        try:
            original = os.path.join(self._root, *tr.select_tls_root(self._manifest).split("/"))
        except (tr.OpsTlsRootRefused, TypeError):
            raise pv.OpsProviderRefused("connect_arguments_invalid") from None
        if set(parsed) != DSN_KEYS or not all(type(parsed[k]) is str and parsed[k] for k in DSN_KEYS) \
                or parsed["sslmode"] != ot.REQUIRED_SSLMODE or parsed["sslrootcert"] != original:
            raise pv.OpsProviderRefused("connect_arguments_invalid")
        fixed = request.fixed
        if not isinstance(fixed, tuple) or not all(type(i) is tuple and len(i) == 2
                                                   and all(type(x) is str for x in i) for i in fixed):
            raise pv.OpsProviderRefused("connect_arguments_conflict")
        names = [name for name, _ in fixed]
        if len(set(names)) != len(names) or set(names) != FIXED_KEYS:
            raise pv.OpsProviderRefused("connect_arguments_conflict")
        arguments = {key: parsed[key] for key in USER_KEYS}                  # user values: these five only
        arguments["sslmode"] = ot.REQUIRED_SSLMODE
        for name, value in fixed:                                            # provider-fixed values
            if name in arguments:
                raise pv.OpsProviderRefused("connect_arguments_conflict")
            arguments[name] = value
        return arguments

    def open(self, request: pv.ConnectRequest) -> Any:
        if self._used:
            raise pv.OpsProviderRefused("adapter_already_used")
        self._used = True
        arguments = self._arguments(request)
        copy = tr.VerifiedRootCopy(self._manifest, self._root)
        try:
            copy.__enter__()
        except tr.OpsTlsRootRefused as refused:
            raise _ranked(_copy_codes(refused)) from None          # the driver is never called
        connection: Any = None
        failures: list[str] = []
        try:
            arguments["sslrootcert"] = copy.path                   # the copy, never the original path
            connection = self._driver(**arguments)
        except (psycopg.Error, OSError) as error:
            failures.append(pv._driver_error(error, "connect_timeout", "connect_failed"))
        except BaseException:
            try:
                copy.close()
            except tr.OpsTlsRootRefused:
                pass                                                # the unexpected error leads; copy stays unconfirmed
            raise
        finally:
            arguments.clear()                                       # drop the password reference
        try:
            copy.close()                                            # only after the driver call has returned
        except tr.OpsTlsRootRefused as refused:
            failures.extend(_copy_codes(refused))
        if connection is not None and failures:
            if not pv._close(connection):
                failures.insert(0, "connection_close_unconfirmed")
        if failures:
            raise _ranked(failures)
        return connection


def provide_with_adapter(inputs: Any, *, expected: Any, driver: Any) -> pv.Handoff:
    """Synthetic only. Needs an explicit driver function: there is no default and no real one here.
    Every call makes a new factory, a new copy and a new observation (a reconnect is a new call)."""
    if not isinstance(inputs, op.PreflightInput) or inputs.mode != op.MODE:
        raise pv.OpsProviderRefused("mode_not_synthetic")
    if driver is None or not callable(driver):
        raise pv.OpsProviderRefused("connection_factory_not_implemented")
    return pv.provide_synthetic_connection(inputs, expected=expected,
                                           factory=CopyingFactory(inputs.manifest, inputs.deploy_root, driver),
                                           observer=ob.CatalogObserver())
