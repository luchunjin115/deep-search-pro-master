import {
  cleanupE2EThreads,
  startPostgres,
  stopTestWebServers,
} from "./support/runtime";

export default function globalTeardown(): void {
  try {
    startPostgres();
    cleanupE2EThreads();
  } finally {
    stopTestWebServers();
  }
}
