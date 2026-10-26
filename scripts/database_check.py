"""Real TLS, least-privilege catalog and bound SDK/Auth integration checks.

Owns a disposable PostgreSQL container; all generated TLS files stay in OS temp.
Optional --workdir uses an explicitly approved local synthetic Supabase project.
Never prints credentials, response bodies, policy expressions or Docker logs.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from postgres_matrix import command, docker_executable
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from rls_doctor.cli.main import app
from rls_doctor.core.config import validate_database_dsn, validate_local_url
from rls_doctor.core.credentials import credentials, local_status
from rls_doctor.core.database_connection import inspection_dsn
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import parse_event
from rls_doctor.core.profiles import DatabaseProfile, save_profile
from rls_doctor.postgres.inspector import InspectorError, discover_database, inspect_table
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]


def require(value: object, code: str) -> None:
    if not value:
        raise DoctorError(code, "Existing-database integration check failed; details suppressed.")


def certificates(folder: Path) -> None:
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RLS Doctor disposable CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(issuer)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    (folder / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for name, hostname, expired in [
        ("valid", "localhost", False),
        ("wrong", "wrong.example.invalid", False),
        ("expired", "localhost", True),
    ]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now - timedelta(hours=1) if expired else now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        (folder / (name + ".crt")).write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        path = folder / (name + ".key")
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        path.chmod(0o600)


def tls_check() -> None:
    executable = docker_executable()
    identity = uuid4().hex
    name = "rls-doctor-database-" + identity[:12]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    password = secrets.token_urlsafe(32)
    reader_password = secrets.token_urlsafe(32)
    admin = make_conninfo(
        host="127.0.0.1",
        port=port,
        dbname="postgres",
        user="postgres",
        password=password,
        sslmode="require",
        connect_timeout=2,
    )
    startup = (
        "chown postgres:postgres /tmp/server.key /tmp/server.crt && "
        "chmod 600 /tmp/server.key && exec docker-entrypoint.sh postgres "
        "-c ssl=on -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key"
    )

    def run(args: list[str]) -> None:
        require(command(executable, args, timeout=90).returncode == 0, "DATABASE_CHECK_DOCKER")

    def ready() -> None:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(admin):
                    return
            except psycopg.Error:
                time.sleep(0.5)
        raise DoctorError("DATABASE_CHECK_READY", "Disposable TLS server did not become ready.")

    with tempfile.TemporaryDirectory(prefix="rls-doctor-tls-") as directory:
        folder = Path(directory)
        certificates(folder)
        owned = False
        with credentials({"POSTGRES_PASSWORD": password}):
            try:
                run(
                    [
                        "create",
                        "--name",
                        name,
                        "--label",
                        "rls-doctor.database-check=" + identity,
                        "--memory",
                        "512m",
                        "--publish",
                        f"127.0.0.1:{port}:5432",
                        "--env",
                        "POSTGRES_PASSWORD",
                        "postgres:18",
                        "sh",
                        "-c",
                        startup,
                    ]
                )
                owned = True
                for suffix in ("crt", "key"):
                    run(["cp", str(folder / ("valid." + suffix)), name + ":/tmp/server." + suffix])
                run(["start", name])
                ready()
                with psycopg.connect(admin, autocommit=True) as connection:
                    connection.execute(
                        sql.SQL("CREATE ROLE rls_reader LOGIN PASSWORD {}").format(
                            sql.Literal(reader_password)
                        )
                    )
                    connection.execute("CREATE SCHEMA auth")
                    connection.execute(
                        "CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql "
                        "STABLE AS 'SELECT NULL::uuid'"
                    )
                    connection.execute("CREATE TABLE public.documents(id int, owner_id uuid)")
                    connection.execute("CREATE TABLE public.secret_policy(id int, note text)")
                    connection.execute("ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY")
                    connection.execute("ALTER TABLE public.secret_policy ENABLE ROW LEVEL SECURITY")
                    connection.execute(
                        "CREATE POLICY own_rows ON public.documents FOR SELECT "
                        "USING ((select auth.uid()) = owner_id)"
                    )
                    connection.execute(
                        "CREATE POLICY opaque ON public.secret_policy FOR SELECT "
                        "USING (note = 'PRIVATE_POLICY_LITERAL')"
                    )
                    connection.execute("GRANT USAGE ON SCHEMA public TO rls_reader")
                    connection.execute("CREATE TABLE public.conditions(id int, owner_id uuid)")
                    connection.execute("ALTER TABLE public.conditions ENABLE ROW LEVEL SECURITY")
                    connection.execute("CREATE POLICY allow_all ON public.conditions USING (true)")
                    connection.execute(
                        "CREATE POLICY deny ON public.conditions AS RESTRICTIVE USING (false)"
                    )
                    connection.execute(
                        "CREATE POLICY own_direct ON public.conditions USING (auth.uid() ="
                        " owner_id) WITH CHECK (auth.uid() = owner_id)"
                    )
                    connection.execute(
                        "CREATE POLICY mixed ON public.conditions USING (auth.uid() = "
                        "owner_id OR id = 1)"
                    )
                    connection.execute(
                        "CREATE FUNCTION auth.must_not_run() RETURNS boolean LANGUAGE "
                        "plpgsql AS $$BEGIN RAISE EXCEPTION 'PRIVATE_POLICY_LITERAL'; "
                        "END$$"
                    )
                    connection.execute(
                        "CREATE POLICY hidden_function ON public.conditions USING "
                        "(auth.must_not_run())"
                    )
                    # Inspector deliberately has no SELECT on either customer table.
                raw = make_conninfo(
                    host="localhost",
                    port=port,
                    dbname="postgres",
                    user="rls_reader",
                    password=reader_password,
                    sslmode="verify-full",
                    sslrootcert=str(folder / "ca.crt"),
                )
                dsn = inspection_dsn(raw, "localhost", approved=True)
                discovery = discover_database(dsn)
                require(discovery["catalog_access"], "DATABASE_CHECK_CATALOG_ACCESS")
                require(discovery["database"]["read_only"], "DATABASE_CHECK_READ_ONLY")
                report = inspect_table(dsn, "public", "documents", "rls_reader", True)
                require(
                    not report["privileges"]["any_column_select"], "DATABASE_CHECK_LEAST_PRIVILEGE"
                )
                shapes = report["policies"][0]["condition_shapes"]
                require(
                    any(
                        s["shape"] == "AUTH_UID_EQUALS_COLUMN" and s["column"] == "owner_id"
                        for s in shapes
                    ),
                    "DATABASE_CHECK_OWNER_SHAPE",
                )
                private = inspect_table(dsn, "public", "secret_policy", "rls_reader", True)
                require(
                    "PRIVATE_POLICY_LITERAL" not in json.dumps(private),
                    "DATABASE_CHECK_POLICY_PRIVACY",
                )
                require(
                    any(
                        s["shape"] == "UNRECOGNIZED"
                        for s in private["policies"][0]["condition_shapes"]
                    ),
                    "DATABASE_CHECK_OPAQUE_SHAPE",
                )
                composition = inspect_table(dsn, "public", "conditions", "rls_reader", True)
                observed_shapes = {
                    c["shape"] for p in composition["policies"] for c in p["condition_shapes"]
                }
                require(
                    {"ALWAYS_TRUE", "ALWAYS_FALSE", "AUTH_UID_EQUALS_COLUMN", "UNRECOGNIZED"}
                    <= observed_shapes,
                    "DATABASE_CHECK_COMPOSITION_SHAPES",
                )
                require(
                    "PRIVATE_POLICY_LITERAL" not in json.dumps(composition),
                    "DATABASE_CHECK_FUNCTION_PRIVACY",
                )
                table_index = next(
                    i for i, t in enumerate(discovery["tables"], 1) if t["name"] == "documents"
                )
                role_index = next(
                    i for i, r in enumerate(discovery["roles"], 1) if r["name"] == "rls_reader"
                )
                for language in ("en", "ru"):
                    wizard_path = folder / ("wizard-" + language + ".json")
                    wizard = CliRunner().invoke(
                        app,
                        ["connect", "--profile", str(wizard_path), "--language", language],
                        input=f"localhost\ny\n{raw}\n{table_index}\n{role_index}\n\n",
                    )
                    require(wizard.exit_code == 0, "DATABASE_CHECK_GUIDED_CONNECT")
                    require(
                        reader_password not in wizard.output + wizard_path.read_text(),
                        "DATABASE_CHECK_GUIDED_PRIVACY",
                    )
                profile = DatabaseProfile(
                    project_id=str(uuid4()),
                    host="localhost",
                    port=port,
                    database="postgres",
                    user="rls_reader",
                    table="public.documents",
                    role="rls_reader",
                    sslrootcert=str(folder / "ca.crt"),
                )
                path = folder / "project.json"
                save_profile(profile, path)
                with credentials({"RLS_DOCTOR_DATABASE_URL": raw}):
                    result = CliRunner().invoke(
                        app,
                        [
                            "diagnose",
                            "--profile",
                            str(path),
                            "--approve-read-only",
                            "--format",
                            "json",
                        ],
                    )
                require(result.exit_code == 2, "DATABASE_CHECK_PROFILE_RUN")
                require(json.loads(result.stdout)["diagnosis_id"], "DATABASE_CHECK_RUN_METADATA")
                require(reader_password not in result.stdout, "DATABASE_CHECK_PASSWORD_PRIVACY")
                print(
                    "PASS verified TLS, least-privilege catalogs, "
                    "private policy shapes and profile diagnosis",
                    flush=True,
                )

                # Wrong CA is another server certificate, not the signing root.
                invalid_ca = conninfo_to_dict(raw)
                invalid_ca["sslrootcert"] = str(folder / "wrong.crt")
                wrong_ca = make_conninfo(**invalid_ca)
                try:
                    inspect_table(
                        inspection_dsn(wrong_ca, "localhost", approved=True),
                        "public",
                        "documents",
                        "rls_reader",
                    )
                except InspectorError:
                    pass
                else:
                    require(False, "DATABASE_CHECK_WRONG_CA_ACCEPTED")
                print("PASS untrusted certificate authority rejected", flush=True)
                for variant in ("wrong", "expired"):
                    run(["stop", name])
                    for suffix in ("crt", "key"):
                        run(
                            [
                                "cp",
                                str(folder / (variant + "." + suffix)),
                                name + ":/tmp/server." + suffix,
                            ]
                        )
                    run(["start", name])
                    ready()
                    try:
                        inspect_table(
                            inspection_dsn(raw, "localhost", approved=True),
                            "public",
                            "documents",
                            "rls_reader",
                        )
                    except InspectorError:
                        pass
                    else:
                        require(False, "DATABASE_CHECK_BAD_CERTIFICATE_ACCEPTED")
                    print("PASS " + variant + " server certificate rejected", flush=True)
            finally:
                if owned:
                    label = command(
                        executable,
                        [
                            "inspect",
                            "--format",
                            '{{index .Config.Labels "rls-doctor.database-check"}}',
                            name,
                        ],
                    )
                    require(
                        label.returncode == 0 and label.stdout.strip() == identity,
                        "DATABASE_CHECK_CLEANUP_OWNERSHIP",
                    )
                    run(["rm", "--force", "--volumes", name])


def auth_check(workdir: Path) -> None:
    require(os.environ.get("RLS_DOCTOR_ALLOW_FIXTURE_SETUP") == "1", "DATABASE_CHECK_AUTH_APPROVAL")
    status = local_status(workdir)
    origin = validate_local_url(status["API_URL"], [54321])
    dsn = validate_database_dsn(status["DB_URL"], [54322])
    key = status.get("ANON_KEY") or status.get("PUBLISHABLE_KEY")
    user_id = None
    token = None
    try:
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
            response = client.post(
                origin + "/auth/v1/signup",
                headers={"apikey": key},
                json={
                    "email": f"rls-doctor-{uuid4()}@example.invalid",
                    "password": secrets.token_urlsafe(32),
                },
            )
            require(response.status_code == 200, "DATABASE_CHECK_AUTH_SIGNUP")
            data = response.json()
            user_id, token = data["user"]["id"], data["access_token"]
        require(isinstance(token, str) and isinstance(user_id, str), "DATABASE_CHECK_AUTH_SESSION")
        project_id = str(uuid4())
        node = os.environ.get("RLS_DOCTOR_NODE") or "node"
        script = """
import {createCaptureFetch} from './packages/capture-sdk/dist/index.js';
let raw=''; for await (const chunk of process.stdin) raw+=chunk;
const c=JSON.parse(raw);
let resolve; const event=new Promise(r=>resolve=r);
const wrapped=createCaptureFetch(fetch,{enabled:true,projectId:c.project,verifyAuth:true,
 allowedOrigin:c.origin,resources:['documents'],sink:resolve});
const response=await wrapped(c.origin+'/rest/v1/documents?select=id',{
 headers:{authorization:'Bearer '+c.token,apikey:c.key,Prefer:'count=exact'}});
if(response.bodyUsed) throw Error('APPLICATION_BODY_CONSUMED');
const timeout=new Promise((_,reject)=>setTimeout(()=>reject(Error('TIMEOUT')),5000));
const captured=await Promise.race([event,timeout]);
process.stdout.write(JSON.stringify(captured));
"""
        result = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT,
            input=json.dumps({"origin": origin, "key": key, "token": token, "project": project_id}),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        require(result.returncode == 0, "DATABASE_CHECK_SDK_CAPTURE")
        require(
            token not in result.stdout
            and key not in result.stdout
            and user_id not in result.stdout,
            "DATABASE_CHECK_AUTH_PRIVACY",
        )
        event = parse_event(json.loads(result.stdout))
        require(event.auth_check == "verified_user", "DATABASE_CHECK_AUTH_CONFIRMATION")
        with tempfile.TemporaryDirectory(prefix="rls-doctor-auth-") as directory:
            folder = Path(directory)
            path = folder / "event.json"
            path.write_text(result.stdout, encoding="utf-8")
            values = conninfo_to_dict(dsn)
            profile = DatabaseProfile(
                project_id=project_id,
                host="127.0.0.1",
                port=54322,
                database=str(values["dbname"]),
                user=str(values["user"]),
                table="public.documents",
                role="authenticated",
                api_origin=origin,
                sslmode="disable",
            )
            saved = folder / "project.json"
            save_profile(profile, saved)
            with credentials({"RLS_DOCTOR_DATABASE_URL": status["DB_URL"]}):
                run = CliRunner().invoke(
                    app,
                    [
                        "diagnose",
                        "--profile",
                        str(saved),
                        "--event",
                        str(path),
                        "--approve-read-only",
                        "--format",
                        "json",
                    ],
                )
            require(run.exit_code == 2, "DATABASE_CHECK_BOUND_DIAGNOSIS")
            report = json.loads(run.stdout)
            require(report["linkage"]["configuration_matches"], "DATABASE_CHECK_PROJECT_LINK")
            require(
                report["identity"]["confirmed_role"] is None, "DATABASE_CHECK_RUNTIME_UNCERTAINTY"
            )
        print(
            "PASS actual Supabase SDK/Auth v1.1 capture and bound database investigation",
            flush=True,
        )
    finally:
        if user_id:
            # Only the synthetic user created by this check, never application rows.
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute("DELETE FROM auth.users WHERE id=%s::uuid", (user_id,))


def unavailable_check() -> None:
    # Keep the port bound but not listening: no other service can take it mid-check.
    with socket.socket() as endpoint:
        endpoint.bind(("127.0.0.1", 0))
        raw = make_conninfo(
            host="127.0.0.1",
            port=endpoint.getsockname()[1],
            dbname="postgres",
            user="reader",
            password="PRIVATE_TEST_SENTINEL",
            sslmode="disable",
        )
        with credentials({"RLS_DOCTOR_DATABASE_URL": raw}):
            result = CliRunner().invoke(
                app,
                [
                    "diagnose",
                    "public.documents",
                    "--host",
                    "127.0.0.1",
                    "--approve-read-only",
                    "--format",
                    "json",
                ],
            )
        require(result.exit_code == 3, "DATABASE_CHECK_UNAVAILABLE_EXIT")
        require(json.loads(result.stdout)["result"] == "ERROR", "DATABASE_CHECK_UNAVAILABLE_RESULT")
        require("PRIVATE_TEST_SENTINEL" not in result.stdout, "DATABASE_CHECK_UNAVAILABLE_PRIVACY")
    print("PASS unreachable endpoint returns a safe operational error", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path)
    args = parser.parse_args()
    unavailable_check()
    tls_check()
    if args.workdir is not None:
        auth_check(args.workdir)


if __name__ == "__main__":
    try:
        main()
    except DoctorError as error:
        print("ERROR " + error.code)
        raise SystemExit(3) from None
    except Exception:
        print("ERROR existing-database integration failed; unsafe details suppressed.")
        raise SystemExit(3) from None
