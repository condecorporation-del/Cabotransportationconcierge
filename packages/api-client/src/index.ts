import createClient from "openapi-fetch";
import type { paths } from "./schema";

export type { components, paths } from "./schema";

/** Cliente tipado: una ruta o un campo que no existe en el backend no compila (WORKPLAN D5). */
export const createApiClient = (baseUrl: string) =>
  createClient<paths>({ baseUrl, credentials: "include" });
