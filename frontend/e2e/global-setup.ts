import { prepareE2EDatabase } from "./support/runtime";

export default function globalSetup(): void {
  prepareE2EDatabase();
}
