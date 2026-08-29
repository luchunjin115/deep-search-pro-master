import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));
const pythonExecutable = fileURLToPath(
  new URL(
    process.platform === "win32"
      ? "../../../.venv/Scripts/python.exe"
      : "../../../.venv/bin/python",
    import.meta.url,
  ),
);
const dockerExecutable = process.platform === "win32" ? "docker.exe" : "docker";

function runPython(arguments_: string[]): void {
  execFileSync(pythonExecutable, arguments_, {
    cwd: repositoryRoot,
    stdio: "pipe",
  });
}

function runDocker(arguments_: string[]): void {
  execFileSync(dockerExecutable, arguments_, {
    cwd: repositoryRoot,
    stdio: "pipe",
  });
}

export function cleanupE2EThreads(): void {
  const cleanupProgram = [
    "from sqlalchemy import delete",
    "from app.core.config import Settings",
    "from app.db.session import create_database_runtime",
    "from app.models.runtime import Thread",
    "runtime = create_database_runtime(Settings())",
    "with runtime.session_factory.begin() as session: session.execute(delete(Thread).where(Thread.title.like('M1-20 E2E %')))",
    "runtime.engine.dispose()",
  ].join("\n");
  runPython(["-c", cleanupProgram]);
}

export function prepareE2EDatabase(): void {
  runPython(["-m", "alembic", "upgrade", "head"]);
  runPython(["-m", "scripts.seed_m1"]);
  cleanupE2EThreads();
}

export function stopPostgres(): void {
  runDocker(["compose", "stop", "postgres"]);
}

export function startPostgres(): void {
  runDocker(["compose", "up", "-d", "--wait", "postgres"]);
}

export function stopTestWebServers(): void {
  if (process.platform !== "win32") return;

  const stopListener = [
    "$listeners = Get-NetTCPConnection -LocalPort 3000,8000 -State Listen -ErrorAction SilentlyContinue",
    "foreach ($listener in $listeners) { Stop-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue }",
  ].join("; ");
  execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", stopListener], {
    cwd: repositoryRoot,
    stdio: "pipe",
  });
}

export function readDemoPassword(): string {
  const configuredPassword = process.env.M1_DEMO_PASSWORD?.trim();
  if (configuredPassword) return configuredPassword;

  const environmentFile = readFileSync(
    fileURLToPath(new URL("../../../.env", import.meta.url)),
    "utf8",
  );
  const line = environmentFile
    .split(/\r?\n/u)
    .find((candidate) => candidate.startsWith("M1_DEMO_PASSWORD="));
  const password = line?.slice("M1_DEMO_PASSWORD=".length).trim();
  if (!password) {
    throw new Error("M1_DEMO_PASSWORD is missing from the E2E environment");
  }
  return password;
}
